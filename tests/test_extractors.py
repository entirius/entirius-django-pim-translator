# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for PIM entity extractors.

Covers extract_simple_t9n, extract_category, extract_product_attrs,
and the EXTRACTORS registry.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django_pim_translator.services.extractor import (
    EXTRACTORS,
    extract_category,
    extract_product_attrs,
    extract_simple_t9n,
)

# ---------------------------------------------------------------------------
# EXTRACTORS registry
# ---------------------------------------------------------------------------


class TestExtractorsRegistry:
    def test_product_registered(self):
        assert "product" in EXTRACTORS

    def test_category_registered(self):
        assert "category" in EXTRACTORS

    def test_feature_registered(self):
        assert "feature" in EXTRACTORS

    def test_attribute_registered(self):
        assert "attribute" in EXTRACTORS

    def test_attributes_group_registered(self):
        assert "attributes_group" in EXTRACTORS

    def test_product_link_type_registered(self):
        assert "product_link_type" in EXTRACTORS

    def test_files_category_registered(self):
        assert "files_category" in EXTRACTORS


# ---------------------------------------------------------------------------
# extract_simple_t9n
# ---------------------------------------------------------------------------


class TestExtractSimpleT9n:
    def test_extracts_source_language_text(self):
        entity = MagicMock()
        entity.pk = 1
        entity.name_t9n = {"en": "Color", "pl": "Kolor"}

        model_class = MagicMock()
        model_class.objects.all.return_value.filter.return_value.iterator.return_value = [entity]

        items, skipped = extract_simple_t9n(model_class, "feature", source_language="en", entity_id=1)

        assert len(items) == 1
        assert items[0]["key"] == "feature.1.name"
        assert items[0]["text"] == "Color"
        assert skipped == 0

    def test_skips_entity_without_name_t9n(self):
        entity = MagicMock(spec=[])
        entity.pk = 2

        model_class = MagicMock()
        model_class.objects.all.return_value.filter.return_value.iterator.return_value = [entity]

        items, skipped = extract_simple_t9n(model_class, "attribute", source_language="en", entity_id=2)

        assert len(items) == 0
        assert skipped == 1

    def test_skips_entity_with_non_dict_name_t9n(self):
        entity = MagicMock()
        entity.pk = 3
        entity.name_t9n = "not a dict"

        model_class = MagicMock()
        model_class.objects.all.return_value.filter.return_value.iterator.return_value = [entity]

        items, skipped = extract_simple_t9n(model_class, "feature", source_language="en", entity_id=3)

        assert len(items) == 0
        assert skipped == 1

    def test_skips_entity_with_empty_source_text(self):
        entity = MagicMock()
        entity.pk = 4
        entity.name_t9n = {"en": "", "pl": "Kolor"}

        model_class = MagicMock()
        model_class.objects.all.return_value.filter.return_value.iterator.return_value = [entity]

        items, skipped = extract_simple_t9n(model_class, "feature", source_language="en", entity_id=4)

        assert len(items) == 0
        assert skipped == 1

    def test_skips_entity_with_missing_source_language(self):
        entity = MagicMock()
        entity.pk = 5
        entity.name_t9n = {"pl": "Kolor"}

        model_class = MagicMock()
        model_class.objects.all.return_value.filter.return_value.iterator.return_value = [entity]

        items, skipped = extract_simple_t9n(model_class, "feature", source_language="en", entity_id=5)

        assert len(items) == 0
        assert skipped == 1

    def test_includes_existing_langs_when_requested(self):
        entity = MagicMock()
        entity.pk = 6
        entity.name_t9n = {"en": "Size", "de": "Größe"}

        model_class = MagicMock()
        model_class.objects.all.return_value.filter.return_value.iterator.return_value = [entity]

        items, _ = extract_simple_t9n(
            model_class, "feature", source_language="en", entity_id=6, include_existing_langs=True
        )

        assert "_existing_langs" in items[0]
        assert set(items[0]["_existing_langs"]) == {"en", "de"}

    def test_strips_whitespace_from_text(self):
        entity = MagicMock()
        entity.pk = 7
        entity.name_t9n = {"en": "  Color  "}

        model_class = MagicMock()
        model_class.objects.all.return_value.filter.return_value.iterator.return_value = [entity]

        items, _ = extract_simple_t9n(model_class, "feature", source_language="en", entity_id=7)

        assert items[0]["text"] == "Color"

    def test_filters_by_entity_ids(self):
        model_class = MagicMock()
        model_class.objects.all.return_value.filter.return_value.iterator.return_value = []

        extract_simple_t9n(model_class, "feature", source_language="en", entity_ids=[1, 2, 3])

        model_class.objects.all.return_value.filter.assert_called_once_with(pk__in=[1, 2, 3])

    def test_no_filter_when_no_ids(self):
        model_class = MagicMock()
        model_class.objects.all.return_value.iterator.return_value = []

        extract_simple_t9n(model_class, "feature", source_language="en")

        model_class.objects.all.return_value.filter.assert_not_called()


# ---------------------------------------------------------------------------
# extract_category
# ---------------------------------------------------------------------------


class TestExtractCategory:
    @patch("django_pim_translator.services.extractor.ProductCategory")
    def test_extracts_all_t9n_fields(self, MockCategory):
        category = MagicMock()
        category.pk = 10
        category.name_t9n = {"en": "Shoes"}
        category.description_t9n = {"en": "All shoes"}
        category.meta_title_t9n = {"en": "Shop Shoes"}
        category.meta_description_t9n = {"en": "Buy shoes online"}
        category.canonical_url_t9n = {"en": "/shoes"}

        MockCategory.objects.filter.return_value.filter.return_value.iterator.return_value = [category]

        items, skipped = extract_category(source_language="en", channel_idx="shop-1", entity_id=10)

        assert len(items) == 5
        keys = {item["key"] for item in items}
        assert "category.10.name" in keys
        assert "category.10.description" in keys
        assert "category.10.meta_title" in keys

    @patch("django_pim_translator.services.extractor.ProductCategory")
    def test_skips_empty_t9n_fields(self, MockCategory):
        category = MagicMock()
        category.pk = 11
        category.name_t9n = {"en": "Shoes"}
        category.description_t9n = {}
        category.meta_title_t9n = None
        category.meta_description_t9n = {"en": ""}
        category.canonical_url_t9n = {"en": "valid"}

        MockCategory.objects.filter.return_value.filter.return_value.iterator.return_value = [category]

        items, skipped = extract_category(source_language="en", channel_idx="shop-1", entity_id=11)

        assert len(items) == 2  # name + canonical_url
        assert skipped == 3

    @patch("django_pim_translator.services.extractor.ProductCategory")
    def test_filters_by_channel(self, MockCategory):
        MockCategory.objects.filter.return_value.iterator.return_value = []

        extract_category(source_language="en", channel_idx="shop-1")

        MockCategory.objects.filter.assert_called_once_with(shop__idx="shop-1")


# ---------------------------------------------------------------------------
# extract_product_attrs
# ---------------------------------------------------------------------------


class TestExtractProductAttrs:
    @patch("django_pim_translator.services.extractor._build_product_attr_queryset")
    def test_extracts_translatable_attr(self, mock_build_qs):
        attr = MagicMock()
        attr.product_id = 100
        attr.value_txt_t9n = {"en": "Leather upper"}
        attr.feature = MagicMock()
        attr.feature.idx = "material"
        attr.product = MagicMock()
        attr.product.inherit_descriptions = False

        mock_build_qs.return_value.iterator.return_value = [attr]

        items, skipped = extract_product_attrs(source_language="en", channel_idx="shop-1")

        assert len(items) == 1
        assert items[0]["key"] == "product_attr.100.material"
        assert items[0]["text"] == "Leather upper"

    @patch("django_pim_translator.services.extractor._build_product_attr_queryset")
    def test_skips_non_dict_value_txt_t9n(self, mock_build_qs):
        attr = MagicMock()
        attr.value_txt_t9n = None

        mock_build_qs.return_value.iterator.return_value = [attr]

        items, skipped = extract_product_attrs(source_language="en", channel_idx="shop-1")

        assert len(items) == 0
        assert skipped == 1

    @patch("django_pim_translator.services.extractor._build_product_attr_queryset")
    @patch("django_pim_translator.services.extractor._is_inherited_description", return_value=True)
    def test_skips_inherited_descriptions(self, mock_inherited, mock_build_qs):
        attr = MagicMock()
        attr.value_txt_t9n = {"en": "Inherited text"}
        attr.feature = MagicMock()
        attr.feature.idx = "description"
        attr.product = MagicMock()

        mock_build_qs.return_value.iterator.return_value = [attr]

        items, skipped = extract_product_attrs(source_language="en", channel_idx="shop-1")

        assert len(items) == 0
        assert skipped == 1

    @patch("django_pim_translator.services.extractor._build_product_attr_queryset")
    def test_includes_existing_langs(self, mock_build_qs):
        attr = MagicMock()
        attr.product_id = 200
        attr.value_txt_t9n = {"en": "Text", "de": "Translated"}
        attr.feature = MagicMock()
        attr.feature.idx = "name"
        attr.product = MagicMock()
        attr.product.inherit_descriptions = False

        mock_build_qs.return_value.iterator.return_value = [attr]

        items, _ = extract_product_attrs(source_language="en", channel_idx="shop-1", include_existing_langs=True)

        assert "_existing_langs" in items[0]
        assert "en" in items[0]["_existing_langs"]
        assert "de" in items[0]["_existing_langs"]
