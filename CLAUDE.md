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
- `tags` — list of lowercase strings for grouping/filtering (optional)
- `variants` — all other acceptable names/spellings/aliases **(required, at least 1)**

### Adding a New Dataset

1. Create `data/<category>.yml` as a YAML list following the schema above.
2. Update `data/README.md` to include the new file in the Files table.
3. Validate: `python3 -c "import yaml; yaml.safe_load(open('data/<category>.yml'))" && echo OK`

See `data/README.md` for a full example entry.

## App Structure

```
app/
  index.html        # Browse UI — fetches JSON API, renders filterable entry list
  browse.js         # Vanilla JS IIFE — all data fetching, search, filter, render logic
  admin/
    index.html      # Decap CMS entry point (CDN-based, no build step)
    config.yml      # CMS schema — one collection per data/*.yml file
scripts/
  build_api.py      # YAML → JSON converter + schema validator
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

## Decap CMS Setup (one-time)

Decap CMS requires a GitHub OAuth App + a small OAuth proxy (no persistent server):

1. Register a GitHub OAuth App at <https://github.com/settings/developers>
   - Callback URL: `https://<your-oauth-proxy>/callback`
2. Deploy an OAuth proxy (Netlify, Cloudflare Workers, or Vercel free tier)
   - Recommended: <https://github.com/sveltia/sveltia-cms-auth> (Cloudflare Workers)
3. Update `app/admin/config.yml`:
   - Set `backend.repo` to `<org>/<repo>`
   - Set `backend.base_url` to your deployed proxy URL

CMS saves can be direct commits to `main` (default) or PRs — set `publish_mode: editorial_workflow` in `config.yml` for PR-based workflow, which will trigger the existing `claude-code-review.yml` auto-review.

## Adding a New Collection

1. Create `data/<category>.yml` following the entry schema.
2. Update `data/README.md` Files table.
3. Add a matching collection block to `app/admin/config.yml` (copy the template at the bottom of the file).
4. Validate: `python3 scripts/build_api.py`
