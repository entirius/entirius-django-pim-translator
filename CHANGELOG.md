# Changelog

## 2.1.1 — 2026-10-27
- Toolbox calls use the instance channel (`ToolboxClient()`, `AI_TOOLBOX_CHANNEL`) instead of the sales channel
  from the URL. Jobs keep the sales channel in `metadata.channel_idx`; `bulk/jobs/` lists only that channel's
  jobs and another channel's job detail answers 404. `AI_TOOLBOX_CHANNEL` is now required.

## 2.1.0 — 2026-10-12

- Toolbox switched off (`AI_TOOLBOX_ENABLED = False`): the `poll_and_apply_job` task logs a warning and returns
  without polling or raising; the API answers 503 `AI_TOOLBOX_DISABLED` (mapping in
  entirius-django-utils-translator). A toolbox that is enabled but not configured raises as before.
- Access: the module declares its own access areas on its AppConfig and its admin views (copied from the
  entirius-django-access defaults; behaviour unchanged).

## 2.0.0 — 2026-07-10

- Initial public release: AI translation bridge for PIM entities — extracts
  translatable fields, forwards them to the AI Toolbox over HTTP, and writes
  translated text back. Zero local models; the toolbox owns jobs, costs, and
  usage.
- `translate_pim` management command for CLI bulk translation with
  `--estimate-only` cost preview.
