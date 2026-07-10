# Django PIM Translator

PIM AI translation bridge for Volkanos: extracts translatable fields from PIM entities, sends them
to the remote AI toolbox over HTTP, and applies translated text back. Zero Django models. Built on
[entirius-django-utils-translator](https://github.com/entirius/entirius-django-utils-translator).

## Quick Start

Requires Python 3.11+ and PostgreSQL 15+ (django-pim).

```bash
make install                     # uv sync, incl. extras
make test                        # pytest against DATABASE_URL
```

Tests read `DATABASE_URL` (default `postgresql://postgres:postgres@localhost:5432/test` —
matches the CI service).

### Other commands

```bash
make check    # ruff check + format-check
make fix      # auto-fix lint + format
```

## Usage

Add `django_pim_translator` to `INSTALLED_APPS` (requires `django_pim`) and set
`AI_TOOLBOX_BASE_URL` + `AI_TOOLBOX_API_KEY`. API mounts at `/api/pim-translator/v2/admin/…`;
bulk CLI via `manage.py translate_pim` and `manage.py import_translations`.

## Details

See `AGENTS.md` for architecture, API surface, and design decisions.
