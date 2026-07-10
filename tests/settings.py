# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import os

import dj_database_url

# PATHS — django_pim reads TMP_DIR at import time
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.abspath(os.path.join(BASE_DIR, "."))
TMP_DIR = os.path.join(DATA_DIR, "tmp/pim-translator-test/")
STATIC_ROOT = os.path.join(DATA_DIR, "static/pim-translator-test/")
MEDIA_ROOT = os.path.join(DATA_DIR, "media/pim-translator-test/")

# Postgres required (django_pim); CI provides DATABASE_URL, locally point it at any
# postgres 15+ (default matches the CI service).
DATABASES = {
    "default": dj_database_url.config(default="postgresql://postgres:postgres@localhost:5432/test"),
}

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "rest_framework",
    "django_regional",
    "django_pim",
    "django_pim_translator",
]

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAdminUser",
    ],
}

SECRET_KEY = "test-secret-key"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True

ROOT_URLCONF = "django_pim_translator.urls"

# Toolbox test settings — overridden in tests via respx mocking.
AI_TOOLBOX_BASE_URL = "https://test-toolbox.internal:8000"
AI_TOOLBOX_API_KEY = "ent_test_fake_key_for_testing"
