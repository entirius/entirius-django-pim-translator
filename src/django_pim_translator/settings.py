# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Module settings for django-pim-translator.

Shared toolbox settings (AI_TOOLBOX_*) and language code mapping are in django_utils_translator.settings.
This file contains PIM-specific settings only.
"""

from enum import StrEnum

from django_utils_translator.settings import (  # noqa: F401 — re-exported for backwards compat
    AI_TOOLBOX_API_KEY,
    AI_TOOLBOX_BASE_URL,
    AI_TOOLBOX_MAX_RETRIES,
    AI_TOOLBOX_TIMEOUT,
    LANGUAGE_CODE_MAP,
    map_to_provider_code,
)


class EntityType(StrEnum):
    """PIM entity types supported by the translator."""

    PRODUCT = "product"
    CATEGORY = "category"
    FEATURE = "feature"
    ATTRIBUTE = "attribute"
    ATTRIBUTES_GROUP = "attributes_group"
    PRODUCT_LINK_TYPE = "product_link_type"
    FILES_CATEGORY = "files_category"


# Feature types supported in v1 (VARCHAR255_T9N=4, TEXT_T9N=6).
TRANSLATABLE_FEATURE_TYPES: set[int] = {4, 6}

# Category t9n fields to translate (url_key excluded — auto-generated from name).
CATEGORY_T9N_FIELDS: list[str] = [
    "name_t9n",
    "description_t9n",
    "meta_title_t9n",
    "meta_description_t9n",
    "canonical_url_t9n",
]
