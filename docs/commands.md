---
title: Management Commands
description: CLI commands for bulk PIM AI translation.
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

## Notes

- Bulk jobs are submitted as async Celery tasks. The command exits after scheduling; `poll_and_apply_job` applies results when the toolbox finishes.
- Estimate-only mode hits the toolbox `/estimate/` endpoint and prints cost without writing anything to PIM.
- If `AI_TOOLBOX_BASE_URL` or `AI_TOOLBOX_API_KEY` is missing, the command exits immediately with an error.
