# Use bash for stricter error handling
set shell := ["bash", "-uc"]

# ---- Project knobs (edit if you renamed things) ----
# Distribution name from [project].name in pyproject.toml
PKG_DIST := "s3-image-dataset-kit"
# Import/package name = folder under src/
PKG_IMPORT := "dataset_tool"

# ---- Plumbing ----

# 1) Lockfile-driven dependency sync (no code install)
sync:
    # Keep env deterministic & fast
    uv sync

# 2) Editable-install your own package so src/ is importable
install:
    # (Re)install your package in editable mode
    uv pip install -e .

# 3) Force a clean reinstall (after changing pyproject metadata/entry points)
reinstall:
    uv pip uninstall {{PKG_DIST}} || true
    uv pip install -e . --force-reinstall

# 4) Smoke test: confirm both the import and the distribution are visible
check:
    uv run python -c 'from importlib import metadata as m; import {{PKG_IMPORT}} as mod; print("import ok:", mod.__name__); print("dist ok:", m.version("{{PKG_DIST}}"))'

# Meta recipe to do both: lockfile deps + editable install + quick check
dev:
    just sync
    just install
    just check

# ---- Your tasks (now guaranteed to see {{PKG_IMPORT}}) ----

# Build a manifest from an image directory
# usage: just manifest /abs/or/relative/path
manifest src_dir:
    just dev
    mkdir -p manifests
    uv run python -m {{PKG_IMPORT}}.scripts.build_manifest \
        --src "{{src_dir}}" \
        --out ./manifests/inventory-v1.jsonl

# Validate an existing manifest path
validate manifest_path:
    just dev
    uv run python -m {{PKG_IMPORT}}.scripts.validate_manifest \
        --manifest "{{manifest_path}}"

# Upload using your script (adjust flags to your s3 target)
upload manifest_path bucket:
    just dev
    uv run python -m {{PKG_IMPORT}}.scripts.upload_dataset \
        --manifest "{{manifest_path}}" \
        --bucket "{{bucket}}"

# Clean the env (optional)
clean:
    rm -rf .venv .uv-cache || true
