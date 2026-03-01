from fastapi import FastAPI
from pydantic import BaseModel
import requests

app = FastAPI(title="Protected Login Demo")

RATELOCK_URL = "http://127.0.0.1:8000/v1/check"

# fake database
USERS = {
    "monisha": "1234",
    "admin": "admin"
}

class LoginRequest(BaseModel):
    username: str
    password: str


@app.post("/login")
def login(req: LoginRequest):

    # Ask RateLock if request is allowed
    response = requests.post(
        RATELOCK_URL,
        json={
            "identifier": req.username,
            "resource": "login",
            "algorithm": "sliding_window",
            "limit": 5,
            "window_seconds": 60,
            "cost": 1
        },
        timeout=2
    ).json()

    # If RateLock blocks → stop immediately
    if not response["allowed"]:
        return {
            "success": False,
            "reason": "Too many login attempts",
            "retry_after": response["retry_after"]
        }

    # Now check password
    real_password = USERS.get(req.username)

    if real_password is None or real_password != req.password:
        return {"success": False, "reason": "Invalid username or password"}

    return {"success": True, "message": "Login successful"}