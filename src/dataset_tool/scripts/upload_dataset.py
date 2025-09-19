from __future__ import annotations

import argparse

from dataset_tool.config import SETTINGS
from dataset_tool.manifest import read_jsonl
from dataset_tool.s3_client import s3_client
from dataset_tool.uploader import (
    build_sha_to_local_map,
    upload_entries,
    upload_manifest,
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="Local source directory of images")
    ap.add_argument("--manifest", required=True, help="Local manifest to upload")
    args = ap.parse_args()

    entries = read_jsonl(args.manifest)
    sha_to_path = build_sha_to_local_map(args.src)

    missing = [e for e in entries if e["sha256"] not in sha_to_path]
    if missing:
        raise SystemExit(f"{len(missing)} entries missing locally; ensure --src matches manifest")

    bucket = SETTINGS.require_bucket()
    s3 = s3_client()

    upload_entries(entries, sha_to_local=sha_to_path, s3=s3)

    upload_manifest(args.manifest, s3=s3, bucket=bucket)
    print(f"Uploaded manifest to s3://{bucket}/{SETTINGS.manifest_key}")

if __name__ == "__main__":
    main()
