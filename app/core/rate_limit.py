from fastapi import HTTPException, Depends, status
from app.redis_client import redis_client
from app.core.auth import get_user_id
import time
from app.core.logging_config import logger

class RateLimiter:
    """
    User-based Sliding Window Rate Limiter using Redis Sorted Sets.
    Provides precise rate limiting by tracking individual request timestamps.
    
    Usage:
    @router.post("/path", dependencies=[Depends(RateLimiter(limit=5, window=60))])
    """
    def __init__(self, limit: int, window: int, scope: str = "default"):
        self.limit = limit
        self.window = window
        self.scope = scope

    async def __call__(self, user_id: str = Depends(get_user_id)):
        # If in development mode without a user_id, skip rate limiting
        if not user_id:
            return True

        # Unique key for this user and scope
        key = f"ratelimit:{self.scope}:{user_id}"
        now = time.time()
        # Anything older than this should be removed
        clear_before = now - self.window

        try:
            # Atomic pipeline to ensure consistency
            pipe = redis_client.pipeline()
            
            # 1. Remove old requests outside the current window
            pipe.zremrangebyscore(key, 0, clear_before)
            
            # 2. Add the current request
            # We use a unique value (timestamp + nanoseconds) to ensure 
            # multiple requests in the same microsecond are all counted.
            pipe.zadd(key, {f"{now}-{time.time_ns()}": now})
            
            # 3. Get the count of requests in the current window
            pipe.zcard(key)
            
            # 4. Set key to expire so Redis stays clean
            pipe.expire(key, self.window)
            
            # Execute all at once
            results = pipe.execute()
            current_count = results[2] # Result of ZCARD
                
            if current_count > self.limit:
                logger.warning(f"Rate limit exceeded for user {user_id} on scope {self.scope}")
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={
                        "error": "RateLimitExceeded",
                        "message": f"Too many requests. Limit is {self.limit} per {self.window} seconds.",
                        "limit": self.limit,
                        "window": self.window,
                        "retry_after": self.window
                    }
                )
        except HTTPException:
            raise
        except Exception as e:
            # Fail-open if Redis is down
            logger.error(f"Rate limiter Redis error: {e}")
            return True

        return True
