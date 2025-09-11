# Just recipes for s3-image-dataset-kit

manifest_file := "./manifests/inventory-v1.jsonl"

setup:
    uv sync

manifest src_dir:
    uv run python -m dataset_tool.scripts.build_manifest --src {{src_dir}} --out {{manifest_file}}

upload src_dir:
    uv run python -m dataset_tool.scripts.upload_dataset --src {{src_dir}} --manifest {{manifest_file}}

validate:
    uv run python -m dataset_tool.scripts.validate_manifest --manifest {{manifest_file}}

random-fetch n:
    uv run python -m dataset_tool.scripts.random_fetch --manifest {{manifest_file}} --n {{n}}
