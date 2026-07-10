# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Root URL configuration for django-pim-translator."""

from django.urls import include, path

urlpatterns = [
    path("api/pim-translator/v2/admin/<str:shop_idx>/", include("django_pim_translator.api.urls")),
]
