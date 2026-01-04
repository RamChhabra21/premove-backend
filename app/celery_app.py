from celery import Celery

celery_app = Celery('tasks', broker='redis://localhost:6379/0')

# celery_app.autodiscover_tasks(["celery_app.celery_app"])
from app.tasks import tasks