"""
Integration test for core user and project persistence workflow.

This test validates the State Unification and DB Hook architectural changes
by testing the complete lifecycle:
1. User sign-up
2. Project creation via /api/beats/create
3. Database persistence verification
"""
import pytest
import httpx
from sqlalchemy import select

from main import app
from database import get_db, Base
from database_models import User, Project
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


@pytest.fixture
async def async_client():
    """
    Async HTTP client fixture with test database override.
    Uses httpx.AsyncClient for asynchronous testing.
    """
    # Import models to ensure they're registered with Base
    import database_models  # noqa: F401
    
    # Create tables for test
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Override the get_db dependency
    app.dependency_overrides[get_db] = override_get_db
    
    # Create async test client
    async with httpx.AsyncClient(app=app, base_url="http://test") as client:
        yield client
    
    # Cleanup: remove dependency override
    app.dependency_overrides.clear()
    
    # Drop tables after test
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.mark.asyncio
async def test_full_project_creation_and_persistence(async_client):
    """
    Test the complete project lifecycle:
    1. User sign-up via /api/auth/signup
    2. Project creation via /api/beats/create (triggers ProjectMemory and DB record)
    3. Database persistence verification
    4. Cleanup
    """
    # Step 1: User Sign-Up
    signup_data = {
        "email": "test_user@example.com",
        "password": "TestPassword123!"
    }
    
    signup_response = await async_client.post(
        "/api/auth/signup",
        json=signup_data
    )
    
    assert signup_response.status_code == 200, f"Signup failed: {signup_response.text}"
    signup_result = signup_response.json()
    assert signup_result["ok"] is True
    user_id = signup_result["user_id"]
    
    # Extract auth token from cookies
    cookies = signup_response.cookies
    assert "auth_token" in cookies, "Auth token cookie not found in signup response"
    auth_token = cookies["auth_token"]
    
    # Step 2: Project Creation via /api/beats/create
    # This endpoint triggers get_or_create_project_memory which creates the DB Project record
    beat_request = {
        "prompt": "Test beat for integration test",
        "mood": "energetic",
        "genre": "hip-hop"
    }
    
    # Make request with auth cookie
    beat_response = await async_client.post(
        "/api/beats/create",
        json=beat_request,
        cookies={"auth_token": auth_token}
    )
    
    assert beat_response.status_code == 200, f"Beat creation failed: {beat_response.text}"
    beat_result = beat_response.json()
    assert beat_result.get("ok") is True or "session_id" in beat_result.get("data", {})
    
    # Extract session_id from response
    session_id = None
    if "data" in beat_result:
        session_id = beat_result["data"].get("session_id")
    # Fallback: check if session_id is at top level
    if not session_id:
        session_id = beat_result.get("session_id")
    
    assert session_id is not None, "session_id not found in beat creation response"
    
    # Step 3: Data Check (DB Persistence)
    # Query the database directly to verify Project record exists
    async with TestAsyncSessionLocal() as db_session:
        # Query for the Project by session_id
        stmt = select(Project).where(Project.session_id == session_id)
        result = await db_session.execute(stmt)
        db_project = result.scalar_one_or_none()
        
        assert db_project is not None, f"Project record not found in database for session_id: {session_id}"
        assert db_project.user_id == int(user_id), f"Project user_id mismatch: expected {user_id}, got {db_project.user_id}"
        assert db_project.session_id == session_id, f"Project session_id mismatch: expected {session_id}, got {db_project.session_id}"
        
        # Verify the project is linked to the correct user
        user_stmt = select(User).where(User.id == int(user_id))
        user_result = await db_session.execute(user_stmt)
        db_user = user_result.scalar_one_or_none()
        
        assert db_user is not None, f"User record not found in database for user_id: {user_id}"
        assert db_user.email == signup_data["email"].lower(), "User email mismatch"
        
        # Step 4: Clean Up
        # Delete the created user and project
        # Delete project first (foreign key constraint)
        await db_session.delete(db_project)
        
        # Delete user
        await db_session.delete(db_user)
        
        await db_session.commit()

