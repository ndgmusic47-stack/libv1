# FORENSIC BEACON — DEPLOYEDy9kXvPq2 — 20251120-224633
"""
Google Single Sign-On (SSO) Router
Handles Google OAuth authentication flow
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from authlib.integrations.starlette_client import OAuth

from database import get_db
from crud.user import UserRepository
from services.trial_service import TrialService
from auth_utils import create_jwt, hash_password
from config import settings
import stripe

logger = logging.getLogger(__name__)

# Initialize OAuth
oauth = OAuth()

# Configure Google OAuth provider
if settings.google_client_id and settings.google_client_secret and settings.google_redirect_uri:
    oauth.register(
        name="google",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={
            "scope": "openid email profile"
        }
    )
else:
    logger.warning("Google OAuth credentials not configured. Google SSO will be unavailable.")

# Create Google auth router
google_auth_router = APIRouter(prefix="/api/auth/google", tags=["google-auth"])


@google_auth_router.get("/login")
async def google_login(request: Request):
    """
    Initiate Google OAuth login flow.
    Redirects user to Google consent screen.
    """
    try:
        if not settings.google_client_id or not settings.google_client_secret or not settings.google_redirect_uri:
            raise HTTPException(status_code=500, detail="Google OAuth not configured")
        
        # Get the OAuth client
        redirect_uri = settings.google_redirect_uri
        
        # Create authorization URL and redirect
        return await oauth.google.authorize_redirect(request, redirect_uri)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Google login initiation failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to initiate Google login: {str(e)}")


@google_auth_router.get("/auth")
async def google_auth_callback(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Handle Google OAuth callback.
    Fetches user profile, creates or logs in user, and redirects to frontend.
    """
    try:
        if not settings.google_client_id or not settings.google_client_secret or not settings.google_redirect_uri:
            raise HTTPException(status_code=500, detail="Google OAuth not configured")
        
        # Fetch access token and user profile from Google
        token = await oauth.google.authorize_access_token(request)
        user_info = token.get("userinfo")
        
        if not user_info:
            # If userinfo is not in token, fetch it separately
            async with oauth.google.get("https://openidconnect.googleapis.com/v1/userinfo", token=token) as resp:
                user_info = await resp.json()
        
        # Extract email from Google profile
        email = user_info.get("email")
        if not email:
            raise HTTPException(status_code=400, detail="Email not provided by Google")
        
        email = email.lower()
        
        # Initialize repository
        user_repo = UserRepository(db)
        
        # Check if user exists
        existing_user = await user_repo.get_user_by_email(email)
        
        if existing_user:
            # User exists - log them in
            user = existing_user
        else:
            # User doesn't exist - create new user
            # Create user with no password (Google auth only)
            # Generate a random password hash that won't be used
            # Users authenticated via Google won't need password
            dummy_password_hash = hash_password("google_sso_nopass")
            
            user_data = {
                "email": email,
                "hashed_password": dummy_password_hash,
                "is_active": True,
                "is_paid_user": False  # Default to free plan
            }
            
            user = await user_repo.create_user(user_data)
            await db.commit()
            await db.refresh(user)
            
            # Start trial period for new user
            trial_service = TrialService(db, user_repo)
            await trial_service.start_trial(user)
            await db.commit()
            await db.refresh(user)
            
            # Create Stripe customer for new user
            if settings.stripe_secret_key:
                try:
                    customer = stripe.Customer.create(
                        email=email,
                        metadata={"user_id": str(user.id)}
                    )
                    # Update user with Stripe customer ID
                    await user_repo.update_user(user, {"stripe_customer_id": customer.id})
                    await db.commit()
                    await db.refresh(user)
                except Exception as e:
                    # Log error but don't fail signup if Stripe is unavailable
                    logger.warning(f"Failed to create Stripe customer: {e}")
        
        # Generate JWT token
        jwt_token = create_jwt(str(user.id))
        
        # Redirect to frontend with cookie set
        frontend_url = settings.frontend_url or "http://localhost:5173"
        
        # Create redirect response
        response = RedirectResponse(url=frontend_url)
        
        # Set auth cookie
        response.set_cookie(
            key="auth_token",
            value=jwt_token,
            httponly=True,
            secure=True,
            samesite="None",
            path="/",
            max_age=604800  # 7 days in seconds
        )
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Google auth callback failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Google authentication failed: {str(e)}")

