# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""`AI_TOOLBOX_ENABLED = False`: the API answers 503 `AI_TOOLBOX_DISABLED`, the apply task returns quietly."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django_utils.toolbox import ToolboxDisabledError, ToolboxNotConfiguredError

from django_pim_translator.clients import ToolboxClient
from django_pim_translator.tasks.apply_job import poll_and_apply_job

BASE = "/api/pim-translator/v2/admin/test-shop"
JOB = ("job-1", "product", "test-shop", "de")
DISABLED = (503, "AI_TOOLBOX_DISABLED")


def _answer(response) -> tuple[int, str]:
    return response.status_code, response.json()["error"]


@pytest.mark.django_db
def test_disabled_entity_translate_answers_503(admin_client):
    payload = {"target_languages": ["de"], "dry_run": True}

    with patch("django_pim_translator.api.views.translator.translate_entity", side_effect=ToolboxDisabledError()):
        response = admin_client.post(f"{BASE}/products/SKU-001/translate/", payload, format="json")

    assert _answer(response) == DISABLED
    assert response.json()["message"] == "AI features are switched off on this instance."


@pytest.mark.django_db
def test_disabled_job_list_answers_503(admin_client, settings):
    settings.AI_TOOLBOX_ENABLED = False

    assert _answer(admin_client.get(f"{BASE}/bulk/jobs/")) == DISABLED


@pytest.mark.django_db
def test_unconfigured_job_list_keeps_its_code(admin_client, settings):
    settings.AI_TOOLBOX_API_KEY = ""

    assert _answer(admin_client.get(f"{BASE}/bulk/jobs/")) == (503, "AI_TOOLBOX_NOT_CONFIGURED")


def test_disabled_apply_task_returns_without_polling(settings, caplog):
    settings.AI_TOOLBOX_ENABLED = False

    with patch.object(ToolboxClient, "get_job") as get_job, caplog.at_level("WARNING", logger="process"):
        assert poll_and_apply_job.run(*JOB) is None

    assert not get_job.called
    assert "Translation job job-1 not polled: AI toolbox disabled" in caplog.text


def test_unconfigured_apply_task_still_raises(settings):
    settings.AI_TOOLBOX_API_KEY = ""

    with pytest.raises(ToolboxNotConfiguredError):
        poll_and_apply_job.run(*JOB)


def test_configured_apply_task_still_polls():
    with patch.object(ToolboxClient, "get_job", return_value={"status": "failed"}) as get_job:
        assert poll_and_apply_job.run(*JOB) is None

    get_job.assert_called_once_with("job-1")
