#!/usr/bin/env python3
"""
Ingest major weapon system programs from the OSD Comptroller
"Program Acquisition Cost by Weapon System" (FY 2025).

Source PDF: https://comptroller.defense.gov/Portals/45/Documents/defbudget/FY2025/FY2025_Weapons.pdf
Usage:
    python3 scripts/ingest/weapons_programs.py sources/fy2025_weapons.pdf
    python3 scripts/build_api.py
"""

import re
import sys
import pathlib
import pdfplumber

OUT_FILE = pathlib.Path("data/weapons_programs.yml")
SOURCE_URL = "https://comptroller.defense.gov/Portals/45/Documents/defbudget/FY2025/FY2025_Weapons.pdf"

PAGE_HEADER = "FY 2025 Program Acquisition Costs by Weapon System"

# Map summary-table section header → tag
CATEGORY_TAGS = {
    "Aircraft and Related Systems":          "aviation",
    "C4I Systems":                           "c4i",
    "Ground Systems":                        "ground",
    "Missile Defense Programs":              "missile-defense",
    "Missiles and Munitions":               "missiles-munitions",
    "Shipbuilding and Maritime Systems":     "shipbuilding",
    "Space Based Systems":                   "space",
    "Science and Technology":               "science-technology",
    "Mission Support Activities":           "mission-support",
}

# Map service qualifier in summary header → tag
SERVICE_TAGS = {
    "Joint Service":         "joint",
    "US Army":               "army",
    "USA":                   "army",
    "US Navy":               "navy",
    "USN":                   "navy",
    "US Marine Corps":       "marine-corps",
    "USMC":                  "marine-corps",
    "USN / US Marine Corps": "navy",
    "US Air Force":          "air-force",
    "USAF":                  "air-force",
    "USSF":                  "space-force",
}


def parse_summary_table(pdf) -> list[dict]:
    """
    Parse pages 17-18 (index 16-17) of the summary table.
    Returns list of {abbrev, name, category, service, page_ref}.
    """
    programs = []
    current_category = ""
    current_service = ""

    for page_idx in [16, 17]:
        text = pdf.pages[page_idx].extract_text() or ""
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("Major Weapon") or line.startswith("($"):
                continue
            if line.startswith("*"):
                continue

            # Detect category/service section headers like:
            # "Aircraft and Related Systems – Joint Service"
            if " – " in line and not re.search(r"\d", line):
                parts = line.split(" – ", 1)
                current_category = parts[0].strip()
                current_service = parts[1].strip() if len(parts) > 1 else ""
                continue

            # Strip the page reference at the end (e.g. "1-2")
            page_ref_m = re.search(r"\b(\d+-\d+)\s*$", line)
            if not page_ref_m:
                continue
            page_ref = page_ref_m.group(1)
            line = line[:page_ref_m.start()].strip()

            # Strip trailing dollar amounts (digits, commas, spaces, periods)
            # PDF extraction mangles multi-digit numbers with spaces
            line = re.sub(r"[\d,\.\s]+$", "", line).strip()
            if not line:
                continue

            # Split abbreviation from full name.
            # Abbreviations are: all-caps, digits, hyphens, slashes, parens, &, spaces between
            # e.g. "CVN 78", "SSBN 826", "SDB I", "NSSL & RSLP", "PAC-3 / MSE"
            # Full name starts at the first word that is NOT pure abbrev-style
            # Heuristic: first word that has a lowercase letter = start of name
            words = line.split()
            split_idx = len(words)  # default: all words are the abbreviation
            for i, w in enumerate(words):
                # a word with any lowercase letter marks the start of the full name
                if re.search(r"[a-z]", w) and not re.match(r"^v?\d", w):
                    split_idx = i
                    break

            if split_idx == 0:
                # Entire line is the name (e.g. a program with no distinct abbrev)
                abbrev = ""
                name = line
            else:
                abbrev = " ".join(words[:split_idx])
                name = " ".join(words[split_idx:])

            if not name:
                name = abbrev
                abbrev = ""

            # Derive category tag
            cat_tag = ""
            for k, v in CATEGORY_TAGS.items():
                if k.lower() in current_category.lower():
                    cat_tag = v
                    break

            # Derive service tag
            svc_tag = ""
            for k, v in SERVICE_TAGS.items():
                if k.lower() in current_service.lower():
                    svc_tag = v
                    break

            # official = full combined name (e.g. "F-35 Joint Strike Fighter")
            full_name = f"{abbrev} {name}".strip() if abbrev else name

            programs.append({
                "abbrev": abbrev,
                "name": full_name,
                "short_name": name,
                "category": cat_tag,
                "service": svc_tag,
                "page_ref": page_ref,
                "description": "",
                "prime_contractor": "",
            })

    return programs


def parse_program_pages(pdf, programs: list[dict]) -> None:
    """
    For each individual program page (starting at page 20 / index 19),
    extract Mission: text and Prime Contractor(s): text.
    Match to summary entries by page_ref footer.
    """
    # Build lookup by page_ref
    by_page_ref = {p["page_ref"]: p for p in programs}

    for page in pdf.pages[18:]:  # program pages start at index 18
        text = page.extract_text() or ""
        lines = [l.strip() for l in text.splitlines() if l.strip()]

        # Find page_ref in last few lines (format "1-2")
        page_ref = None
        for line in reversed(lines[-5:]):
            m = re.match(r"^(\d+-\d+)$", line)
            if m:
                page_ref = m.group(1)
                break
        if not page_ref or page_ref not in by_page_ref:
            continue

        entry = by_page_ref[page_ref]

        # Extract Mission: sentence
        full_text = " ".join(lines)
        mission_m = re.search(r"Mission:\s*(.+?)(?:FY \d{4} Program:|Prime Contractor|$)",
                               full_text, re.DOTALL)
        if mission_m:
            mission = re.sub(r"\s+", " ", mission_m.group(1)).strip().rstrip(".")
            entry["description"] = mission[:300]  # cap at ~300 chars

        # Extract Prime Contractor(s):
        pc_m = re.search(r"Prime Contractor\(s\):\s*(.+?)(?:FY \d{4}|$)", full_text, re.DOTALL)
        if pc_m:
            pc = re.sub(r"\s+", " ", pc_m.group(1)).strip()
            entry["prime_contractor"] = pc[:200]


def yaml_str(s: str) -> str:
    specials = set(':,#[]{}*&?|-<>=!%@`\'"')
    if any(c in s for c in specials) or s.startswith(" "):
        escaped = s.replace('"', '\\"')
        return f'"{escaped}"'
    return s


def to_yaml_entry(p: dict) -> str:
    tags = ["weapons-program"]
    if p["category"]:
        tags.append(p["category"])
    if p["service"]:
        tags.append(p["service"])

    variants = []
    if p["abbrev"]:
        variants.append(p["abbrev"])
    if p["short_name"] and p["short_name"] != p["name"]:
        variants.append(p["short_name"])
    if not variants:
        variants.append(p["name"])

    lines = [f"- official: {yaml_str(p['name'])}"]
    if p["abbrev"]:
        lines.append(f"  abbreviation: {yaml_str(p['abbrev'])}")
    if p["description"]:
        lines.append(f"  description: {yaml_str(p['description'])}")
    lines.append(f"  source: {yaml_str(SOURCE_URL)}")
    lines.append(f"  tags:")
    for tag in tags:
        lines.append(f"    - {tag}")
    lines.append(f"  variants:")
    for v in variants:
        lines.append(f"    - {yaml_str(v)}")
    return "\n".join(lines)


def main() -> None:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <path/to/FY2025_Weapons.pdf>", file=sys.stderr)
        sys.exit(1)

    pdf_path = sys.argv[1]
    print(f"Parsing {pdf_path} ...")
    with pdfplumber.open(pdf_path) as pdf:
        programs = parse_summary_table(pdf)
        print(f"  {len(programs)} programs found in summary table")
        parse_program_pages(pdf, programs)

    with_desc = sum(1 for p in programs if p["description"])
    print(f"  {with_desc} programs have descriptions")

    blocks = [to_yaml_entry(p) for p in programs]
    content = "# Major Weapon System Programs — FY 2025 President's Budget\n"
    content += f"# Source: {SOURCE_URL}\n"
    content += "# Do not edit manually — re-run scripts/ingest/weapons_programs.py to refresh\n\n"
    content += "\n\n".join(blocks) + "\n"

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(content)
    print(f"  wrote {OUT_FILE}  ({len(programs)} entries)")
    print("\nNext: python3 scripts/build_api.py")


if __name__ == "__main__":
    main()
