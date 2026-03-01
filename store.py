import redis
import threading
from typing import Optional

INCREMENT_SCRIPT = """
local current = tonumber(redis.call('GET', KEYS[1])) or 0
if ARGV[1] == '0' then
    return current
end
local new_val = redis.call('INCRBY', KEYS[1], ARGV[1])
if ARGV[2] ~= '0' then
    redis.call('EXPIRE', KEYS[1], ARGV[2])
end
return new_val
"""


class RedisStore:
    def __init__(self):
        self.client = redis.Redis(
            host='localhost',
            port=6379,
            decode_responses=True
        )
        self._lock = threading.Lock()
        self.client.ping()

        # load increment script
        self._increment_sha = self.client.script_load(INCREMENT_SCRIPT)

        # load sliding window script
        with open("atomic_sliding_window.lua", "r") as f:
            self._sliding_sha = self.client.script_load(f.read())

        print("[Store] Connected to Redis")

    def atomic_increment(self, key: str, amount: int = 1, ttl_seconds: Optional[float] = None) -> int:
        return int(self.client.evalsha(
            self._increment_sha,
            1,
            key,
            str(amount),
            str(int(ttl_seconds)) if ttl_seconds else '0'
        ))

    def sliding_window_check(self, current_key, prev_key, limit, window_seconds, cost, now):
        result = self.client.evalsha(
            self._sliding_sha,
            2,
            current_key,
            prev_key,
            limit,
            window_seconds,
            cost,
            now
        )

        allowed = bool(result[0])
        weighted = int(result[1])
        prev_weight = float(result[2])
        current = int(result[3])
        prev = int(result[4])

        return allowed, weighted, prev_weight, current, prev

    def delete(self, key: str):
        self.client.delete(key)

    def keys_with_prefix(self, prefix: str) -> list:
        return self.client.keys(f"{prefix}*")

    def flush(self):
        self.client.flushdb()

    def size(self) -> int:
        return self.client.dbsize()

    def stats(self) -> dict:
        info = self.client.info('memory')
        return {
            "total_keys": self.client.dbsize(),
            "used_memory": info['used_memory_human'],
            "backend": "redis"
        }

    @property
    def data(self):
        return _RedisDataProxy(self.client)


class _RedisDataProxy:
    def __init__(self, client):
        self._client = client

    def get(self, key: str):
        val = self._client.hgetall(key)
        return val if val else None

    def __setitem__(self, key: str, value: dict):
        pipe = self._client.pipeline()
        pipe.delete(key)
        for k, v in value.items():
            pipe.hset(key, k, str(v))
        pipe.expire(key, 3600)
        pipe.execute()


store = RedisStore()