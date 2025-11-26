import logging
import httpx
from app.celery_app import celery_app
from app.config import settings

logger = logging.getLogger(__name__)

@celery_app.task(name="notify_project_owner")
def notify_project_owner(project_id: int, author_id: int, text: str):
    """Send notification to project owner"""
    try:
        payload = {
            "project_id": project_id,
            "author_id": author_id,
            "text": text,
        }
        httpx.post(
            settings.NOTIFICATION_SERVICE_URL,
            json=payload,
            timeout=5.0,
        )
        logger.info(f"Notification sent for project {project_id}")
    except Exception as e:
        logger.exception(f"[notify_project_owner] Failed: {e}")


@celery_app.task(name="publish_event")
def publish_event(event_type: str, payload: dict):
    """Publish comment_created event to analytics"""
    try:
        httpx.post(
            settings.ANALYTICS_BROKER_URL,
            json={"event_type": event_type, "payload": payload},
            timeout=5.0,
        )
        logger.info(f"Event '{event_type}' published.")
    except Exception as e:
        logger.exception(f"[publish_event] Failed: {e}")
