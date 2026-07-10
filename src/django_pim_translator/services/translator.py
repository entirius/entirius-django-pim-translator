# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Orchestrator: extract → ToolboxClient call → apply.

Ties extraction, translation via remote toolbox, and application together.
"""

from __future__ import annotations

import concurrent.futures
import logging
from decimal import Decimal

from django_pim.models import Attribute, Channel, Feature, Product, ProductCategory, RealProduct

from django_pim_translator.clients import ToolboxClient
from django_pim_translator.schemas.responses import (
    BulkTranslateEstimateResponse,
    BulkTranslateJobResponse,
    LanguageCostEstimate,
    TranslateEntityResponse,
)
from django_pim_translator.services.extractor import EXTRACTORS
from django_pim_translator.settings import map_to_provider_code

logger = logging.getLogger("process")


def _resolve_source_language(channel_idx: str, source_language: str | None) -> str:
    """Resolve source language from explicit param or channel default."""
    if source_language:
        return source_language
    try:
        channel = Channel.objects.select_related("default_language").get(idx=channel_idx)
        if channel.default_language:
            return channel.default_language.iso2
    except Channel.DoesNotExist:
        pass
    return "en"


def _resolve_entity_pk(entity_type: str, entity_id: int | str, channel_idx: str) -> int:
    """Resolve URL identifier (SKU/idx string) to database PK for extractors."""
    if isinstance(entity_id, int):
        return entity_id
    try:
        if entity_type == "product":
            return (
                Product.objects.filter(shop__idx=channel_idx, real_product__sku=entity_id)
                .values_list("pk", flat=True)
                .get()
            )
        if entity_type == "category":
            return (
                ProductCategory.objects.filter(shop__idx=channel_idx, idx=entity_id).values_list("pk", flat=True).get()
            )
        if entity_type == "feature":
            return Feature.objects.filter(idx=entity_id).values_list("pk", flat=True).get()
        if entity_type == "attribute":
            return Attribute.objects.filter(idx=entity_id).values_list("pk", flat=True).get()
    except (
        Product.DoesNotExist,
        ProductCategory.DoesNotExist,
        Feature.DoesNotExist,
        Attribute.DoesNotExist,
        RealProduct.DoesNotExist,
    ):
        raise ValueError(f"{entity_type} '{entity_id}' not found in channel '{channel_idx}'")
    # Fallback — try int conversion for backwards compat.
    return int(entity_id)


def _extract_entity_items(
    entity_type: str,
    entity_id: int | str,
    channel_idx: str,
    source_lang: str,
) -> tuple[list[dict], int, int]:
    """Extract items from a single PIM entity. Returns (items, skipped, resolved_pk)."""
    extractor_fn = EXTRACTORS.get(entity_type)
    if not extractor_fn:
        raise ValueError(f"Unknown entity type: {entity_type}")

    resolved_id = _resolve_entity_pk(entity_type, entity_id, channel_idx)

    extract_kwargs: dict = {"source_language": source_lang, "entity_id": resolved_id}
    if entity_type in ("product", "category"):
        extract_kwargs["channel_idx"] = channel_idx

    items, skipped = extractor_fn(**extract_kwargs)
    return items, skipped, resolved_id


def translate_entity(
    channel_idx: str,
    entity_type: str,
    entity_id: int | str,
    target_languages: list[str],
    source_language: str | None = None,
    provider: str | None = None,
    formality: str | None = None,
    context: str | None = None,
    dry_run: bool = False,
) -> TranslateEntityResponse | BulkTranslateJobResponse:
    """Translate a single entity. dry_run=True → estimate, dry_run=False → async job."""
    source_lang = _resolve_source_language(channel_idx, source_language)
    items, skipped, _ = _extract_entity_items(entity_type, entity_id, channel_idx, source_lang)

    if not items:
        return TranslateEntityResponse(
            entity_type=entity_type,
            entity_id=str(entity_id),
            dry_run=dry_run,
            translations_applied=0 if not dry_run else None,
            skipped_items=skipped,
            target_languages=target_languages,
            total_chars=0,
            cost_usd=Decimal("0"),
        )

    mapped_source = map_to_provider_code(source_lang)
    total_chars = sum(len(item["text"]) for item in items)

    with ToolboxClient(channel_idx) as client:
        if dry_run:
            return _estimate_entity(
                client, items, target_languages, mapped_source, provider, entity_type, entity_id, skipped, total_chars
            )
        return _create_jobs(
            client,
            items,
            target_languages,
            mapped_source,
            provider,
            formality,
            context,
            entity_type,
            channel_idx,
            total_chars,
        )


def _estimate_entity(
    client: ToolboxClient,
    items: list[dict],
    target_languages: list[str],
    mapped_source: str,
    provider: str | None,
    entity_type: str,
    entity_id: int | str,
    skipped: int,
    total_chars: int,
) -> TranslateEntityResponse:
    """Estimate cost via toolbox /estimate/ endpoint."""
    mapped_targets = [map_to_provider_code(lang) for lang in target_languages]
    estimate = client.estimate(items=items, target_languages=mapped_targets, provider=provider)

    per_language = []
    for i, lang in enumerate(target_languages):
        per_lang_data = estimate.get("per_language", [])
        cost = per_lang_data[i].get("estimated_cost_usd") if i < len(per_lang_data) else None
        per_language.append(
            LanguageCostEstimate(
                language=lang,
                items=len(items),
                chars=total_chars,
                cost_usd=Decimal(str(cost)) if cost else None,
            )
        )

    total_cost = Decimal(str(estimate.get("total_cost_usd", 0))) if estimate.get("total_cost_usd") else None

    return TranslateEntityResponse(
        entity_type=entity_type,
        entity_id=str(entity_id),
        dry_run=True,
        translations_applied=None,
        skipped_items=skipped,
        target_languages=target_languages,
        total_chars=total_chars * len(target_languages),
        cost_usd=total_cost,
        per_language=per_language,
    )


def _create_jobs(
    client: ToolboxClient,
    items: list[dict],
    target_languages: list[str],
    mapped_source: str,
    provider: str | None,
    formality: str | None,
    context: str | None,
    entity_type: str,
    channel_idx: str,
    total_chars: int,
) -> BulkTranslateJobResponse:
    """Create async jobs on toolbox + dispatch Celery polling tasks.

    Used by both single-entity and bulk translate — unified job flow.
    """
    from django_pim_translator.tasks.apply_job import poll_and_apply_job

    job_ids: list[str] = []
    total_estimated_cost = Decimal("0")

    for target_lang in target_languages:
        mapped_target = map_to_provider_code(target_lang)

        job = client.create_job(
            items=items,
            target_language=mapped_target,
            source_language=mapped_source,
            provider=provider,
            formality=formality,
            context=context,
            metadata={"entity_type": entity_type, "channel_idx": channel_idx, "target_language": target_lang},
        )

        job_id = job.get("id", "")
        job_ids.append(job_id)

        estimated = job.get("estimated_cost_usd")
        if estimated:
            total_estimated_cost += Decimal(str(estimated))

        poll_and_apply_job.delay(
            job_id=job_id,
            entity_type=entity_type,
            channel_idx=channel_idx,
            target_language=target_lang,
        )

    return BulkTranslateJobResponse(
        entity_type=entity_type,
        job_ids=job_ids,
        estimated_items=len(items),
        estimated_cost_usd=total_estimated_cost,
        status="pending",
        target_languages=target_languages,
    )


def translate_bulk(
    channel_idx: str,
    entity_type: str,
    target_languages: list[str],
    source_language: str | None = None,
    entity_ids: list[int] | None = None,
    provider: str | None = None,
    formality: str | None = None,
    context: str | None = None,
    dry_run: bool = False,
    force: bool = False,
) -> BulkTranslateJobResponse | BulkTranslateEstimateResponse:
    """Bulk translate all entities of a type in channel. Or estimate if dry_run=True.

    When force=False (default), items already translated in a target language are skipped.
    When force=True, all items are re-translated regardless of existing translations.
    """
    source_lang = _resolve_source_language(channel_idx, source_language)

    extractor_fn = EXTRACTORS.get(entity_type)
    if not extractor_fn:
        raise ValueError(f"Unknown entity type: {entity_type}")

    extract_kwargs: dict = {"source_language": source_lang, "include_existing_langs": not force}
    if entity_type in ("product", "category"):
        extract_kwargs["channel_idx"] = channel_idx
    if entity_ids:
        extract_kwargs["entity_ids"] = entity_ids

    all_items, _skipped = extractor_fn(**extract_kwargs)

    # Build per-language item lists, filtering out already-translated items when force=False.
    items_per_lang: dict[str, list[dict]] = {}
    for lang in target_languages:
        if force:
            items_per_lang[lang] = all_items
        else:
            items_per_lang[lang] = [
                {k: v for k, v in item.items() if k != "_existing_langs"}
                for item in all_items
                if lang not in item.get("_existing_langs", [])
            ]

    mapped_source = map_to_provider_code(source_lang)

    with ToolboxClient(channel_idx) as client:
        if dry_run:
            return _estimate_bulk(
                client, items_per_lang, target_languages, provider, entity_type, force, all_items, channel_idx
            )
        return _create_jobs_bulk(
            client,
            items_per_lang,
            target_languages,
            mapped_source,
            provider,
            formality,
            context,
            entity_type,
            channel_idx,
        )


def _estimate_bulk_forced(
    client: ToolboxClient,
    all_items: list[dict],
    target_languages: list[str],
    provider: str | None,
) -> tuple[list[LanguageCostEstimate], int, int]:
    """Estimate when force=True — single toolbox call, same items for all languages."""
    total_chars = sum(len(item["text"]) for item in all_items)
    mapped_targets = [map_to_provider_code(lang) for lang in target_languages]
    estimate = client.estimate(items=all_items, target_languages=mapped_targets, provider=provider)

    per_language: list[LanguageCostEstimate] = []
    per_lang_data = estimate.get("per_language", [])
    for i, lang in enumerate(target_languages):
        cost = per_lang_data[i].get("estimated_cost_usd") if i < len(per_lang_data) else None
        per_language.append(
            LanguageCostEstimate(
                language=lang,
                items=len(all_items),
                chars=total_chars,
                cost_usd=Decimal(str(cost)) if cost else None,
            )
        )

    return per_language, len(all_items), total_chars * len(target_languages)


def _estimate_bulk_filtered(
    items_per_lang: dict[str, list[dict]],
    target_languages: list[str],
    provider: str | None,
    channel_idx: str,
) -> tuple[list[LanguageCostEstimate], int, int]:
    """Estimate when force=False — parallel per-language toolbox calls."""

    def _estimate_lang(lang: str) -> LanguageCostEstimate:
        lang_items = items_per_lang[lang]
        lang_chars = sum(len(item["text"]) for item in lang_items)
        if not lang_items:
            return LanguageCostEstimate(language=lang, items=0, chars=0, cost_usd=Decimal("0"))
        mapped_target = map_to_provider_code(lang)
        with ToolboxClient(channel_idx) as thread_client:
            estimate = thread_client.estimate(items=lang_items, target_languages=[mapped_target], provider=provider)
        per_lang_data = estimate.get("per_language", [])
        cost = per_lang_data[0].get("estimated_cost_usd") if per_lang_data else None
        return LanguageCostEstimate(
            language=lang,
            items=len(lang_items),
            chars=lang_chars,
            cost_usd=Decimal(str(cost)) if cost else Decimal("0"),
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        per_language = list(executor.map(_estimate_lang, target_languages, timeout=120))

    total_items = sum(r.items for r in per_language)
    total_chars = sum(r.chars for r in per_language)
    return per_language, total_items, total_chars


def _estimate_bulk(
    client: ToolboxClient,
    items_per_lang: dict[str, list[dict]],
    target_languages: list[str],
    provider: str | None,
    entity_type: str,
    force: bool,
    all_items: list[dict],
    channel_idx: str = "",
) -> BulkTranslateEstimateResponse:
    """Estimate bulk cost via toolbox /estimate/."""
    if force:
        per_language, total_items, total_chars = _estimate_bulk_forced(client, all_items, target_languages, provider)
    else:
        per_language, total_items, total_chars = _estimate_bulk_filtered(
            items_per_lang, target_languages, provider, channel_idx
        )

    total_cost = sum((r.cost_usd or Decimal("0")) for r in per_language)

    return BulkTranslateEstimateResponse(
        entity_type=entity_type,
        estimated_items=total_items,
        total_chars=total_chars,
        estimated_cost_usd=total_cost if total_cost else None,
        target_languages=target_languages,
        per_language=per_language,
    )


def _create_jobs_bulk(
    client: ToolboxClient,
    items_per_lang: dict[str, list[dict]],
    target_languages: list[str],
    mapped_source: str,
    provider: str | None,
    formality: str | None,
    context: str | None,
    entity_type: str,
    channel_idx: str,
) -> BulkTranslateJobResponse:
    """Create async jobs per target language, skipping languages with no items to translate."""
    from django_pim_translator.tasks.apply_job import poll_and_apply_job

    job_ids: list[str] = []
    total_estimated_cost = Decimal("0")
    total_items = 0

    for target_lang in target_languages:
        lang_items = items_per_lang[target_lang]
        if not lang_items:
            logger.info("translate_bulk: skipping %s for %s — no items to translate", entity_type, target_lang)
            continue

        mapped_target = map_to_provider_code(target_lang)
        job = client.create_job(
            items=lang_items,
            target_language=mapped_target,
            source_language=mapped_source,
            provider=provider,
            formality=formality,
            context=context,
            metadata={"entity_type": entity_type, "channel_idx": channel_idx, "target_language": target_lang},
        )

        job_id = job.get("id", "")
        job_ids.append(job_id)
        total_items = max(total_items, len(lang_items))

        estimated = job.get("estimated_cost_usd")
        if estimated:
            total_estimated_cost += Decimal(str(estimated))

        poll_and_apply_job.delay(
            job_id=job_id,
            entity_type=entity_type,
            channel_idx=channel_idx,
            target_language=target_lang,
        )

    return BulkTranslateJobResponse(
        entity_type=entity_type,
        job_ids=job_ids,
        estimated_items=total_items,
        estimated_cost_usd=total_estimated_cost,
        status="pending",
        target_languages=target_languages,
    )
