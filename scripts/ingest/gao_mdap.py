#!/usr/bin/env python3
"""
Ingest weapon programs from the GAO Weapon Systems Annual Assessment.

Source PDF: https://www.gao.gov/products/gao-25-107569
            (download manually — GAO blocks automated requests)

Usage:
    python3 scripts/ingest/gao_mdap.py sources/gao-25-107569.pdf
    python3 scripts/build_api.py   # validate + build JSON
"""

import re
import sys
import pathlib
import pdfplumber

OUT_FILE = pathlib.Path("data/mdap_programs.yml")
SOURCE_URL = "https://www.gao.gov/products/gao-25-107569"

# The TOC lives on pages 4-6 of this report (1-indexed); 3-5 zero-indexed.
# Scan one extra page to be safe.
TOC_PAGES = range(3, 6)

# Real program page numbers in this report all start at 65 (first MDAP).
# TOC entries for sections (Letter, Background, etc.) have small page numbers.
# Increment numbers in names (e.g. "Increment 3") also produce small matches.
# Treating any trailing number < 60 as "part of the name, not a page ref"
# keeps multi-word names intact and filters section noise.
MIN_PROGRAM_PAGE = 60

# Service section header keywords → (tag, abbreviation ref into military_services)
SERVICE_HEADERS = {
    "air force":   ("air-force",   "USAF"),
    "army":        ("army",        "USA"),
    "navy":        ("navy",        "USN"),
    "marine":      ("marine-corps","USMC"),
    "space force": ("space-force", "USSF"),
}

# TOC lines that are report-structure entries, not program names
SKIP_RE = re.compile(
    r"^(letter|background|dod plans|programs are|programs could|"
    r"conclusions|recommendations|agency comments|appendix|"
    r"related gao|contents|page [ivxlcdm]+|tables|figures|abbreviations|"
    r"speed$|cycles$|acquisitions$|development$|guide$|phases$|"
    r"assessments$)",
    re.IGNORECASE,
)

ENDS_WITH_NUM = re.compile(r"^(.+?)\s+(\d+)\s*$")


def detect_service(text: str) -> tuple[str, str | None] | None:
    lower = text.lower()
    if "assessment" not in lower:
        return None
    for key, val in SERVICE_HEADERS.items():
        if key in lower:
            return val
    return None


def yaml_str(s: str) -> str:
    if any(c in s for c in ':,#[]{}*&?|-<>=!%@`\'"'):
        return f'"{s.replace(chr(34), chr(92)+chr(34))}"'
    return s


def to_yaml_entry(name: str, acronym: str | None,
                  svc_tag: str, svc_abbr: str | None,
                  program_type: str) -> str:
    tags = [program_type, svc_tag]
    variants: list[str] = []
    if acronym:
        variants.append(acronym)
    variants.append(name)

    lines = [f"- official: {yaml_str(name)}"]
    if acronym:
        lines.append(f"  abbreviation: {yaml_str(acronym)}")
    lines.append(f"  source: {yaml_str(SOURCE_URL)}")
    lines.append(f"  tags:")
    for tag in tags:
        lines.append(f"    - {tag}")
    if svc_abbr:
        lines.append(f"  related:")
        lines.append(f"    - ref: {svc_abbr}")
        lines.append(f"      type: operator")
    lines.append(f"  variants:")
    for v in variants:
        lines.append(f"    - {yaml_str(v)}")
    return "\n".join(lines)


def parse_toc(pdf) -> list[dict]:
    """
    Parse the Table of Contents to extract all program names and their service.

    TOC line patterns:
      Normal:     "B-52 Commercial Engine Replacement Program (B-52 CERP) 65"
      No acronym: "F-15EX 72"
      Wraps mid-name:
                  "F-15 Eagle Passive Active Warning Survivability System (F-15"
                  "EPAWSS) 71"
      Wraps before acronym:
                  "Advanced Anti-Radiation Guided Missile—Extended Range"
                  "(AARGM-ER) 117"
      Name ends with increment number (looks like small page ref):
                  "Maneuver Short Range Air Defense Increment 3"
                  "(M-SHORAD Inc 3) 107"
    """
    programs: list[dict] = []
    seen: set[str] = set()
    svc_tag, svc_abbr = "defense-wide", None
    prog_type = "mdap"
    pending = ""   # accumulates lines of a multi-line program name

    for pi in TOC_PAGES:
        page = pdf.pages[pi]
        text = page.extract_text() or ""

        for raw in text.splitlines():
            line = raw.strip()
            if not line:
                continue

            # Service section headers contain both a service keyword and "assessment"
            svc = detect_service(line)
            if svc:
                svc_tag, svc_abbr = svc
                prog_type = "mdap"
                pending = ""
                continue

            # Program-type subsections
            if re.search(r"middle tier|mta program", line, re.IGNORECASE):
                prog_type = "mta"
                pending = ""
                continue
            if re.search(r"future major weapon", line, re.IGNORECASE):
                prog_type = "future"
                pending = ""
                continue

            m = ENDS_WITH_NUM.match(line)

            # --- Line does NOT end with a number ---
            if not m:
                if SKIP_RE.match(line) or len(line) < 4:
                    pending = ""
                else:
                    # First half of a wrapped name
                    pending = (pending + " " + line).strip() if pending else line
                continue

            candidate = m.group(1).strip()
            page_num = int(m.group(2))

            # Skip known section/metadata lines
            if SKIP_RE.match(candidate):
                pending = ""
                continue

            # Skip service header lines (already handled above via detect_service(line))
            if detect_service(candidate):
                pending = ""
                continue

            # --- Trailing number is too small to be a real program page ---
            # Treat it as part of the name (e.g. "Increment 3", year fragments)
            if page_num < MIN_PROGRAM_PAGE:
                if not SKIP_RE.match(candidate) and len(candidate) > 3:
                    # Preserve the full original line content as pending
                    pending = (pending + " " + line).strip() if pending else line
                else:
                    pending = ""
                continue

            # --- Real program entry (page_num >= 60) ---
            # Combine with any pending prefix
            if pending:
                full = (pending + " " + candidate).strip()
                pending = ""
            else:
                full = candidate

            if len(full) < 4 or re.match(r"^\d", full):
                continue

            # Extract trailing parenthesized acronym
            acronym = None
            am = re.search(r"\(([A-Z0-9][A-Z0-9\-/ ]{1,})\)\s*$", full)
            if am:
                acronym = am.group(1).strip()

            key = full.lower()
            if key not in seen:
                seen.add(key)
                programs.append({
                    "name": full,
                    "acronym": acronym,
                    "svc_tag": svc_tag,
                    "svc_abbr": svc_abbr,
                    "type": prog_type,
                })

    return programs


def main() -> None:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <path/to/gao-25-107569.pdf>", file=sys.stderr)
        sys.exit(1)

    pdf_path = sys.argv[1]
    print(f"Parsing {pdf_path} ...")

    with pdfplumber.open(pdf_path) as pdf:
        print(f"  PDF has {len(pdf.pages)} pages — parsing table of contents ...")
        programs = parse_toc(pdf)

    print(f"  {len(programs)} programs extracted")

    if not programs:
        print("ERROR: No programs found. Inspect TOC pages manually.", file=sys.stderr)
        sys.exit(1)

    from collections import Counter
    print(f"  By type:    { dict(Counter(p['type'] for p in programs)) }")
    print(f"  By service: { dict(Counter(p['svc_tag'] for p in programs)) }")
    print()
    for p in programs:
        abbr = f" ({p['acronym']})" if p['acronym'] else ""
        print(f"  [{p['svc_tag']:12s}] {p['name'][:70]}{abbr}")

    answer = input("\nLook correct? Write to data/mdap_programs.yml? [y/N] ").strip().lower()
    if answer != "y":
        print("Aborted.")
        sys.exit(0)

    blocks = [
        to_yaml_entry(p["name"], p["acronym"], p["svc_tag"], p["svc_abbr"], p["type"])
        for p in programs
    ]

    content  = "# GAO Weapon Systems Annual Assessment — FY 2025 (GAO-25-107569)\n"
    content += f"# Source: {SOURCE_URL}\n"
    content += "# Do not edit manually — re-run scripts/ingest/gao_mdap.py to refresh\n\n"
    content += "\n\n".join(blocks) + "\n"

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(content)
    print(f"  wrote {OUT_FILE}  ({len(programs)} entries)")
    print("\nNext: python3 scripts/build_api.py")


if __name__ == "__main__":
    main()
