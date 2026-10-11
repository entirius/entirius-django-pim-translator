---
title: Management Commands
description: CLI commands for bulk PIM AI translation and for importing official translations.
---

## translate_pim

Bulk-translate PIM entities from the command line.

```bash
python manage.py translate_pim \
  --channel <shop_idx> \
  --target pl \
  --type product \
  [--estimate-only]
```

| Option | Required | Description |
|--------|----------|-------------|
| `--channel` | Yes | PIM `channel_idx` (must have a bound `TranslatorClientChannel`) |
| `--target` | Yes | ISO 639-1 target language code |
| `--type` | Yes | `product`, `category`, `feature`, `attribute`, `attributes_group`, `product_link_type`, or `files_category` |
| `--estimate-only` | No | Estimate cost without sending to provider |

### Examples

```bash
# Estimate cost for all Polish product translations
python manage.py translate_pim --channel default-europe --target pl --type product --estimate-only

# Translate all categories to German
python manage.py translate_pim --channel default-europe --target de --type category
```

The command delegates to the same `translator.py` orchestrator used by the API — extract → toolbox → apply.

## import_translations

Imports official translations — no AI, no toolbox call.

When translations already exist (e.g. scraped from a foreign-language sibling site, joined by SKU),
skip the toolbox and feed the applicator directly:

```bash
python manage.py import_translations \
    --channel <channel_idx> --target en --file translations.jsonl --dry-run
```

Input is JSONL — one row per product: `{"sku": "SKU-1", "fields": {"name": "...",
"description": "<p>...</p>"}}`. Each `fields` key MUST equal a PIM system feature idx
(name, description, short_description). `importer.py` resolves SKU → product_id, builds
`product_attr.{id}.{feature_idx}` items, and calls `apply_product_translations` — so
HTML sanitize, `overridden_langs`, and row locking are inherited. Null/blank values are
skipped (never overwrite PIM with empties). `--dry-run` reports unmatched SKUs and
products with no existing attribute row (which the applicator would silently skip).

## Notes

- Bulk jobs are submitted as async Celery tasks. The command exits after scheduling; `poll_and_apply_job` applies results when the toolbox finishes.
- Estimate-only mode hits the toolbox `/estimate/` endpoint and prints cost without writing anything to PIM.
- If `AI_TOOLBOX_BASE_URL` or `AI_TOOLBOX_API_KEY` is missing, the command exits immediately with an error.
