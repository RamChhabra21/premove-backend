import redis
import ssl
from app.core.config import settings

# Initialize Redis client using the URL from settings
# We use ssl_cert_reqs=ssl.CERT_NONE to match the Celery configuration for Upstash/SSL connections
redis_kwargs = {
    "decode_responses": True,
    "max_connections": 5,
    "socket_timeout": 5,
    "socket_connect_timeout": 5,
}

if settings.REDIS_URL.startswith("rediss://"):
    redis_kwargs["ssl_cert_reqs"] = ssl.CERT_NONE

redis_client = redis.from_url(
    settings.REDIS_URL,
    **redis_kwargs
)