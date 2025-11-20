"""
Comprehensive security tests for authentication module.

Tests cover:
- Password strength validation (strong passwords, weak passwords, missing complexity)
- JWT security (missing secret key)
- Token expiration handling
"""
import pytest
import asyncio
from unittest.mock import patch
from fastapi.testclient import TestClient

from main import app
from auth_utils import create_jwt, create_expired_jwt
from config import settings
from database import get_db, Base
from tests.conftest import TestAsyncSessionLocal, test_engine


# Override get_db dependency to use test database
async def override_get_db():
    """Override get_db to use test database"""
    async with TestAsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# Create TestClient with database override
@pytest.fixture
def client():
    """FastAPI TestClient fixture with test database override"""
    # Import models to ensure they're registered with Base
    import database_models  # noqa: F401
    
    # Create tables for test
    async def setup_db():
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    
    # Run async setup
    asyncio.run(setup_db())
    
    # Override the get_db dependency
    app.dependency_overrides[get_db] = override_get_db
    
    # Create test client
    test_client = TestClient(app)
    
    yield test_client
    
    # Cleanup: remove dependency override
    app.dependency_overrides.clear()
    
    # Drop tables after test
    async def teardown_db():
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
    
    asyncio.run(teardown_db())


def test_strong_password_success(client):
    """
    Test Strong Password Success: Verify a signup request succeeds with a strong,
    12+ character password containing all required complexity rules.
    """
    # Strong password: 12+ chars, uppercase, lowercase, digit, special char
    strong_password = "StrongPass123!"
    test_email = "test_strong@example.com"
    
    response = client.post(
        "/api/auth/signup",
        json={
            "email": test_email,
            "password": strong_password
        }
    )
    
    # Should succeed with 200 status
    assert response.status_code == 200
    response_data = response.json()
    assert response_data["ok"] is True
    assert "user_id" in response_data
    
    # Should have auth_token cookie
    assert "auth_token" in response.cookies


def test_weak_password_rejection_min_length(client):
    """
    Test Weak Password Rejection (Min Length): Verify signup is rejected (HTTP 400)
    if the password is less than 12 characters.
    """
    # Password with only 11 characters (below minimum)
    weak_password = "ShortPass1!"
    test_email = "test_short@example.com"
    
    response = client.post(
        "/api/auth/signup",
        json={
            "email": test_email,
            "password": weak_password
        }
    )
    
    # Should be rejected with 400 status
    assert response.status_code == 400
    response_data = response.json()
    assert "detail" in response_data
    assert "12 characters" in response_data["detail"].lower()


def test_weak_password_rejection_missing_complexity(client):
    """
    Test Weak Password Rejection (Missing Complexity): Verify signup is rejected (HTTP 400)
    if the password is 12+ characters but lacks complexity (e.g., no uppercase, no digit).
    """
    # Test case 1: Missing uppercase (12+ chars, has lowercase, digit, special)
    test_cases = [
        ("lowercasepass123!", "uppercase"),  # No uppercase
        ("NOLOWERCASE123!", "lowercase"),     # No lowercase
        ("NoDigitsSpecial!", "digit"),        # No digits
        ("NoSpecialChars123", "special"),     # No special characters
    ]
    
    for password, missing_type in test_cases:
        test_email = f"test_{missing_type}@example.com"
        
        response = client.post(
            "/api/auth/signup",
            json={
                "email": test_email,
                "password": password
            }
        )
        
        # Should be rejected with 400 status
        assert response.status_code == 400, f"Password '{password}' should be rejected for missing {missing_type}"
        response_data = response.json()
        assert "detail" in response_data
        # Should contain a message about the missing complexity requirement
        assert missing_type.lower() in response_data["detail"].lower() or "password must" in response_data["detail"].lower()


def test_jwt_security_missing_key():
    """
    Test JWT Security (Missing Key): Confirm create_jwt() raises a ValueError
    if settings.jwt_secret_key is intentionally set to None or an empty string,
    validating the security logic we implemented in auth_utils.py.
    """
    # Save original value
    original_key = settings.jwt_secret_key
    
    try:
        # Test with None - patch the settings object directly
        with patch('auth_utils.settings.jwt_secret_key', None):
            with pytest.raises(ValueError, match="JWT_SECRET_KEY is not set"):
                create_jwt("test_user_id")
        
        # Test with empty string
        with patch('auth_utils.settings.jwt_secret_key', ""):
            with pytest.raises(ValueError, match="JWT_SECRET_KEY is not set"):
                create_jwt("test_user_id")
        
    finally:
        # Restore original value by ensuring it's set back
        # Since we're patching, this should be automatic, but we'll be explicit
        pass


def test_authentication_failure_expired_token(client):
    """
    Test Authentication Failure (Expired Token): Test that an endpoint protected by
    get_current_user returns HTTP 401 when provided with an expired JWT token.
    """
    # Ensure JWT secret key is set for this test
    if not settings.jwt_secret_key:
        pytest.skip("JWT_SECRET_KEY not set - cannot test expired token")
    
    # First, create a user to have a valid user_id
    strong_password = "TestPassword123!"
    test_email = "test_expired@example.com"
    
    # Create user via signup
    signup_response = client.post(
        "/api/auth/signup",
        json={
            "email": test_email,
            "password": strong_password
        }
    )
    
    assert signup_response.status_code == 200
    user_id = signup_response.json()["user_id"]
    
    # Create an expired JWT token (expired 1 second ago)
    expired_token = create_expired_jwt(user_id, expired_seconds_ago=1)
    
    # Try to access a protected endpoint (/api/auth/me) with expired token
    # Using cookie
    response = client.get(
        "/api/auth/me",
        cookies={"auth_token": expired_token}
    )
    
    # Should return 401 Unauthorized
    assert response.status_code == 401
    response_data = response.json()
    assert "detail" in response_data
    assert "expired" in response_data["detail"].lower() or "invalid" in response_data["detail"].lower()
    
    # Also test with Authorization header
    response = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {expired_token}"}
    )
    
    # Should also return 401
    assert response.status_code == 401
    response_data = response.json()
    assert "detail" in response_data
    assert "expired" in response_data["detail"].lower() or "invalid" in response_data["detail"].lower()

