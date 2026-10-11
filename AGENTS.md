# AGENTS.md

entirius-django-pim-translator (Django app `django_pim_translator`) — PIM AI translation bridge of Entirius.
Extracts translatable fields from PIM entities, sends them to the remote AI toolbox via HTTP, and applies
translated text back. Zero Django models — the toolbox is the single source of truth for jobs, costs, and usage.

## Commands

| Command | Meaning |
|---|---|
| `make install` | sync dependencies (uv, incl. extras) |
| `make check` | lint + format-check (ruff) |
| `make fix` | auto-fix lint + format |
| `make test` | test suite (pytest + pytest-django) |

Tests need PostgreSQL (through `django_pim`): `DATABASE_URL`, default
`postgresql://postgres:postgres@localhost:5432/test` — matches the CI service.

## Conventions

- English only: code, docs, commits, branches, PRs.
- MPL-2.0: every non-trivial source file carries the license header (pre-commit inserts it).
- Toolchain: uv + ruff + hatchling + pytest; all config in `pyproject.toml`; `uv.lock` committed.
- Git flow: `master` (production) + `develop` (integration); changes land via PR; semver tag on `master`.
- Never rename the package / Django app_label `django_pim_translator` — it is a schema contract.
- Migrations are part of the public contract — never edit an already released migration.
- Default: do not commit — git is the user's call.
- Access: areas live on the AppConfig (`access_areas`, `access_route_rules`), every admin view carries
  `access_area`; a new admin route without one fails `tests/test_access_ownership.py`.
- No AI attribution in commits or PR descriptions.

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
Toolbox communication: `translator → ToolboxClient (django_utils_translator) → HTTP → AI toolbox`.

| Topic | Where |
|---|---|
| Endpoints, request flow, toolbox communication, design decisions | `docs/index.md` |
| `translate_pim`, `import_translations` (official translations, no AI) | `docs/commands.md` |
| The `AI_TOOLBOX_*` settings | `django_utils.toolbox` — `docs/toolbox-client.md` of `entirius-django-utils` |
| What changed and why | `CHANGELOG.md` |

## Gotchas

- `AI_TOOLBOX_BASE_URL` and `AI_TOOLBOX_API_KEY` are required while the toolbox is enabled — module fails loud
  if missing.
- `AI_TOOLBOX_ENABLED = False` (the switch of `entirius-django-utils`): the endpoints answer 503
  `AI_TOOLBOX_DISABLED`; `poll_and_apply_job` logs a warning and returns without polling or raising.
- PIM language codes (gb, us) are mapped to provider codes (EN-GB, EN-US) via `LANGUAGE_CODE_MAP`.
- Category `url_key_t9n` is auto-generated from translated name — never AI-translated.
- Inherited description features are skipped by extractor (would be clobbered by inheritance sync).
- Bulk jobs create one toolbox job PER target language — 3 target langs = 3 jobs.
