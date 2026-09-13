from __future__ import annotations

import base64
import io

import pytest
from werkzeug.datastructures import FileStorage

from app import create_app
from app.utils import uploads


_PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


class FakeR2Client:
    def __init__(self):
        self.put_calls = []
        self.delete_calls = []

    def put_object(self, **kwargs):
        self.put_calls.append(kwargs)

    def delete_object(self, **kwargs):
        self.delete_calls.append(kwargs)


@pytest.fixture
def app():
    application = create_app()
    application.config.update(
        TESTING=True,
        R2_MEDIA_ENABLED=True,
        R2_MEDIA_BUCKET="ideaflow-media",
        R2_MEDIA_ENDPOINT="https://account.r2.cloudflarestorage.com",
        R2_MEDIA_ACCESS_KEY_ID="test-key",
        R2_MEDIA_SECRET_ACCESS_KEY="test-secret",
        R2_MEDIA_PUBLIC_URL="https://media.idea-flows.online",
        R2_MEDIA_PREFIX="menu",
    )
    return application


def test_r2_upload_uses_verified_content_and_immutable_cache(app, monkeypatch):
    fake_client = FakeR2Client()
    monkeypatch.setattr(uploads, "_get_r2_client", lambda: fake_client)
    upload = FileStorage(stream=io.BytesIO(_PNG_1X1), filename="dish.png")

    with app.app_context():
        image_url, error = uploads.validate_and_save_image(upload)

    assert error is None
    assert image_url.startswith("https://media.idea-flows.online/menu/menu_")
    assert image_url.endswith(".png")
    assert len(fake_client.put_calls) == 1
    call = fake_client.put_calls[0]
    assert call["Bucket"] == "ideaflow-media"
    assert call["Key"].startswith("menu/menu_")
    assert call["ContentType"] == "image/png"
    assert call["CacheControl"] == "public, max-age=31536000, immutable"


def test_r2_delete_only_accepts_the_configured_media_prefix(app, monkeypatch):
    fake_client = FakeR2Client()
    monkeypatch.setattr(uploads, "_get_r2_client", lambda: fake_client)

    with app.app_context():
        uploads.delete_old_image(
            "https://media.idea-flows.online/menu/menu_deadbeef.png"
        )
        uploads.delete_old_image(
            "https://media.idea-flows.online/private/not-menu.png"
        )

    assert fake_client.delete_calls == [
        {"Bucket": "ideaflow-media", "Key": "menu/menu_deadbeef.png"}
    ]


def test_corrupt_image_is_rejected_before_upload(app, monkeypatch):
    fake_client = FakeR2Client()
    monkeypatch.setattr(uploads, "_get_r2_client", lambda: fake_client)
    upload = FileStorage(stream=io.BytesIO(b"not an image"), filename="dish.png")

    with app.app_context():
        image_url, error = uploads.validate_and_save_image(upload)

    assert image_url is None
    assert "Invalid or corrupted" in error
    assert fake_client.put_calls == []
