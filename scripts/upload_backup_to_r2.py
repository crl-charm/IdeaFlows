"""Upload a private backup, verify the bytes, then publish its completion marker."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from getpass import getpass
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import time
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import boto3
from boto3.exceptions import S3UploadFailedError
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError


BUCKET = "ideaflow-backups"
REQUIRED_FILES = ("pos_db.sql", "production-files.tar.gz")
ENV_PREFIX = "IDEAFLOW_BACKUP_R2_"
CHUNK_SIZE = 1024 * 1024


class BackupError(Exception):
    """A safe diagnostic that contains no provider response or credentials."""


def atomic_json(path: Path, value: dict) -> None:
    """Private, same-directory replacement; an interrupted write keeps the old file."""
    descriptor, temporary = tempfile.mkstemp(prefix=".backup-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
            json.dump(value, output, indent=2, sort_keys=True)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def file_details(path: Path) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size == 0:
        raise BackupError("Missing, empty, or symlinked backup file")
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(CHUNK_SIZE), b""):
            digest.update(chunk)
            size += len(chunk)
    return {"name": path.name, "size": size, "sha256": digest.hexdigest()}


def credentials(non_interactive: bool) -> tuple[str, str, str]:
    if non_interactive:
        values = [os.environ.get(ENV_PREFIX + name, "").strip() for name in
                  ("ENDPOINT", "ACCESS_KEY_ID", "SECRET_ACCESS_KEY")]
    else:
        values = [input("Paste S3 endpoint: ").strip(),
                  getpass("Paste Access Key ID: ").strip(),
                  getpass("Paste Secret Access Key: ").strip()]
    endpoint, access_key, secret_key = values
    endpoint = endpoint.rstrip("/").removesuffix(f"/{BUCKET}")
    parsed = urlsplit(endpoint)
    if (parsed.scheme != "https" or not parsed.hostname
            or not re.fullmatch(r"[a-zA-Z0-9-]+\.r2\.cloudflarestorage\.com", parsed.hostname)
            or parsed.path or parsed.query or parsed.fragment or parsed.username
            or parsed.password or parsed.netloc != parsed.hostname
            or not re.fullmatch(r"[a-fA-F0-9]{32}", access_key) or not secret_key):
        raise BackupError("Missing/invalid R2 endpoint or credentials (Access Key ID must be 32 hex characters)")
    return endpoint, access_key, secret_key


def create_client(values: tuple[str, str, str]):
    endpoint, access_key, secret_key = values
    return boto3.client(
        "s3", endpoint_url=endpoint, aws_access_key_id=access_key,
        aws_secret_access_key=secret_key, region_name="auto",
        config=Config(signature_version="s3v4", connect_timeout=10, read_timeout=60,
                      retries={"mode": "standard", "total_max_attempts": 4}),
    )


def network_retry(operation):
    """SDK retries requests; this also retries interrupted response-body streams."""
    for attempt in range(3):
        try:
            return operation()
        except ClientError as error:
            status = error.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0)
            if status not in (408, 429, 500, 502, 503, 504):
                raise BackupError("R2 request rejected; check backup bucket access and credentials") from None
        except (BotoCoreError, OSError, S3UploadFailedError):
            pass
        if attempt < 2:
            time.sleep(2 ** attempt)
    raise BackupError("R2 transfer/read-back failed after bounded retries")


def remote_details(client, key: str) -> dict:
    response = client.get_object(Bucket=BUCKET, Key=key)
    body = response["Body"]
    digest, size = hashlib.sha256(), 0
    try:
        for chunk in iter(lambda: body.read(CHUNK_SIZE), b""):
            digest.update(chunk)
            size += len(chunk)
    finally:
        body.close()
    if response["ContentLength"] != size:
        raise OSError("Incomplete R2 object body")
    return {"name": key.rsplit("/", 1)[-1], "size": size, "sha256": digest.hexdigest()}


def existing_manifest(client, key: str) -> dict | None:
    try:
        response = client.get_object(Bucket=BUCKET, Key=key)
    except ClientError as error:
        if error.response.get("Error", {}).get("Code") in ("NoSuchKey", "404", "NotFound"):
            return None
        raise
    body = response["Body"]
    try:
        if response["ContentLength"] > CHUNK_SIZE:
            raise BackupError("Existing R2 completion manifest is invalid")
        payload = body.read(CHUNK_SIZE + 1)
        if len(payload) != response["ContentLength"]:
            raise OSError("Incomplete R2 manifest body")
        value = json.loads(payload)
        if not isinstance(value, dict):
            raise ValueError
        return value
    except (ValueError, UnicodeError):
        raise BackupError("Existing R2 completion manifest is invalid") from None
    finally:
        body.close()


def upload_backup(folder: Path, client, metadata: dict | None = None) -> dict:
    if not folder.is_dir() or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,150}", folder.name):
        raise BackupError("Invalid backup folder or R2 prefix")
    details = [file_details(folder / name) for name in REQUIRED_FILES]
    marker = f"{folder.name}/manifest.json"
    previous = network_retry(lambda: existing_manifest(client, marker))
    if previous is not None:
        if (previous.get("schema_version") != 1 or previous.get("status") != "complete"
                or previous.get("bucket") != BUCKET or previous.get("prefix") != folder.name
                or previous.get("files") != details
                or (metadata and any(previous.get(key) != value for key, value in metadata.items()))):
            raise BackupError("Existing completed backup differs; refusing to overwrite it")
    for info in details:
        source = folder / info["name"]
        key = f"{folder.name}/{source.name}"
        if previous is None:
            network_retry(lambda: client.upload_file(str(source), BUCKET, key))
        actual = network_retry(lambda: remote_details(client, key))
        if actual != info:
            raise BackupError("R2 size/SHA-256 verification failed; no new completion marker")
        print(f"UPLOADED AND VERIFIED: {key} ({info['size']} bytes; SHA-256 matched)", flush=True)
    verified = datetime.now(timezone.utc)
    manifest = previous or {
        **(metadata or {"kind": "manual-upload"}),
        "schema_version": 1, "status": "complete", "bucket": BUCKET,
        "prefix": folder.name, "files": details,
        "verified_at_utc": verified.isoformat(),
        "verified_at_manila": verified.astimezone(ZoneInfo("Asia/Manila")).isoformat(),
    }
    if previous is None:
        payload = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
        network_retry(lambda: client.put_object(Bucket=BUCKET, Key=marker, Body=payload,
                                                ContentType="application/json"))
        if network_retry(lambda: existing_manifest(client, marker)) != manifest:
            raise BackupError("R2 completion manifest read-back failed")
    atomic_json(folder / "manifest.json", manifest)
    print("DAILY R2 BACKUP COMPLETE", flush=True)
    return manifest


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path, help="Verified backup directory")
    parser.add_argument("--non-interactive", action="store_true", help="Read backup-specific environment variables; never prompt")
    args = parser.parse_args(argv)
    os.umask(0o077)
    try:
        folder = args.folder.resolve(strict=True)
        for name in REQUIRED_FILES:
            file_details(folder / name)
        upload_backup(folder, create_client(credentials(args.non_interactive)))
        return 0
    except BackupError as error:
        print(f"BACKUP FAILED: {error}", flush=True)
    except Exception as error:
        # Provider/URL exceptions may contain credentials. Never print their text.
        print(f"BACKUP FAILED: {type(error).__name__}; check configuration and file access", flush=True)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
