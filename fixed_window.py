import math
import time
from store import store


def check(key, limit, window_seconds, cost=1):
    now = time.time()
    window_start = math.floor(now / window_seconds) * window_seconds
    reset_at = window_start + window_seconds
    redis_key = f"fw:{key}:{int(window_start)}"

    # Redis returns the raw count directly, not a dict
    current_count = store.atomic_increment(
        redis_key, amount=0, ttl_seconds=window_seconds * 2
    )

    if current_count + cost > limit:
        return {
            "allowed": False,
            "count": current_count,
            "limit": limit,
            "remaining": 0,
            "reset_at": reset_at,
            "retry_after": math.ceil(reset_at - now),
            "algorithm": "fixed_window",
        }

    new_count = store.atomic_increment(
        redis_key, amount=cost, ttl_seconds=window_seconds * 2
    )

    return {
        "allowed": True,
        "count": new_count,
        "limit": limit,
        "remaining": max(0, limit - new_count),
        "reset_at": reset_at,
        "retry_after": None,
        "algorithm": "fixed_window",
    }