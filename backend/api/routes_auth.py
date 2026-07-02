from fastapi import APIRouter, HTTPException

from .. import auth
from ..models import LoginRequest

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login")
def login(body: LoginRequest):
    token = auth.login(body.username, body.password)
    if token is None:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    return {"token": token}


@router.post("/logout")
def logout(token: str = auth.AuthDep):
    auth.logout(token)
    return {"ok": True}
