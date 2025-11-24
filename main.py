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
from starlette.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

# Import routers
from routers.content_router import router as content_router
from routers.billing_router import billing_router
from routers.beat_router import beat_router
from routers.lyrics_router import lyrics_router
from routers.media_router import media_router
from routers.mix_router import mix_router, mix_config_router
from routers.mix_ws_router import router as mix_ws_router
from routers.release_router import release_router
from routers.analytics_router import analytics_router
from routers.social_router import social_router
from utils.rate_limit import RateLimiterMiddleware
from database import init_db
from config.settings import settings, MEDIA_DIR

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

app.add_middleware(UncaughtExceptionMiddleware)
app.add_middleware(RateLimiterMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

# CORS MUST be near the bottom
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Directory setup
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
app.include_router(content_router)
app.include_router(billing_router)
app.include_router(beat_router)
app.include_router(lyrics_router)
app.include_router(media_router)
app.include_router(mix_router)
app.include_router(mix_config_router)
app.include_router(mix_ws_router)
app.include_router(release_router)
app.include_router(analytics_router)
app.include_router(social_router)

# ============================================================================
# FRONTEND SERVING (MUST BE LAST - AFTER ALL API ROUTES)
# ============================================================================

# Correct location in Render runtime: /opt/render/project/src/frontend/dist
FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"

# Mount assets folder
app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

# Serve SPA fallback
app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="spa-root")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
