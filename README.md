# entirius-django-pim-translator

A Django module that translates the product catalogue of Entirius, the open-source modular ecommerce platform.
It extracts translatable fields from PIM entities, sends them to an AI toolbox service over HTTP and writes
the translated text back.

[![PyPI](https://img.shields.io/pypi/v/entirius-django-pim-translator.svg)](https://pypi.org/project/entirius-django-pim-translator/)
[![Python](https://img.shields.io/pypi/pyversions/entirius-django-pim-translator.svg)](https://pypi.org/project/entirius-django-pim-translator/)
[![License: MPL-2.0](https://img.shields.io/badge/license-MPL--2.0-blue.svg)](https://github.com/entirius/entirius-django-pim-translator/blob/develop/LICENSE)

## What it does

- Translates products, categories, features, attributes and other PIM entities into the requested target languages.
- Estimates the cost first: every translate call accepts `dry_run` and returns an estimate without translating.
- Runs bulk translation as toolbox jobs that a Celery task polls and applies when they finish.
- Sanitises translated HTML and marks the target language as overridden, so inheritance does not undo it.
- Imports existing official translations from a JSONL file without calling the AI toolbox.
- Exposes an admin API (JWT, Pydantic schemas, OpenAPI) and the commands `translate_pim` and `import_translations`.

## Installation

```shell
uv add entirius-django-pim-translator
pip install entirius-django-pim-translator
```

```python
INSTALLED_APPS = [
    # ...
    "django_pim",
    "django_utils",
    "django_utils_translator",
    "django_pim_translator",
]

# main/urls.py
urlpatterns.append(path("", include("django_pim_translator.urls")))
```

The module needs a reachable AI toolbox service, configured through `AI_TOOLBOX_BASE_URL` and
`AI_TOOLBOX_API_KEY` of `entirius-django-utils`; the channel idx of a call is sent as the toolbox channel. The
toolbox itself is not part of this package. Settings reference:
https://github.com/entirius/entirius-django-utils/blob/develop/docs/toolbox-client.md

## Quick start

```python
from django_pim_translator.services.translator import translate_entity

estimate = translate_entity(
    channel_idx="my-channel",
    entity_type="product",
    entity_id="SKU-1",
    target_languages=["pl"],
    dry_run=True,
)
```

With `dry_run=True` the call returns a cost estimate; without it a toolbox job is created and applied by the
Celery task. The admin API is mounted under `api/pim-translator/v2/admin/<shop_idx>/`. The
same orchestrator backs `manage.py translate_pim`.

## Requirements

- Python 3.11 or newer, Django 5.0 or newer.
- PostgreSQL (through `entirius-django-pim`) and a Celery worker.
- A reachable AI toolbox service (`AI_TOOLBOX_*` settings).
- Entirius packages pulled in: `entirius-django-pim`, `entirius-django-utils`,
  `entirius-django-utils-translator`.

## Documentation

- Module docs: https://github.com/entirius/entirius-django-pim-translator/tree/develop/docs
- Entirius documentation: https://docs.entirius.com/
- Changelog: https://github.com/entirius/entirius-django-pim-translator/blob/develop/CHANGELOG.md

## Part of Entirius

This module runs inside the Entirius backend service (Volkanos) next to the PIM module it translates.

- Backend service: https://github.com/entirius/entirius-service-volkanos
- Docker harness: https://github.com/entirius/entirius-zeno
- Sibling modules: https://github.com/entirius/entirius-django-pim, https://github.com/entirius/entirius-django-utils-translator,
  https://github.com/entirius/entirius-django-contentdb-translator

## Development

```shell
make install     # sync dependencies (uv, incl. extras)
make check       # lint + format check (ruff)
make test        # test suite (pytest; PostgreSQL through DATABASE_URL)
```

Development and agent instructions: https://github.com/entirius/entirius-django-pim-translator/blob/develop/AGENTS.md

## License

Mozilla Public License 2.0 (MPL-2.0) — see https://github.com/entirius/entirius-django-pim-translator/blob/develop/LICENSE.
