# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Pydantic response schemas for django-pim-translator API."""

from decimal import Decimal

from pydantic import BaseModel, Field


class LanguageCostEstimate(BaseModel):
    """Per-language cost breakdown — included when dry_run=True."""

    language: str = Field(description="PIM language code", examples=["de"])
    items: int = Field(description="Number of text items for this language", examples=[6])
    chars: int = Field(description="Total characters for this language", examples=[1710])
    cost_usd: Decimal | None = Field(description="Estimated cost in USD", examples=["0.03420000"])


class LanguageTranslateResult(BaseModel):
    """Per-language translation result — included when dry_run=False."""

    language: str = Field(description="PIM language code", examples=["de"])
    translations_applied: int = Field(description="Number of t9n fields updated", examples=[6])
    chars: int = Field(description="Total characters translated", examples=[1710])
    cost_usd: Decimal | None = Field(description="Actual cost in USD", examples=["0.03420000"])


class TranslateEntityResponse(BaseModel):
    """Response for single entity translation (or dry_run estimate)."""

    entity_type: str = Field(description="Entity type translated", examples=["product"])
    entity_id: str = Field(description="SKU, idx, or code identifying the entity", examples=["CHAIR-001"])
    dry_run: bool = Field(description="True if this was an estimate only", examples=[False])
    translations_applied: int | None = Field(
        default=None,
        description="Total t9n fields updated across all languages. None when dry_run=True.",
        examples=[12],
    )
    skipped_items: int = Field(
        default=0, description="Items skipped (empty source text, corrupt data, inherited)", examples=[2]
    )
    target_languages: list[str] = Field(description="Target languages requested", examples=[["de", "fr"]])
    total_chars: int = Field(description="Total characters across all languages", examples=[3420])
    cost_usd: Decimal | None = Field(description="Total cost (actual or estimated)", examples=["0.06840000"])
    per_language: list[LanguageCostEstimate | LanguageTranslateResult] = Field(
        default_factory=list, description="Per-language breakdown"
    )


class BulkTranslateJobResponse(BaseModel):
    """Response 202 — bulk translation job(s) created (dry_run=False)."""

    entity_type: str = Field(description="Entity type being translated", examples=["product"])
    job_ids: list[str] = Field(
        description="Translation job UUIDs (one per target language)",
        examples=[["a1b2c3d4-e5f6-7890-abcd-ef1234567890"]],
    )
    estimated_items: int = Field(description="Total items per language", examples=[6200])
    estimated_cost_usd: Decimal | None = Field(description="Estimated total cost", examples=["124.00"])
    status: str = Field(default="pending", description="Initial job status", examples=["pending"])
    target_languages: list[str] = Field(description="Target language codes", examples=[["de", "fr"]])


class BulkTranslateEstimateResponse(BaseModel):
    """Response 200 — bulk cost estimate (dry_run=True). No job created."""

    entity_type: str = Field(description="Entity type estimated", examples=["product"])
    estimated_items: int = Field(description="Total items that would be translated per language", examples=[6200])
    total_chars: int = Field(description="Total characters across all languages", examples=[482000])
    estimated_cost_usd: Decimal | None = Field(description="Estimated total cost", examples=["124.00"])
    target_languages: list[str] = Field(description="Target language codes", examples=[["de", "fr"]])
    per_language: list[LanguageCostEstimate] = Field(description="Per-language cost breakdown")
