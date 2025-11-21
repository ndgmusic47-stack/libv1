"""
Authentication utilities: Password hashing and JWT token management
"""

import jwt
from datetime import datetime, timedelta
from passlib.context import CryptContext
from typing import Optional
from config import settings

# Password hashing context
pwd_context = CryptContext(
    schemes=["argon2"],
    deprecated="auto"
)

# JWT configuration
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    """Hash a password using argon2"""
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


def calculate_trial_days_remaining(user) -> Optional[int]:
    """
    Calculate the number of days remaining in the user's trial period.
    
    Args:
        user: User object with trial_start_date attribute
        
    Returns:
        Number of days remaining (can be negative if expired), or None if no trial_start_date
    """
    if not user or not hasattr(user, 'trial_start_date') or not user.trial_start_date:
        return None
    
    try:
        trial_start = datetime.fromisoformat(user.trial_start_date.replace('Z', '+00:00'))
        if trial_start.tzinfo is None:
            trial_start = trial_start.replace(tzinfo=timedelta(seconds=0))
        now = datetime.utcnow().replace(tzinfo=timedelta(seconds=0))
        
        # Trial period is 72 hours (3 days)
        trial_end = trial_start + timedelta(hours=72)
        remaining = (trial_end - now).total_seconds() / 86400  # Convert to days
        
        return int(remaining)
    except (ValueError, AttributeError) as e:
        return None


def get_subscription_status(user) -> str:
    """
    Get the current subscription status for a user.
    
    Rules:
    - If subscription_status == "active": is_paid_user = True, status = "active"
    - Else if trial still active (<72 hours): status = "trial"
    - Else: status = "expired"
    
    Args:
        user: User object with subscription_status, is_paid_user, and trial_start_date attributes
        
    Returns:
        Subscription status string: "active", "trial", or "expired"
    """
    if not user:
        return "expired"
    
    # Check if user has active subscription
    subscription_status = getattr(user, 'subscription_status', None)
    if subscription_status == "active":
        return "active"
    
    # Check if trial is still active
    trial_days_remaining = calculate_trial_days_remaining(user)
    if trial_days_remaining is not None and trial_days_remaining > 0:
        return "trial"
    
    # Otherwise, expired
    return "expired"
