import bcrypt
import jwt
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import Depends, HTTPException, Query, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from backend.app.config import settings
from backend.app.database import get_db
from backend.app.models.user import User

# HTTP Bearer Token Handler
security_bearer = HTTPBearer(auto_error=False)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify raw password against bcrypt hash using bcrypt."""
    try:
        password_bytes = plain_password.encode("utf-8")[:72]
        hash_bytes = hashed_password.encode("utf-8")
        return bcrypt.checkpw(password_bytes, hash_bytes)
    except Exception:
        return False

def get_password_hash(password: str) -> str:
    """Generate secure bcrypt password hash using bcrypt."""
    password_bytes = password.encode("utf-8")[:72]
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password_bytes, salt).decode("utf-8")

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Encode JWT access token with payload and expiration."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc)})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str) -> Optional[dict]:
    """Decode and validate JWT token."""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.ALGORITHM])
        return payload
    except (jwt.PyJWTError, Exception):
        return None

def get_current_user(
    auth: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer),
    token_query: Optional[str] = Query(None, alias="token"),
    db: Session = Depends(get_db)
) -> User:
    """
    Dependency to retrieve and validate authenticated user from JWT.
    Supports standard 'Authorization: Bearer <token>' header as well as '?token=...' query parameter
    for direct browser preview/download requests.
    """
    raw_token = None
    if auth and auth.credentials:
        raw_token = auth.credentials.strip()
    elif token_query:
        raw_token = token_query.strip()

    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    payload = decode_access_token(raw_token)
    if not payload or "sub" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user_sub = str(payload.get("sub", ""))
    if user_sub.isdigit():
        user = db.query(User).filter(User.id == int(user_sub), User.is_active == True).first()
    else:
        user = db.query(User).filter(User.email == user_sub, User.is_active == True).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account does not exist or is inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user

def get_current_admin_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """Dependency to require Admin role authorization."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrative privileges required for this operation"
        )
    return current_user

def get_optional_current_user(
    auth: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer),
    token_query: Optional[str] = Query(None, alias="token"),
    db: Session = Depends(get_db)
) -> Optional[User]:
    """Optional user dependency for public/hybrid endpoints."""
    raw_token = None
    if auth and auth.credentials:
        raw_token = auth.credentials.strip()
    elif token_query:
        raw_token = token_query.strip()

    if not raw_token:
        return None
    payload = decode_access_token(raw_token)
    if not payload or "sub" not in payload:
        return None
    try:
        user_id = int(payload.get("sub"))
        return db.query(User).filter(User.id == user_id, User.is_active == True).first()
    except Exception:
        return None
