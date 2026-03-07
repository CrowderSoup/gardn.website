# gardn/celery.py
from __future__ import annotations

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "gardn.settings")

app = Celery("gardn")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
