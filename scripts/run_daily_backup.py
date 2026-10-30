"""Root-run database/media backup. No Flask import, app restart, or data deletion."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import gzip
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tarfile
import tempfile
from zoneinfo import ZoneInfo

from dotenv import dotenv_values

if __package__:
    from . import upload_backup_to_r2 as uploader
else:
    import upload_backup_to_r2 as uploader


MANILA = ZoneInfo("Asia/Manila")
CORE_TABLES = {"users", "customer_sessions", "transactions", "expenses", "receivables", "payables"}
MEDIA_PATHS = ("static/uploads", "static/images")
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
    required = max(MIN_FREE_BYTES, db_bytes * 4 + media_bytes + 256 * 1024 ** 2)
    if shutil.disk_usage(root).free < required:
        raise uploader.BackupError("Insufficient free backup space; existing backups were preserved")
    revision = command(["git", "-C", str(app_dir), "rev-parse", "HEAD"])
    if not re.fullmatch(r"[a-f0-9]{40}", revision):
        raise uploader.BackupError("Cannot record the application Git revision")
    return {"git_revision": revision, "expected_table_count": len(tables),
            "scope": {"database": "pos_db", "local_media": list(MEDIA_PATHS),
                      "external_media": "not included; inventory separately before enablement"}}


def validate_local(folder: Path, expected_tables: int) -> dict:
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
    with tarfile.open(archive, "r|gz") as source:
        for member in source:
            entries += 1
            if member.isdir() and member.name in MEDIA_PATHS:
                media_roots.add(member.name)
            if (not any(member.name == name or member.name.startswith(name + "/") for name in MEDIA_PATHS)
                    or not (member.isfile() or member.isdir()) or ".." in Path(member.name).parts):
                raise uploader.BackupError("Unexpected archive entry; no upload accepted")
            if member.isfile():
                with source.extractfile(member) as data:
                    while data.read(uploader.CHUNK_SIZE):
                        pass
    # Tar readers can stop before the gzip trailer/CRC, so also drain gzip to EOF.
    with gzip.open(archive, "rb") as source:
        while source.read(uploader.CHUNK_SIZE):
            pass
    if media_roots != set(MEDIA_PATHS):
        raise uploader.BackupError("Files archive is missing a required media directory")
    for name in uploader.REQUIRED_FILES:
        uploader.file_details(folder / name)
    return {"table_definitions": definitions, "insert_statements": inserts, "archive_entries": entries}


def create_local(folder: Path, app_dir: Path, stage) -> None:
    stage("database-dump")
    with (folder / "pos_db.sql").open("xb") as output:
        command(["mysqldump", "--single-transaction", "--quick", "--routines", "--triggers",
                 "--events", "--hex-blob", "--no-tablespaces", "--dump-date", "pos_db"],
                output=output, timeout=900)
    stage("media-archive")
    # Retry a changing-file archive once, without regenerating the database dump.
    for attempt in range(2):
        try:
            with (folder / "production-files.tar.gz").open("wb") as output:
                command(["tar", "-C", str(app_dir), "-czf", "-", *MEDIA_PATHS],
                        output=output, timeout=600)
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
            validate_local(folder, metadata["expected_table_count"])
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
            create_local(folder, args.app_dir.resolve(), stage)
            stage("local-validation")
            metadata["validation"] = validate_local(folder, metadata["expected_table_count"])
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
