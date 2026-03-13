#!/usr/bin/env python3
"""
Build script: data/*.yml → dist/api/*.json + dist/api/index.json

Validates schema on every entry:
  - `official`  must be a non-empty string
  - `variants`  must be a list with at least one entry

Exits with code 1 and prints errors if validation fails.
Run: python3 scripts/build_api.py
"""

import json
import pathlib
import sys
import yaml

DATA_DIR = pathlib.Path("data")
DIST_DIR = pathlib.Path("dist/api")


def label_from_name(name: str) -> str:
    return name.replace("_", " ").title()


def validate(entry: dict, collection: str, idx: int) -> list[str]:
    errors = []
    prefix = f"{collection}[{idx}]"
    official = entry.get("official")
    if not official or not str(official).strip():
        errors.append(f"{prefix}: 'official' is required and must be a non-empty string")
    variants = entry.get("variants")
    if not isinstance(variants, list) or len(variants) == 0:
        errors.append(f"{prefix}: 'variants' must be a list with at least one entry")
    return errors


def main() -> int:
    yml_files = sorted(DATA_DIR.glob("*.yml"))
    if not yml_files:
        print(f"No .yml files found in {DATA_DIR}/", file=sys.stderr)
        return 1

    DIST_DIR.mkdir(parents=True, exist_ok=True)

    all_errors: list[str] = []
    collections: list[dict] = []

    for yml_path in yml_files:
        collection_name = yml_path.stem

        with yml_path.open() as f:
            data = yaml.safe_load(f)

        if data is None:
            data = []

        if not isinstance(data, list):
            all_errors.append(f"{yml_path}: expected a YAML list at top level")
            continue

        file_errors: list[str] = []
        for idx, entry in enumerate(data):
            if not isinstance(entry, dict):
                file_errors.append(f"{collection_name}[{idx}]: entry must be a mapping")
                continue
            file_errors.extend(validate(entry, collection_name, idx))

        if file_errors:
            all_errors.extend(file_errors)
            continue

        out_path = DIST_DIR / f"{collection_name}.json"
        out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        print(f"  wrote {out_path}  ({len(data)} entries)")

        collections.append({
            "name": collection_name,
            "label": label_from_name(collection_name),
            "count": len(data),
            "path": f"{collection_name}.json",
        })

    if all_errors:
        print("\nSchema validation errors:", file=sys.stderr)
        for err in all_errors:
            print(f"  ✗ {err}", file=sys.stderr)
        return 1

    index = {"collections": collections}
    index_path = DIST_DIR / "index.json"
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2))
    print(f"  wrote {index_path}  ({len(collections)} collections)")

    print(f"\nBuild complete: {sum(c['count'] for c in collections)} total entries "
          f"across {len(collections)} collection(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
