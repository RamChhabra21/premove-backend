import redis 

redis_connection = redis.Redis(host="localhost", port=6379, decode_responses=True)