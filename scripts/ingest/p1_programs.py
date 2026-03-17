#!/usr/bin/env python3
"""
Ingest procurement line items from the OSD Comptroller P-1 (FY 2025).

Source PDF: https://comptroller.defense.gov/Portals/45/Documents/defbudget/FY2025/FY2025_p1.pdf
Usage:
    python3 scripts/ingest/p1_programs.py sources/fy2025_p1.pdf
    python3 scripts/build_api.py
"""

import re
import sys
import pathlib
import pdfplumber

OUT_FILE = pathlib.Path("data/procurement_programs.yml")
SOURCE_URL = "https://comptroller.defense.gov/Portals/45/Documents/defbudget/FY2025/FY2025_p1.pdf"

# Appropriation code → (component_tag, category_tag)
APPROPRIATION_MAP = {
    "2031": ("army",        "aircraft"),
    "2032": ("army",        "missiles"),
    "2033": ("army",        "weapons-tracked-vehicles"),
    "2034": ("army",        "ammunition"),
    "2035": ("army",        "other-procurement"),
    "2036": ("army",        "chemical-munitions"),
    "1506": ("navy",        "aircraft"),
    "1507": ("navy",        "weapons"),
    "1611": ("navy",        "shipbuilding"),
    "1810": ("navy",        "other-procurement"),
    "1820": ("marine-corps","procurement"),
    "1109": ("marine-corps","procurement"),
    "3010": ("air-force",   "aircraft"),
    "3020": ("air-force",   "missiles"),
    "3080": ("air-force",   "ammunition"),
    "3300": ("air-force",   "other-procurement"),
    "3031": ("space-force", "procurement"),
    "0300": ("defense-wide","procurement"),
    "0400": ("defense-wide","procurement"),
}

# Ident codes to skip (advance procurement continuations, less/subtraction lines)
SKIP_IDENT = {"C", "L"}

# Line pattern:
# <line_no>  <item_name>  <ident_code>  <sec(U|C)>  [qty cost ...]
# OR without ident code for some lines (treated as continuation or no-code items)
LINE_RE = re.compile(
    r"^(\d+)\s+"          # line number
    r"(.+?)\s+"           # item name
    r"([A-Z])\s+"         # ident code
    r"([UC])\s*"          # security classification
    r"[\d,\s()\-]*$"      # quantities/costs (ignored)
)


def component_from_approp(code: str) -> tuple[str, str]:
    """Return (component_tag, category_tag) from a 4-digit appropriation code."""
    return APPROPRIATION_MAP.get(code, ("defense-wide", "procurement"))


def extract_acronym(name: str) -> str | None:
    """Pull a parenthesized acronym from a program name."""
    m = re.search(r"\(([A-Z][A-Z0-9\-]{1,})\)$", name.strip())
    return m.group(1) if m else None


def yaml_str(s: str) -> str:
    specials = set(':,#[]{}*&?|-<>=!%@`\'"')
    if any(c in s for c in specials) or s.startswith(" "):
        escaped = s.replace('"', '\\"')
        return f'"{escaped}"'
    return s


def parse_pdf(pdf_path: str) -> list[dict]:
    programs: list[dict] = []
    seen: set[str] = set()
    current_approp_code = ""
    current_component = "defense-wide"
    current_category = "procurement"

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for raw_line in text.splitlines():
                line = raw_line.strip()

                # Detect appropriation header
                approp_m = re.search(r"Appropriation:\s*(\d{4})\s", line)
                if approp_m:
                    current_approp_code = approp_m.group(1)
                    current_component, current_category = component_from_approp(current_approp_code)
                    continue

                m = LINE_RE.match(line)
                if not m:
                    continue

                _line_no, name, ident, classification = (
                    m.group(1), m.group(2).strip(), m.group(3), m.group(4)
                )

                # Skip advance procurement continuation lines and subtraction lines
                if ident in SKIP_IDENT:
                    continue

                # Skip classified placeholder lines and budget-adjustment noise
                if re.match(r"^(Classified|classified)\b", name):
                    continue
                NOISE = ("Adj to Match", "Continuing Resolution", "Undistributed",
                         "Closed Account", "Less:", "Less: Advance")
                if any(name.startswith(n) for n in NOISE):
                    continue

                # Deduplicate by name + appropriation
                key = f"{current_approp_code}:{name.lower()}"
                if key in seen:
                    continue
                seen.add(key)

                programs.append({
                    "name": name,
                    "ident": ident,
                    "classification": classification,
                    "component": current_component,
                    "category": current_category,
                    "approp": current_approp_code,
                })

    return programs


def to_yaml_entry(p: dict) -> str:
    tags = ["procurement", "p1", p["component"], p["category"]]
    if p["classification"] == "C":
        tags.append("classified")

    acronym = extract_acronym(p["name"])
    variants = [p["name"]]
    if acronym:
        variants.append(acronym)

    lines = [f"- official: {yaml_str(p['name'])}"]
    if acronym:
        lines.append(f"  abbreviation: {yaml_str(acronym)}")
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
        print(f"Usage: {sys.argv[0]} <path/to/FY2025_p1.pdf>", file=sys.stderr)
        sys.exit(1)

    pdf_path = sys.argv[1]
    print(f"Parsing {pdf_path} ...")
    programs = parse_pdf(pdf_path)
    print(f"  {len(programs)} unique procurement line items found")

    programs.sort(key=lambda p: (p["component"], p["approp"], p["name"]))

    blocks = [to_yaml_entry(p) for p in programs]
    content = "# Procurement Programs (P-1) — FY 2025 President's Budget\n"
    content += f"# Source: {SOURCE_URL}\n"
    content += "# Do not edit manually — re-run scripts/ingest/p1_programs.py to refresh\n\n"
    content += "\n\n".join(blocks) + "\n"

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(content)
    print(f"  wrote {OUT_FILE}  ({len(programs)} entries)")
    print("\nNext: python3 scripts/build_api.py")


if __name__ == "__main__":
    main()
