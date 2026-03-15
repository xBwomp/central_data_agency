# Central Data Agency

> **Disclaimer:** This is a private project and is not affiliated with, endorsed by, or representative of any government entity or agency. The name "Central Data Agency" is a descriptive label for this data project only. Impersonating a U.S. government officer or employee is a federal crime under [18 U.S.C. § 912](https://www.law.cornell.edu/uscode/text/18/912).

A named-entity registry for defense and government programs — tracking canonical names, abbreviations, and the many alternate names used across PMOs, PEOs, congressional budgets, GAO reports, and contractor documents.

## What it does

- **Source of truth**: `data/*.yml` — human-readable YAML, version-controlled in Git
- **Browse UI**: filterable, searchable web interface at `https://xbwomp.github.io/central_data_agency/`
- **JSON API**: static endpoints at `https://xbwomp.github.io/central_data_agency/api/`
## Data structure

Each entry in a dataset has:

| Field | Required | Description |
|---|---|---|
| `official` | Yes | Canonical full name |
| `abbreviation` | No | Shortest standard acronym or code |
| `description` | No | One-sentence plain-English description |
| `tags` | No | Lowercase labels for grouping/filtering |
| `variants` | Yes (min 1) | All other names, spellings, and aliases |

See `data/README.md` for a full example and instructions for adding new datasets.

## API

```
GET /api/index.json                   # manifest of all collections
GET /api/<collection>.json            # all entries in a collection
```

Example:
```
GET https://xbwomp.github.io/central_data_agency/api/military_services.json
```

## Local development

**Build the JSON API from YAML:**
```bash
pip install pyyaml
python3 scripts/build_api.py
# → writes dist/api/*.json
```

**Preview the browse UI:**
```bash
cd dist
python3 -m http.server 8000
# open http://localhost:8000
```

## Adding data

Data is maintained as YAML files in `data/`. Edit directly on GitHub or clone the repo:

```bash
git clone https://github.com/xBwomp/central_data_agency
cd central_data_agency
```

Ingestion scripts in `scripts/ingest/` pull from public sources (USASpending.gov, OSD budget exhibits, GAO reports) and normalize to the entry schema.

To add a new dataset manually:
1. Create `data/<category>.yml` following the entry schema
2. Update the Files table in `data/README.md`
3. Validate: `python3 scripts/build_api.py`
4. Commit and push — Pages deploys automatically

## How it deploys

On every push to `main` that touches `data/`, `app/`, or `scripts/build_api.py`, GitHub Actions:
1. Runs `build_api.py` to convert YAML → JSON and validate schema
2. Assembles `dist/` (browse UI + JSON API)
3. Deploys `dist/` to GitHub Pages
