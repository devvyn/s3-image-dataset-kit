
from __future__ import annotations

import mimetypes
import os
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

from tqdm import tqdm

try:
    from PIL import Image  # optional
except Exception:
    Image = None  # width/height omitted if Pillow missing

from botocore.exceptions import ClientError

from .config import SETTINGS
from .hashutil import sha256_file
from .manifest import ManifestEntry, to_manifest_entry, write_jsonl
from .s3_client import s3_client


def iter_images(src_dir: str) -> Iterable[str]:
    exts = {'.jpg','.jpeg','.png','.tif','.tiff'}
    for root, _, files in os.walk(src_dir):
        for name in files:
            if os.path.splitext(name)[1].lower() in exts:
                yield os.path.join(root, name)

def _object_key_from_sha(sha: str, ext: str) -> str:
    return f"images/{sha[:2]}/{sha[2:4]}/{sha}{ext}"

def _content_type(path: str) -> str:
    t, _ = mimetypes.guess_type(path)
    return t or "application/octet-stream"

def _maybe_dims(path: str) -> tuple[Optional[int], Optional[int]]:
    if Image is None:
        return None, None
    try:
        with Image.open(path) as img:
            w, h = img.size
            return int(w), int(h)
    except Exception:
        return None, None

def build_manifest(src_dir: str, logical_map: dict[str, str] | None = None):
    entries: list[ManifestEntry] = []
    for path in tqdm(iter_images(src_dir), desc="Hashing"):
        sha = sha256_file(path)
        ext = os.path.splitext(path)[1].lower()
        if ext == ".jpeg":
            ext = ".jpg"
        key = _object_key_from_sha(sha, ext)
        size = os.path.getsize(path)
        ctype = _content_type(path)
        w, h = _maybe_dims(path)
        logical_id = None
        if logical_map:
            fname = os.path.basename(path)
            logical_id = logical_map.get(fname) or logical_map.get(path)
        entries.append(ManifestEntry(
            sha256=sha,
            path=key,
            bytes=size,
            content_type=ctype,
            width=w,
            height=h,
            logical_id=logical_id,
        ))
    return entries

def build_sha_to_local_map(src_dir: str) -> dict[str, str]:
    """Compute a mapping of SHA256 hash → local file path."""

    mapping: dict[str, str] = {}
    for path in iter_images(src_dir):
        sha = sha256_file(path)
        mapping[sha] = path
    return mapping


def upload_entries(
    entries: Iterable[ManifestEntry | Mapping[str, Any]],
    *,
    src_dir: str | None = None,
    sha_to_local: Mapping[str, str] | None = None,
) -> list[ManifestEntry]:
    """Upload manifest entries using a local SHA→path mapping.

    Provide either ``src_dir`` (to derive a mapping) or ``sha_to_local``.
    Objects already present in the bucket are skipped. The returned list contains
    normalized entries with the latest known ETag populated (when available).
    """

    if sha_to_local is None:
        if not src_dir:
            raise ValueError("upload_entries requires src_dir or sha_to_local mapping")
        sha_to_local = build_sha_to_local_map(src_dir)

    bucket = SETTINGS.require_bucket()
    s3 = s3_client()

    uploaded: list[ManifestEntry] = []

    for record in tqdm(entries, desc="Uploading"):
        entry = to_manifest_entry(record)
        local_path = sha_to_local.get(entry.sha256)
        if not local_path:
            raise FileNotFoundError(
                f"Local file for SHA {entry.sha256} not found; ensure source matches manifest"
            )

        try:
            head = s3.head_object(Bucket=bucket, Key=entry.path)
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "")
            if error_code not in {"404", "NoSuchKey", "NotFound"}:
                raise
        else:
            entry.etag = head.get("ETag")
            uploaded.append(entry)
            continue

        etag = upload_file(local_path, entry, bucket=bucket)
        if etag:
            entry.etag = etag
        uploaded.append(entry)

    return uploaded

def upload_file(local_path: str, entry: ManifestEntry, *, bucket: str | None = None) -> str | None:
    if bucket is None:
        bucket = SETTINGS.require_bucket()
    s3 = s3_client()
    with open(local_path, "rb") as f:
        response = s3.put_object(
            Bucket=bucket,
            Key=entry.path,
            Body=f,
            ContentType=entry.content_type,
            CacheControl="public, max-age=31536000, immutable"
        )
    return response.get("ETag")

def write_manifest(entries: list[ManifestEntry], out_path: str):
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    write_jsonl(entries, out_path)

def upload_manifest(local_manifest_path: str):
    bucket = SETTINGS.require_bucket()
    s3 = s3_client()
    with open(local_manifest_path, "rb") as f:
        s3.put_object(
            Bucket=bucket,
            Key=SETTINGS.manifest_key,
            Body=f,
            ContentType="application/json",
            CacheControl="no-cache"
        )
