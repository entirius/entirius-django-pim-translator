# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""DRF views for django-pim-translator.

Auth: standard Volkanos JWT + IsAdminUser (NOT toolbox auth).
Outbound calls to toolbox use API key via ToolboxClient.
"""

from __future__ import annotations

import logging

from django_utils.api.v2_errors import raise_pydantic_as_drf
from django_utils_translator.clients import ToolboxError
from django_utils_translator.views import handle_toolbox_error
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from pydantic import ValidationError
from rest_framework import status, viewsets
from rest_framework.permissions import IsAdminUser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication

from django_pim_translator.clients import ToolboxClient
from django_pim_translator.schemas.requests import BulkTranslateRequest, TranslateEntityRequest
from django_pim_translator.schemas.responses import (
    BulkTranslateEstimateResponse,
    BulkTranslateJobResponse,
)
from django_pim_translator.services import translator

logger = logging.getLogger("process")

_CHANNEL_PARAM = OpenApiParameter(
    name="shop_idx", location="path", description="PIM Channel identifier", required=True, type=str
)


@extend_schema_view(
    create=extend_schema(
        tags=["Translations"],
        summary="Translate entity",
        description="Translate all translatable fields of a PIM entity to target languages. "
        "Set dry_run=true for cost estimate without calling the provider.",
        parameters=[_CHANNEL_PARAM],
        request=TranslateEntityRequest,
        responses={
            200: {"description": "Dry-run estimate"},
            202: BulkTranslateJobResponse,
            400: {"description": "Validation error"},
            402: {"description": "Budget exceeded (dry_run=false only)"},
            404: {"description": "Entity or channel not found"},
            502: {"description": "Provider API error (dry_run=false only)"},
        },
    ),
)
class EntityTranslateView(viewsets.ViewSet):
    """Translate (or estimate) a single PIM entity's translatable fields.

    Shared view — entity_type resolved from URL initkwargs.
    """

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUser]
    access_area = "pim_translator.translate"

    # Set by urls.py initkwargs.
    entity_type: str = ""
    id_kwarg: str = ""

    def create(self, request: Request, shop_idx: str, **kwargs) -> Response:
        try:
            data = TranslateEntityRequest(**request.data)
        except ValidationError as exc:
            raise_pydantic_as_drf(exc)

        entity_id = kwargs.get(self.id_kwarg) or kwargs.get("sku") or kwargs.get("idx")
        if not entity_id:
            return Response(
                {"error": "VALIDATION_ERROR", "message": "Entity identifier missing from URL."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            result = translator.translate_entity(
                channel_idx=shop_idx,
                entity_type=self.entity_type,
                entity_id=entity_id,
                target_languages=data.target_languages,
                source_language=data.source_language,
                provider=data.provider,
                formality=data.formality,
                context=data.context,
                dry_run=data.dry_run,
            )
        except ValueError as exc:
            return Response({"error": "VALIDATION_ERROR", "message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except ToolboxError as exc:
            return handle_toolbox_error(exc)

        http_status = status.HTTP_200_OK if data.dry_run else status.HTTP_202_ACCEPTED
        return Response(result.model_dump(), status=http_status)


@extend_schema_view(
    create=extend_schema(
        tags=["Translation Jobs"],
        summary="Bulk translate entities",
        description="Translate all entities of a given type in the channel. "
        "Set dry_run=true for cost estimate without creating a job.",
        parameters=[_CHANNEL_PARAM],
        request=BulkTranslateRequest,
        responses={
            200: BulkTranslateEstimateResponse,
            202: BulkTranslateJobResponse,
            400: {"description": "Validation error"},
            402: {"description": "Budget exceeded (dry_run=false only)"},
            429: {"description": "Concurrent job limit (dry_run=false only)"},
        },
    ),
)
class BulkTranslateView(viewsets.ViewSet):
    """Bulk translate (or estimate) all entities of a type in a channel."""

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUser]
    access_area = "pim_translator.translate"

    def create(self, request: Request, shop_idx: str) -> Response:
        try:
            data = BulkTranslateRequest(**request.data)
        except ValidationError as exc:
            raise_pydantic_as_drf(exc)

        try:
            result = translator.translate_bulk(
                channel_idx=shop_idx,
                entity_type=data.entity_type,
                target_languages=data.target_languages,
                source_language=data.source_language,
                entity_ids=data.entity_ids,
                provider=data.provider,
                formality=data.formality,
                context=data.context,
                dry_run=data.dry_run,
                force=data.force,
            )
        except ValueError as exc:
            return Response({"error": "VALIDATION_ERROR", "message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except ToolboxError as exc:
            return handle_toolbox_error(exc)

        http_status = status.HTTP_200_OK if data.dry_run else status.HTTP_202_ACCEPTED
        return Response(result.model_dump(), status=http_status)


@extend_schema_view(
    list=extend_schema(
        tags=["Translation Jobs"],
        summary="List translation jobs",
        description="List translation jobs for this channel (proxied from toolbox).",
        parameters=[
            _CHANNEL_PARAM,
            OpenApiParameter(name="status", location="query", description="Filter by job status", required=False),
        ],
        responses={200: {"description": "Paginated job list from toolbox"}},
    ),
    retrieve=extend_schema(
        tags=["Translation Jobs"],
        summary="Get job detail",
        description="Get translation job detail (proxied from toolbox).",
        parameters=[
            _CHANNEL_PARAM,
            OpenApiParameter(name="pk", location="path", description="Job UUID", required=True),
        ],
        responses={200: {"description": "Job detail"}, 404: {"description": "Job not found"}},
    ),
)
class BulkJobViewSet(viewsets.ViewSet):
    """Proxy job status from toolbox — no local state."""

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUser]
    access_area = "pim_translator.translate"

    def list(self, request: Request, shop_idx: str) -> Response:
        status_filter = request.query_params.get("status")
        try:
            page = int(request.query_params.get("page", 1))
        except (ValueError, TypeError):
            return Response(
                {"error": "VALIDATION_ERROR", "message": "page must be an integer."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with ToolboxClient(shop_idx) as client:
                result = client.list_jobs(status=status_filter, page=page)
        except ToolboxError as exc:
            return handle_toolbox_error(exc)

        return Response(result, status=status.HTTP_200_OK)

    def retrieve(self, request: Request, shop_idx: str, pk: str | None = None) -> Response:
        try:
            with ToolboxClient(shop_idx) as client:
                result = client.get_job(pk)
        except ToolboxError as exc:
            return handle_toolbox_error(exc)

        return Response(result, status=status.HTTP_200_OK)
