---
title: PIM Translator
description: AI translation bridge for PIM entities — extracts, translates via AI Toolbox, applies back.
---

PIM AI translation bridge. Extracts translatable fields from PIM entities, forwards them to the remote `entirius-ai-toolbox` via HTTP, and writes translated text back. Zero local Django models — the toolbox is the single source of truth for jobs, costs, and usage.

**Tech:** Python >=3.11 · Django >=5.0 · DRF · Pydantic · httpx · nh3

## Architecture

```
django-pim-translator
├── clients/
│   ├── toolbox.py          # httpx HTTP client for AI toolbox API
│   └── errors.py           # ToolboxError hierarchy
├── services/
│   ├── extractor.py        # Pull translatable fields from PIM entities
│   ├── applicator.py       # Write translations back to PIM
│   └── translator.py       # Orchestrator: extract → toolbox → apply
├── schemas/                # Request/response Pydantic models
├── api/                    # DRF ViewSets + URL patterns
└── tasks/
    └── apply_job.py        # Celery: poll toolbox → apply on completion
```

Layer rule: `API → translator (orchestrator) → extractor/applicator → PIM models`.

## Request Flow

```
CMS → POST /bulk/translate/ (or single-entity endpoint)
  → extractor: pull field values from PIM entity
  → ToolboxClient: POST /api/ai-translator/v2/admin/{channel_idx}/estimate/
  → (if not estimate-only) ToolboxClient: POST /api/ai-translator/v2/admin/{channel_idx}/jobs/
  → Celery poll: GET /api/ai-translator/v2/admin/{channel_idx}/jobs/{id}/
  → On completion: GET /api/ai-translator/v2/admin/{channel_idx}/jobs/{id}/results/
  → applicator: write translated values back via select_for_update()
  → overridden_langs: append target language to prevent inheritance clobbering
```

## API

All endpoints: JWT + `IsAdminUser`. Prefix: `/api/pim-translator/v2/admin/{channel_idx}/`

| Method | Path | Summary |
|--------|------|---------|
| POST | `products/{sku}/translate/` | Translate single product |
| POST | `categories/{idx}/translate/` | Translate single category |
| POST | `features/{idx}/translate/` | Translate single feature |
| POST | `attributes/{feature_idx}/{idx}/translate/` | Translate single attribute |
| POST | `bulk/translate/` | Bulk translate (async job or `dry_run`) |
| GET | `bulk/jobs/` | List jobs (proxied from toolbox) |
| GET | `bulk/jobs/{pk}/` | Job status (proxied from toolbox) |

All POST endpoints accept `dry_run: true` for cost estimation without calling the provider.

## Configuration

```python
# settings_local.py
AI_TOOLBOX_BASE_URL = "http://ai-toolbox:8001"   # required
AI_TOOLBOX_API_KEY = "ent_prod_..."               # required
AI_TOOLBOX_TIMEOUT = 60                           # optional, request timeout in seconds (default: 60)
AI_TOOLBOX_MAX_RETRIES = 3                        # optional, max retry attempts (default: 3)
```

`AI_TOOLBOX_BASE_URL` and `AI_TOOLBOX_API_KEY` are required — the module fails loud if either is missing.

See [AI Toolbox → Configuration](/ai-toolbox/configuration/) for generating an API key.

## Key Design Decisions

- **Zero models** — no migrations, no local DB tables. All tracking lives in the AI toolbox.
- **`select_for_update()`** on all JSON field writes — prevents concurrent applicator data loss.
- **`overridden_langs`** — applicator appends target language after writing. Prevents channel inheritance from clobbering AI translations.
- **HTML sanitization** — `nh3.clean()` on all translated text before writing to PIM.
- **`JSON_T9N` deferred** — type 11 excluded from v1. `VARCHAR255_T9N` (4) and `TEXT_T9N` (6) cover 90%+ of content.
- **Celery polling** — `poll_and_apply_job` checks the toolbox every 30 s for bulk job completion.

See [Management Commands](./commands/) for CLI bulk translation.
