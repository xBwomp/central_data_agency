#!/usr/bin/env python3
"""
Ingest RDT&E program elements from the OSD Comptroller R-1 (FY 2025).

Source PDF: https://comptroller.defense.gov/Portals/45/Documents/defbudget/fy2025/fy2025_r1.pdf
            (download manually — comptroller.defense.gov blocks automated requests)
Usage:
    python3 scripts/ingest/r1_programs.py /home/jeff/FY2025_r1.pdf
    python3 scripts/build_api.py   # validate + build JSON
"""

import re
import sys
import pathlib
import pdfplumber

OUT_FILE = pathlib.Path("data/rdte_programs.yml")
SOURCE_URL = "https://comptroller.defense.gov/Portals/45/Documents/defbudget/fy2025/fy2025_r1.pdf"

# Regex for a program-element data line:
#   <line_no>  <PE_number>  <program name...>  <act>  <U|C>  [dollar amounts]
# PE numbers are 7 digits + 1+ uppercase letter suffix
PE_LINE_RE = re.compile(
    r"^\d+\s+"                    # line number
    r"(\d{7}[A-Z]+)\s+"           # PE number (group 1)
    r"(.+?)\s+"                   # program name (group 2, non-greedy)
    r"(\d{2})\s+"                 # budget activity (group 3)
    r"([UC])\s*"                  # classification (group 4)
    r"[\d,\s]*$"                  # dollar amounts (ignored)
)

# Map PE-number suffix → component tag
SUFFIX_COMPONENT = {
    "A":  ("army",        "Department of the Army"),
    "N":  ("navy",        "Department of the Navy"),
    "M":  ("marine-corps","United States Marine Corps"),
    "F":  ("air-force",   "Department of the Air Force"),
    "R":  ("air-force",   "Air Force Reserve"),
    "H":  ("air-force",   "Air National Guard"),
    "S":  ("space-force", "United States Space Force"),
    "D":  ("defense-wide","Defense-Wide"),
    "O":  ("ote",         "Operational Test and Evaluation"),
    "E":  ("defense-wide","Defense-Wide"),
    "G":  ("defense-wide","Defense-Wide"),
    "K":  ("defense-wide","Defense-Wide"),
    "L":  ("defense-wide","Defense-Wide"),
    "C":  ("defense-wide","Defense-Wide"),
    "I":  ("defense-wide","Defense-Wide"),
}

BUDGET_ACTIVITY = {
    "01": "basic-research",
    "02": "applied-research",
    "03": "advanced-technology-development",
    "04": "advanced-component-development",
    "05": "system-development-and-demonstration",
    "06": "management-support",
    "07": "operational-systems-development",
    "08": "software-and-digital-technology",
}


def component_from_pe(pe: str) -> tuple[str, str]:
    """Return (tag, label) from the letter suffix(es) of a PE number."""
    suffix = re.sub(r"^\d+", "", pe)          # e.g. "0601102A" → "A"
    # Use first letter for lookup; multi-letter suffixes are rare variants
    key = suffix[0] if suffix else "D"
    return SUFFIX_COMPONENT.get(key, ("defense-wide", "Defense-Wide"))


def extract_acronym(name: str) -> str | None:
    """Pull the last parenthesized acronym from a program name, if any."""
    m = re.search(r"\(([A-Z][A-Z0-9\-]{1,})\)$", name.strip())
    return m.group(1) if m else None


def yaml_str(s: str) -> str:
    """Quote a YAML string if it contains special characters."""
    specials = set(':,#[]{}*&?|-<>=!%@`\'"')
    if any(c in s for c in specials):
        escaped = s.replace('"', '\\"')
        return f'"{escaped}"'
    return s


def to_yaml_entry(pe: str, name: str, act: str, classification: str) -> str:
    comp_tag, _comp_label = component_from_pe(pe)
    ba_tag = BUDGET_ACTIVITY.get(act, f"ba{act}")

    tags = ["rdte", "program-element", comp_tag, ba_tag]
    if classification == "C":
        tags.append("classified")

    variants = [pe]                         # PE number is always a variant
    acronym = extract_acronym(name)
    if acronym and acronym != pe:
        variants.append(acronym)

    lines = [f"- official: {yaml_str(name)}"]
    if acronym and acronym != pe:
        lines.append(f"  abbreviation: {yaml_str(acronym)}")
    lines.append(f"  source: {yaml_str(SOURCE_URL)}")
    lines.append(f"  tags:")
    for tag in tags:
        lines.append(f"    - {tag}")
    lines.append(f"  variants:")
    for v in variants:
        lines.append(f"    - {yaml_str(v)}")
    return "\n".join(lines)


def parse_pdf(pdf_path: str) -> list[dict]:
    programs: list[dict] = []
    seen_pes: set[str] = set()

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for line in text.splitlines():
                m = PE_LINE_RE.match(line.strip())
                if not m:
                    continue
                pe, name, act, classification = (
                    m.group(1), m.group(2).strip(), m.group(3), m.group(4)
                )
                # Skip classified placeholder lines (PE 999999999 etc.)
                if re.match(r"^9+$", pe.rstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZ")):
                    continue
                # Deduplicate (same PE can appear on summary + detail pages)
                if pe in seen_pes:
                    continue
                seen_pes.add(pe)
                programs.append({
                    "pe": pe,
                    "name": name,
                    "act": act,
                    "classification": classification,
                })

    return programs


def main() -> None:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <path/to/FY2025_r1.pdf>", file=sys.stderr)
        sys.exit(1)

    pdf_path = sys.argv[1]
    print(f"Parsing {pdf_path} ...")
    programs = parse_pdf(pdf_path)
    print(f"  {len(programs)} unique program elements found")

    # Sort: component suffix, then PE number
    programs.sort(key=lambda p: (p["pe"][-1:], p["pe"]))

    blocks = [to_yaml_entry(p["pe"], p["name"], p["act"], p["classification"])
              for p in programs]

    content = "# RDT&E Program Elements (R-1) — FY 2025 President's Budget\n"
    content += f"# Source: {SOURCE_URL}\n"
    content += "# Do not edit manually — re-run scripts/ingest/r1_programs.py to refresh\n\n"
    content += "\n\n".join(blocks) + "\n"

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(content)
    print(f"  wrote {OUT_FILE}  ({len(programs)} entries)")
    print("\nNext: python3 scripts/build_api.py")


if __name__ == "__main__":
    main()
