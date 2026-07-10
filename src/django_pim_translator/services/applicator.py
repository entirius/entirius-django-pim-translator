# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Apply translations back to PIM entities.

Critical requirements:
1. Update overridden_langs after writing to value_txt_t9n (prevents inheritance clobber).
2. Use select_for_update() on rows before JSON read-modify-write (prevents concurrent data loss).
3. Sanitize HTML in translated text via nh3.clean() before writing (prevents stored XSS).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from django.db import DatabaseError, transaction
from django_pim.models import (
    Attribute,
    AttributesGroup,
    Feature,
    FilesCategory,
    ProductAttribute,
    ProductCategory,
    ProductLinkType,
)
from django_utils_translator.sanitize import sanitize

from django_pim_translator.settings import EntityType

logger = logging.getLogger("process")


@dataclass
class ApplyResult:
    """Result of applying translations."""

    updated: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)


@transaction.atomic
def apply_product_translations(items: list[dict], target_language: str) -> ApplyResult:
    """Apply translations to ProductAttribute rows.

    Locks rows with select_for_update() before modifying value_txt_t9n.
    After writing, appends target_language to overridden_langs.
    """
    result = ApplyResult()

    # Group items by product_attr key → {(product_id, feature_idx): translated_text}
    translations: dict[tuple[int, str], str] = {}
    for item in items:
        key = item.get("key", "")
        text = item.get("translated_text", "") or item.get("text", "")
        if not key.startswith("product_attr.") or not text:
            result.skipped += 1
            continue

        parts = key.removeprefix("product_attr.").split(".", 1)
        if len(parts) != 2:
            result.skipped += 1
            continue

        try:
            product_id = int(parts[0])
        except (ValueError, TypeError):
            result.skipped += 1
            continue

        translations[(product_id, parts[1])] = sanitize(text)

    if not translations:
        return result

    # Build lookup for efficient querying.
    product_ids = {pid for pid, _ in translations}
    feature_idxs = {fidx for _, fidx in translations}

    try:
        attrs = list(
            ProductAttribute.objects.select_for_update(nowait=True)
            .filter(product_id__in=product_ids, feature__idx__in=feature_idxs)
            .select_related("feature")
        )
    except DatabaseError:
        logger.warning("apply_product_translations: rows locked by concurrent job, will retry")
        raise

    to_update: list[ProductAttribute] = []
    for attr in attrs:
        lookup_key = (attr.product_id, attr.feature.idx)
        if lookup_key not in translations:
            continue

        translated_text = translations[lookup_key]

        # Write translation to value_txt_t9n.
        t9n = attr.value_txt_t9n if isinstance(attr.value_txt_t9n, dict) else {}
        t9n[target_language] = translated_text
        attr.value_txt_t9n = t9n

        # CRITICAL: update overridden_langs to prevent inheritance clobber.
        overridden = set(attr.overridden_langs) if isinstance(attr.overridden_langs, list) else set()
        overridden.add(target_language)
        attr.overridden_langs = sorted(overridden)

        to_update.append(attr)

    if to_update:
        ProductAttribute.objects.bulk_update(to_update, fields=["value_txt_t9n", "overridden_langs"], batch_size=500)
        result.updated = len(to_update)

    return result


@transaction.atomic
def apply_category_translations(items: list[dict], target_language: str, channel_idx: str) -> ApplyResult:
    """Apply translations to ProductCategory rows.

    After updating name_t9n, auto-generates url_key_t9n via generate_url_key().
    """
    result = ApplyResult()

    # Group: {category_id: {field_name: translated_text}}
    translations: dict[int, dict[str, str]] = {}
    for item in items:
        key = item.get("key", "")
        text = item.get("translated_text", "") or item.get("text", "")
        if not key.startswith("category.") or not text:
            result.skipped += 1
            continue

        parts = key.removeprefix("category.").split(".", 1)
        if len(parts) != 2:
            result.skipped += 1
            continue

        try:
            cat_id = int(parts[0])
        except (ValueError, TypeError):
            result.skipped += 1
            continue

        translations.setdefault(cat_id, {})[parts[1]] = sanitize(text)

    if not translations:
        return result

    try:
        categories = list(
            ProductCategory.objects.select_for_update(nowait=True).filter(
                pk__in=translations.keys(), shop__idx=channel_idx
            )
        )
    except DatabaseError:
        logger.warning("apply_category_translations: rows locked by concurrent job, will retry")
        raise

    to_update: list[ProductCategory] = []
    update_fields: set[str] = set()

    for category in categories:
        field_translations = translations.get(category.pk, {})
        if not field_translations:
            continue

        for field_name, translated_text in field_translations.items():
            t9n_field = f"{field_name}_t9n"
            if not hasattr(category, t9n_field):
                result.skipped += 1
                continue

            t9n = getattr(category, t9n_field)
            if not isinstance(t9n, dict):
                t9n = {}
            t9n[target_language] = translated_text
            setattr(category, t9n_field, t9n)
            update_fields.add(t9n_field)

        # Auto-generate url_key from translated name.
        if "name" in field_translations:
            url_key = category.generate_url_key(target_language)
            t9n = category.url_key_t9n if isinstance(category.url_key_t9n, dict) else {}
            t9n[target_language] = url_key
            category.url_key_t9n = t9n
            update_fields.add("url_key_t9n")

        to_update.append(category)

    if to_update and update_fields:
        ProductCategory.objects.bulk_update(to_update, fields=list(update_fields), batch_size=500)
        result.updated = len(to_update)

    return result


@transaction.atomic
def apply_simple_t9n_translations(
    model_class: type,
    items: list[dict],
    target_language: str,
    entity_type: str,
) -> ApplyResult:
    """Apply translations to simple name_t9n fields (Feature, Attribute, etc.)."""
    result = ApplyResult()

    translations: dict[int, str] = {}
    prefix = f"{entity_type}."
    for item in items:
        key = item.get("key", "")
        text = item.get("translated_text", "") or item.get("text", "")
        if not key.startswith(prefix) or not text:
            result.skipped += 1
            continue

        parts = key.removeprefix(prefix).split(".", 1)
        try:
            entity_id = int(parts[0])
        except (ValueError, TypeError):
            result.skipped += 1
            continue

        translations[entity_id] = sanitize(text)

    if not translations:
        return result

    try:
        entities = list(model_class.objects.select_for_update(nowait=True).filter(pk__in=translations.keys()))
    except DatabaseError:
        logger.warning("apply_simple_t9n_translations: rows locked by concurrent job, will retry")
        raise

    to_update = []
    for entity in entities:
        translated_text = translations.get(entity.pk)
        if not translated_text:
            continue

        t9n = entity.name_t9n if isinstance(entity.name_t9n, dict) else {}
        t9n[target_language] = translated_text
        entity.name_t9n = t9n
        to_update.append(entity)

    if to_update:
        model_class.objects.bulk_update(to_update, fields=["name_t9n"], batch_size=500)
        result.updated = len(to_update)

    return result


# Registry: entity_type → applicator function.
APPLICATORS: dict[EntityType, Any] = {
    EntityType.PRODUCT: apply_product_translations,
    EntityType.CATEGORY: apply_category_translations,
    EntityType.FEATURE: lambda items, target_language, **kw: apply_simple_t9n_translations(
        Feature, items, target_language, EntityType.FEATURE
    ),
    EntityType.ATTRIBUTE: lambda items, target_language, **kw: apply_simple_t9n_translations(
        Attribute, items, target_language, EntityType.ATTRIBUTE
    ),
    EntityType.ATTRIBUTES_GROUP: lambda items, target_language, **kw: apply_simple_t9n_translations(
        AttributesGroup, items, target_language, EntityType.ATTRIBUTES_GROUP
    ),
    EntityType.PRODUCT_LINK_TYPE: lambda items, target_language, **kw: apply_simple_t9n_translations(
        ProductLinkType, items, target_language, EntityType.PRODUCT_LINK_TYPE
    ),
    EntityType.FILES_CATEGORY: lambda items, target_language, **kw: apply_simple_t9n_translations(
        FilesCategory, items, target_language, EntityType.FILES_CATEGORY
    ),
}
