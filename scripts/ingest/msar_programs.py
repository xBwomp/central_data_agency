#!/usr/bin/env python3
"""
Ingest MDAP program data from Modernized Selected Acquisition Reports (MSARs).

Source: https://www.esd.whs.mil/Records-Declass/FOIA/Reading-Room/Reading-Room-List_2/Selected_Acquisition_Reports/FY_2023_SARS/
Usage:
    python3 scripts/ingest/msar_programs.py sources/msars/
    python3 scripts/build_api.py
"""

import re
import sys
import pathlib
import pdfplumber

OUT_FILE = pathlib.Path("data/msar_programs.yml")
SOURCE_BASE = "https://www.esd.whs.mil/Portals/54/Documents/FOID/Reading%20Room/Selected_Acquisition_Reports/FY_2023_SARS/"

COMPONENT_TAGS = {
    "department of the army":       "army",
    "army":                         "army",
    "department of the navy":       "navy",
    "navy":                         "navy",
    "department of the air force":  "air-force",
    "air force":                    "air-force",
    "united states space force":    "space-force",
    "space force":                  "space-force",
    "united states marine corps":   "marine-corps",
    "marine corps":                 "marine-corps",
    "defense acquisition executive":"defense-wide",
    "defense-wide":                 "defense-wide",
    "missile defense agency":       "defense-wide",
}


def component_tag(text: str) -> str:
    t = text.lower().strip()
    for k, v in COMPONENT_TAGS.items():
        if k in t:
            return v
    return "defense-wide"


SPLIT_X = 290  # x-coordinate boundary between Full Name and Short Name columns


def parse_msar(pdf_path: pathlib.Path) -> dict | None:
    """Extract program metadata from an MSAR PDF using word-position column splitting."""
    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            desc_page = None
            for page in pdf.pages[3:12]:
                t = page.extract_text() or ""
                if "Full Name" in t and "Short Name" in t:
                    desc_page = page
                    break

            if desc_page is None:
                print(f"  WARN: no Program Description page in {pdf_path.name}")
                return None

            words = desc_page.extract_words()

            # Find row index of "Full Name" / "Short Name" header
            header_idx = next(
                (i for i, w in enumerate(words) if w["text"] == "Full" and
                 i + 1 < len(words) and words[i + 1]["text"] == "Name"),
                None
            )
            if header_idx is None:
                return None

            # Collect words after the header, split by column, until we hit
            # "Lead Component" or "Milestone" (next table section)
            full_words = []
            short_words = []
            # Stop at left-column row labels that indicate the next table section
            STOP_WORDS = {"Lead", "Supporting", "Adaptive"}

            for w in words[header_idx + 4:]:  # skip "Full" "Name" "Short" "Name"
                if w["text"] in STOP_WORDS and w["x0"] < SPLIT_X:
                    break
                # Also stop on PNO (programme number) which only appears in left col
                if w["text"] == "PNO" and w["x0"] < SPLIT_X:
                    break
                if w["x0"] < SPLIT_X:
                    full_words.append(w["text"])
                else:
                    short_words.append(w["text"])

            full_name = " ".join(full_words).strip()
            short_name = " ".join(short_words).strip()

            # Remove trailing noise from short_name (e.g. "Milestone Decision Authority")
            short_name = re.sub(r"\s*(Milestone|Decision|Authority|Component|Executive"
                                r"|Defense|Acquisition|PNO|Program)\b.*", "",
                                short_name, flags=re.IGNORECASE).strip()

            if not full_name:
                return None

            # Lead Component — first left-column word(s) after "Lead Component" header
            text = desc_page.extract_text() or ""
            comp_m = re.search(r"Lead Component\s*\n(.+?)\n", text)
            lead_component = comp_m.group(1).strip() if comp_m else ""

            # PEO — right column after "Program Executive Office"
            peo_words = []
            in_peo = False
            for w in words:
                if w["text"] == "Office" and peo_words == []:
                    in_peo = True
                    continue
                if in_peo and w["x0"] >= SPLIT_X:
                    if w["text"] in ("Lead", "Supporting", "Joint", "Adaptive"):
                        break
                    peo_words.append(w["text"])
                    if len(peo_words) >= 8:
                        break
            peo = " ".join(peo_words).strip()

            # Mission text
            mission = ""
            mission_m = re.search(
                r"\bMission\b\s*\n(.+?)(?:\nProgram Description|\Z)",
                text, re.DOTALL
            )
            if mission_m:
                mission = re.sub(r"\s+", " ", mission_m.group(1)).strip()[:400]

            return {
                "full_name": full_name,
                "short_name": short_name,
                "lead_component": lead_component,
                "peo": peo,
                "mission": mission,
                "source_file": pdf_path.name,
            }
    except Exception as e:
        print(f"  ERROR parsing {pdf_path.name}: {e}")
        return None


def yaml_str(s: str) -> str:
    specials = set(':,#[]{}*&?|-<>=!%@`\'"')
    if any(c in s for c in specials) or s.startswith(" "):
        escaped = s.replace('"', '\\"')
        return f'"{escaped}"'
    return s or '""'


def to_yaml_entry(p: dict) -> str:
    comp = component_tag(p["lead_component"])
    tags = ["msar", "mdap", comp]

    variants = []
    if p["short_name"] and p["short_name"] != p["full_name"]:
        variants.append(p["short_name"])
    variants.append(p["full_name"])

    source_url = SOURCE_BASE + p["source_file"].replace(" ", "%20")

    lines = [f"- official: {yaml_str(p['full_name'])}"]
    if p["short_name"] and p["short_name"] != p["full_name"]:
        lines.append(f"  abbreviation: {yaml_str(p['short_name'])}")
    if p["mission"]:
        lines.append(f"  description: {yaml_str(p['mission'])}")
    lines.append(f"  source: {yaml_str(source_url)}")
    if p["lead_component"]:
        lines.append(f"  # lead component: {p['lead_component']}")
    if p["peo"]:
        lines.append(f"  # peo: {p['peo']}")
    lines.append(f"  tags:")
    for tag in tags:
        lines.append(f"    - {tag}")
    lines.append(f"  variants:")
    for v in variants:
        lines.append(f"    - {yaml_str(v)}")
    return "\n".join(lines)


def main() -> None:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <sources/msars/>", file=sys.stderr)
        sys.exit(1)

    msar_dir = pathlib.Path(sys.argv[1])
    pdfs = sorted(msar_dir.glob("*.pdf"))
    print(f"Found {len(pdfs)} PDFs in {msar_dir}")

    programs = []
    for pdf_path in pdfs:
        print(f"  parsing {pdf_path.name} ...", end=" ", flush=True)
        result = parse_msar(pdf_path)
        if result:
            programs.append(result)
            print(f"→ {result['short_name'] or result['full_name'][:40]}")
        else:
            print("→ SKIPPED")

    programs.sort(key=lambda p: p["full_name"])
    print(f"\n{len(programs)} programs parsed successfully")

    blocks = [to_yaml_entry(p) for p in programs]
    content = "# MDAP Programs from Modernized Selected Acquisition Reports (MSARs) — FY 2023\n"
    content += f"# Source: https://www.esd.whs.mil/Records-Declass/FOIA/Reading-Room/Reading-Room-List_2/Selected_Acquisition_Reports/FY_2023_SARS/\n"
    content += "# Do not edit manually — re-run scripts/ingest/msar_programs.py to refresh\n\n"
    content += "\n\n".join(blocks) + "\n"

    OUT_FILE.write_text(content)
    print(f"wrote {OUT_FILE}")
    print("\nNext: python3 scripts/build_api.py")


if __name__ == "__main__":
    main()
