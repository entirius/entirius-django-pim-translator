# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for the official-translation importer (pure logic, no DB).

Covers load_jsonl, build_items, SKU normalization, and null/blank skipping.
DB-dependent paths (_resolve_skus, import_translations) are covered by
integration tests against PIM models.
"""

from __future__ import annotations

import pytest

from django_pim_translator.services.importer import (
    _norm_sku,
    build_items,
    load_jsonl,
)


class TestNormSku:
    def test_lowercases_and_strips(self):
        assert _norm_sku(" 35/368_BLU ") == "35/368_blu"

    def test_none_becomes_empty(self):
        assert _norm_sku(None) == ""


class TestLoadJsonl:
    def test_reads_rows_and_ignores_blank_lines(self, tmp_path):
        f = tmp_path / "t.jsonl"
        f.write_text('{"sku": "34/448", "fields": {"name": "A"}}\n\n{"sku": "34/453"}\n', encoding="utf-8")
        rows = load_jsonl(f)
        assert len(rows) == 2
        assert rows[0]["sku"] == "34/448"

    def test_invalid_json_raises_with_line_number(self, tmp_path):
        f = tmp_path / "bad.jsonl"
        f.write_text('{"sku": "ok"}\nNOT JSON\n', encoding="utf-8")
        with pytest.raises(ValueError, match="line 2"):
            load_jsonl(f)


class TestBuildItems:
    def test_maps_field_name_to_feature_idx_key(self):
        rows = [{"sku": "34/448", "fields": {"name": "EN Name", "description": "<p>EN</p>"}}]
        items = build_items(rows, {"34/448": 100})
        assert {"key": "product_attr.100.name", "translated_text": "EN Name"} in items
        assert {"key": "product_attr.100.description", "translated_text": "<p>EN</p>"} in items

    def test_skips_unmatched_sku(self):
        rows = [{"sku": "99/999", "fields": {"name": "X"}}]
        assert build_items(rows, {"34/448": 100}) == []

    def test_skips_null_and_blank_fields(self):
        rows = [{"sku": "34/448", "fields": {"name": None, "short_description": "  ", "description": "keep"}}]
        items = build_items(rows, {"34/448": 100})
        assert len(items) == 1
        assert items[0]["key"] == "product_attr.100.description"

    def test_sku_match_is_case_insensitive(self):
        rows = [{"sku": "35/368_BLU", "fields": {"name": "X"}}]
        items = build_items(rows, {"35/368_blu": 7})
        assert items[0]["key"] == "product_attr.7.name"

    def test_preserves_full_html_verbatim(self):
        html = "<div><p>Product details:</p><ul><li>safe for breastfeeding</li></ul></div>"
        rows = [{"sku": "34/448", "fields": {"description": html}}]
        items = build_items(rows, {"34/448": 100})
        assert items[0]["translated_text"] == html
