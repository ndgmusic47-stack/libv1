"""
Label-in-a-Box Phase 2 Backend - Production Demo
Clean backend using ONLY: Beatoven, OpenAI (text), Auphonic, GetLate, local services
"""

from pathlib import Path
import logging
import traceback

from fastapi import FastAPI, APIRouter, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

# Import routers
from content import content_router
from auth import auth_router
from routers.billing_router import billing_router
from routers.beat_router import beat_router
from routers.lyrics_router import lyrics_router
from routers.media_router import media_router
from routers.release_router import release_router
from routers.analytics_router import analytics_router
from routers.social_router import social_router
from routers.google_auth_router import google_auth_router
from utils.rate_limit import RateLimiterMiddleware
from database import init_db
from config import settings

# ============================================================================
# PHASE 2.2: SHARED UTILITIES
# ============================================================================

# Logging setup - write ALL events to /logs/app.log
LOGS_DIR = Path("./logs")
LOGS_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOGS_DIR / "app.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Phase 1 normalized JSON response helpers - now from unified module
from backend.utils.responses import success_response, error_response

# ============================================================================
# FASTAPI APP SETUP
# ============================================================================

app = FastAPI(title="Label in a Box v4 - Phase 2.2")

# Default session secret key (fallback if SESSION_SECRET_KEY not set)
DEFAULT_SESSION_SECRET = "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6"

# Enforce HTTPS in production (Render)
def _is_render_env() -> bool:
    """Check if running in Render.com environment"""
    return bool(settings.render or settings.render_external_url or settings.render_service_name)

# Uncaught exception middleware - logs all unhandled exceptions and returns 500
class UncaughtExceptionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        try:
            return await call_next(request)
        except Exception as e:
            logger.error(f"Uncaught exception: {e}\n{traceback.format_exc()}")
            return JSONResponse(
                status_code=500,
                content={"ok": False, "error": "Internal Server Error"}
            )

app.add_middleware(UncaughtExceptionMiddleware)

# Session middleware for Google SSO flow
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret_key or DEFAULT_SESSION_SECRET,
    max_age=7 * 24 * 60 * 60,  # 7 days in seconds
    same_site='none',
    https_only=_is_render_env()
)

# Phase 1: Required API keys for startup validation
REQUIRED_KEYS = [
    "OPENAI_API_KEY",
    "BEATOVEN_API_KEY",
    "BUFFER_TOKEN",
    "DISTROKID_KEY",
]

# Map environment variable names to settings attributes
REQUIRED_KEY_MAP = {
    "OPENAI_API_KEY": settings.openai_api_key,
    "BEATOVEN_API_KEY": settings.beatoven_api_key,
    "BUFFER_TOKEN": settings.buffer_token,
    "DISTROKID_KEY": settings.distrokid_key,
}

# CORS middleware (Phase 1 hardening)
allowed_origins = []
if settings.frontend_url:
    allowed_origins = [settings.frontend_url]
else:
    allowed_origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Total-Count"],
)
# Rate limiting middleware (Phase 1)
app.add_middleware(RateLimiterMiddleware, requests_per_minute=30)

class EnforceHTTPSMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if _is_render_env():
            proto = request.headers.get("x-forwarded-proto", "")
            if proto and proto.lower() != "https":
                return error_response("HTTPS required", status_code=403)
        return await call_next(request)

app.add_middleware(EnforceHTTPSMiddleware)

# Security headers middleware
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses: CSP, HSTS, X-Frame-Options, X-Content-Type-Options"""
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        
        # Content-Security-Policy: Strict CSP to mitigate XSS risks
        # Allow self, inline scripts/styles (for frontend), and Beatoven API
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "connect-src 'self' https://public-api.beatoven.ai; "
            "img-src 'self' data: blob:; "
            "font-src 'self' data:; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "form-action 'self';"
        )
        
        # Strict-Transport-Security: Enforce HTTPS for 1 year, include subdomains
        # Only set in production (Render environment) where HTTPS is guaranteed
        if _is_render_env():
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        
        # X-Frame-Options: Prevent clickjacking attacks
        response.headers["X-Frame-Options"] = "DENY"
        
        # X-Content-Type-Options: Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"
        
        return response

app.add_middleware(SecurityHeadersMiddleware)

# Directory setup
MEDIA_DIR = Path("./media")
ASSETS_DIR = Path("./assets")
MEDIA_DIR.mkdir(exist_ok=True)
ASSETS_DIR.mkdir(exist_ok=True)
(ASSETS_DIR / "demo").mkdir(exist_ok=True)

# Serve static files
app.mount("/media", StaticFiles(directory=str(MEDIA_DIR)), name="media")

# ============================================================================
# API ROUTER WRAPPER (adds /api prefix for all endpoints)
# ============================================================================
# Note: The api router is kept for potential future use, but currently all
# endpoints are defined in their respective router modules
# api = APIRouter(prefix="/api")  # Currently unused

# ============================================================================
# STARTUP CHECKS - ENV KEYS (Phase 1)
# ============================================================================
@app.on_event("startup")
async def check_env_keys_on_startup():
    """Check for missing environment variables on startup (non-fatal warning)"""
    missing = []
    key_checks = {
        "OPENAI_API_KEY": settings.openai_api_key,
        "SUNO_API_KEY": None,  # Not in settings, skip
        "BUFFER_TOKEN": settings.buffer_token,
        "DISTROKID_KEY": settings.distrokid_key,
    }
    for env_key, value in key_checks.items():
        if value is None and env_key != "SUNO_API_KEY":  # Skip SUNO_API_KEY check
            missing.append(env_key)
    if missing:
        logger.warning(f"Startup check: Missing environment variables: {', '.join(missing)}")
    else:
        logger.info("Startup check: All critical environment variables are set")

# Phase 1: Additional startup validation for required keys (non-fatal)
@app.on_event("startup")
async def validate_keys():
    """Validate required API keys are present (non-fatal)"""
    missing = []
    for key in REQUIRED_KEYS:
        value = REQUIRED_KEY_MAP.get(key)
        if not value:
            missing.append(key)
    
    if missing:
        logger.warning(f"⚠️ Missing API keys: {missing}")
    else:
        logger.info("🔐 All API keys loaded successfully")

# Initialize database on startup
@app.on_event("startup")
async def initialize_database():
    """Initialize the SQLite database and create all tables."""
    try:
        await init_db()
        logger.info("✅ Database initialized successfully")
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        raise

# ============================================================================
# INCLUDE ROUTERS
# ============================================================================
app.include_router(auth_router)
app.include_router(google_auth_router)
app.include_router(content_router)
app.include_router(billing_router)
app.include_router(beat_router)
app.include_router(lyrics_router)
app.include_router(media_router)
app.include_router(release_router)
app.include_router(analytics_router)
app.include_router(social_router)

# ============================================================================
# FRONTEND SERVING (MUST BE LAST - AFTER ALL API ROUTES)
# ============================================================================

FRONTEND_DIST = Path(__file__).parent / "frontend" / "dist"

if FRONTEND_DIST.exists() and (FRONTEND_DIST / "index.html").exists():
    @app.get("/{path:path}")
    async def serve_frontend(request: Request, path: str):
        """
        Serve frontend files or index.html for SPA routes.
        Handles React Router client-side routing.
        """
        # Skip API routes and media routes (shouldn't reach here but safety check)
        if path.startswith("api/") or path.startswith("media/"):
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Not found")
        
        # Try to serve the actual file if it exists (JS, CSS, images, etc.)
        file_path = FRONTEND_DIST / path
        if path and file_path.exists() and file_path.is_file():
            # Security: Ensure file is within FRONTEND_DIST directory
            try:
                file_path.resolve().relative_to(FRONTEND_DIST.resolve())
            except ValueError:
                # Path outside FRONTEND_DIST, deny access
                from fastapi import HTTPException
                raise HTTPException(status_code=403, detail="Access denied")
            return FileResponse(str(file_path))
        
        # For all SPA routes (like /signup, /login, etc.), return index.html
        index_path = FRONTEND_DIST / "index.html"
        if index_path.exists():
            return FileResponse(str(index_path))
        
        # If index.html doesn't exist, return 404
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Frontend not built")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
