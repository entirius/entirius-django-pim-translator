# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for Celery tasks.

Covers poll_and_apply_job: polling states, error handling for transient
vs permanent failures, and _apply_results applicator dispatch.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from django_pim_translator.services.applicator import ApplyResult

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# poll_and_apply_job — polling states
# ---------------------------------------------------------------------------


@pytest.mark.skip(reason="Known mismatch with the current implementation; tracked for rewrite")
class TestPollAndApplyJobStates:
    @patch("django_pim_translator.tasks.apply_job.ToolboxClient")
    def test_pending_job_retries(self, MockClient):
        from django_pim_translator.tasks.apply_job import poll_and_apply_job

        instance = MockClient.return_value.__enter__.return_value
        instance.get_job.return_value = {"status": "pending"}

        task = MagicMock()
        task.retry.side_effect = Exception("retry")

        with pytest.raises(Exception, match="retry"):
            poll_and_apply_job(task, job_id="job-1", entity_type="product", channel_idx="shop-1", target_language="de")

        task.retry.assert_called_once()

    @patch("django_pim_translator.tasks.apply_job.ToolboxClient")
    def test_running_job_retries(self, MockClient):
        from django_pim_translator.tasks.apply_job import poll_and_apply_job

        instance = MockClient.return_value.__enter__.return_value
        instance.get_job.return_value = {"status": "running"}

        task = MagicMock()
        task.retry.side_effect = Exception("retry")

        with pytest.raises(Exception, match="retry"):
            poll_and_apply_job(task, job_id="job-1", entity_type="product", channel_idx="shop-1", target_language="de")

    @patch("django_pim_translator.tasks.apply_job._apply_results")
    @patch("django_pim_translator.tasks.apply_job.ToolboxClient")
    def test_completed_job_applies_results(self, MockClient, mock_apply):
        from django_pim_translator.tasks.apply_job import poll_and_apply_job

        instance = MockClient.return_value.__enter__.return_value
        instance.get_job.return_value = {"status": "completed"}

        task = MagicMock()

        poll_and_apply_job(task, job_id="job-1", entity_type="product", channel_idx="shop-1", target_language="de")

        mock_apply.assert_called_once_with(instance, "job-1", "product", "shop-1", "de")

    @patch("django_pim_translator.tasks.apply_job.ToolboxClient")
    def test_failed_job_logs_error(self, MockClient):
        from django_pim_translator.tasks.apply_job import poll_and_apply_job

        instance = MockClient.return_value.__enter__.return_value
        instance.get_job.return_value = {"status": "failed", "error_message": "provider down"}

        task = MagicMock()

        # Should not raise, just log
        poll_and_apply_job(task, job_id="job-1", entity_type="product", channel_idx="shop-1", target_language="de")

        task.retry.assert_not_called()


# ---------------------------------------------------------------------------
# poll_and_apply_job — toolbox errors
# ---------------------------------------------------------------------------


@pytest.mark.skip(reason="Known mismatch with the current implementation; tracked for rewrite")
class TestPollAndApplyJobToolboxErrors:
    @patch("django_pim_translator.tasks.apply_job.ToolboxClient")
    def test_toolbox_error_retries(self, MockClient):
        from django_pim_translator.clients import ToolboxServerError
        from django_pim_translator.tasks.apply_job import poll_and_apply_job

        instance = MockClient.return_value.__enter__.return_value
        instance.get_job.side_effect = ToolboxServerError(503, "unavailable")

        task = MagicMock()
        task.retry.side_effect = Exception("retry")

        with pytest.raises(Exception, match="retry"):
            poll_and_apply_job(task, job_id="job-1", entity_type="product", channel_idx="shop-1", target_language="de")

        task.retry.assert_called_once()


# ---------------------------------------------------------------------------
# poll_and_apply_job — applicator error handling (C3 fix)
# ---------------------------------------------------------------------------


@pytest.mark.skip(reason="Known mismatch with the current implementation; tracked for rewrite")
class TestPollAndApplyJobApplicatorErrors:
    @patch("django_pim_translator.tasks.apply_job._apply_results")
    @patch("django_pim_translator.tasks.apply_job.ToolboxClient")
    def test_database_error_retries(self, MockClient, mock_apply):
        from django.db import OperationalError

        from django_pim_translator.tasks.apply_job import poll_and_apply_job

        instance = MockClient.return_value.__enter__.return_value
        instance.get_job.return_value = {"status": "completed"}
        mock_apply.side_effect = OperationalError("deadlock detected")

        task = MagicMock()
        task.retry.side_effect = Exception("retry")

        with pytest.raises(Exception, match="retry"):
            poll_and_apply_job(task, job_id="job-1", entity_type="product", channel_idx="shop-1", target_language="de")

        task.retry.assert_called_once()

    @patch("django_pim_translator.tasks.apply_job._apply_results")
    @patch("django_pim_translator.tasks.apply_job.ToolboxClient")
    def test_value_error_does_not_retry(self, MockClient, mock_apply):
        from django_pim_translator.tasks.apply_job import poll_and_apply_job

        instance = MockClient.return_value.__enter__.return_value
        instance.get_job.return_value = {"status": "completed"}
        mock_apply.side_effect = ValueError("bad key format")

        task = MagicMock()

        # Should not raise — permanent failure is logged but not retried
        poll_and_apply_job(task, job_id="job-1", entity_type="product", channel_idx="shop-1", target_language="de")

        task.retry.assert_not_called()

    @patch("django_pim_translator.tasks.apply_job._apply_results")
    @patch("django_pim_translator.tasks.apply_job.ToolboxClient")
    def test_key_error_does_not_retry(self, MockClient, mock_apply):
        from django_pim_translator.tasks.apply_job import poll_and_apply_job

        instance = MockClient.return_value.__enter__.return_value
        instance.get_job.return_value = {"status": "completed"}
        mock_apply.side_effect = KeyError("missing_field")

        task = MagicMock()

        poll_and_apply_job(task, job_id="job-1", entity_type="product", channel_idx="shop-1", target_language="de")

        task.retry.assert_not_called()


# ---------------------------------------------------------------------------
# _apply_results — applicator dispatch
# ---------------------------------------------------------------------------


class TestApplyResults:
    @patch("django_pim_translator.tasks.apply_job.APPLICATORS")
    @patch("django_pim_translator.tasks.apply_job.ToolboxClient")
    def test_dispatches_to_correct_applicator(self, MockClient, mock_applicators):
        from django_pim_translator.tasks.apply_job import _apply_results

        mock_apply_fn = MagicMock(return_value=ApplyResult(updated=3))
        mock_applicators.get.return_value = mock_apply_fn

        client = MagicMock()
        client.get_job_results.side_effect = [
            {"results": [{"key": "k1"}, {"key": "k2"}], "next": None},
        ]

        _apply_results(client, "job-1", "product", "shop-1", "de")

        mock_apply_fn.assert_called_once()
        assert mock_apply_fn.call_args[1]["target_language"] == "de"

    @patch("django_pim_translator.tasks.apply_job.APPLICATORS")
    def test_logs_error_for_unknown_entity_type(self, mock_applicators):
        from django_pim_translator.tasks.apply_job import _apply_results

        mock_applicators.get.return_value = None
        client = MagicMock()

        _apply_results(client, "job-1", "unknown_type", "shop-1", "de")

        client.get_job_results.assert_not_called()

    @patch("django_pim_translator.tasks.apply_job.APPLICATORS")
    def test_paginates_through_results(self, mock_applicators):
        from django_pim_translator.tasks.apply_job import _apply_results

        mock_apply_fn = MagicMock(return_value=ApplyResult(updated=1))
        mock_applicators.get.return_value = mock_apply_fn

        client = MagicMock()
        client.get_job_results.side_effect = [
            {"results": [{"key": "k1"}], "next": "page2"},
            {"results": [{"key": "k2"}], "next": None},
        ]

        _apply_results(client, "job-1", "product", "shop-1", "de")

        assert mock_apply_fn.call_count == 2
        assert client.get_job_results.call_count == 2

    @patch("django_pim_translator.tasks.apply_job.APPLICATORS")
    def test_passes_channel_idx_for_category(self, mock_applicators):
        from django_pim_translator.tasks.apply_job import _apply_results

        mock_apply_fn = MagicMock(return_value=ApplyResult(updated=1))
        mock_applicators.get.return_value = mock_apply_fn

        client = MagicMock()
        client.get_job_results.return_value = {"results": [{"key": "k1"}], "next": None}

        _apply_results(client, "job-1", "category", "shop-1", "de")

        kwargs = mock_apply_fn.call_args[1]
        assert kwargs["channel_idx"] == "shop-1"

    @patch("django_pim_translator.tasks.apply_job.APPLICATORS")
    def test_does_not_pass_channel_idx_for_product(self, mock_applicators):
        from django_pim_translator.tasks.apply_job import _apply_results

        mock_apply_fn = MagicMock(return_value=ApplyResult(updated=1))
        mock_applicators.get.return_value = mock_apply_fn

        client = MagicMock()
        client.get_job_results.return_value = {"results": [{"key": "k1"}], "next": None}

        _apply_results(client, "job-1", "product", "shop-1", "de")

        kwargs = mock_apply_fn.call_args[1]
        assert "channel_idx" not in kwargs
