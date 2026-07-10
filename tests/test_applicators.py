# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for PIM entity applicators.

Covers key parsing, sanitization, translation writing,
overridden_langs management, and the APPLICATORS registry.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from django_pim_translator.services.applicator import (
    APPLICATORS,
    ApplyResult,
    apply_category_translations,
    apply_product_translations,
    apply_simple_t9n_translations,
)

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# APPLICATORS registry
# ---------------------------------------------------------------------------


class TestApplicatorsRegistry:
    def test_product_registered(self):
        assert "product" in APPLICATORS

    def test_category_registered(self):
        assert "category" in APPLICATORS

    def test_feature_registered(self):
        assert "feature" in APPLICATORS

    def test_attribute_registered(self):
        assert "attribute" in APPLICATORS

    def test_attributes_group_registered(self):
        assert "attributes_group" in APPLICATORS

    def test_product_link_type_registered(self):
        assert "product_link_type" in APPLICATORS

    def test_files_category_registered(self):
        assert "files_category" in APPLICATORS


# ---------------------------------------------------------------------------
# apply_product_translations — key parsing
# ---------------------------------------------------------------------------


class TestApplyProductTranslationsKeyParsing:
    @patch("django_pim_translator.services.applicator.ProductAttribute")
    @patch("django_pim_translator.services.applicator.sanitize", side_effect=lambda x: x)
    def test_skips_items_with_wrong_prefix(self, mock_sanitize, MockPA):
        items = [{"key": "category.1.name", "translated_text": "Translated"}]
        result = apply_product_translations(items, target_language="de")
        assert result.skipped == 1
        assert result.updated == 0

    @patch("django_pim_translator.services.applicator.ProductAttribute")
    @patch("django_pim_translator.services.applicator.sanitize", side_effect=lambda x: x)
    def test_skips_items_with_empty_text(self, mock_sanitize, MockPA):
        items = [{"key": "product_attr.1.material", "translated_text": ""}]
        result = apply_product_translations(items, target_language="de")
        assert result.skipped == 1

    @patch("django_pim_translator.services.applicator.ProductAttribute")
    @patch("django_pim_translator.services.applicator.sanitize", side_effect=lambda x: x)
    def test_skips_items_with_malformed_key(self, mock_sanitize, MockPA):
        items = [{"key": "product_attr.badkey", "translated_text": "Text"}]
        result = apply_product_translations(items, target_language="de")
        assert result.skipped == 1

    @patch("django_pim_translator.services.applicator.ProductAttribute")
    @patch("django_pim_translator.services.applicator.sanitize", side_effect=lambda x: x)
    def test_skips_items_with_non_integer_product_id(self, mock_sanitize, MockPA):
        items = [{"key": "product_attr.abc.material", "translated_text": "Text"}]
        result = apply_product_translations(items, target_language="de")
        assert result.skipped == 1

    @patch("django_pim_translator.services.applicator.ProductAttribute")
    @patch("django_pim_translator.services.applicator.sanitize", side_effect=lambda x: x)
    def test_returns_early_when_no_valid_translations(self, mock_sanitize, MockPA):
        items = [{"key": "wrong.prefix", "translated_text": "Text"}]
        result = apply_product_translations(items, target_language="de")
        MockPA.objects.select_for_update.assert_not_called()
        assert result.updated == 0


# ---------------------------------------------------------------------------
# apply_product_translations — write logic
# ---------------------------------------------------------------------------


class TestApplyProductTranslationsWrite:
    @patch("django_pim_translator.services.applicator.ProductAttribute")
    @patch("django_pim_translator.services.applicator.sanitize", side_effect=lambda x: x)
    def test_writes_translation_and_updates_overridden_langs(self, mock_sanitize, MockPA):
        attr = MagicMock()
        attr.product_id = 1
        attr.feature = MagicMock()
        attr.feature.idx = "material"
        attr.value_txt_t9n = {"en": "Leather"}
        attr.overridden_langs = ["en"]

        MockPA.objects.select_for_update.return_value.filter.return_value.select_related.return_value = [attr]

        items = [{"key": "product_attr.1.material", "translated_text": "Leder"}]
        result = apply_product_translations(items, target_language="de")

        assert result.updated == 1
        assert attr.value_txt_t9n["de"] == "Leder"
        assert "de" in attr.overridden_langs
        assert "en" in attr.overridden_langs
        MockPA.objects.bulk_update.assert_called_once()

    @patch("django_pim_translator.services.applicator.ProductAttribute")
    @patch("django_pim_translator.services.applicator.sanitize", side_effect=lambda x: x)
    def test_initializes_empty_value_txt_t9n(self, mock_sanitize, MockPA):
        attr = MagicMock()
        attr.product_id = 2
        attr.feature = MagicMock()
        attr.feature.idx = "color"
        attr.value_txt_t9n = None  # corrupt data
        attr.overridden_langs = None

        MockPA.objects.select_for_update.return_value.filter.return_value.select_related.return_value = [attr]

        items = [{"key": "product_attr.2.color", "translated_text": "Rot"}]
        result = apply_product_translations(items, target_language="de")

        assert result.updated == 1
        assert attr.value_txt_t9n == {"de": "Rot"}


# ---------------------------------------------------------------------------
# apply_category_translations
# ---------------------------------------------------------------------------


class TestApplyCategoryTranslations:
    @patch("django_pim_translator.services.applicator.ProductCategory")
    @patch("django_pim_translator.services.applicator.sanitize", side_effect=lambda x: x)
    def test_skips_items_with_wrong_prefix(self, mock_sanitize, MockCat):
        items = [{"key": "product_attr.1.name", "translated_text": "Text"}]
        result = apply_category_translations(items, target_language="de", channel_idx="shop-1")
        assert result.skipped == 1

    @patch("django_pim_translator.services.applicator.ProductCategory")
    @patch("django_pim_translator.services.applicator.sanitize", side_effect=lambda x: x)
    def test_writes_translation_to_t9n_field(self, mock_sanitize, MockCat):
        category = MagicMock()
        category.pk = 10
        category.name_t9n = {"en": "Shoes"}
        category.url_key_t9n = {}
        category.generate_url_key.return_value = "schuhe"

        MockCat.objects.select_for_update.return_value.filter.return_value = [category]

        items = [{"key": "category.10.name", "translated_text": "Schuhe"}]
        result = apply_category_translations(items, target_language="de", channel_idx="shop-1")

        assert result.updated == 1
        assert category.name_t9n["de"] == "Schuhe"
        assert category.url_key_t9n["de"] == "schuhe"

    @patch("django_pim_translator.services.applicator.ProductCategory")
    @patch("django_pim_translator.services.applicator.sanitize", side_effect=lambda x: x)
    def test_returns_early_when_no_valid_translations(self, mock_sanitize, MockCat):
        items = [{"key": "bad.key", "translated_text": "Text"}]
        result = apply_category_translations(items, target_language="de", channel_idx="shop-1")
        MockCat.objects.select_for_update.assert_not_called()


# ---------------------------------------------------------------------------
# apply_simple_t9n_translations
# ---------------------------------------------------------------------------


class TestApplySimpleT9nTranslations:
    def test_writes_translation_to_name_t9n(self):
        entity = MagicMock()
        entity.pk = 1
        entity.name_t9n = {"en": "Color"}

        model_class = MagicMock()
        model_class.objects.select_for_update.return_value.filter.return_value = [entity]

        items = [{"key": "feature.1.name", "translated_text": "Farbe"}]
        result = apply_simple_t9n_translations(model_class, items, target_language="de", entity_type="feature")

        assert result.updated == 1
        assert entity.name_t9n["de"] == "Farbe"
        model_class.objects.bulk_update.assert_called_once()

    def test_skips_items_with_wrong_prefix(self):
        model_class = MagicMock()

        items = [{"key": "category.1.name", "translated_text": "Text"}]
        result = apply_simple_t9n_translations(model_class, items, target_language="de", entity_type="feature")

        assert result.skipped == 1
        assert result.updated == 0

    def test_skips_items_with_non_integer_id(self):
        model_class = MagicMock()

        items = [{"key": "feature.abc.name", "translated_text": "Text"}]
        result = apply_simple_t9n_translations(model_class, items, target_language="de", entity_type="feature")

        assert result.skipped == 1

    def test_initializes_empty_name_t9n(self):
        entity = MagicMock()
        entity.pk = 2
        entity.name_t9n = "not a dict"

        model_class = MagicMock()
        model_class.objects.select_for_update.return_value.filter.return_value = [entity]

        items = [{"key": "feature.2.name", "translated_text": "Farbe"}]
        result = apply_simple_t9n_translations(model_class, items, target_language="de", entity_type="feature")

        assert result.updated == 1
        assert entity.name_t9n == {"de": "Farbe"}


# ---------------------------------------------------------------------------
# ApplyResult
# ---------------------------------------------------------------------------


class TestApplyResult:
    def test_defaults(self):
        result = ApplyResult()
        assert result.updated == 0
        assert result.skipped == 0
        assert result.errors == []

    def test_errors_list_not_shared(self):
        r1 = ApplyResult()
        r2 = ApplyResult()
        r1.errors.append("err")
        assert r2.errors == []
