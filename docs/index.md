---
title: PIM Translator
description: AI translation bridge for PIM entities — extracts, translates via AI Toolbox, applies back.
---

PIM AI translation bridge. Extracts translatable fields from PIM entities, forwards them to the remote AI toolbox via HTTP, and writes translated text back. Zero local Django models — the toolbox is the single source of truth for jobs, costs, and usage.

**Tech:** Python >=3.11 · Django >=5.0 · DRF · Pydantic · httpx · nh3

## Architecture

```
src/django_pim_translator/
├── apps.py                    # DjangoPimTranslatorConfig
├── settings.py                # EntityType, translatable field lists; re-exports AI_TOOLBOX_*, LANGUAGE_CODE_MAP
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

## Request Flow

```
CMS → POST /bulk/translate/ (or single-entity endpoint)
  → extractor: pull field values from PIM entity
  → ToolboxClient: POST /api/ai-translator/v2/admin/{AI_TOOLBOX_CHANNEL}/estimate/
  → (if not estimate-only) ToolboxClient: POST /api/ai-translator/v2/admin/{AI_TOOLBOX_CHANNEL}/jobs/
  → Celery poll: GET /api/ai-translator/v2/admin/{AI_TOOLBOX_CHANNEL}/jobs/{id}/
  → On completion: GET /api/ai-translator/v2/admin/{AI_TOOLBOX_CHANNEL}/jobs/{id}/results/
  → applicator: write translated values back via select_for_update()
  → overridden_langs: append target language to prevent inheritance clobbering
```

## API

All endpoints: JWT + `IsAdminUser`. Prefix: `/api/pim-translator/v2/admin/{shop_idx}/`

| Method | Path | Summary |
|--------|------|---------|
| POST | `products/{sku}/translate/` | Translate single product |
| POST | `categories/{idx}/translate/` | Translate single category |
| POST | `features/{idx}/translate/` | Translate single feature |
| POST | `attributes/{feature_idx}/{idx}/translate/` | Translate single attribute |
| POST | `bulk/translate/` | Bulk translate (async job or `dry_run`) |
| GET | `bulk/jobs/` | List this sales channel's jobs (proxied from toolbox, filtered by `metadata.channel_idx`) |
| GET | `bulk/jobs/{pk}/` | Job status (proxied from toolbox; 404 for another channel's job) |

All POST endpoints accept `dry_run: true` for cost estimation without calling the provider.

## Configuration

```python
# settings_local.py
AI_TOOLBOX_BASE_URL = "http://ai-toolbox:8001"   # required
AI_TOOLBOX_API_KEY = "ent_prod_..."               # required
AI_TOOLBOX_CHANNEL = "my-instance"                 # required, the instance channel on the toolbox
AI_TOOLBOX_TIMEOUT = 60                           # optional, request timeout in seconds (default: 60)
AI_TOOLBOX_MAX_RETRIES = 3                        # optional, max retry attempts (default: 3)
```

`AI_TOOLBOX_BASE_URL` and `AI_TOOLBOX_API_KEY` are required — the module fails loud if either is missing.

With `AI_TOOLBOX_ENABLED = False` the toolbox is switched off on purpose: every endpoint answers 503 `AI_TOOLBOX_DISABLED` and `poll_and_apply_job` logs a warning and returns without polling.

API keys are generated in the AI Toolbox admin — see its configuration guide.

## Toolbox Communication

The AI toolbox runs on a separate machine. Communication via HTTP:

- **ToolboxClient** (from `entirius-django-utils-translator`) sends requests with `X-API-Key` header
- Settings: `AI_TOOLBOX_BASE_URL`, `AI_TOOLBOX_API_KEY` in the host service settings
- Toolbox endpoints used: `/translate/`, `/estimate/`, `/jobs/`, `/jobs/{id}/`, `/jobs/{id}/results/`

## Key Design Decisions

- **Zero models** — no migrations, no local DB tables. All tracking lives in the AI toolbox.
- **`select_for_update()`** on all JSON field writes — prevents concurrent applicator data loss.
- **`overridden_langs`** — applicator appends target language after writing. Prevents channel inheritance from clobbering AI translations.
- **HTML sanitization** — `nh3.clean()` on all translated text before writing to PIM.
- **`JSON_T9N` deferred** — type 11 excluded from v1. `VARCHAR255_T9N` (4) and `TEXT_T9N` (6) cover 90%+ of content.
- **Celery polling** — `poll_and_apply_job` checks the toolbox every 30 s for bulk job completion.

See [Management Commands](./commands/) for CLI bulk translation.
