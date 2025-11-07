import logging
import httpx
from celery import Celery, shared_task
from app.config import settings

logger = logging.getLogger(__name__)

# === CELERY CONFIG ===
app = Celery(
    "comment_service",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

app.conf.task_default_queue = "comments"

# -------------------------------------------------------
# Background tasks
# -------------------------------------------------------

@shared_task
def notify_project_owner(project_id: int, author_id: int, text: str):
    """Sends a notification to the project owner"""
    try:
        payload = {
            "project_id": project_id,
            "author_id": author_id,
            "text": text,
        }
        httpx.post(settings.NOTIFICATION_SERVICE_URL, json=payload, timeout=5.0)
        logger.info(f"Notification sent for project {project_id}")
    except Exception as e:
        logger.exception(f"[notify_project_owner] Failed to send notification: {e}")


@shared_task
def publish_event(event_type: str, payload: dict):
    """Publishes event to analytics"""
    try:
        httpx.post(
            settings.ANALYTICS_BROKER_URL,
            json={"event_type": event_type, "payload": payload},
            timeout=5.0,
        )
        logger.info(f"Event '{event_type}' published.")
    except Exception as e:
        logger.exception(f"[publish_event] Failed to publish event: {e}")
