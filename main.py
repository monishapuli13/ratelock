import os
import time
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from sqlalchemy.orm import Session
from sqlalchemy import text

from database import engine, Base, get_db
from models import User

from auth import (
    hash_password,
    verify_password,
    create_access_token,
    decode_token,
    generate_api_key,
    hash_api_key,
    verify_api_key
)

import fixed_window
import slidingwindow as sliding_window
import token_bucket
from store import store


# ==========================
# Auto Schema Migration
# ==========================

def ensure_schema():
    with engine.connect() as conn:
        conn.execute(text("""
            ALTER TABLE users
            ADD COLUMN IF NOT EXISTS api_key_hash TEXT;
        """))
        conn.commit()


ensure_schema()

# ==========================
# App Setup
# ==========================

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="RateLock",
    description="Rate Limiter as a Service",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL")
security = HTTPBearer()


# ==========================
# AUTH HELPERS
# ==========================

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):

    token = credentials.credentials
    payload = decode_token(token)

    email = payload.get("sub")

    if not email:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = db.query(User).filter(User.email == email).first()

    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    if not user.is_approved:
        raise HTTPException(status_code=403, detail="Account not approved")

    return user


def require_admin(user: User = Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def get_user_from_api_key(
    x_api_key: str = Header(None),
    db: Session = Depends(get_db)
):

    if not x_api_key:
        raise HTTPException(status_code=401, detail="API key required")

    users = db.query(User).filter(User.api_key_hash.isnot(None)).all()

    for user in users:
        if verify_api_key(x_api_key, user.api_key_hash):
            return user

    raise HTTPException(status_code=401, detail="Invalid API key")


# ==========================
# Schemas
# ==========================

class RegisterRequest(BaseModel):
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


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


# ==========================
# AUTH ENDPOINTS
# ==========================

@app.post("/register")
def register(user: RegisterRequest, db: Session = Depends(get_db)):

    existing = db.query(User).filter(User.email == user.email).first()

    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    hashed = hash_password(user.password)

    if ADMIN_EMAIL and user.email == ADMIN_EMAIL:
        role = "admin"
        is_approved = True
    else:
        role = "user"
        is_approved = False

    new_user = User(
        email=user.email,
        password_hash=hashed,
        role=role,
        is_approved=is_approved
    )

    db.add(new_user)
    db.commit()

    if role == "admin":
        return {"message": "Admin account created successfully."}

    return {"message": "User registered. Await admin approval."}


@app.post("/login")
def login(user: LoginRequest, db: Session = Depends(get_db)):

    db_user = db.query(User).filter(User.email == user.email).first()

    if not db_user:
        raise HTTPException(status_code=400, detail="Invalid credentials")

    if not verify_password(user.password, db_user.password_hash):
        raise HTTPException(status_code=400, detail="Invalid credentials")

    if not db_user.is_approved:
        raise HTTPException(status_code=403, detail="Account not approved yet")

    token = create_access_token({"sub": db_user.email})

    return {
        "access_token": token,
        "token_type": "bearer",
        "role": db_user.role
    }


# ==========================
# ADMIN ENDPOINTS
# ==========================

@app.get("/admin/users")
def list_users(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return db.query(User).all()


@app.post("/admin/approve/{user_id}")
def approve_user(user_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):

    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_approved = True
    db.commit()

    return {"message": f"User {user.email} approved."}


# ==========================
# API KEY
# ==========================

@app.post("/generate-api-key")
def create_api_key(user: User = Depends(get_current_user), db: Session = Depends(get_db)):

    raw_key = generate_api_key()
    hashed = hash_api_key(raw_key)

    user.api_key_hash = hashed
    db.commit()

    return {
        "api_key": raw_key,
        "message": "Store this securely. It will not be shown again."
    }


# ==========================
# RATE LIMIT ENDPOINTS
# ==========================

@app.post("/v1/check")
async def check_rate_limit(req: CheckRequest, user: User = Depends(get_user_from_api_key)):

    key = f"user:{user.id}:{req.identifier}:{req.resource}"

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
        raise HTTPException(status_code=400, detail="Unknown algorithm")

    return result


# ==========================
# UTIL ENDPOINTS
# ==========================

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "timestamp": time.time()
    }


@app.get("/")
async def root():
    return {
        "service": "RateLock",
        "version": "2.0.0",
        "docs": "/docs"
    }