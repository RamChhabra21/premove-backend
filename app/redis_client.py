import redis
import ssl
from app.core.config import settings

# Initialize Redis client using the URL from settings
# We use ssl_cert_reqs=ssl.CERT_NONE to match the Celery configuration for Upstash/SSL connections
redis_client = redis.from_url(
    settings.REDIS_URL,
    decode_responses=True,
    ssl_cert_reqs=ssl.CERT_NONE if settings.REDIS_URL.startswith("rediss://") else None
)