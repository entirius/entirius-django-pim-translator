# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Import official translations from an external source (sibling-site scrape) into PIM.

Unlike the AI path (extract → toolbox → apply), this bypasses the toolbox entirely:
we already have human/official translations, so we build applicator items directly
and reuse ``apply_product_translations``. All write safety (HTML sanitize,
overridden_langs, row locking) comes from the existing applicator.

Input contract — one JSON object per line (JSONL):

    {"sku": "34/448", "fields": {"name": "...", "description": "<p>...</p>"}}

Each key in ``fields`` MUST equal a PIM system feature idx (name, description,
short_description, ...). Null/empty field values are skipped — existing PIM
values are never overwritten with blanks.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from django_pim.models import Product, ProductAttribute

from django_pim_translator.services.applicator import apply_product_translations

logger = logging.getLogger("process")

# Key format shared with the applicator (see extractor.KEY_PRODUCT_ATTR).
KEY_PRODUCT_ATTR = "product_attr.{product_id}.{feature_idx}"


@dataclass
class ImportReport:
    """Outcome of an import run (or dry-run preview)."""

    rows: int = 0
    matched_products: int = 0
    unmatched_skus: list[str] = field(default_factory=list)
    items_built: int = 0
    missing_attr_rows: list[str] = field(default_factory=list)
    updated: int = 0
    skipped: int = 0


def load_jsonl(path: str | Path) -> list[dict]:
    """Read a JSONL file into a list of row dicts. Blank lines are ignored."""
    rows: list[dict] = []
    with Path(path).open(encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on line {line_no}: {exc}") from exc
    return rows


def build_items(rows: list[dict], sku_to_pid: dict[str, int]) -> list[dict]:
    """Pure transform: JSONL rows + sku→product_id map → applicator items.

    Skips unmatched SKUs and null/blank field values. Field name maps directly
    to the PIM feature idx (name → "name", description → "description").
    """
    items: list[dict] = []
    for row in rows:
        pid = sku_to_pid.get(_norm_sku(row.get("sku")))
        if not pid:
            continue
        for feature_idx, value in (row.get("fields") or {}).items():
            if value is None or not str(value).strip():
                continue
            items.append(
                {
                    "key": KEY_PRODUCT_ATTR.format(product_id=pid, feature_idx=feature_idx),
                    "translated_text": str(value),
                }
            )
    return items


def import_translations(
    channel_idx: str,
    target_language: str,
    rows: list[dict],
    dry_run: bool = False,
) -> ImportReport:
    """Resolve SKUs, build items, and apply them (or preview when dry_run)."""
    report = ImportReport(rows=len(rows))

    skus = [_norm_sku(r.get("sku")) for r in rows if r.get("sku")]
    sku_to_pid = _resolve_skus(channel_idx, skus)
    report.matched_products = len(set(sku_to_pid.values()))
    report.unmatched_skus = sorted({s for s in skus if s not in sku_to_pid})

    items = build_items(rows, sku_to_pid)
    report.items_built = len(items)
    report.missing_attr_rows = _find_missing_attr_rows(items)

    if dry_run or not items:
        report.skipped = len(items)
        return report

    result = apply_product_translations(items=items, target_language=target_language)
    report.updated = result.updated
    report.skipped = result.skipped
    return report


def _norm_sku(sku: str | None) -> str:
    """Normalize SKU for case-insensitive matching (RealProduct.sku has a Lower index)."""
    return str(sku).strip().lower() if sku else ""


def _resolve_skus(channel_idx: str, skus: list[str]) -> dict[str, int]:
    """Map normalized SKU → Product.pk within the channel. Unknown SKUs are absent."""
    if not skus:
        return {}
    pairs = Product.objects.filter(shop__idx=channel_idx, real_product__sku__in=skus).values_list(
        "real_product__sku", "pk"
    )
    return {_norm_sku(sku): pid for sku, pid in pairs}


def _find_missing_attr_rows(items: list[dict]) -> list[str]:
    """Keys whose ProductAttribute row does not exist yet (applicator would skip them)."""
    wanted: set[tuple[int, str]] = set()
    for item in items:
        pid, _, fidx = item["key"].removeprefix("product_attr.").partition(".")
        wanted.add((int(pid), fidx))

    product_ids = {pid for pid, _ in wanted}
    feature_idxs = {fidx for _, fidx in wanted}
    existing = set(
        ProductAttribute.objects.filter(product_id__in=product_ids, feature__idx__in=feature_idxs).values_list(
            "product_id", "feature__idx"
        )
    )
    return sorted(f"product_attr.{pid}.{fidx}" for pid, fidx in wanted - existing)
