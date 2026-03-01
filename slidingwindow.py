import math
import time
from store import store


def check(key, limit, window_seconds, cost=1):
    now = time.time()

    window_start = math.floor(now / window_seconds) * window_seconds
    prev_window_start = window_start - window_seconds
    reset_at = window_start + window_seconds

    current_key = f"sw:{key}:{int(window_start)}"
    prev_key = f"sw:{key}:{int(prev_window_start)}"

    allowed, weighted, prev_weight, current_count, prev_count = store.sliding_window_check(
        current_key,
        prev_key,
        limit,
        window_seconds,
        cost,
        now
    )

    if not allowed:
        return {
            "allowed": False,
            "count": weighted,
            "limit": limit,
            "remaining": 0,
            "reset_at": reset_at,
            "retry_after": math.ceil(reset_at - now),
            "algorithm": "sliding_window",
            "debug": {
                "current_count": current_count,
                "prev_count": prev_count,
                "prev_weight": round(prev_weight, 3),
                "weighted_count": weighted,
            }
        }

    return {
        "allowed": True,
        "count": weighted,
        "limit": limit,
        "remaining": max(0, limit - weighted),
        "reset_at": reset_at,
        "retry_after": None,
        "algorithm": "sliding_window",
        "debug": {
            "current_count": current_count,
            "prev_count": prev_count,
            "prev_weight": round(prev_weight, 3),
            "weighted_count": weighted,
        }
    }