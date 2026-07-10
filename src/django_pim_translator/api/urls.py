# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""URL patterns for django-pim-translator API."""

from django.urls import path

from django_pim_translator.api.views import BulkJobViewSet, BulkTranslateView, EntityTranslateView
from django_pim_translator.settings import EntityType

app_name = "pim_translator_api"

urlpatterns = [
    # Sync — single entity (shared view, entity_type resolved from initkwargs).
    path(
        "products/<str:sku>/translate/",
        EntityTranslateView.as_view({"post": "create"}, entity_type=EntityType.PRODUCT, id_kwarg="sku"),
        name="product-translate",
    ),
    path(
        "categories/<str:idx>/translate/",
        EntityTranslateView.as_view({"post": "create"}, entity_type=EntityType.CATEGORY, id_kwarg="idx"),
        name="category-translate",
    ),
    path(
        "features/<str:idx>/translate/",
        EntityTranslateView.as_view({"post": "create"}, entity_type=EntityType.FEATURE, id_kwarg="idx"),
        name="feature-translate",
    ),
    path(
        "attributes/<str:feature_idx>/<str:idx>/translate/",
        EntityTranslateView.as_view({"post": "create"}, entity_type=EntityType.ATTRIBUTE, id_kwarg="idx"),
        name="attribute-translate",
    ),
    # Bulk — translate or estimate (dry_run=true).
    path("bulk/translate/", BulkTranslateView.as_view({"post": "create"}), name="bulk-translate"),
    path("bulk/jobs/", BulkJobViewSet.as_view({"get": "list"}), name="bulk-job-list"),
    path("bulk/jobs/<str:pk>/", BulkJobViewSet.as_view({"get": "retrieve"}), name="bulk-job-detail"),
]
