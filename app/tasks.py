from celery import shared_task
import httpx
import os

NOTIFICATION_SERVICE_URL = os.getenv("NOTIFICATION_SERVICE_URL", "http://web:8000/api/notifications/")
ANALYTICS_BROKER_URL = os.getenv("ANALYTICS_BROKER_URL", "http://analytics-service:8000/api/events/")

@shared_task
def notify_project_owner(project_id: int, author_id: int, text: str):
    """
    Надсилає повідомлення власнику проекту про новий коментар
    """
    try:
        payload = {
            "project_id": project_id,
            "author_id": author_id,
            "text": text
        }
        httpx.post(f"{NOTIFICATION_SERVICE_URL}", json=payload, timeout=5.0)
    except Exception as e:
        print(f"[notify_project_owner] Failed: {e}")

@shared_task
def publish_event(event_type: str, payload: dict):
    """
    Надсилає подію до аналітики
    """
    try:
        httpx.post(f"{ANALYTICS_BROKER_URL}", json={
            "event_type": event_type,
            "payload": payload
        }, timeout=5.0)
    except Exception as e:
        print(f"[publish_event] Failed: {e}")
