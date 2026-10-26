from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
import jwt
import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from config import get_auth_config

security = HTTPBearer(auto_error=False)

def verify_password(plain_password: str, stored_password: str) -> bool:
    if not stored_password:
        return False
    # Check if stored as plain text
    if plain_password == stored_password:
        return True
    # Check if stored as bcrypt hash
    try:
        if stored_password.startswith("$2b$") or stored_password.startswith("$2a$"):
            return bcrypt.checkpw(plain_password.encode('utf-8'), stored_password.encode('utf-8'))
    except Exception:
        pass
    return False

def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    conf = get_auth_config()
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=conf.get("token_expire_minutes", 1440))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, conf.get("jwt_secret", "ai-trade-secret"), algorithm=conf.get("jwt_algorithm", "HS256"))
    return encoded_jwt

def decode_access_token(token: str) -> Optional[dict]:
    conf = get_auth_config()
    try:
        payload = jwt.decode(token, conf.get("jwt_secret", "ai-trade-secret"), algorithms=[conf.get("jwt_algorithm", "HS256")])
        return payload
    except Exception:
        return None

def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> Dict[str, Any]:
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = credentials.credentials
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    username = payload.get("sub")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )
    return {"username": username}
