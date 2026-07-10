# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Pydantic request schemas for django-pim-translator API."""

from pydantic import BaseModel, Field

from django_pim_translator.settings import EntityType


class TranslateEntityRequest(BaseModel):
    """Shared request for sync entity translation (product, category, feature, attribute).

    When dry_run=True, returns cost estimate without calling the provider.
    """

    target_languages: list[str] = Field(
        min_length=1, description="Target PIM language codes (e.g. de, fr, gb)", examples=[["de", "fr", "gb"]]
    )
    source_language: str | None = Field(
        default=None,
        description="Source PIM language code. Defaults to channel.default_language iso2.",
        examples=["en"],
    )
    provider: str | None = Field(
        default=None, description="Provider override (deepl or gemini). Defaults to channel config.", examples=["deepl"]
    )
    formality: str | None = Field(
        default=None, description="Formality level (more, less, default). Provider-dependent.", examples=["more"]
    )
    context: str | None = Field(
        default=None,
        description="Domain context for better translation quality.",
        examples=["E-commerce for baby products"],
    )
    dry_run: bool = Field(
        default=False,
        description="When true, extract items and calculate cost without calling the provider. "
        "Response includes per_language cost breakdown.",
        examples=[False],
    )


class BulkTranslateRequest(BaseModel):
    """Bulk translation request — all entities of a type in a channel.

    When dry_run=True, returns 200 with cost estimate; when False, returns 202 with job_id.
    """

    entity_type: EntityType = Field(
        description="Entity type to translate: product, category, feature, attribute, attributes_group",
        examples=["product"],
    )
    target_languages: list[str] = Field(min_length=1, description="Target PIM language codes", examples=[["de", "fr"]])
    source_language: str | None = Field(
        default=None, description="Source PIM language code. Defaults to channel default.", examples=["en"]
    )
    entity_ids: list[int] | None = Field(
        default=None, description="Specific entity IDs. None = all in channel.", examples=[[1, 2, 3]]
    )
    provider: str | None = Field(default=None, description="Provider override", examples=["deepl"])
    formality: str | None = Field(default=None, description="Formality level", examples=["more"])
    context: str | None = Field(default=None, description="Domain context", examples=["E-commerce for baby products"])
    dry_run: bool = Field(
        default=False, description="When true, returns cost estimate without creating a job.", examples=[False]
    )
    force: bool = Field(
        default=False,
        description="When false, skip fields that already have a translation in the target language. "
        "When true, overwrite existing translations.",
        examples=[False],
    )
