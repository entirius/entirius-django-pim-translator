# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Management command for bulk PIM translation via AI toolbox."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from django_pim_translator.services.extractor import EXTRACTORS
from django_pim_translator.services.translator import translate_bulk, translate_entity


class Command(BaseCommand):
    help = "Translate PIM entities via AI toolbox. Supports single entity or bulk channel translation."

    def add_arguments(self, parser):
        parser.add_argument("--channel", required=True, help="PIM Channel idx (e.g., europe)")
        parser.add_argument(
            "--type",
            required=True,
            choices=list(EXTRACTORS.keys()),
            help="Entity type to translate",
        )
        parser.add_argument("--source", required=True, help="Source language code (e.g., en)")
        parser.add_argument("--target", nargs="+", required=True, help="Target language codes (e.g., de fr)")
        parser.add_argument("--sku", help="Translate single product by SKU")
        parser.add_argument("--idx", help="Translate single entity by idx (feature, category, etc.)")
        parser.add_argument("--provider", help="Provider override (deepl or gemini)")
        parser.add_argument("--formality", choices=["more", "less", "default"], help="Formality level")
        parser.add_argument("--context", help="Domain context (e.g., 'E-commerce for baby products')")
        parser.add_argument("--estimate-only", action="store_true", help="Show cost estimate without translating")

    def handle(self, *args, **options):
        channel = options["channel"]
        entity_type = options["type"]
        source = options["source"]
        targets = options["target"]
        provider = options.get("provider")
        formality = options.get("formality")
        context = options.get("context")
        dry_run = options["estimate_only"]

        entity_id = options.get("sku") or options.get("idx")

        if entity_id:
            self._translate_single(
                channel, entity_type, entity_id, targets, source, provider, formality, context, dry_run
            )
        else:
            self._translate_bulk(channel, entity_type, targets, source, provider, formality, context, dry_run)

    def _translate_single(
        self, channel, entity_type, entity_id, targets, source, provider, formality, context, dry_run
    ):
        self.stdout.write(
            f"{'Estimating' if dry_run else 'Translating'} {entity_type} {entity_id} → {', '.join(targets)}"
        )

        result = translate_entity(
            channel_idx=channel,
            entity_type=entity_type,
            entity_id=entity_id,
            target_languages=targets,
            source_language=source,
            provider=provider,
            formality=formality,
            context=context,
            dry_run=dry_run,
        )

        if dry_run:
            self.stdout.write(f"Estimated cost: ${result.cost_usd or 0}")
            for lang_est in result.per_language:
                self.stdout.write(
                    f"  {lang_est.language}: {lang_est.items} items, {lang_est.chars} chars, ${lang_est.cost_usd or 0}"
                )
        else:
            self.stdout.write(
                self.style.SUCCESS(f"Translated {result.translations_applied} fields, cost: ${result.cost_usd or 0}")
            )
            self.stdout.write(f"Skipped: {result.skipped_items}")

    def _translate_bulk(self, channel, entity_type, targets, source, provider, formality, context, dry_run):
        self.stdout.write(
            f"{'Estimating' if dry_run else 'Submitting'} bulk {entity_type} translation → {', '.join(targets)}"
        )

        result = translate_bulk(
            channel_idx=channel,
            entity_type=entity_type,
            target_languages=targets,
            source_language=source,
            provider=provider,
            formality=formality,
            context=context,
            dry_run=dry_run,
        )

        if dry_run:
            self.stdout.write(f"Estimated: {result.estimated_items} items, ${result.estimated_cost_usd or 0}")
            for lang_est in result.per_language:
                self.stdout.write(
                    f"  {lang_est.language}: {lang_est.items} items, {lang_est.chars} chars, ${lang_est.cost_usd or 0}"
                )
        else:
            self.stdout.write(self.style.SUCCESS(f"Created {len(result.job_ids)} job(s): {', '.join(result.job_ids)}"))
            self.stdout.write(f"Estimated items: {result.estimated_items}, cost: ${result.estimated_cost_usd or 0}")
            self.stdout.write("Celery tasks dispatched — translations will be applied on completion.")
