# Changelog

## 2.0.0 — 2026-07-10

- Initial public release: AI translation bridge for PIM entities — extracts
  translatable fields, forwards them to the AI Toolbox over HTTP, and writes
  translated text back. Zero local models; the toolbox owns jobs, costs, and
  usage.
- `translate_pim` management command for CLI bulk translation with
  `--estimate-only` cost preview.
