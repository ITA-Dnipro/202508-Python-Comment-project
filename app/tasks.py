import logging
from celery import shared_task
import httpx
import os

NOTIFICATION_SERVICE_URL = os.getenv("NOTIFICATION_SERVICE_URL", "http://web:8000/api/notifications/")
ANALYTICS_BROKER_URL = os.getenv("ANALYTICS_BROKER_URL", "http://analytics-service:8000/api/events/")

logger = logging.getLogger(__name__)

@shared_task
def notify_project_owner(project_id: int, author_id: int, text: str):
    """
    Sends a notification to the project owner about a new comment
    """
    try:
        payload = {
            "project_id": project_id,
            "author_id": author_id,
            "text": text
        }
        httpx.post(f"{NOTIFICATION_SERVICE_URL}", json=payload, timeout=5.0)
    except Exception as e:
        logger.exception(f"[notify_project_owner] Failed to send notification: {e}")

@shared_task
def publish_event(event_type: str, payload: dict):
    """
    Sends an event to the analytics broker
    """
    try:
        httpx.post(f"{ANALYTICS_BROKER_URL}", json={
            "event_type": event_type,
            "payload": payload
        }, timeout=5.0)
    except Exception as e:
        logger.exception(f"[publish_event] Failed to publish event: {e}")
