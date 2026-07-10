# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Import official translations from a JSONL file into PIM (no AI toolbox).

Used to load human/official translations scraped from a sibling site
(e.g. a foreign-language storefront of the same shop), joined by SKU.
Reuses the product applicator, so all write safety is preserved.

    python manage.py import_translations \\
        --channel acme_b2c_pln --target en --file translations.jsonl --dry-run
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from django_pim_translator.services.importer import import_translations, load_jsonl


class Command(BaseCommand):
    help = "Import official translations from a JSONL file into PIM product T9N fields."

    def add_arguments(self, parser):
        parser.add_argument("--channel", required=True, help="PIM Channel idx (e.g., acme_b2c_pln)")
        parser.add_argument("--target", required=True, help="Target language iso2 code (e.g., en)")
        parser.add_argument("--file", required=True, help="Path to JSONL file with {sku, fields}")
        parser.add_argument("--dry-run", action="store_true", help="Preview matches without writing")

    def handle(self, *args, **options):
        try:
            rows = load_jsonl(options["file"])
        except (OSError, ValueError) as exc:
            raise CommandError(str(exc)) from exc

        dry_run = options["dry_run"]
        self.stdout.write(
            f"{'Previewing' if dry_run else 'Importing'} {len(rows)} row(s) "
            f"→ channel '{options['channel']}' target '{options['target']}'"
        )

        report = import_translations(
            channel_idx=options["channel"],
            target_language=options["target"],
            rows=rows,
            dry_run=dry_run,
        )
        self._print_report(report, dry_run)

    def _print_report(self, report, dry_run: bool) -> None:
        self.stdout.write(f"  rows:             {report.rows}")
        self.stdout.write(f"  matched products: {report.matched_products}")
        self.stdout.write(f"  items built:      {report.items_built}")

        if report.unmatched_skus:
            self.stdout.write(
                self.style.WARNING(
                    f"  unmatched SKUs ({len(report.unmatched_skus)}): {', '.join(report.unmatched_skus[:20])}"
                    + (" …" if len(report.unmatched_skus) > 20 else "")
                )
            )
        if report.missing_attr_rows:
            self.stdout.write(
                self.style.WARNING(
                    f"  no PIM attribute row ({len(report.missing_attr_rows)}) — would be skipped: "
                    + ", ".join(report.missing_attr_rows[:20])
                    + (" …" if len(report.missing_attr_rows) > 20 else "")
                )
            )

        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Dry-run: would write {report.items_built - len(report.missing_attr_rows)} field(s)."
                )
            )
        else:
            self.stdout.write(self.style.SUCCESS(f"Applied {report.updated} field(s), skipped {report.skipped}."))
