"""
Minimal JWT auth for the demo.

In production, swap `authenticate_user` for a real user store (DB table or
your company's IdP / SSO via OAuth2/OIDC) and use passlib to verify hashed
passwords instead of a plaintext .env comparison. The token issuance and
verification machinery below (JWT creation, expiry, FastAPI dependency)
is the reusable part.
"""
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import BaseModel

from app.config import settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")


class TokenData(BaseModel):
    username: str


def authenticate_user(username: str, password: str) -> bool:
    # Demo-only credential check. Replace with a real user table + hashed
    # password comparison (passlib.CryptContext) before this touches
    # anything with real data behind it.
    return username == settings.demo_username and password == settings.demo_password


def create_access_token(username: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": username, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def get_current_user(token: str = Depends(oauth2_scheme)) -> TokenData:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        username = payload.get("sub")
        if username is None:
            raise credentials_exception
        return TokenData(username=username)
    except JWTError:
        raise credentials_exception
