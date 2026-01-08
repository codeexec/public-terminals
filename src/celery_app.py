"""
Celery application configuration for background tasks
"""

from celery import Celery
from celery.schedules import crontab
from src.config import settings

# Create Celery app
celery_app = Celery(
    "terminal_server", broker=settings.REDIS_URL, backend=settings.REDIS_URL
)

# Celery configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)

# Periodic task schedule
celery_app.conf.beat_schedule = {
    "cleanup-expired-terminals": {
        "task": "src.services.cleanup_service.run_cleanup_task",
        "schedule": crontab(
            minute=f"*/{settings.CLEANUP_INTERVAL_MINUTES}"
        ),  # Every N minutes
    },
}

# Auto-discover tasks
celery_app.autodiscover_tasks(["src.services"])

# Explicitly import tasks to ensure they are registered
import src.services.cleanup_service
