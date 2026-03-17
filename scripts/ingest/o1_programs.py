#!/usr/bin/env python3
"""
Ingest Operation & Maintenance budget activity lines from the OSD Comptroller O-1 (FY 2025).

Source PDF: https://comptroller.defense.gov/Portals/45/Documents/defbudget/FY2025/FY2025_o1.pdf
Usage:
    python3 scripts/ingest/o1_programs.py sources/fy2025_o1.pdf
    python3 scripts/build_api.py
"""

import re
import sys
import pathlib
import pdfplumber

OUT_FILE = pathlib.Path("data/om_programs.yml")
SOURCE_URL = "https://comptroller.defense.gov/Portals/45/Documents/defbudget/FY2025/FY2025_o1.pdf"

# Appropriation code → component tag
APPROP_COMPONENT = {
    "2020": "army",
    "2065": "army",
    "1804": "navy",
    "1806": "navy",
    "1107": "marine-corps",
    "3400": "air-force",
    "3740": "air-force",
    "4930": "defense-wide",
    "0100": "defense-wide",
    "0130": "defense-wide",
    "0160": "defense-wide",
    "0400": "defense-wide",
    "0300": "defense-wide",
}

# Budget activity code → tag
BA_TAGS = {
    "01": "operating-forces",
    "02": "mobilization",
    "03": "training-recruiting",
    "04": "admin-servicewide",
    "05": "support-other-nations",
    "06": "special-operations",
}

# Line pattern: <approp_code> <sub1(3 digits)> <sub2(alphanum)> <name> <U|C> <amounts>
# e.g. "2020A 010 111 Maneuver Units U 5,395,251 ..."
# e.g. "1804N 130 1C1C Combat Communications and Electronic Warfare U 1,718,946 ..."
LINE_RE = re.compile(
    r"^(\d{4}[A-Z])\s+"   # appropriation code (group 1)
    r"(\d{3})\s+"          # sub1 sequence (group 2)
    r"(\w{2,6})\s+"        # sub2 line code (group 3)
    r"(.+?)\s+"            # program name (group 4)
    r"([UC])\s*"           # security classification (group 5)
    r"[\d,\s\-]*$"         # dollar amounts (ignored)
)


def component_from_approp(approp: str) -> str:
    code = approp[:4]
    return APPROP_COMPONENT.get(code, "defense-wide")


def yaml_str(s: str) -> str:
    specials = set(':,#[]{}*&?|-<>=!%@`\'"')
    if any(c in s for c in specials) or s.startswith(" "):
        escaped = s.replace('"', '\\"')
        return f'"{escaped}"'
    return s


def parse_pdf(pdf_path: str) -> list[dict]:
    programs: list[dict] = []
    seen: set[str] = set()
    current_ba = "01"

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for raw_line in text.splitlines():
                line = raw_line.strip()

                # Detect current budget activity
                ba_m = re.search(r"Budget Activity\s+0?(\d+):", line)
                if ba_m:
                    current_ba = ba_m.group(1).zfill(2)
                    continue

                m = LINE_RE.match(line)
                if not m:
                    continue

                approp, _sub1, _sub2, name, classification = (
                    m.group(1), m.group(2), m.group(3), m.group(4).strip(), m.group(5)
                )

                # Skip total/subtotal and budget-adjustment noise
                if re.match(r"^(Total|TOTAL)\b", name):
                    continue
                NOISE = ("Adj to Match", "Continuing Resolution", "Undistributed",
                         "Closed Account")
                if any(name.startswith(n) for n in NOISE):
                    continue

                component = component_from_approp(approp)
                ba_tag = BA_TAGS.get(current_ba, f"ba{current_ba}")

                # Deduplicate by approp + name
                key = f"{approp}:{name.lower()}"
                if key in seen:
                    continue
                seen.add(key)

                programs.append({
                    "name": name,
                    "approp": approp,
                    "component": component,
                    "ba_tag": ba_tag,
                    "classification": classification,
                })

    return programs


def to_yaml_entry(p: dict) -> str:
    tags = ["o-and-m", p["component"], p["ba_tag"]]
    if p["classification"] == "C":
        tags.append("classified")

    lines = [f"- official: {yaml_str(p['name'])}"]
    lines.append(f"  source: {yaml_str(SOURCE_URL)}")
    lines.append(f"  tags:")
    for tag in tags:
        lines.append(f"    - {tag}")
    lines.append(f"  variants:")
    lines.append(f"    - {yaml_str(p['name'])}")
    return "\n".join(lines)


def main() -> None:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <path/to/FY2025_o1.pdf>", file=sys.stderr)
        sys.exit(1)

    pdf_path = sys.argv[1]
    print(f"Parsing {pdf_path} ...")
    programs = parse_pdf(pdf_path)
    print(f"  {len(programs)} unique O&M budget lines found")

    programs.sort(key=lambda p: (p["component"], p["approp"], p["name"]))

    blocks = [to_yaml_entry(p) for p in programs]
    content = "# Operation & Maintenance Programs (O-1) — FY 2025 President's Budget\n"
    content += f"# Source: {SOURCE_URL}\n"
    content += "# Do not edit manually — re-run scripts/ingest/o1_programs.py to refresh\n\n"
    content += "\n\n".join(blocks) + "\n"

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(content)
    print(f"  wrote {OUT_FILE}  ({len(programs)} entries)")
    print("\nNext: python3 scripts/build_api.py")


if __name__ == "__main__":
    main()
