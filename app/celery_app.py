# app/celery_app.py
from celery import Celery
from app.config import settings

celery_app = Celery(
    "comment_service",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.task_default_queue = "comments"
celery_app.conf.worker_prefetch_multiplier = 1
celery_app.conf.task_acks_late = True

__all__ = ["celery_app"]
