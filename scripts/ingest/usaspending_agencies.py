#!/usr/bin/env python3
"""
Ingest federal agencies from the USASpending.gov API.

Source: GET https://api.usaspending.gov/api/v2/references/toptier_agencies/
Output: data/federal_agencies.yml

Usage:
    python3 scripts/ingest/usaspending_agencies.py
    python3 scripts/build_api.py   # validate + build JSON
"""

import json
import pathlib
import urllib.request

API_URL = "https://api.usaspending.gov/api/v2/references/toptier_agencies/"
OUT_FILE = pathlib.Path("data/federal_agencies.yml")


def fetch_agencies() -> list[dict]:
    print(f"Fetching {API_URL} ...")
    with urllib.request.urlopen(API_URL) as resp:
        data = json.load(resp)
    return data["results"]


def build_variants(name: str, abbreviation: str | None, slug: str | None) -> list[str]:
    """Generate reasonable name variants from available fields."""
    seen = {name}
    variants = []

    # Slug-derived readable name (e.g. "department-of-defense" → "Department of Defense")
    if slug:
        slug_name = slug.replace("-", " ").title()
        if slug_name not in seen:
            seen.add(slug_name)
            variants.append(slug_name)

    # Abbreviation as a variant if it differs from the name
    if abbreviation and abbreviation not in seen:
        seen.add(abbreviation)
        variants.append(abbreviation)

    # Always include at least the official name itself as a variant
    if not variants:
        variants.append(name)

    return variants


TYPE_KEYWORDS = [
    "department",
    "office",
    "commission",
    "board",
    "council",
    "administration",
    "agency",
    "corporation",
    "foundation",
    "service",
    "bureau",
    "institute",
    "authority",
    "center",
    "court",
]


def agency_type_tag(name: str) -> str | None:
    lower = name.lower()
    for kw in TYPE_KEYWORDS:
        if kw in lower:
            return kw
    return None


def to_yaml_entry(agency: dict) -> str:
    name = agency["agency_name"].strip()
    abbr = (agency.get("abbreviation") or "").strip() or None
    slug = agency.get("agency_slug") or None

    variants = build_variants(name, abbr, slug)
    tags = ["federal-agency"]
    type_tag = agency_type_tag(name)
    if type_tag:
        tags.append(type_tag)

    lines = [f"- official: {yaml_str(name)}"]
    if abbr:
        lines.append(f"  abbreviation: {yaml_str(abbr)}")
    lines.append(f"  source: {yaml_str(API_URL)}")
    lines.append(f"  tags:")
    for tag in tags:
        lines.append(f"    - {tag}")
    lines.append(f"  variants:")
    for v in variants:
        lines.append(f"    - {yaml_str(v)}")

    return "\n".join(lines)


def yaml_str(s: str) -> str:
    """Quote a string for YAML if it contains special characters."""
    if any(c in s for c in (':', '#', '[', ']', '{', '}', ',', '&', '*', '?', '|', '-', '<', '>', '=', '!', '%', '@', '`', '"', "'")):
        escaped = s.replace('"', '\\"')
        return f'"{escaped}"'
    return s


def main() -> None:
    agencies = fetch_agencies()
    print(f"  {len(agencies)} agencies retrieved")

    # Sort by name for stable diffs
    agencies.sort(key=lambda a: a["agency_name"].lower())

    blocks = [to_yaml_entry(a) for a in agencies]
    content = "# Federal agencies — ingested from USASpending.gov\n"
    content += f"# Source: {API_URL}\n"
    content += "# Do not edit manually — re-run scripts/ingest/usaspending_agencies.py to refresh\n\n"
    content += "\n\n".join(blocks) + "\n"

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(content)
    print(f"  wrote {OUT_FILE}  ({len(agencies)} entries)")
    print("\nNext: python3 scripts/build_api.py")


if __name__ == "__main__":
    main()
