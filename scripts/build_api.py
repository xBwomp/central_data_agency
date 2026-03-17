#!/usr/bin/env python3
"""
Build script: data/*.yml → dist/api/*.json + dist/api/index.json
                         + dist/api/relationships.json

Validates schema on every entry:
  - `official`   must be a non-empty string
  - `variants`   must be a list with at least one entry
  - `related`    if present, must be a list of {ref: str, type: str} mappings
                 where type is one of VALID_RELATIONSHIP_TYPES and ref resolves
                 to a known abbreviation or official name across all collections

Exits with code 1 and prints errors if validation fails.
Run: python3 scripts/build_api.py
"""

import json
import pathlib
import sys
import yaml

DATA_DIR = pathlib.Path("data")
DIST_DIR = pathlib.Path("dist/api")

VALID_RELATIONSHIP_TYPES = {
    "variant",
    "component",
    "upgrade",
    "successor",
    "predecessor",
    "operator",
    "prime-contractor",
    "customer",
    "associated",
}


_COLLECTION_LABELS: dict[str, str] = {
    "mdap_programs":        "MDAP Programs",
    "msar_programs":        "MSAR Programs",
    "rdte_programs":        "RDT&E Programs",
    "om_programs":          "O&M Programs",
    "weapons_programs":     "Weapons Programs",
    "procurement_programs": "Procurement Programs",
    "federal_agencies":     "Federal Agencies",
    "military_services":    "Military Services",
}


def label_from_name(name: str) -> str:
    if name in _COLLECTION_LABELS:
        return _COLLECTION_LABELS[name]
    return name.replace("_", " ").title()


def entry_key(entry: dict) -> str:
    """The canonical lookup key for an entry: abbreviation if present, else official."""
    return entry.get("abbreviation") or entry.get("official", "")


def build_ref_index(all_collections: dict[str, list[dict]]) -> dict[str, str]:
    """
    Build a global lookup: ref string → collection name.
    Indexes both abbreviation and official name for every entry.
    """
    index: dict[str, str] = {}
    for coll_name, entries in all_collections.items():
        for entry in entries:
            if abbr := entry.get("abbreviation"):
                index[abbr] = coll_name
            if official := entry.get("official"):
                index[official] = coll_name
    return index


def validate_entry(entry: dict, collection: str, idx: int) -> list[str]:
    """Validate a single entry's structure (not cross-collection refs)."""
    errors = []
    prefix = f"{collection}[{idx}]"

    official = entry.get("official")
    if not official or not str(official).strip():
        errors.append(f"{prefix}: 'official' is required and must be a non-empty string")

    variants = entry.get("variants")
    if not isinstance(variants, list) or len(variants) == 0:
        errors.append(f"{prefix}: 'variants' must be a list with at least one entry")

    related = entry.get("related")
    if related is not None:
        if not isinstance(related, list):
            errors.append(f"{prefix}: 'related' must be a list")
        else:
            for i, rel in enumerate(related):
                rprefix = f"{prefix}.related[{i}]"
                if not isinstance(rel, dict):
                    errors.append(f"{rprefix}: must be a mapping with 'ref' and 'type'")
                    continue
                if not rel.get("ref"):
                    errors.append(f"{rprefix}: 'ref' is required")
                rel_type = rel.get("type")
                if not rel_type:
                    errors.append(f"{rprefix}: 'type' is required")
                elif rel_type not in VALID_RELATIONSHIP_TYPES:
                    errors.append(
                        f"{rprefix}: unknown type '{rel_type}' "
                        f"(valid: {', '.join(sorted(VALID_RELATIONSHIP_TYPES))})"
                    )

    return errors


def validate_refs(
    all_collections: dict[str, list[dict]],
    ref_index: dict[str, str],
) -> list[str]:
    """Second pass: validate that every related[].ref resolves to a known entry."""
    errors = []
    for coll_name, entries in all_collections.items():
        for idx, entry in enumerate(entries):
            for rel in entry.get("related") or []:
                ref = rel.get("ref", "")
                if ref and ref not in ref_index:
                    errors.append(
                        f"{coll_name}[{idx}] ({entry.get('official', '?')}): "
                        f"related ref '{ref}' does not match any known abbreviation or official name"
                    )
    return errors


def build_relationships(
    all_collections: dict[str, list[dict]],
    ref_index: dict[str, str],
) -> list[dict]:
    """Emit flat edge list for relationships.json."""
    edges = []
    for coll_name, entries in all_collections.items():
        for entry in entries:
            from_key = entry_key(entry)
            for rel in entry.get("related") or []:
                ref = rel.get("ref", "")
                to_coll = ref_index.get(ref, "unknown")
                edges.append({
                    "from": from_key,
                    "from_collection": coll_name,
                    "to": ref,
                    "to_collection": to_coll,
                    "type": rel.get("type"),
                })
    return edges


def main() -> int:
    yml_files = sorted(DATA_DIR.glob("*.yml"))
    if not yml_files:
        print(f"No .yml files found in {DATA_DIR}/", file=sys.stderr)
        return 1

    DIST_DIR.mkdir(parents=True, exist_ok=True)

    all_errors: list[str] = []
    all_collections: dict[str, list[dict]] = {}
    collections_meta: list[dict] = []

    # --- Pass 1: load + per-entry validation ---
    for yml_path in yml_files:
        collection_name = yml_path.stem

        with yml_path.open() as f:
            data = yaml.safe_load(f)

        if data is None:
            data = []

        if isinstance(data, dict) and "entries" in data:
            data = data["entries"]

        if not isinstance(data, list):
            all_errors.append(
                f"{yml_path}: expected a YAML list at top level "
                f"(or an object with an 'entries' list)"
            )
            continue

        file_errors: list[str] = []
        for idx, entry in enumerate(data):
            if not isinstance(entry, dict):
                file_errors.append(f"{collection_name}[{idx}]: entry must be a mapping")
                continue
            file_errors.extend(validate_entry(entry, collection_name, idx))

        if file_errors:
            all_errors.extend(file_errors)
            continue

        all_collections[collection_name] = data

    if all_errors:
        print("\nSchema validation errors:", file=sys.stderr)
        for err in all_errors:
            print(f"  ✗ {err}", file=sys.stderr)
        return 1

    # --- Pass 2: cross-collection ref validation ---
    ref_index = build_ref_index(all_collections)
    ref_errors = validate_refs(all_collections, ref_index)
    if ref_errors:
        print("\nRelationship ref errors:", file=sys.stderr)
        for err in ref_errors:
            print(f"  ✗ {err}", file=sys.stderr)
        return 1

    # --- Write collection JSON files ---
    for collection_name, data in all_collections.items():
        out_path = DIST_DIR / f"{collection_name}.json"
        out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        print(f"  wrote {out_path}  ({len(data)} entries)")
        collections_meta.append({
            "name": collection_name,
            "label": label_from_name(collection_name),
            "count": len(data),
            "path": f"{collection_name}.json",
        })

    # --- Write relationships.json ---
    edges = build_relationships(all_collections, ref_index)
    rel_path = DIST_DIR / "relationships.json"
    rel_path.write_text(json.dumps(edges, ensure_ascii=False, indent=2))
    print(f"  wrote {rel_path}  ({len(edges)} relationships)")

    # --- Write index.json ---
    index = {"collections": collections_meta}
    index_path = DIST_DIR / "index.json"
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2))
    print(f"  wrote {index_path}  ({len(collections_meta)} collections)")

    print(
        f"\nBuild complete: {sum(c['count'] for c in collections_meta)} total entries "
        f"across {len(collections_meta)} collection(s), {len(edges)} relationships."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
