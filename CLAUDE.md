# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## GitHub Actions (Claude Integration)

Two workflows are configured in `.github/workflows/`:

- **`claude.yml`** — Triggers when `@claude` is mentioned in issues, PR comments, or PR reviews. Uses `CLAUDE_CODE_OAUTH_TOKEN` secret.
- **`claude-code-review.yml`** — Automatically reviews every PR (opened, updated, reopened) using the `code-review` plugin.

Both workflows require the `CLAUDE_CODE_OAUTH_TOKEN` secret to be set in the repository settings.

## Data Structure

Named-entity datasets live in the `data/` directory. Each category is a separate `.yml` file containing a list of entries.

### Entry Schema

- `official` — canonical full name **(required)**
- `abbreviation` — shortest standard acronym/code (optional)
- `description` — one-sentence plain-English description (optional)
- `source` — URL or citation for the official name (optional, e.g. API endpoint, statute, document)
- `tags` — list of lowercase strings for grouping/filtering (optional)
- `variants` — all other acceptable names/spellings/aliases **(required, at least 1)**

### Adding a New Dataset

1. Create `data/<category>.yml` as a YAML list following the schema above.
2. Update `data/README.md` to include the new file in the Files table.
3. Validate: `python3 scripts/build_api.py`

See `data/README.md` for a full example entry.

## App Structure

```
app/
  index.html        # Browse UI — fetches JSON API, renders filterable entry list
  browse.js         # Vanilla JS IIFE — all data fetching, search, filter, render logic
scripts/
  build_api.py      # YAML → JSON converter + schema validator
  ingest/           # Data ingestion scripts (web scraping, PDF parsing, API calls)
data/               # Source YAML files — one file per collection
dist/               # gitignored; assembled and deployed by publish.yml
  api/
    index.json      # manifest: { collections: [{name, label, count, path}] }
    <collection>.json
```

## Build & Deploy

Run the build locally:
```bash
pip install pyyaml
python3 scripts/build_api.py
# → writes dist/api/*.json
```

On push to `main`, `.github/workflows/publish.yml` runs the build script and deploys `dist/` to GitHub Pages. The browse UI and JSON API are then live at:
```
https://<org>.github.io/central_data_agency/
https://<org>.github.io/central_data_agency/api/<collection>.json
https://<org>.github.io/central_data_agency/api/index.json
```

## Data Ingestion Workflow

Data is added by running ingestion scripts locally, reviewing the output, and pushing. Scripts live in `scripts/ingest/`. The general pattern:

1. Fetch data from a public source (API, PDF, web page)
2. Normalize to the entry schema (official, abbreviation, description, tags, variants)
3. Write to `data/<collection>.yml`
4. Validate: `python3 scripts/build_api.py`
5. Commit and push — Pages deploys automatically

### Known Sources

- **USASpending.gov API** — federal agencies and sub-agencies with CGAC/SUBTIER codes
- **OSD Comptroller R-1** — RDT&E program elements (PDF, annual)
- **OSD Comptroller P-1** — Procurement programs (PDF, annual)
- **GAO reports** — program assessments and high-risk list

## Adding a New Collection

1. Create `data/<category>.yml` following the entry schema.
2. Update `data/README.md` Files table.
3. Validate: `python3 scripts/build_api.py`
