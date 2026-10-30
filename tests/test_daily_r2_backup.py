"""Isolated backup orchestration and failure tests: no real DB, R2, or secrets."""

from argparse import Namespace
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import HTTPSHandler, build_opener
from urllib.response import addinfourl

from botocore.exceptions import ClientError
import pytest

from app import create_app
from scripts import run_daily_backup as runner
from scripts import upload_backup_to_r2 as uploader


@pytest.fixture
def app():
    application = create_app()
    application.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    return application


@pytest.fixture(autouse=True)
def no_real_credentials(monkeypatch):
    for name in ("ENDPOINT", "ACCESS_KEY_ID", "SECRET_ACCESS_KEY"):
        monkeypatch.delenv(uploader.ENV_PREFIX + name, raising=False)
    monkeypatch.setattr(uploader.time, "sleep", lambda _: None)


class FakeR2:
    def __init__(self):
        self.objects = {}
        self.events = []
        self.failures = 0
        self.corrupt = False
        self.corrupt_manifest = False

    def upload_file(self, source, bucket, key):
        if self.failures:
            self.failures -= 1
            raise OSError("secret-must-never-appear")
        self.events.append(("upload", key))
        self.objects[key] = Path(source).read_bytes()

    def put_object(self, **kwargs):
        self.events.append(("manifest", kwargs["Key"]))
        self.objects[kwargs["Key"]] = kwargs["Body"]

    def get_object(self, **kwargs):
        key = kwargs["Key"]
        self.events.append(("read", key))
        if key not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey"},
                               "ResponseMetadata": {"HTTPStatusCode": 404}}, "GetObject")
        data = self.objects[key]
        if self.corrupt and not key.endswith("manifest.json"):
            data = bytes([data[0] ^ 1]) + data[1:]  # Same size: HEAD alone cannot catch this.
        if self.corrupt_manifest and key.endswith("manifest.json"):
            data = b"{}"
        return {"Body": io.BytesIO(data), "ContentLength": len(data)}


def local_set(folder):
    folder.mkdir(exist_ok=True)
    sql = "\n".join(f"CREATE TABLE `{table}` (id int);" for table in sorted(runner.CORE_TABLES))
    sql += "\nINSERT INTO `users` VALUES (1);\n-- Dump completed on 2026-10-30 23:30:00\n"
    (folder / "pos_db.sql").write_text(sql, encoding="utf-8")
    with tarfile.open(folder / "production-files.tar.gz", "w:gz") as archive:
        for name in runner.MEDIA_PATHS:
            member = tarfile.TarInfo(name)
            member.type = tarfile.DIRTYPE
            archive.addfile(member)
        member = tarfile.TarInfo("static/images/logo.jpg")
        member.size = 5
        archive.addfile(member, io.BytesIO(b"image"))
    return folder


def test_upload_verifies_bytes_then_manifest_and_safe_retry(tmp_path):
    folder = local_set(tmp_path / "daily-test")
    client = FakeR2()
    first = uploader.upload_backup(folder, client)
    marker = f"{folder.name}/manifest.json"
    marker_index = client.events.index(("manifest", marker))
    for name in uploader.REQUIRED_FILES:
        assert client.events.index(("read", f"{folder.name}/{name}")) < marker_index
    assert first == json.loads((folder / "manifest.json").read_text())
    assert uploader.upload_backup(folder, client) == first
    assert sum(action == "upload" for action, _ in client.events) == 2
    assert sum(action == "manifest" for action, _ in client.events) == 1
    (folder / "pos_db.sql").write_text("changed", encoding="utf-8")
    with pytest.raises(uploader.BackupError, match="refusing to overwrite"):
        uploader.upload_backup(folder, client)


@pytest.mark.parametrize("failure", ["same-size-corruption", "upload-interrupted", "manifest-corrupt"])
def test_upload_failures_never_create_local_completion(tmp_path, failure):
    folder = local_set(tmp_path / "daily-test")
    client = FakeR2()
    client.corrupt = failure == "same-size-corruption"
    client.failures = 3 if failure == "upload-interrupted" else 0
    client.corrupt_manifest = failure == "manifest-corrupt"
    with pytest.raises(uploader.BackupError):
        uploader.upload_backup(folder, client)
    assert not (folder / "manifest.json").exists()
    if failure != "manifest-corrupt":
        assert f"{folder.name}/manifest.json" not in client.objects


def test_manual_prompts_preserved_and_unattended_never_prompts(tmp_path, monkeypatch, capsys):
    folder = local_set(tmp_path / "daily-test")
    monkeypatch.setattr("builtins.input", lambda _: pytest.fail("unattended process prompted"))
    assert uploader.main([str(folder), "--non-interactive"]) == 1
    assert "credentials" in capsys.readouterr().out
    monkeypatch.setattr("builtins.input", lambda _: "https://account.r2.cloudflarestorage.com/ideaflow-backups/")
    values = iter(["a" * 32, "fake-test-secret"])
    monkeypatch.setattr(uploader, "getpass", lambda _: next(values))
    monkeypatch.setattr(uploader, "create_client", lambda _: FakeR2())
    assert uploader.main([str(folder)]) == 0


def test_network_retry_is_bounded_and_redacts_provider_errors(monkeypatch):
    calls = []

    def fail():
        calls.append(1)
        raise OSError("secret-must-never-appear")

    with pytest.raises(uploader.BackupError, match="bounded retries") as error:
        uploader.network_retry(fail)
    assert len(calls) == 3
    assert "secret-must" not in str(error.value)
    calls.clear()

    def denied():
        calls.append(1)
        raise ClientError({"Error": {"Code": "AccessDenied", "Message": "secret"},
                           "ResponseMetadata": {"HTTPStatusCode": 403}}, "PutObject")

    with pytest.raises(uploader.BackupError, match="rejected"):
        uploader.network_retry(denied)
    assert len(calls) == 1


def test_interrupted_remote_stream_is_retried():
    class ShortOnce(FakeR2):
        count = 0

        def get_object(self, **kwargs):
            result = super().get_object(**kwargs)
            self.count += 1
            if self.count == 1:
                result["ContentLength"] += 1
            return result

    client = ShortOnce()
    client.objects["test/pos_db.sql"] = b"sql-data"
    result = uploader.network_retry(lambda: uploader.remote_details(client, "test/pos_db.sql"))
    assert result["size"] == 8
    assert client.count == 2


@pytest.fixture
def setup_run(tmp_path, monkeypatch):
    root = tmp_path / "backups"
    root.mkdir(mode=0o700)
    app_dir = tmp_path / "site"
    for name in runner.MEDIA_PATHS:
        (app_dir / name).mkdir(parents=True)
    args = Namespace(app_dir=app_dir, backup_root=root, env_file=tmp_path / "missing.env",
                     retry_upload=None, preflight=False, scheduled=True)
    client, calls = FakeR2(), []
    for name, value in [("ENDPOINT", "https://account.r2.cloudflarestorage.com"),
                        ("ACCESS_KEY_ID", "a" * 32), ("SECRET_ACCESS_KEY", "fake-test-secret")]:
        monkeypatch.setenv(uploader.ENV_PREFIX + name, value)
    monkeypatch.setattr(uploader, "create_client", lambda _: client)
    monkeypatch.setattr(runner.shutil, "which", lambda name: name)
    monkeypatch.setattr(runner.shutil, "disk_usage", lambda _: SimpleNamespace(free=20 * 1024 ** 3))
    monkeypatch.setattr(runner, "now", lambda: datetime(2026, 10, 30, 15, 30, tzinfo=timezone.utc))

    def fake_command(arguments, *, output=None, timeout=120):
        calls.append(arguments)
        tool = arguments[0]
        if tool == "mysql":
            if "JSON_OBJECT" in arguments[-1]:
                return "\n".join(json.dumps(item) for item in getattr(args, "media_sources", []))
            return "\n".join(f"{table}\tInnoDB\t100" for table in sorted(runner.CORE_TABLES))
        if tool == "git":
            return "a" * 40
        if tool == "mysqldump":
            fixture = local_set(tmp_path / "fixture")
            output.write((fixture / "pos_db.sql").read_bytes())
        elif tool == "tar":
            if runner.EXTERNAL_MEDIA_ROOT in arguments:
                subprocess.run(arguments, stdout=output, stderr=subprocess.PIPE, timeout=15, check=True)
            else:
                output.write((tmp_path / "fixture" / "production-files.tar.gz").read_bytes())
        else:
            pytest.fail(f"Unexpected tool: {tool}")

    monkeypatch.setattr(runner, "command", fake_command)
    return args, root, client, calls


def test_automated_run_records_provenance_and_only_verified_last_success(setup_run):
    args, root, client, calls = setup_run
    assert runner.run_locked(args, root) == 0
    status = json.loads((root / "last-attempt.json").read_text())
    latest = json.loads((root / "last-success.json").read_text())
    manifest = json.loads((root / status["run_id"] / "manifest.json").read_text())
    assert status["status"] == "success" and status["local_complete"]
    assert latest["prefix"].startswith("auto-daily-20261030-233000-")
    assert manifest["scheduled_for_manila"] == "2026-10-30T23:30:00+08:00"
    assert manifest["validation"]["table_definitions"] == len(runner.CORE_TABLES)
    assert manifest["scope"]["local_media"] == list(runner.MEDIA_PATHS)
    assert all("systemctl" not in command for command in calls)
    assert any("--single-transaction" in command and "--events" in command for command in calls)


@pytest.mark.parametrize("failure", ["database", "archive", "disk", "engine", "corrupt", "credentials"])
def test_failed_run_preserves_last_success_and_files(setup_run, monkeypatch, failure, capsys):
    args, root, client, calls = setup_run
    previous = b'{"prefix":"old-verified"}\n'
    (root / "last-success.json").write_bytes(previous)
    original = runner.command

    def failing_command(arguments, **kwargs):
        if arguments[0] == {"database": "mysqldump", "archive": "tar"}.get(failure):
            raise uploader.BackupError("Simulated tool failure")
        value = original(arguments, **kwargs)
        return value.replace("InnoDB", "MyISAM") if failure == "engine" and arguments[0] == "mysql" else value

    monkeypatch.setattr(runner, "command", failing_command)
    if failure == "disk":
        monkeypatch.setattr(runner.shutil, "disk_usage", lambda _: SimpleNamespace(free=0))
    if failure == "credentials":
        monkeypatch.delenv(uploader.ENV_PREFIX + "SECRET_ACCESS_KEY")
    client.corrupt = failure == "corrupt"
    assert runner.run_locked(args, root) == 1
    status = json.loads((root / "last-attempt.json").read_text())
    assert status["status"] == "failed"
    assert (root / "last-success.json").read_bytes() == previous
    assert not list(root.glob("auto-daily-*/manifest.json"))
    if failure in ("database", "archive", "corrupt"):
        assert list(root.glob("auto-daily-*/run.json"))
    assert "fake-test-secret" not in capsys.readouterr().out


def test_failed_upload_retry_reuses_same_dump_and_recovers(setup_run):
    args, root, client, calls = setup_run
    client.failures = 3
    assert runner.run_locked(args, root) == 1
    saved = json.loads((root / "last-attempt.json").read_text())
    folder = root / saved["run_id"]
    assert saved["local_complete"] and not (root / "last-success.json").exists()
    original_sql = (folder / "pos_db.sql").read_bytes()
    args.retry_upload, args.scheduled = folder, False
    client.failures = 3
    assert runner.run_locked(args, root) == 1
    assert json.loads((folder / "run.json").read_text())["local_complete"]
    assert runner.run_locked(args, root) == 0
    assert (folder / "pos_db.sql").read_bytes() == original_sql
    assert sum(command[0] == "mysqldump" for command in calls) == 1


def test_retry_rejects_changed_local_bytes_even_if_sql_still_valid(setup_run):
    args, root, client, calls = setup_run
    client.failures = 3
    assert runner.run_locked(args, root) == 1
    saved = json.loads((root / "last-attempt.json").read_text())
    folder = root / saved["run_id"]
    sql = folder / "pos_db.sql"
    sql.write_bytes(sql.read_bytes().replace(b"VALUES (1)", b"VALUES (2)"))
    args.retry_upload = folder
    assert runner.run_locked(args, root) == 1
    assert "changed" in json.loads((folder / "run.json").read_text())["error"]
    assert not (root / "last-success.json").exists()


def test_archive_warning_retries_without_redumping(setup_run, monkeypatch):
    args, root, client, calls = setup_run
    original, attempts = runner.command, []

    def transient_archive(arguments, **kwargs):
        if arguments[0] == "tar":
            attempts.append(1)
            if len(attempts) == 1:
                raise uploader.BackupError("Changing-file archive warning")
        return original(arguments, **kwargs)

    monkeypatch.setattr(runner, "command", transient_archive)
    assert runner.run_locked(args, root) == 0
    assert len(attempts) == 2
    assert sum(command[0] == "mysqldump" for command in calls) == 1


def test_root_guard_or_lock_conflict_preserves_active_run_status(setup_run, monkeypatch):
    args, root, client, calls = setup_run
    active = b'{"status":"running","run_id":"active"}'
    (root / "last-attempt.json").write_bytes(active)

    @contextmanager
    def busy(_):
        raise uploader.BackupError("Another backup holds the lock")
        yield

    monkeypatch.setattr(runner, "exclusive_lock", busy)
    # CI runs as an ordinary Linux user; its root-ownership guard fires first.
    expected = "root-owned" if os.name == "posix" and os.geteuid() != 0 else "holds the lock"
    with pytest.raises(uploader.BackupError, match=expected):
        runner.run(args)
    assert (root / "last-attempt.json").read_bytes() == active
    assert not calls


def test_preflight_creates_no_dump_or_remote_requests(setup_run):
    args, root, client, calls = setup_run
    args.preflight, args.scheduled = True, False
    assert runner.run_locked(args, root) == 0
    assert json.loads((root / "last-attempt.json").read_text())["status"] == "preflight-passed"
    assert not list(root.glob("auto-daily-*")) and not client.events
    assert not (root / "last-success.json").exists()


def test_status_write_failure_does_not_mask_backup_failure(setup_run, monkeypatch, capsys):
    args, root, client, calls = setup_run
    original_json, original_command = uploader.atomic_json, runner.command

    def full_disk(path, value):
        if value.get("status") == "failed":
            raise OSError("secret-from-provider")
        return original_json(path, value)

    def failed_dump(arguments, **kwargs):
        if arguments[0] == "mysqldump":
            raise uploader.BackupError("Database dump failed")
        return original_command(arguments, **kwargs)

    monkeypatch.setattr(uploader, "atomic_json", full_disk)
    monkeypatch.setattr(runner, "command", failed_dump)
    assert runner.run_locked(args, root) == 1
    output = capsys.readouterr().out
    assert "Database dump failed" in output and "STATUS WRITE FAILED" in output
    assert "secret-from-provider" not in output
    assert not (root / "last-success.json").exists()


def test_completion_tracking_failure_does_not_advance_last_success(setup_run, monkeypatch):
    args, root, client, calls = setup_run
    previous = b'{"prefix":"old-verified"}'
    (root / "last-success.json").write_bytes(previous)
    original = uploader.atomic_json

    def cannot_finish_status(path, value):
        if path.name == "last-attempt.json" and value.get("status") == "success":
            raise OSError("Cannot save completion status")
        return original(path, value)

    monkeypatch.setattr(uploader, "atomic_json", cannot_finish_status)
    assert runner.run_locked(args, root) == 1
    assert (root / "last-success.json").read_bytes() == previous
    assert json.loads((root / "last-attempt.json").read_text())["status"] == "failed"


def test_retry_outside_root_is_read_only(setup_run, tmp_path):
    args, root, client, calls = setup_run
    outside = tmp_path / "auto-daily-outside"
    outside.mkdir()
    args.retry_upload = outside
    assert runner.run_locked(args, root) == 1
    assert list(outside.iterdir()) == []


@pytest.mark.parametrize("damage", ["sql-truncated", "schema-missing", "gzip-crc"])
def test_local_validation_rejects_invalid_backups(tmp_path, damage):
    folder = local_set(tmp_path / "backup")
    sql = folder / "pos_db.sql"
    if damage == "sql-truncated":
        sql.write_bytes(sql.read_bytes().split(b"-- Dump completed")[0])
    elif damage == "schema-missing":
        sql.write_bytes(sql.read_bytes().replace(b"CREATE TABLE `users`", b"CREATE TABLE `other`"))
    else:
        archive = folder / "production-files.tar.gz"
        value = bytearray(archive.read_bytes())
        value[-8] ^= 1
        archive.write_bytes(value)
    with pytest.raises((uploader.BackupError, OSError, tarfile.TarError)):
        runner.validate_local(folder, len(runner.CORE_TABLES))


@pytest.mark.parametrize(("utc", "expected"), [
    ("2026-10-30T15:29:59+00:00", "2026-10-29T23:30:00+08:00"),
    ("2026-10-30T15:30:00+00:00", "2026-10-30T23:30:00+08:00"),
    ("2026-10-30T16:15:00+00:00", "2026-10-30T23:30:00+08:00"),
])
def test_scheduled_date_crosses_midnight_correctly(utc, expected):
    assert runner.scheduled_for(datetime.fromisoformat(utc)) == expected


@pytest.mark.skipif(os.name != "posix", reason="Linux flock is verified on Linux CI/VPS")
def test_native_lock_prevents_overlap(tmp_path):
    with runner.exclusive_lock(tmp_path):
        with pytest.raises(uploader.BackupError, match="holds the lock"):
            with runner.exclusive_lock(tmp_path):
                pytest.fail("Overlapping backup entered")
    with runner.exclusive_lock(tmp_path):
        pass


def test_command_suppresses_subprocess_secrets(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=1, stderr=b"secret", stdout=b"secret"))
    with pytest.raises(uploader.BackupError) as error:
        runner.command(["mysqldump"])
    assert "secret" not in str(error.value)


@pytest.mark.skipif(shutil.which("tar") is None, reason="Native tar is required on the VPS")
def test_native_tar_output_passes_streamed_validation(tmp_path):
    folder = local_set(tmp_path / "backup")
    site = tmp_path / "site"
    for name in runner.MEDIA_PATHS:
        (site / name).mkdir(parents=True)
    (site / "static/images/logo.jpg").write_bytes(b"image")
    with (folder / "production-files.tar.gz").open("wb") as output:
        runner.command(["tar", "-C", str(site), "-czf", "-", *runner.MEDIA_PATHS], output=output)
    result = runner.validate_local(folder, len(runner.CORE_TABLES))
    assert result["archive_entries"] == 3


def test_timer_templates_and_linux_line_endings():
    project = Path(__file__).resolve().parents[1]
    timer = (project / "deploy/ideaflow-daily-backup.timer").read_text()
    assert "OnCalendar=*-*-* 23:30:00 Asia/Manila" in timer
    assert "Persistent=true" in timer
    service = (project / "deploy/ideaflow-daily-backup.service").read_text()
    assert "TimeoutStartSec=30min" in service and "--scheduled" in service
    assert "EnvironmentFile=/etc/ideaflow/backup.env" in service
    assert "Telegram" not in service and "systemctl stop" not in service
    for name in ("scripts/run_daily_backup.sh", "deploy/ideaflow-daily-backup.service", "deploy/ideaflow-daily-backup.timer"):
        assert b"\r" not in (project / name).read_bytes()


class MediaResponse(io.BytesIO):
    status = 200

    def __init__(self, body, *, length=None, content_type="image/png"):
        super().__init__(body)
        self.headers = {"Content-Length": str(len(body) if length is None else length),
                        "Content-Type": content_type}


@pytest.fixture
def media_http(monkeypatch):
    responses, requests = {}, []

    def open_media(request, **kwargs):
        requests.append(request.full_url)
        return responses[request.full_url]()

    monkeypatch.setattr(runner, "build_opener", lambda *handlers: SimpleNamespace(open=open_media))
    return responses, requests


@pytest.mark.skipif(shutil.which("tar") is None, reason="Native tar is required for the media archive check")
def test_menu_images_archive_round_trip_and_retry_uses_saved_snapshot(setup_run, media_http, tmp_path):
    args, root, client, calls = setup_run
    responses, requests = media_http
    sources = [{"menu_item_id": 4, "url": "https://media.idea-flows.online/menu/first.png"},
               {"menu_item_id": 9, "url": "https://media.idea-flows.online/menu/second.png"}]
    args.media_sources = sources + [{"menu_item_id": 10, "url": "/static/uploads/local.png"}]
    bodies = {sources[0]["url"]: b"first-image-bytes", sources[1]["url"]: b"second-image-bytes"}
    for url, body in bodies.items():
        responses[url] = lambda body=body: MediaResponse(body)
    (args.app_dir / "static/images/logo.jpg").write_bytes(b"local-logo")
    client.failures = 3
    assert runner.run_locked(args, root) == 1
    status = json.loads((root / "last-attempt.json").read_text())
    assert status["local_complete"] and not (root / "last-success.json").exists()
    folder = root / status["run_id"]
    metadata = status["metadata"]
    assert metadata["scope"]["external_media"]["image_count"] == 2
    assert metadata["validation"]["external_media_images"] == 2
    with tarfile.open(folder / "production-files.tar.gz", "r:gz") as archive:
        assert archive.extractfile("static/images/logo.jpg").read() == b"local-logo"
        index = json.load(archive.extractfile("external-media/manifest.json"))
        for image in index["images"]:
            body = archive.extractfile("external-media/" + image["file"]).read()
            assert body == bodies[image["url"]]
            assert image["size"] == len(body) and image["sha256"] == hashlib.sha256(body).hexdigest()
    # A saved backup retries without querying changed live images or downloading again.
    responses.clear()
    args.media_sources = []
    args.retry_upload, args.scheduled = folder, False
    assert runner.run_locked(args, root) == 0
    assert requests == [item["url"] for item in sources]
    assert sum(call[0] == "mysqldump" for call in calls) == 1
    marker = json.loads(client.objects[f"{folder.name}/manifest.json"])
    assert marker["files"] == [uploader.file_details(folder / name) for name in uploader.REQUIRED_FILES]
    # A valid gzip with altered image bytes must still fail its per-image checksum.
    damaged = tmp_path / "damaged"
    damaged.mkdir()
    shutil.copyfile(folder / "pos_db.sql", damaged / "pos_db.sql")
    with tarfile.open(folder / "production-files.tar.gz", "r:gz") as source:
        with tarfile.open(damaged / "production-files.tar.gz", "w:gz") as target:
            for member in source:
                body = source.extractfile(member).read() if member.isfile() else None
                if member.name == "external-media/files/4.bin":
                    body = b"changed"
                    member.size = len(body)
                target.addfile(member, io.BytesIO(body) if body is not None else None)
    with pytest.raises(uploader.BackupError, match="SHA-256"):
        runner.validate_local(damaged, len(runner.CORE_TABLES), sources)


@pytest.mark.parametrize("url", [
    "http://media.idea-flows.online/a.png", "https://127.0.0.1/a.png", "file:///etc/passwd",
    "https://media.idea-flows.online.evil.invalid/a.png", "https://user:secret@media.idea-flows.online/a.png",
])
def test_untrusted_menu_image_addresses_fail_before_download(setup_run, media_http, url):
    args, root, client, calls = setup_run
    args.media_sources = [{"menu_item_id": 1, "url": url}]
    assert runner.run_locked(args, root) == 1
    assert not media_http[1] and not client.events
    assert not any(call[0] == "mysqldump" for call in calls)
    assert not (root / "last-success.json").exists()


@pytest.mark.parametrize("failure", ["forbidden", "short-body", "oversized", "html"])
def test_bad_menu_image_response_preserves_last_success(setup_run, media_http, capsys, failure):
    args, root, client, calls = setup_run
    url = "https://media.idea-flows.online/menu/a.png?token=secret-must-never-appear"
    args.media_sources = [{"menu_item_id": 1, "url": url}]
    previous = b'{"prefix":"previous-verified"}'
    (root / "last-success.json").write_bytes(previous)

    def response():
        if failure == "forbidden":
            raise HTTPError(url, 403, "secret-must-never-appear", {}, io.BytesIO(b"secret"))
        return MediaResponse(b"image", length=10 if failure == "short-body" else runner.MAX_IMAGE_BYTES + 1
                             if failure == "oversized" else None,
                             content_type="text/html" if failure == "html" else "image/png")

    media_http[0][url] = response
    assert runner.run_locked(args, root) == 1
    status = json.loads((root / "last-attempt.json").read_text())
    assert status["stage"] == "external-media-download" and not status["local_complete"]
    assert (root / "last-success.json").read_bytes() == previous and not client.events
    assert "secret-must-never-appear" not in capsys.readouterr().out


def test_media_redirect_is_rejected_without_contacting_redirect_target(tmp_path, monkeypatch):
    requests = []

    class RedirectResponse(HTTPSHandler):
        def https_open(self, request):
            requests.append(request.full_url)
            response = addinfourl(io.BytesIO(b""), {"Location": "https://127.0.0.1/private"}, request.full_url, 302)
            response.msg = "Found"
            return response

    monkeypatch.setattr(runner, "build_opener", lambda *handlers: build_opener(*handlers, RedirectResponse()))
    item = {"menu_item_id": 1, "url": "https://media.idea-flows.online/menu/a.png"}
    with pytest.raises(uploader.BackupError, match="redirected"):
        runner.download_menu_image(item, tmp_path / "image.bin")
    assert requests == [item["url"]]


@pytest.mark.parametrize("change_at", [2, 3])
def test_changing_menu_references_prevents_completion(setup_run, media_http, monkeypatch, change_at):
    args, root, client, calls = setup_run
    source = {"menu_item_id": 1, "url": "https://media.idea-flows.online/menu/original.png"}
    inventories = []

    def inventory():
        inventories.append(1)
        return [source] if len(inventories) < change_at else [{**source, "url": source["url"] + "?v=new"}]

    monkeypatch.setattr(runner, "external_media_inventory", inventory)
    media_http[0][source["url"]] = lambda: MediaResponse(b"image")
    assert runner.run_locked(args, root) == 1
    status = json.loads((root / "last-attempt.json").read_text())
    assert "references changed" in status["error"] and not status["local_complete"]
    assert not client.events and not (root / "last-success.json").exists()
