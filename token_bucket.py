import time
from store import store


def check(key, capacity, refill_rate, cost=1):
    bucket_key = f"tb:{key}"
    now = time.time()

    with store._lock:
        entry = store.data.get(bucket_key)

        if entry is None:
            tokens = float(capacity)
            last_refill = now
        else:
            tokens = float(entry.get("tokens", capacity))
            last_refill = float(entry.get("last_refill", now))

        elapsed = now - last_refill
        tokens = min(float(capacity), tokens + elapsed * refill_rate)
        last_refill = now

        if tokens < cost:
            tokens_needed = cost - tokens
            wait_seconds = tokens_needed / refill_rate
            store.data[bucket_key] = {"tokens": tokens, "last_refill": last_refill}
            return {
                "allowed": False,
                "tokens_remaining": round(tokens, 2),
                "capacity": capacity,
                "refill_rate": refill_rate,
                "retry_after": round(wait_seconds, 2),
                "algorithm": "token_bucket",
            }

        tokens -= cost
        store.data[bucket_key] = {"tokens": tokens, "last_refill": last_refill}

    return {
        "allowed": True,
        "tokens_remaining": round(tokens, 2),
        "capacity": capacity,
        "refill_rate": refill_rate,
        "retry_after": None,
        "algorithm": "token_bucket",
    }