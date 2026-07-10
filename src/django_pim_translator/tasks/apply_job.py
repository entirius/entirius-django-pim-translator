# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Celery task: poll toolbox HTTP API for job completion, apply translations to PIM."""

from __future__ import annotations

import logging

from celery import shared_task
from django.db import DatabaseError, OperationalError

from django_pim_translator.clients import ToolboxClient, ToolboxError
from django_pim_translator.services.applicator import APPLICATORS

logger = logging.getLogger("process")


@shared_task(bind=True, max_retries=120, default_retry_delay=30)
def poll_and_apply_job(
    self,
    job_id: str,
    entity_type: str,
    channel_idx: str,
    target_language: str,
) -> None:
    """Poll toolbox job status via HTTP every 30s.

    When completed: fetch results via HTTP, apply translations to PIM (local ORM).
    Max retries=120 x 30s = 1 hour timeout for bulk jobs.
    """
    with ToolboxClient(channel_idx, max_retries=1) as client:
        try:
            job = client.get_job(job_id)
        except ToolboxError as exc:
            logger.error("Failed to poll job %s: %s", job_id, exc.message)
            raise self.retry(exc=exc)

        job_status = job.get("status")

        if job_status in ("pending", "running"):
            raise self.retry()

        if job_status == "completed":
            try:
                _apply_results(client, job_id, entity_type, channel_idx, target_language)
            except (OperationalError, DatabaseError) as exc:
                logger.warning("Transient DB error applying job %s, will retry: %s", job_id, exc)
                raise self.retry(exc=exc)
            except (ValueError, KeyError) as exc:
                logger.error("Permanent error applying job %s — will not retry: %s", job_id, exc)

        if job_status == "failed":
            logger.error("Translation job %s failed: %s", job_id, job.get("error_message", "unknown"))


def _apply_results(
    client: ToolboxClient,
    job_id: str,
    entity_type: str,
    channel_idx: str,
    target_language: str,
) -> None:
    """Fetch all pages of job results and apply to PIM."""
    apply_fn = APPLICATORS.get(entity_type)
    if not apply_fn:
        logger.error("No applicator for entity_type=%s, job=%s", entity_type, job_id)
        return

    page = 1
    total_applied = 0

    while True:
        result_page = client.get_job_results(job_id, page=page, page_size=100)
        results = result_page.get("results", [])
        if not results:
            break

        apply_kwargs: dict = {"items": results, "target_language": target_language}
        if entity_type == "category":
            apply_kwargs["channel_idx"] = channel_idx

        apply_result = apply_fn(**apply_kwargs)
        total_applied += apply_result.updated

        if not result_page.get("next"):
            break
        page += 1

    logger.info("Applied %d translations for job %s (%s → %s)", total_applied, job_id, entity_type, target_language)
