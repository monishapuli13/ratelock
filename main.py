import time
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

import fixed_window
import slidingwindow as sliding_window
import token_bucket
from store import store

app = FastAPI(title="RateLock", description="Rate Limiter as a Service — Phase 1", version="1.0.0")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class CheckRequest(BaseModel):
    identifier: str
    resource: str = "*"
    algorithm: str = "sliding_window"
    limit: int
    window_seconds: int
    cost: int = 1
    capacity: Optional[int] = None
    refill_rate: Optional[float] = None


class ResetRequest(BaseModel):
    identifier: str
    resource: str = "*"


@app.post("/v1/check")
async def check_rate_limit(req: CheckRequest):
    key = f"{req.identifier}:{req.resource}"

    if req.algorithm == "fixed_window":
        result = fixed_window.check(key=key, limit=req.limit, window_seconds=req.window_seconds, cost=req.cost)

    elif req.algorithm == "sliding_window":
        result = sliding_window.check(key=key, limit=req.limit, window_seconds=req.window_seconds, cost=req.cost)

    elif req.algorithm == "token_bucket":
        capacity = req.capacity or req.limit
        refill_rate = req.refill_rate or (req.limit / req.window_seconds)
        result = token_bucket.check(key=key, capacity=capacity, refill_rate=refill_rate, cost=req.cost)

    else:
        return {"error": f"Unknown algorithm: {req.algorithm}"}

    return result


@app.post("/v1/reset")
async def reset_limit(req: ResetRequest):
    key = f"{req.identifier}:{req.resource}"
    deleted = []
    for prefix in [f"fw:{key}:", f"sw:{key}:", f"tb:{key}"]:
        keys = store.keys_with_prefix(prefix)
        for k in keys:
            store.delete(k)
            deleted.append(k)
    return {"reset": True, "keys_cleared": len(deleted)}


@app.get("/v1/inspect/{identifier}")
async def inspect(identifier: str, resource: str = "*"):
    key = f"{identifier}:{resource}"
    keys = (store.keys_with_prefix(f"fw:{key}") +
            store.keys_with_prefix(f"sw:{key}") +
            store.keys_with_prefix(f"tb:{key}"))
    state = {k: store.get(k) for k in keys if store.get(k)}
    return {"identifier": identifier, "resource": resource, "state": state, "timestamp": time.time()}


@app.get("/v1/stats")
async def stats():
    return store.stats()


@app.get("/health")
async def health():
    return {"status": "healthy", "store": store.stats(), "timestamp": time.time()}


@app.get("/")
async def root():
    return {
        "service": "RateLock",
        "phase": "1 - In-Memory",
        "docs": "http://localhost:8000/docs"
    }