"""Root-run database/media backup. No Flask import, app restart, or data deletion."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tarfile
import tempfile
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from zoneinfo import ZoneInfo

from dotenv import dotenv_values

if __package__:
    from . import upload_backup_to_r2 as uploader
else:
    import upload_backup_to_r2 as uploader


MANILA = ZoneInfo("Asia/Manila")
CORE_TABLES = {"users", "customer_sessions", "transactions", "expenses", "receivables", "payables", "menu_items"}
MEDIA_PATHS = ("static/uploads", "static/images")
EXTERNAL_MEDIA_HOST = "media.idea-flows.online"
EXTERNAL_MEDIA_ROOT = "external-media"
MAX_IMAGE_BYTES = 20 * 1024 ** 2
MIN_FREE_BYTES = 1024 ** 3


def now() -> datetime:
    return datetime.now(timezone.utc)


def scheduled_for(start: datetime) -> str:
    local = start.astimezone(MANILA)
    target = local.replace(hour=23, minute=30, second=0, microsecond=0)
    if local < target:
        target -= timedelta(days=1)
    return target.isoformat()


def load_environment(path: Path) -> None:
    if not path.exists():
        return  # systemd may already have supplied the environment.
    if path.is_symlink() or not path.is_file():
        raise uploader.BackupError("Backup credentials must be a regular private file")
    info = path.stat()
    if os.name == "posix" and (info.st_uid != 0 or info.st_mode & 0o077):
        raise uploader.BackupError("Backup credential file must be root-owned and mode 600")
    for key, value in dotenv_values(path, interpolate=False).items():
        if key.startswith("IDEAFLOW_BACKUP_") and value is not None:
            os.environ.setdefault(key, value)


@contextmanager
def exclusive_lock(root: Path):
    import fcntl  # Linux VPS; the flock also covers direct/manual Python runs.

    with (root / ".backup.lock").open("a+b") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise uploader.BackupError("Another backup holds the lock; this attempt created no backup") from None
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def command(arguments: list[str], *, output=None, timeout=120):
    try:
        result = subprocess.run(arguments, stdin=subprocess.DEVNULL,
                                stdout=output if output is not None else subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise uploader.BackupError("Backup tool unavailable or timed out; inspect the reported stage") from None
    if result.returncode:
        raise uploader.BackupError("Backup tool failed; no completion recorded (tool output suppressed for privacy)")
    return result.stdout.decode("utf-8").strip() if output is None else None


def external_media_inventory() -> list[dict]:
    rows = command(["mysql", "--batch", "--raw", "--skip-column-names", "--connect-timeout=10", "pos_db", "-e",
                    "SELECT JSON_OBJECT('menu_item_id',id,'url',image_url) FROM menu_items "
                    "WHERE image_url IS NOT NULL AND image_url <> '' ORDER BY id"])
    sources = []
    for line in rows.splitlines():
        item = json.loads(line)
        url = item["url"]
        parsed = urlsplit(url)
        if not parsed.scheme and not parsed.netloc:
            continue  # Local images are already included by the local tar paths.
        if (type(item["menu_item_id"]) is not int or item["menu_item_id"] <= 0
                or parsed.scheme != "https" or parsed.netloc.lower() != EXTERNAL_MEDIA_HOST
                or parsed.fragment or not parsed.path or parsed.path == "/"
                or any(ord(char) < 32 for char in url)):
            raise uploader.BackupError("Unsupported external menu image address; review media backup scope")
        sources.append(item)
    return sources


class NoMediaRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # A trusted media URL must never redirect a root backup to another host.


def download_menu_image(item: dict, destination: Path) -> dict:
    def transfer():
        try:
            response = build_opener(NoMediaRedirects()).open(
                Request(item["url"], headers={"User-Agent": "IdeaFlowBackup/1.0"}), timeout=15)
        except HTTPError as error:
            error.close()
            if error.code in (408, 429, 500, 502, 503, 504):
                raise OSError("Media download temporarily unavailable") from None
            raise uploader.BackupError("Menu image unavailable or redirected; no completed backup recorded") from None
        with response:
            content_type = response.headers.get("Content-Type", "application/octet-stream").split(";", 1)[0].lower()
            expected = response.headers.get("Content-Length")
            expected = int(expected) if expected is not None else None
            if (response.status != 200 or (expected is not None and not 0 < expected <= MAX_IMAGE_BYTES)
                    or not (content_type.startswith("image/") or content_type == "application/octet-stream")):
                raise uploader.BackupError("Menu image response is invalid or exceeds the 20 MiB backup limit")
            digest, size = hashlib.sha256(), 0
            with destination.open("wb") as output:
                while chunk := response.read(uploader.CHUNK_SIZE):
                    size += len(chunk)
                    if size > MAX_IMAGE_BYTES:
                        raise uploader.BackupError("Menu image exceeds the 20 MiB backup limit")
                    digest.update(chunk)
                    output.write(chunk)
            if not size or expected is not None and size != expected:
                raise OSError("Incomplete menu image download")
            return {**item, "file": f"files/{destination.name}", "size": size,
                    "sha256": digest.hexdigest(), "content_type": content_type}
    return uploader.network_retry(transfer)


def preflight(app_dir: Path, root: Path) -> dict:
    for tool in ("mysql", "mysqldump", "tar", "git"):
        if not shutil.which(tool):
            raise uploader.BackupError(f"Required backup tool unavailable: {tool}")
    media_bytes = 0
    for name in MEDIA_PATHS:
        directory = app_dir / name
        if directory.is_symlink() or not directory.is_dir():
            raise uploader.BackupError("Required local media directory is missing or symlinked")
        for path in directory.rglob("*"):
            if path.is_symlink():
                raise uploader.BackupError("Local media contains a symlink; review archive scope first")
            if path.is_file():
                media_bytes += path.stat().st_size
    rows = command(["mysql", "--batch", "--skip-column-names", "--connect-timeout=10", "-e",
                    "SELECT TABLE_NAME,COALESCE(ENGINE,''),COALESCE(DATA_LENGTH,0)+COALESCE(INDEX_LENGTH,0) "
                    "FROM information_schema.TABLES WHERE TABLE_SCHEMA='pos_db' AND TABLE_TYPE='BASE TABLE'"])
    tables, db_bytes = set(), 0
    for line in rows.splitlines():
        table, engine, size = line.split("\t")
        if engine.upper() != "INNODB":
            raise uploader.BackupError("Non-InnoDB tables require a different snapshot strategy")
        tables.add(table)
        db_bytes += int(size)
    if not CORE_TABLES.issubset(tables):
        raise uploader.BackupError("Required application tables missing from pos_db")
    external = external_media_inventory()
    # ponytail: budget two maximum-size copies; use measured sizes if menus outgrow this conservative bound.
    external_bytes = len(external) * MAX_IMAGE_BYTES * 2
    required = max(MIN_FREE_BYTES, db_bytes * 4 + media_bytes + external_bytes + 256 * 1024 ** 2)
    if shutil.disk_usage(root).free < required:
        raise uploader.BackupError("Insufficient free backup space; existing backups were preserved")
    revision = command(["git", "-C", str(app_dir), "rev-parse", "HEAD"])
    if not re.fullmatch(r"[a-f0-9]{40}", revision):
        raise uploader.BackupError("Cannot record the application Git revision")
    return {"git_revision": revision, "expected_table_count": len(tables),
            "external_media_inventory": external,
            "scope": {"database": "pos_db", "local_media": list(MEDIA_PATHS),
                      "external_media": {"host": EXTERNAL_MEDIA_HOST, "image_count": len(external),
                                         "archive_path": EXTERNAL_MEDIA_ROOT + "/"}}}


def validate_local(folder: Path, expected_tables: int, external_sources=()) -> dict:
    definitions, inserts, found, last_line = 0, 0, set(), b""
    with (folder / "pos_db.sql").open("rb") as source:
        # Inspect short prefixes without loading an extended INSERT into memory.
        while prefix := source.readline(512):
            definitions += prefix.startswith(b"CREATE TABLE ")
            inserts += prefix.startswith(b"INSERT INTO ")
            match = re.match(rb"CREATE TABLE `([^`]+)`", prefix)
            if match:
                found.add(match[1].decode("ascii"))
            if prefix.strip():
                last_line = prefix
            while prefix and not prefix.endswith(b"\n"):
                prefix = source.readline(1024 * 1024)
    if (not last_line.startswith(b"-- Dump completed on ") or definitions != expected_tables
            or not CORE_TABLES.issubset(found)):
        raise uploader.BackupError("Database dump incomplete or schema count changed; no upload accepted")
    archive = folder / "production-files.tar.gz"
    entries, media_roots = 0, set()
    roots = (*MEDIA_PATHS, EXTERNAL_MEDIA_ROOT) if external_sources else MEDIA_PATHS
    seen_names, external_files, external_index = set(), {}, None
    with tarfile.open(archive, "r|gz") as source:
        for member in source:
            entries += 1
            if member.name in seen_names:
                raise uploader.BackupError("Duplicate archive entry; no upload accepted")
            seen_names.add(member.name)
            if member.isdir() and member.name in MEDIA_PATHS:
                media_roots.add(member.name)
            if (not any(member.name == name or member.name.startswith(name + "/") for name in roots)
                    or not (member.isfile() or member.isdir()) or ".." in Path(member.name).parts):
                raise uploader.BackupError("Unexpected archive entry; no upload accepted")
            if member.isfile():
                with source.extractfile(member) as data:
                    if member.name == EXTERNAL_MEDIA_ROOT + "/manifest.json":
                        if member.size > 1024 ** 2:
                            raise uploader.BackupError("External media index exceeds the backup limit")
                        external_index = json.loads(data.read())
                    else:
                        digest, size = hashlib.sha256(), 0
                        while chunk := data.read(uploader.CHUNK_SIZE):
                            if member.name.startswith(EXTERNAL_MEDIA_ROOT + "/"):
                                digest.update(chunk)
                                size += len(chunk)
                        if member.name.startswith(EXTERNAL_MEDIA_ROOT + "/"):
                            name = member.name[len(EXTERNAL_MEDIA_ROOT) + 1:]
                            if not re.fullmatch(r"files/[1-9][0-9]*\.bin", name):
                                raise uploader.BackupError("Unexpected external media file")
                            external_files[name] = (size, digest.hexdigest())
    # Tar readers can stop before the gzip trailer/CRC, so also drain gzip to EOF.
    with gzip.open(archive, "rb") as source:
        while source.read(uploader.CHUNK_SIZE):
            pass
    if media_roots != set(MEDIA_PATHS):
        raise uploader.BackupError("Files archive is missing a required media directory")
    if external_sources:
        try:
            images = external_index["images"]
            if (external_index["schema_version"] != 1
                    or [{"menu_item_id": image["menu_item_id"], "url": image["url"]} for image in images] != list(external_sources)
                    or set(external_files) != {image["file"] for image in images}
                    or any(image["file"] != f"files/{image['menu_item_id']}.bin"
                           or external_files[image["file"]] != (image["size"], image["sha256"]) for image in images)):
                raise ValueError
        except (KeyError, TypeError, ValueError):
            raise uploader.BackupError("External media files/index failed count or SHA-256 validation") from None
    for name in uploader.REQUIRED_FILES:
        uploader.file_details(folder / name)
    return {"table_definitions": definitions, "insert_statements": inserts, "archive_entries": entries,
            "external_media_images": len(external_sources)}


def create_local(folder: Path, app_dir: Path, stage, external_sources=()) -> None:
    stage("database-dump")
    with (folder / "pos_db.sql").open("xb") as output:
        command(["mysqldump", "--single-transaction", "--quick", "--routines", "--triggers",
                 "--events", "--hex-blob", "--no-tablespaces", "--dump-date", "pos_db"],
                output=output, timeout=900)
    sources = list(external_sources)
    if external_media_inventory() != sources:
        raise uploader.BackupError("Menu image references changed during the dump; retry in a quiet window")
    with tempfile.TemporaryDirectory(prefix=".external-media-", dir=folder) as temporary:
        if sources:
            stage("external-media-download")
            media_dir = Path(temporary) / EXTERNAL_MEDIA_ROOT
            (media_dir / "files").mkdir(mode=0o700, parents=True)
            images = [download_menu_image(item, media_dir / "files" / f"{item['menu_item_id']}.bin") for item in sources]
            uploader.atomic_json(media_dir / "manifest.json", {"schema_version": 1, "images": images})
            if external_media_inventory() != sources:
                raise uploader.BackupError("Menu image references changed during download; retry in a quiet window")
        stage("media-archive")
        arguments = ["tar", "-C", str(app_dir), "-czf", "-", *MEDIA_PATHS]
        if sources:
            arguments.extend(["-C", temporary, EXTERNAL_MEDIA_ROOT])
        # Retry a changing-file archive once, without regenerating the dump or downloads.
        for attempt in range(2):
            try:
                with (folder / "production-files.tar.gz").open("wb") as output:
                    command(arguments, output=output, timeout=600)
                break
            except uploader.BackupError:
                if attempt:
                    raise


def run(args) -> int:
    if args.backup_root.is_symlink():
        raise uploader.BackupError("Backup root must not be a symlink")
    root = args.backup_root.resolve()
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name == "posix" and (root.stat().st_uid != 0 or root.stat().st_mode & 0o077):
        raise uploader.BackupError("Backup root must be root-owned and mode 700")
    # Losing a lock must not overwrite the active run's status.
    with exclusive_lock(root):
        return run_locked(args, root)


def run_locked(args, root: Path) -> int:
    start = now()
    status = {"status": "running", "stage": "preflight", "started_at_utc": start.isoformat(),
              "started_at_manila": start.astimezone(MANILA).isoformat(), "local_complete": False}
    folder = None

    def stage(name):
        status["stage"] = name
        uploader.atomic_json(root / "last-attempt.json", status)
        if folder:
            uploader.atomic_json(folder / "run.json", status)
        print(f"BACKUP STAGE: {name}", flush=True)

    try:
        stage("preflight")
        load_environment(args.env_file)
        client = uploader.create_client(uploader.credentials(True))
        if args.retry_upload:
            candidate = args.retry_upload.resolve(strict=True)
            if candidate.parent != root or not candidate.name.startswith("auto-daily-"):
                raise uploader.BackupError("Retry folder must be an automated backup directly inside the backup root")
            folder = candidate
            saved = json.loads((folder / "run.json").read_text(encoding="utf-8"))
            if not saved.get("local_complete"):
                raise uploader.BackupError("Saved local backup did not complete; create a new backup instead")
            metadata = saved["metadata"]
            # Preserve the original set's identity even if revalidation fails.
            status.update(run_id=folder.name, metadata=metadata, local_complete=True,
                          local_files=saved["local_files"])
            stage("local-validation")
            validate_local(folder, metadata["expected_table_count"], metadata.get("external_media_inventory", ()))
            if [uploader.file_details(folder / name) for name in uploader.REQUIRED_FILES] != saved["local_files"]:
                raise uploader.BackupError("Saved local backup changed; refusing to upload different bytes under the same run ID")
        else:
            metadata = preflight(args.app_dir.resolve(), root)
            if args.preflight:
                status.update(status="preflight-passed", completed_at_utc=now().isoformat())
                uploader.atomic_json(root / "last-attempt.json", status)
                print("PREFLIGHT PASSED: local checks; remote access is tested during upload", flush=True)
                return 0
            folder = Path(tempfile.mkdtemp(prefix=f"auto-daily-{start.astimezone(MANILA):%Y%m%d-%H%M%S}-", dir=root))
            metadata.update(kind="automated", started_at_utc=start.isoformat(),
                            started_at_manila=start.astimezone(MANILA).isoformat(),
                            scheduled_for_manila=scheduled_for(start) if args.scheduled else None)
            status.update(run_id=folder.name, metadata=metadata)
            create_local(folder, args.app_dir.resolve(), stage, metadata["external_media_inventory"])
            stage("local-validation")
            metadata["validation"] = validate_local(folder, metadata["expected_table_count"], metadata["external_media_inventory"])
        status.update(run_id=folder.name, metadata=metadata, local_complete=True,
                      local_files=[uploader.file_details(folder / name) for name in uploader.REQUIRED_FILES])
        stage("r2-upload-and-verification")
        manifest = uploader.upload_backup(folder, client, metadata)
        completed = now()
        status.update(status="success", stage="complete", completed_at_utc=completed.isoformat(),
                      completed_at_manila=completed.astimezone(MANILA).isoformat())
        success_record = {
            "prefix": folder.name, "verified_at_utc": manifest["verified_at_utc"],
            "scheduled_for_manila": metadata.get("scheduled_for_manila"),
            "completed_at_utc": completed.isoformat(), "completed_at_manila": completed.astimezone(MANILA).isoformat(),
        }
        uploader.atomic_json(folder / "run.json", status)
        uploader.atomic_json(root / "last-attempt.json", status)
        uploader.atomic_json(root / "last-success.json", success_record)
        print(f"AUTOMATED BACKUP VERIFIED: {folder.name}", flush=True)
        return 0
    except Exception as error:
        status.update(status="failed", failed_at_utc=now().isoformat(),
                      error=str(error) if isinstance(error, uploader.BackupError) else type(error).__name__)
        print(f"BACKUP FAILED at {status['stage']}: {status['error']}", flush=True)
        # Disk exhaustion or a permissions failure must not hide the original failure.
        for path in [root / "last-attempt.json"] + ([folder / "run.json"] if folder else []):
            try:
                uploader.atomic_json(path, status)
            except OSError:
                print("BACKUP STATUS WRITE FAILED: check disk space and private directory access", flush=True)
        return 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-dir", type=Path, default=Path("/var/www/pos"))
    parser.add_argument("--backup-root", type=Path, default=Path("/var/backups/ideaflow"))
    parser.add_argument("--env-file", type=Path, default=Path("/etc/ideaflow/backup.env"))
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--preflight", action="store_true", help="Check local prerequisites; create no backup")
    mode.add_argument("--retry-upload", type=Path, help="Retry a completed local backup without dumping again")
    mode.add_argument("--scheduled", action="store_true", help="Associate with the latest due 23:30 Manila schedule")
    args = parser.parse_args(argv)
    os.umask(0o077)

    def interrupted(signum, frame):
        raise uploader.BackupError("Backup interrupted or service time limit reached")

    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    try:
        return run(args)
    except Exception as error:
        print(f"BACKUP FAILED: {str(error) if isinstance(error, uploader.BackupError) else type(error).__name__}", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
