# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Extract translatable fields from PIM entities into toolbox-compatible items.

Each extractor returns (items, skipped_count) where items are plain dicts
matching the toolbox API contract: {"key": "...", "text": "..."}.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from django.db.models import QuerySet
from django_pim.models import (
    Attribute,
    AttributesGroup,
    Feature,
    FilesCategory,
    ProductAttribute,
    ProductCategory,
    ProductLinkType,
)
from django_pim.settings import DESCRIPTION_FEATURE_IDXS

from django_pim_translator.settings import CATEGORY_T9N_FIELDS, TRANSLATABLE_FEATURE_TYPES, EntityType

logger = logging.getLogger("process")

# Key format constants — contract between extractor and applicator.
KEY_PRODUCT_ATTR = "product_attr.{product_id}.{feature_idx}"
KEY_CATEGORY = "category.{category_id}.{field_name}"
KEY_SIMPLE = "{entity_type}.{entity_id}.name"


def extract_simple_t9n(
    model_class: type,
    entity_type: str,
    source_language: str,
    entity_id: int | None = None,
    entity_ids: list[int] | None = None,
    include_existing_langs: bool = False,
) -> tuple[list[dict], int]:
    """Extract name_t9n from simple entities (Feature, Attribute, AttributesGroup, etc.)."""
    qs = model_class.objects.all()
    if entity_id is not None:
        qs = qs.filter(pk=entity_id)
    elif entity_ids:
        qs = qs.filter(pk__in=entity_ids)

    items: list[dict] = []
    skipped = 0

    for entity in qs.iterator(chunk_size=500):
        t9n = getattr(entity, "name_t9n", None)
        if not isinstance(t9n, dict):
            skipped += 1
            continue

        text = t9n.get(source_language, "")
        if not text or not str(text).strip():
            skipped += 1
            continue

        item: dict = {
            "key": KEY_SIMPLE.format(entity_type=entity_type, entity_id=entity.pk),
            "text": str(text).strip(),
        }
        if include_existing_langs:
            item["_existing_langs"] = list(t9n.keys())
        items.append(item)

    return items, skipped


def extract_category(
    source_language: str,
    channel_idx: str,
    entity_id: int | None = None,
    entity_ids: list[int] | None = None,
    include_existing_langs: bool = False,
) -> tuple[list[dict], int]:
    """Extract 5 t9n fields from ProductCategory (url_key excluded — auto-generated)."""
    qs = ProductCategory.objects.filter(shop__idx=channel_idx)
    if entity_id is not None:
        qs = qs.filter(pk=entity_id)
    elif entity_ids:
        qs = qs.filter(pk__in=entity_ids)

    items: list[dict] = []
    skipped = 0

    for category in qs.iterator(chunk_size=500):
        for field_name in CATEGORY_T9N_FIELDS:
            t9n = getattr(category, field_name, None)
            if not isinstance(t9n, dict):
                skipped += 1
                continue

            text = t9n.get(source_language, "")
            if not text or not str(text).strip():
                skipped += 1
                continue

            # Strip _t9n suffix for the key label (e.g., "name_t9n" → "name").
            label = field_name.removesuffix("_t9n")
            item: dict = {
                "key": KEY_CATEGORY.format(category_id=category.pk, field_name=label),
                "text": str(text).strip(),
            }
            if include_existing_langs:
                item["_existing_langs"] = list(t9n.keys())
            items.append(item)

    return items, skipped


def extract_product_attrs(
    source_language: str,
    channel_idx: str,
    entity_id: int | None = None,
    entity_ids: list[int] | None = None,
    include_existing_langs: bool = False,
) -> tuple[list[dict], int]:
    """Extract value_txt_t9n from ProductAttribute rows with T9N feature types.

    Rules:
    - Only VARCHAR255_T9N (4) and TEXT_T9N (6) — JSON_T9N deferred to v2.
    - Skip rows where value_txt_t9n is not a dict (corrupt data guard).
    - Skip rows where source_language key is missing or empty.
    - Skip inherited descriptions (inherit_descriptions=True + feature in DESCRIPTION_FEATURE_IDXS).
    - Use feature.name as context_mode key for LLM cross-field awareness.
    """
    qs = _build_product_attr_queryset(channel_idx, entity_id, entity_ids)

    items: list[dict] = []
    skipped = 0

    for attr in qs.iterator(chunk_size=1000):
        if not isinstance(attr.value_txt_t9n, dict):
            skipped += 1
            continue

        text = attr.value_txt_t9n.get(source_language, "")
        if not text or not str(text).strip():
            skipped += 1
            continue

        # Skip inherited description features — they'll be clobbered by next inheritance sync.
        if _is_inherited_description(attr):
            skipped += 1
            continue

        item: dict = {
            "key": KEY_PRODUCT_ATTR.format(product_id=attr.product_id, feature_idx=attr.feature.idx),
            "text": str(text).strip(),
        }
        if include_existing_langs:
            item["_existing_langs"] = list(attr.value_txt_t9n.keys())
        items.append(item)

    return items, skipped


def _build_product_attr_queryset(
    channel_idx: str,
    entity_id: int | None,
    entity_ids: list[int] | None,
) -> QuerySet:
    qs = ProductAttribute.objects.filter(
        product__shop__idx=channel_idx,
        feature__feature_type__in=TRANSLATABLE_FEATURE_TYPES,
    ).select_related("feature", "product")
    if entity_id is not None:
        qs = qs.filter(product_id=entity_id)
    elif entity_ids:
        qs = qs.filter(product_id__in=entity_ids)
    return qs


def _is_inherited_description(attr: Any) -> bool:
    """Check if this attribute is an inherited description that would be clobbered."""
    if not hasattr(attr, "product"):
        return False
    product = attr.product
    if not getattr(product, "inherit_descriptions", False):
        return False
    return attr.feature.idx in DESCRIPTION_FEATURE_IDXS


def _resolve_feature_label(feature: Feature, language: str) -> str:
    """Get human-readable feature name for context_mode keys."""
    if isinstance(feature.name_t9n, dict):
        name = feature.name_t9n.get(language, "")
        if name:
            return str(name)
    return feature.idx


# Registry: entity_type → extractor function.
EXTRACTORS: dict[EntityType, Callable[..., tuple[list[dict], int]]] = {
    EntityType.PRODUCT: extract_product_attrs,
    EntityType.CATEGORY: extract_category,
    EntityType.FEATURE: lambda **kw: extract_simple_t9n(Feature, EntityType.FEATURE, **kw),
    EntityType.ATTRIBUTE: lambda **kw: extract_simple_t9n(Attribute, EntityType.ATTRIBUTE, **kw),
    EntityType.ATTRIBUTES_GROUP: lambda **kw: extract_simple_t9n(AttributesGroup, EntityType.ATTRIBUTES_GROUP, **kw),
    EntityType.PRODUCT_LINK_TYPE: lambda **kw: extract_simple_t9n(ProductLinkType, EntityType.PRODUCT_LINK_TYPE, **kw),
    EntityType.FILES_CATEGORY: lambda **kw: extract_simple_t9n(FilesCategory, EntityType.FILES_CATEGORY, **kw),
}
