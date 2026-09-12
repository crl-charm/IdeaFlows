from __future__ import annotations

import io
import logging
import os
import uuid
from urllib.parse import unquote, urlsplit

from flask import current_app
from PIL import Image, ImageOps, UnidentifiedImageError
from werkzeug.utils import secure_filename

logger = logging.getLogger(__name__)

_FORMAT_DETAILS = {
    "JPEG": ("jpg", "image/jpeg"),
    "PNG": ("png", "image/png"),
    "GIF": ("gif", "image/gif"),
    "WEBP": ("webp", "image/webp"),
}
_MAX_IMAGE_PIXELS = 25_000_000


def get_upload_folder():
    """Return the local fallback folder, creating it when necessary."""
    folder = current_app.config.get(
        "UPLOAD_FOLDER",
        os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "static",
            "uploads",
            "menu",
        ),
    )
    os.makedirs(folder, exist_ok=True)
    return folder


def allowed_file(filename):
    """Check the user-facing extension before doing content validation."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in current_app.config.get(
        "ALLOWED_UPLOAD_EXTENSIONS", {"png", "jpg", "jpeg", "gif", "webp"}
    )


def _r2_enabled():
    return bool(current_app.config.get("R2_MEDIA_ENABLED"))


def _get_r2_client():
    """Create an S3-compatible client only when R2 is actually used."""
    try:
        import boto3
        from botocore.config import Config as BotoConfig
    except ImportError as exc:  # pragma: no cover - deployment dependency guard
        raise RuntimeError("boto3 is required when R2 media storage is enabled") from exc

    return boto3.client(
        "s3",
        endpoint_url=current_app.config["R2_MEDIA_ENDPOINT"],
        aws_access_key_id=current_app.config["R2_MEDIA_ACCESS_KEY_ID"],
        aws_secret_access_key=current_app.config["R2_MEDIA_SECRET_ACCESS_KEY"],
        region_name="auto",
        config=BotoConfig(
            signature_version="s3v4",
            retries={"max_attempts": 3, "mode": "standard"},
            connect_timeout=5,
            read_timeout=15,
        ),
    )


def _validated_image_bytes(file):
    """Read, verify, resize, and encode an uploaded image."""
    max_size = current_app.config.get("UPLOAD_MAX_FILE_SIZE", 5 * 1024 * 1024)
    raw = file.read(max_size + 1)
    if not raw:
        raise ValueError("File is empty")
    if len(raw) > max_size:
        raise ValueError(f"File too large. Max size: {max_size / 1024 / 1024:.0f}MB")

    try:
        with Image.open(io.BytesIO(raw)) as probe:
            image_format = (probe.format or "").upper()
            width, height = probe.size
            probe.verify()
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        raise ValueError("Invalid or corrupted image file") from exc

    if image_format not in _FORMAT_DETAILS:
        raise ValueError("File type not allowed. Use: PNG, JPG, JPEG, GIF, WebP")
    if width <= 0 or height <= 0 or width * height > _MAX_IMAGE_PIXELS:
        raise ValueError("Image dimensions are too large")

    extension, content_type = _FORMAT_DETAILS[image_format]

    # Keep animated GIF data intact after Pillow has verified the whole file.
    if image_format == "GIF":
        return raw, extension, content_type

    with Image.open(io.BytesIO(raw)) as image:
        image = ImageOps.exif_transpose(image)
        if image.width > 800:
            ratio = 800 / image.width
            image = image.resize(
                (800, max(1, int(image.height * ratio))), Image.Resampling.LANCZOS
            )

        output = io.BytesIO()
        if image_format == "JPEG":
            if image.mode not in ("RGB", "L"):
                image = image.convert("RGB")
            image.save(output, format="JPEG", quality=80, optimize=True)
        elif image_format == "PNG":
            image.save(output, format="PNG", optimize=True)
        else:
            image.save(output, format="WEBP", quality=80, method=6)
        return output.getvalue(), extension, content_type


def validate_and_save_image(file):
    """Validate an image and save it to R2 or the local development folder."""
    try:
        if not file or not file.filename:
            return None, "No file provided"
        if not allowed_file(file.filename):
            return None, "File type not allowed. Use: PNG, JPG, JPEG, GIF, WebP"
        if not secure_filename(file.filename):
            return None, "Invalid filename"

        body, extension, content_type = _validated_image_bytes(file)
        unique_filename = f"menu_{uuid.uuid4().hex}.{extension}"

        if _r2_enabled():
            prefix = current_app.config["R2_MEDIA_PREFIX"]
            key = f"{prefix}/{unique_filename}"
            _get_r2_client().put_object(
                Bucket=current_app.config["R2_MEDIA_BUCKET"],
                Key=key,
                Body=body,
                ContentType=content_type,
                CacheControl="public, max-age=31536000, immutable",
            )
            return f"{current_app.config['R2_MEDIA_PUBLIC_URL']}/{key}", None

        filepath = os.path.join(get_upload_folder(), unique_filename)
        with open(filepath, "wb") as destination:
            destination.write(body)
        return f"/static/uploads/menu/{unique_filename}", None
    except ValueError as exc:
        return None, str(exc)
    except Exception:
        logger.exception("Image save failed")
        return None, "Unable to store the image. Please try again."


def _r2_key_from_url(image_url):
    public_url = current_app.config.get("R2_MEDIA_PUBLIC_URL", "").rstrip("/")
    if not public_url or not image_url.startswith(f"{public_url}/"):
        return None
    key = unquote(urlsplit(image_url).path.lstrip("/"))
    prefix = f"{current_app.config.get('R2_MEDIA_PREFIX', 'menu').strip('/')}/"
    return key if key.startswith(prefix) else None


def delete_old_image(image_url):
    """Best-effort removal for media that is no longer referenced."""
    if not image_url:
        return
    try:
        key = _r2_key_from_url(image_url) if _r2_enabled() else None
        if key:
            _get_r2_client().delete_object(
                Bucket=current_app.config["R2_MEDIA_BUCKET"], Key=key
            )
            logger.info("Deleted unreferenced R2 image: %s", key)
            return

        local_prefix = "/static/uploads/menu/"
        if image_url.startswith(local_prefix):
            filename = os.path.basename(image_url.removeprefix(local_prefix))
            filepath = os.path.join(get_upload_folder(), filename)
            if os.path.isfile(filepath):
                os.remove(filepath)
                logger.info("Deleted unreferenced local image: %s", filename)
    except Exception:
        # Database operations remain successful if remote cleanup needs a retry.
        # Unique names prevent failed cleanup from corrupting a newer image.
        logger.exception("Unable to delete unreferenced image")
