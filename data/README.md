# Data Directory

This directory contains YAML files, each representing a named-entity category. Each file is a list of entries following the schema below.

## Entry Schema

| Field | Required | Type | Description |
|---|---|---|---|
| `official` | Yes | string | The canonical full name of the entity |
| `abbreviation` | No | string | The shortest standard acronym or code |
| `description` | No | string | A one-sentence plain-English description |
| `source` | No | string | URL or citation for the official name (e.g. the API, document, or statute it was drawn from) |
| `tags` | No | list of strings | Lowercase labels for grouping and filtering |
| `variants` | Yes (min 1) | list of strings | All other acceptable names, spellings, or aliases (include the abbreviation here if it is used as a name) |

## File Format

Each `.yml` file is a bare YAML list, or an object with an `entries:` key (both are supported by the build script).

## Example Entry

```yaml
- official: US Navy
  abbreviation: USN
  description: The naval warfare service branch of the United States Armed Forces.
  source: https://www.defense.gov/About/Branches-of-the-Military/
  tags:
    - military
    - branch
  variants:
    - United States Navy
    - Navy
    - USN
```

## Adding a New Dataset

1. Create a new `.yml` file in this directory named after the category (e.g., `federal_agencies.yml`).
2. Add a list of entries following the schema above.
3. Every entry must have `official` and at least one entry in `variants`.
4. Validate the file: `python3 -c "import yaml, sys; yaml.safe_load(open('data/<filename>.yml'))" && echo OK`

## Files

| File | Description | Source |
|---|---|---|
| `military_services.yml` | The six branches of the US Military | Title 10 U.S.C. |
| `federal_agencies.yml` | 111 federal top-tier agencies | USASpending.gov API |
