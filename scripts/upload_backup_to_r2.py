"""Manually upload one verified IdeaFlow backup folder to private Cloudflare R2."""

from __future__ import annotations

import argparse
from getpass import getpass
from pathlib import Path

import boto3
from botocore.config import Config


BUCKET = "ideaflow-backups"
REQUIRED_FILES = ("pos_db.sql", "production-files.tar.gz")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Upload a daily IdeaFlow backup to its private R2 bucket."
    )
    parser.add_argument("folder", type=Path, help="Absolute daily backup directory")
    args = parser.parse_args()

    folder = args.folder.resolve()
    if not folder.is_dir():
        raise SystemExit(f"Backup folder does not exist: {folder}")

    sources = [folder / name for name in REQUIRED_FILES]
    missing = [str(path) for path in sources if not path.is_file() or path.stat().st_size == 0]
    if missing:
        raise SystemExit("Missing or empty backup file(s): " + ", ".join(missing))

    endpoint = input("Paste S3 endpoint: ").strip().rstrip("/")
    endpoint = endpoint.removesuffix(f"/{BUCKET}")
    access_key = getpass("Paste Access Key ID: ").strip()
    secret_key = getpass("Paste Secret Access Key: ").strip()
    if not endpoint.startswith("https://") or not access_key or not secret_key:
        raise SystemExit("Endpoint or credentials are empty/invalid")

    s3 = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="auto",
        config=Config(signature_version="s3v4"),
    )

    for source in sources:
        key = f"{folder.name}/{source.name}"
        expected_size = source.stat().st_size
        s3.upload_file(str(source), BUCKET, key)
        actual_size = s3.head_object(Bucket=BUCKET, Key=key)["ContentLength"]
        if actual_size != expected_size:
            raise SystemExit(
                f"R2 size verification failed for {key}: "
                f"local={expected_size}, remote={actual_size}"
            )
        print(f"UPLOADED AND VERIFIED: {key} ({actual_size} bytes)")

    print("DAILY R2 BACKUP COMPLETE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
