"""
Authentication utilities: Password hashing and JWT token management
"""

import jwt
from datetime import datetime, timedelta
from passlib.context import CryptContext
from config import settings

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT configuration
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    """Hash a password using bcrypt"""
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its hash"""
    return pwd_context.verify(password, password_hash)


def create_jwt(user_id: str) -> str:
    """Create a JWT token for a user"""
    if not settings.jwt_secret_key:
        raise ValueError("JWT_SECRET_KEY is not set. Cannot create JWT token.")
    
    payload = {
        "sub": user_id,
        "exp": datetime.utcnow() + timedelta(days=7)
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=ALGORITHM)


def decode_jwt(token: str):
    """Decode a JWT token. Returns None if invalid."""
    if not settings.jwt_secret_key:
        raise ValueError("JWT_SECRET_KEY is not set. Cannot decode JWT token.")
    
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def create_expired_jwt(user_id: str, expired_seconds_ago: int = 1) -> str:
    """
    Create an expired JWT token for testing purposes.
    
    Args:
        user_id: User ID to include in token
        expired_seconds_ago: How many seconds ago the token should have expired (default: 1)
        
    Returns:
        Expired JWT token string
        
    Raises:
        ValueError: If JWT_SECRET_KEY is not set
    """
    if not settings.jwt_secret_key:
        raise ValueError("JWT_SECRET_KEY is not set. Cannot create JWT token.")
    
    payload = {
        "sub": user_id,
        "exp": datetime.utcnow() - timedelta(seconds=expired_seconds_ago)
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=ALGORITHM)
