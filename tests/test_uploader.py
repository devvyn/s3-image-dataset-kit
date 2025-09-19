from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest
from botocore.exceptions import ClientError

from dataset_tool import uploader
from dataset_tool.manifest import ManifestEntry


def _touch_file(path: Path, data: bytes = b"data") -> str:
    path.write_bytes(data)
    return str(path)


@pytest.fixture(autouse=True)
def _silence_tqdm(monkeypatch):
    monkeypatch.setattr(uploader, "tqdm", lambda iterable, **_: iterable)


@pytest.fixture
def _stub_bucket(monkeypatch):
    monkeypatch.setattr(uploader.SETTINGS, "require_bucket", lambda: "test-bucket", raising=False)


def test_upload_entries_skips_existing_object(tmp_path: Path, monkeypatch, _stub_bucket):
    sha = "a" * 64
    entry = ManifestEntry(
        sha256=sha,
        path=uploader._object_key_from_sha(sha, ".jpg"),
        bytes=3,
    )
    local_map = {sha: _touch_file(tmp_path / "image.jpg", b"abc")}

    fake_s3 = Mock()
    fake_s3.head_object.return_value = {"ETag": '"existing"'}

    monkeypatch.setattr(uploader, "s3_client", lambda: fake_s3)
    result = uploader.upload_entries([entry], sha_to_local=local_map)

    assert result[0].etag == '"existing"'
    assert fake_s3.put_object.call_count == 0


def test_upload_entries_uploads_and_sets_etag(tmp_path: Path, monkeypatch, _stub_bucket):
    sha = "b" * 64
    entry = ManifestEntry(
        sha256=sha,
        path=uploader._object_key_from_sha(sha, ".jpg"),
        bytes=4,
    )
    local_map = {sha: _touch_file(tmp_path / "image2.jpg", b"abcd")}

    fake_s3 = Mock()
    fake_s3.head_object.side_effect = ClientError({"Error": {"Code": "404"}}, "HeadObject")
    fake_s3.put_object.return_value = {"ETag": '"uploaded"'}

    monkeypatch.setattr(uploader, "s3_client", lambda: fake_s3)
    result = uploader.upload_entries([entry], sha_to_local=local_map)

    assert fake_s3.put_object.call_count == 1
    assert result[0].etag == '"uploaded"'
