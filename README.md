# S3 Image Dataset Kit (Immutable, Read-Only, Random Access)

A minimal, production-friendly toolkit for hosting ~3k read-only JPEGs in S3/S3-compatible storage, with
content-addressed keys, a JSONL manifest, and a read-through cache client for containers and task runners.

> Philosophy: **Don't bake images into Docker.** Put them in object storage, fetch on demand, cache locally.

## Features
- **Content-addressed uploads** (SHA256) with two-level prefix split: `images/ab/cd/<sha256>.jpg`
- **JSONL manifest** with bytes, content-type, optional width/height, optional logical IDs
- **Read-through cache client** for random access workloads
- Supports AWS S3 and S3-compatible endpoints (MinIO, Cloudflare R2, DO Spaces, etc.)
- Clean **uv-managed** Python project; includes **justfile** recipes

## Requirements
- Python 3.10+
- [uv](https://github.com/astral-sh/uv) (Python package/dependency manager)
- (Optional) [`just`](https://github.com/casey/just) if you want to use the bundled command recipes
- An S3 or S3-compatible bucket and credentials (static keys or IAM role)
- (Optional) Docker, rclone

## Configuration
The toolkit loads configuration from environment variables and `.env` via `python-dotenv`. Start by copying
the sample file and filling in your values:

```bash
cp .env.example .env
# edit .env with your bucket and credentials
```

Key settings:

| Variable | Description |
| --- | --- |
| `S3_BUCKET` | **Required.** Bucket name that stores `images/` and the manifest. |
| `AWS_REGION` | AWS region (defaults to `us-east-1`). |
| `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` | Static credentials for local/dev usage. Prefer IAM roles in production. |
| `S3_ENDPOINT_URL` | Optional S3-compatible endpoint (MinIO, R2, etc.). Leave unset for AWS. |
| `CACHE_DIR` | Local on-disk cache directory for the read-through client (`/tmp/imgcache` default). |
| `MANIFEST_KEY` | Manifest location inside the bucket (`manifests/inventory-v1.jsonl` default). |
| `DATASET_LOGICAL_MAP` | Optional CSV mapping (`filename,logical_id`) used when building manifests. |

You can also override these ad-hoc, e.g. `S3_BUCKET=my-dataset uv run python -m dataset_tool.scripts.upload_dataset ...`.

## Installation
Two common installation patterns are supported.

### Developer setup (editable install + dev tooling)
1. Sync dependencies into the project-managed virtual environment:
   ```bash
   uv sync
   ```
2. Install the project itself in editable mode so that `src/` is importable:
   ```bash
   uv pip install -e .
   ```
3. (Optional) Run the bundled smoke check:
   ```bash
   just check    # or run `just dev` to execute sync + install + check together
   ```

When using the uv-managed environment you can prefix commands with `uv run` without manually activating `.venv`.

### Operator / runtime install (no dev dependencies)
1. Create or reuse a virtual environment (shown here with uv):
   ```bash
   uv venv .venv
   source .venv/bin/activate
   ```
2. Install the package and runtime dependencies:
   ```bash
   uv pip install .
   # include Pillow for width/height metadata if desired
   uv pip install '.[images]'
   ```
3. Run the CLIs directly from that environment, e.g. `python -m dataset_tool.scripts.build_manifest ...`.

## Command reference
### Python module CLIs
Use `uv run python -m …` if you are relying on the uv-managed environment, otherwise run them inside your own
virtual environment.

| Command | Purpose |
| --- | --- |
| `python -m dataset_tool.scripts.build_manifest --src ./data/images --out ./manifests/inventory-v1.jsonl [--logical-map ./logical-map.csv]` | Hash local images, populate optional logical IDs, and write a JSONL manifest. Falls back to `DATASET_LOGICAL_MAP` from the environment. |
| `python -m dataset_tool.scripts.validate_manifest --manifest ./manifests/inventory-v1.jsonl [--schema schema/inventory-v1.schema.json]` | Validate a manifest file against the bundled JSON Schema. |
| `python -m dataset_tool.scripts.upload_dataset --src ./data/images --manifest ./manifests/inventory-v1.jsonl` | Upload objects and manifest to the bucket configured via `S3_BUCKET`, updating entries with S3 ETags. Requires AWS credentials/role. |
| `python -m dataset_tool.scripts.random_fetch --manifest ./manifests/inventory-v1.jsonl [--n 5]` | Sample N records from the manifest, download them through the cache (`CACHE_DIR`), and print local paths. |

### `just` recipes
`just` is optional but provides reproducible workflows. All recipes run `just dev` first to guarantee an up-to-date
editable install.

| Recipe | Arguments | Description |
| --- | --- | --- |
| `just sync` | – | Install lockfile-managed dependencies into `.venv` via uv. |
| `just install` | – | Editable install of the project into the uv environment. |
| `just reinstall` | – | Force a reinstall after metadata changes. |
| `just check` | – | Smoke test that both the import and distribution metadata resolve. |
| `just dev` | – | Run `sync`, `install`, and `check` in sequence. |
| `just manifest` | `<src_dir>` | Build `manifests/inventory-v1.jsonl` from a directory of images (uses `build_manifest`). |
| `just validate` | `<manifest_path>` | Validate a manifest against the JSON Schema. |
| `just upload` | `<src_dir> <manifest_path>` | Upload objects and manifest to `S3_BUCKET` using `upload_dataset`. |
| `just clean` | – | Remove `.venv` and `.uv-cache`. |

## Quick start workflow
1. Configure environment:
   ```bash
   cp .env.example .env
   # set S3_BUCKET, AWS_REGION, and any credentials in .env
   ```
2. Build a manifest from your images:
   ```bash
   just manifest ./data/images
   ```
3. Upload objects + manifest to your bucket (ensure `S3_BUCKET` is set):
   ```bash
   just upload ./data/images ./manifests/inventory-v1.jsonl
   ```
4. Exercise the read-through cache client:
   ```bash
   uv run python -m dataset_tool.scripts.random_fetch --manifest ./manifests/inventory-v1.jsonl --n 5
   ```

## Directory Layout
```
s3://YOUR_BUCKET/
  images/
    ab/cd/<sha256>.jpg
  manifests/
    inventory-v1.jsonl
```

### Manifest fields (JSONL per-line object)
```json
{
  "sha256": "abcdef...",
  "path": "images/ab/cd/abcdef....jpg",
  "bytes": 4283749,
  "content_type": "image/jpeg",
  "width": 4928,
  "height": 3264,
  "logical_id": "DAO-12345",
  "etag": "\"9a8b7c6d...\""
}
```

## Docker (client/demo)
You do **not** bake images into the container. This image only contains the client tool.

```bash
# Build
docker build -t dataset-client .

# Run demo (needs env for S3 + manifest access, and a cache volume)
docker run --rm -it \
  --env-file .env \
  -v /tmp/imgcache:/tmp/imgcache \
  dataset-client \
  python -m dataset_tool.scripts.random_fetch --n 3
```

## Notes
- Width/height require Pillow; if not installed, they are omitted.
- Set `DATASET_LOGICAL_MAP` to a CSV mapping from filename → logical_id, if needed.

## Security
Use IAM roles in cloud; for local/dev, use presigned URLs or scoped access keys.
Bucket should allow `GetObject` to runner roles and restrict `PutObject` to uploader roles.

## License
MIT
