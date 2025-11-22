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
        
        # DEBUG: Log session state before OAuth redirect
        session_state_before = dict(request.session) if hasattr(request, 'session') else {}
        logger.error("=" * 80)
        logger.error("GOOGLE LOGIN - BEFORE REDIRECT (DEBUG)")
        logger.error("=" * 80)
        logger.error(f"Session contents before redirect: {session_state_before}")
        logger.error(f"Session cookie in request: {request.cookies.get('session', 'NOT FOUND')}")
        logger.error(f"Redirect URI: {settings.google_redirect_uri}")
        logger.error("=" * 80)
        
        # Get the OAuth client
        redirect_uri = settings.google_redirect_uri
        
        # Create authorization URL and redirect
        # Authlib automatically generates state and stores it in request.session
        response = await oauth.google.authorize_redirect(request, redirect_uri)
        
        # DEBUG: Log session state after OAuth redirect (state should be stored now)
        session_state_after = dict(request.session) if hasattr(request, 'session') else {}
        
        # Find the actual state key that authlib created (might be dynamic like _state_google_{state_value})
        # Search for keys starting with '_state_google'
        authlib_state_key = None
        for key in session_state_after.keys():
            if key.startswith('_state_google'):
                authlib_state_key = key
                break
        
        # If not found with pattern, try the static key
        if not authlib_state_key:
            authlib_state_key = '_state_google'
        
        # NEW: Store the pointer to this key so callback can retrieve it
        if authlib_state_key in session_state_after:
            request.session["_state_google_current"] = authlib_state_key
            # Ensure session is seen as modified
            request.session.modified = True
        
        # CRITICAL: Check if Set-Cookie header is present in response
        set_cookie_headers = response.headers.getlist("set-cookie") if hasattr(response.headers, 'getlist') else []
        if not set_cookie_headers:
            # Try alternative method
            set_cookie_raw = response.headers.get("set-cookie", "")
            if set_cookie_raw:
                set_cookie_headers = [set_cookie_raw]
        
        logger.error("=" * 80)
        logger.error("GOOGLE LOGIN - AFTER REDIRECT (DEBUG)")
        logger.error("=" * 80)
        logger.error(f"Session contents after redirect: {session_state_after}")
        # Authlib stores state with key pattern: '_state_{provider_name}' or '_state_{provider_name}_{state_value}'
        if authlib_state_key in session_state_after:
            logger.error(f"✅ STATE STORED IN SESSION: {authlib_state_key} = {session_state_after[authlib_state_key][:50]}...")
            logger.error(f"✅ POINTER STORED: _state_google_current = {authlib_state_key}")
        else:
            logger.error(f"❌ STATE NOT FOUND IN SESSION (expected key: {authlib_state_key})")
            logger.error(f"Available session keys: {list(session_state_after.keys())}")
        
        # CRITICAL: Log Set-Cookie headers in response
        logger.error("=" * 80)
        logger.error("RESPONSE HEADERS - SET-COOKIE (CRITICAL)")
        logger.error("=" * 80)
        if set_cookie_headers:
            logger.error(f"✅ Set-Cookie headers found: {len(set_cookie_headers)}")
            for idx, cookie in enumerate(set_cookie_headers):
                logger.error(f"  Cookie #{idx + 1}: {cookie[:200]}...")  # First 200 chars
                if "session" in cookie.lower():
                    logger.error(f"    ✅ 'session' cookie found in Set-Cookie")
                    # Extract cookie attributes
                    if "SameSite=None" in cookie or "SameSite=none" in cookie:
                        logger.error(f"    ✅ SameSite=None present")
                    if "Secure" in cookie:
                        logger.error(f"    ✅ Secure flag present")
                    if "HttpOnly" in cookie:
                        logger.error(f"    ✅ HttpOnly flag present")
        else:
            logger.error(f"❌ NO Set-Cookie headers found in response!")
            logger.error(f"   This means the session cookie is NOT being sent to the browser!")
        
        # Log all response headers for debugging
        logger.error(f"All response headers: {dict(response.headers)}")
        
        # Log request forwarding info
        logger.error(f"Request x-forwarded-proto: {request.headers.get('x-forwarded-proto', 'NOT SET')}")
        logger.error(f"Request x-forwarded-for: {request.headers.get('x-forwarded-for', 'NOT SET')}")
        logger.error(f"Request host: {request.headers.get('host', 'NOT SET')}")
        logger.error(f"Request URL scheme: {request.url.scheme}")
        logger.error("=" * 80)
        
        return response
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
    # Prevent FastAPI/Starlette from auto-parsing Google OAuth tokens as form fields (avoids password>72 bytes bcrypt error)
    request._form = None
    """
    Handle Google OAuth callback.
    Fetches user profile, creates or logs in user, and redirects to frontend.
    """
    try:
        # DEBUG: Log session and query params BEFORE state validation
        session_contents = dict(request.session) if hasattr(request, 'session') else {}
        incoming_state = request.query_params.get('state', 'NOT FOUND')
        
        # Load the key pointer saved during login redirect
        dynamic_key = request.session.get("_state_google_current")
        
        stored_state = None
        if dynamic_key:
            stored_state = request.session.get(dynamic_key)
        
        # DEBUG: If still missing, log available keys
        if not stored_state:
            logger.error(f"Google OAuth: state key '{dynamic_key}' not found. Available: {list(request.session.keys())}")
        
        logger.error("=" * 80)
        logger.error("GOOGLE CALLBACK - BEFORE STATE VALIDATION (DEBUG)")
        logger.error("=" * 80)
        logger.error(f"Incoming state param from Google: {incoming_state}")
        logger.error(f"Dynamic key pointer (_state_google_current): {dynamic_key}")
        logger.error(f"Stored state in session ({dynamic_key}): {stored_state}")
        logger.error(f"Full session contents: {session_contents}")
        logger.error(f"Session cookie in request.cookies: {request.cookies.get('session', 'NOT FOUND')}")
        logger.error(f"All cookies in request.cookies: {dict(request.cookies)}")
        logger.error(f"Request URL: {request.url}")
        logger.error(f"Request URL scheme: {request.url.scheme}")
        logger.error(f"Request URL host: {request.url.hostname}")
        logger.error(f"Request headers (relevant):")
        
        # Parse Cookie header manually to see all cookies
        cookie_header = request.headers.get('cookie', 'NOT FOUND')
        logger.error(f"  - Cookie header (raw): {cookie_header[:500]}...")
        if cookie_header != 'NOT FOUND':
            # Parse cookies from header
            cookies_list = cookie_header.split(';')
            logger.error(f"  - Cookie header parsed: {len(cookies_list)} cookies found")
            for cookie in cookies_list:
                cookie = cookie.strip()
                if cookie.lower().startswith('session'):
                    logger.error(f"    ✅ Found 'session' cookie in header: {cookie[:100]}...")
                logger.error(f"    Cookie: {cookie[:150]}")
        
        logger.error(f"  - Referer: {request.headers.get('referer', 'NOT FOUND')}")
        logger.error(f"  - Origin: {request.headers.get('origin', 'NOT FOUND')}")
        logger.error(f"  - x-forwarded-proto: {request.headers.get('x-forwarded-proto', 'NOT SET')}")
        logger.error(f"  - x-forwarded-for: {request.headers.get('x-forwarded-for', 'NOT SET')}")
        logger.error(f"  - host: {request.headers.get('host', 'NOT SET')}")
        
        # Check if session exists as attribute
        logger.error(f"Request has 'session' attribute: {hasattr(request, 'session')}")
        if hasattr(request, 'session'):
            logger.error(f"Request.session type: {type(request.session)}")
            logger.error(f"Request.session ID (if available): {getattr(request.session, 'id', 'N/A')}")
        
        logger.error("=" * 80)
        
        if not settings.google_client_id or not settings.google_client_secret or not settings.google_redirect_uri:
            raise HTTPException(status_code=500, detail="Google OAuth not configured")
        
        # Fetch access token and user profile from Google
        # This internally validates the state from session against incoming state param
        # If state mismatch, this will raise an error
        try:
            token = await oauth.google.authorize_access_token(request)
        except Exception as state_error:
            # Log detailed error about state mismatch
            logger.error("=" * 80)
            logger.error("STATE VALIDATION FAILED (DEBUG)")
            logger.error("=" * 80)
            logger.error(f"Error type: {type(state_error).__name__}")
            logger.error(f"Error message: {str(state_error)}")
            logger.error(f"Incoming state: {incoming_state}")
            logger.error(f"Stored state: {stored_state}")
            logger.error(f"States match: {incoming_state == stored_state}")
            logger.error(f"Session was empty: {len(session_contents) == 0}")
            logger.error("=" * 80)
            raise
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
        
        # DEBUG: Log successful state validation
        logger.error("=" * 80)
        logger.error("GOOGLE CALLBACK - STATE VALIDATED SUCCESSFULLY (DEBUG)")
        logger.error("=" * 80)
        logger.error(f"✅ State validation passed")
        logger.error(f"✅ Access token received from Google")
        logger.error(f"Email: {email}")
        logger.error("=" * 80)
        
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
        
        # DEBUG: Log final session state after callback
        final_session = dict(request.session) if hasattr(request, 'session') else {}
        logger.error("=" * 80)
        logger.error("GOOGLE CALLBACK - FINAL STATE (DEBUG)")
        logger.error("=" * 80)
        logger.error(f"Session contents after callback: {final_session}")
        logger.error(f"Redirecting to: {frontend_url}")
        logger.error("=" * 80)
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Google auth callback failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Google authentication failed: {str(e)}")

