from celery import Celery
from app.core.config import settings

# Initialize Celery with configuration from settings
celery_app = Celery(
    'premove_tasks',
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND
)

# Configure Celery
celery_app.conf.update(
    # Task execution settings
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    
    # Task time limits
    task_time_limit=settings.CELERY_TASK_TIME_LIMIT,
    task_soft_time_limit=settings.CELERY_TASK_SOFT_TIME_LIMIT,
    
    # Task retry settings
    task_acks_late=True,  # Acknowledge task after completion
    task_reject_on_worker_lost=True,  # Reject task if worker crashes
    
    # Result backend settings
    result_expires=3600,  # Results expire after 1 hour
    result_persistent=True,  # Persist results to backend
    
    # Worker settings
    worker_prefetch_multiplier=1,  # Disable prefetching for fair distribution
    worker_max_tasks_per_child=1000,  # Restart worker after N tasks to prevent memory leaks

    broker_use_ssl={"ssl_cert_reqs": ssl.CERT_NONE},
    redis_backend_use_ssl={"ssl_cert_reqs": ssl.CERT_NONE},
)

# Import tasks to register them with Celery
from app.tasks import tasks