import time
import os
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from database import engine, SessionLocal
from models import Base, User
from auth import hash_password, verify_password, create_access_token, decode_token

import fixed_window
import slidingwindow as sliding_window
import token_bucket
from store import store

# Create DB tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="RateLock",
    description="Rate Limiter as a Service — Phase 1",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# DATABASE DEPENDENCY
# =========================

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# =========================
# AUTH SCHEMAS
# =========================

class RegisterRequest(BaseModel):
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


# =========================
# RATE LIMIT SCHEMAS
# =========================

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


# =========================
# SECURITY
# =========================

security = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
):
    token = credentials.credentials
    payload = decode_token(token)
    email = payload.get("sub")

    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user


# =========================
# AUTH ENDPOINTS
# =========================

@app.post("/register")
def register(data: RegisterRequest, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.email == data.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    new_user = User(
        email=data.email,
        hashed_password=hash_password(data.password),
        is_approved=False
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return {"message": "User registered. Await admin approval."}


@app.post("/login")
def login(data: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()

    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not user.is_approved:
        raise HTTPException(status_code=403, detail="Account not approved yet")

    token = create_access_token({"sub": user.email})

    return {
        "access_token": token,
        "token_type": "bearer"
    }


# =========================
# PROTECTED RATE LIMIT ENDPOINT
# =========================

@app.post("/v1/check")
async def check_rate_limit(
    req: CheckRequest,
    current_user: User = Depends(get_current_user)
):
    key = f"{current_user.email}:{req.identifier}:{req.resource}"

    if req.algorithm == "fixed_window":
        result = fixed_window.check(
            key=key,
            limit=req.limit,
            window_seconds=req.window_seconds,
            cost=req.cost
        )

    elif req.algorithm == "sliding_window":
        result = sliding_window.check(
            key=key,
            limit=req.limit,
            window_seconds=req.window_seconds,
            cost=req.cost
        )

    elif req.algorithm == "token_bucket":
        capacity = req.capacity or req.limit
        refill_rate = req.refill_rate or (req.limit / req.window_seconds)
        result = token_bucket.check(
            key=key,
            capacity=capacity,
            refill_rate=refill_rate,
            cost=req.cost
        )

    else:
        return {"error": f"Unknown algorithm: {req.algorithm}"}

    return result


# =========================
# OTHER ENDPOINTS
# =========================

@app.post("/v1/reset")
async def reset_limit(
    req: ResetRequest,
    current_user: User = Depends(get_current_user)
):
    key = f"{current_user.email}:{req.identifier}:{req.resource}"
    deleted = []

    for prefix in [f"fw:{key}:", f"sw:{key}:", f"tb:{key}"]:
        keys = store.keys_with_prefix(prefix)
        for k in keys:
            store.delete(k)
            deleted.append(k)

    return {"reset": True, "keys_cleared": len(deleted)}


@app.get("/v1/stats")
async def stats(current_user: User = Depends(get_current_user)):
    return store.stats()


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "store": store.stats(),
        "timestamp": time.time()
    }


@app.get("/")
async def root():
    return {
        "service": "RateLock",
        "phase": "1 - Auth Enabled",
        "docs": "https://ratelock.onrender.com/docs"
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)