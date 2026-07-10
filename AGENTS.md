# AGENTS.md

PIM AI translation bridge for Volkanos — distribution `entirius-django-pim-translator`, Django app
`django_pim_translator`. Extracts translatable fields from PIM entities, sends them to the remote
AI toolbox via HTTP, and applies translated text back. Zero Django models — the toolbox is the
single source of truth for jobs, costs, and usage.

**Tech:** Python >=3.11, Django >=5.0, DRF, Pydantic, entirius-django-utils-translator

## Commands

| Command | Meaning |
|---|---|
| `make install` | sync dependencies (uv, incl. extras) |
| `make check` | lint + format-check (ruff) |
| `make fix` | auto-fix lint + format |
| `make test` | test suite (pytest + pytest-django) |

## Conventions

- English only: code, docs, commits, branches, PRs.
- MPL-2.0: every non-trivial source file carries the license header (pre-commit inserts it).
- Toolchain: uv + ruff + hatchling + pytest; all config in `pyproject.toml`; `uv.lock` committed.
- Git flow: `master` (production) + `develop` (integration); changes land via PR; semver tag on `master`.
- Never rename the package / Django app_label `django_pim_translator` — it is a schema contract.
- Migrations are part of the public contract — never edit an already released migration.
- Default: do not commit — git is the user's call.

## Architecture

```
src/django_pim_translator/
├── apps.py                    # DjangoPimTranslatorConfig
├── settings.py                # AI_TOOLBOX_BASE_URL, API_KEY, LANGUAGE_CODE_MAP
├── clients/
│   └── __init__.py            # Re-exports ToolboxClient + errors from django_utils_translator
├── services/
│   ├── extractor.py           # 3 functions + EXTRACTORS registry
│   ├── applicator.py          # 3 functions + APPLICATORS registry
│   ├── translator.py          # Orchestrator: extract → toolbox → apply
│   └── importer.py            # Import official translations (no toolbox) → applicator
├── schemas/
│   ├── requests.py            # TranslateEntityRequest, BulkTranslateRequest
│   └── responses.py           # TranslateEntityResponse, BulkTranslate*Response
├── api/
│   ├── views.py               # EntityTranslateView, BulkTranslateView, BulkJobViewSet
│   └── urls.py                # URL patterns
├── tasks/
│   └── apply_job.py           # Celery: poll toolbox → apply translations
└── management/commands/
    ├── translate_pim.py        # CLI for bulk AI translation
    └── import_translations.py  # CLI: import official translations from JSONL (no AI)
```

Layer rule: `API → translator (orchestrator) → extractor/applicator → PIM models`.
Toolbox communication: `translator → ToolboxClient (django_utils_translator) → HTTP → AI toolbox`.

## Importing Official Translations (no AI)

When translations already exist (e.g. scraped from a foreign-language sibling site, joined by SKU),
skip the toolbox and feed the applicator directly:

```bash
python manage.py import_translations \
    --channel <channel_idx> --target en --file translations.jsonl --dry-run
```

Input is JSONL — one row per product: `{"sku": "34/448", "fields": {"name": "...",
"description": "<p>...</p>"}}`. Each `fields` key MUST equal a PIM system feature idx
(name, description, short_description). `importer.py` resolves SKU → product_id, builds
`product_attr.{id}.{feature_idx}` items, and calls `apply_product_translations` — so
HTML sanitize, `overridden_langs`, and row locking are inherited. Null/blank values are
skipped (never overwrite PIM with empties). `--dry-run` reports unmatched SKUs and
products with no existing attribute row (which the applicator would silently skip).

## API Surface

All endpoints: JWT + IsAdminUser. Prefix: `/api/pim-translator/v2/admin/{channel_idx}/`

| Method | Path | Summary |
|--------|------|---------|
| POST | `products/{sku}/translate/` | Translate/estimate single product |
| POST | `categories/{idx}/translate/` | Translate/estimate single category |
| POST | `features/{idx}/translate/` | Translate/estimate single feature |
| POST | `attributes/{feature_idx}/{idx}/translate/` | Translate/estimate single attribute |
| POST | `bulk/translate/` | Bulk translate/estimate (async job or dry_run) |
| GET | `bulk/jobs/` | List translation jobs (proxied from toolbox) |
| GET | `bulk/jobs/{pk}/` | Get job status (proxied from toolbox) |

All POST endpoints accept `dry_run: true` for cost estimation without calling the provider.

## Toolbox Communication

The AI toolbox runs on a separate machine. Communication via HTTP:

- **ToolboxClient** (from `entirius-django-utils-translator`) sends requests with `X-API-Key` header
- Settings: `AI_TOOLBOX_BASE_URL`, `AI_TOOLBOX_API_KEY` in the host service settings
- Toolbox endpoints used: `/translate/`, `/estimate/`, `/jobs/`, `/jobs/{id}/`, `/jobs/{id}/results/`

## Key Design Decisions

1. **Zero Django models** — no migrations, no DB tables. Toolbox tracks jobs/costs.
2. **overridden_langs** — applicator appends target language after writing translations. Prevents
   inheritance from clobbering AI translations.
3. **select_for_update()** — all JSON field writes use row locking to prevent concurrent data loss.
4. **JSON_T9N deferred** — type 11 excluded from v1. VARCHAR255_T9N (4) and TEXT_T9N (6) cover 90%+ of content.
5. **Celery polling** — `poll_and_apply_job` task checks toolbox every 30s for bulk job completion.
6. **HTML sanitization** — `nh3.clean()` on all translated text before writing to PIM.

## Testing

Postgres required (django_pim). Tests read `DATABASE_URL` (default
`postgresql://postgres:postgres@localhost:5432/test` — matches the CI service). Run via `make test`.

## Gotchas

- `AI_TOOLBOX_BASE_URL` and `AI_TOOLBOX_API_KEY` are required — module fails loud if missing.
- PIM language codes (gb, us) are mapped to provider codes (EN-GB, EN-US) via `LANGUAGE_CODE_MAP`.
- Category `url_key_t9n` is auto-generated from translated name — never AI-translated.
- Inherited description features are skipped by extractor (would be clobbered by inheritance sync).
- Bulk jobs create one toolbox job PER target language — 3 target langs = 3 jobs.
