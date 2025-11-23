"""
Shared utility functions for routers and services
"""
import json
import logging
import time
import hashlib
import uuid
from pathlib import Path
from typing import Optional, Callable, Any, Awaitable
from datetime import datetime
from gtts import gTTS
from sqlalchemy.ext.asyncio import AsyncSession

from backend.utils.responses import success_response, error_response
from config.settings import settings, MEDIA_DIR

logger = logging.getLogger(__name__)

# Redis client for caching
_redis_cache_client = None
_redis_cache_available = False

try:
    import redis
    redis_url = settings.redis_url
    if redis_url:
        try:
            # Parse Redis URL (supports redis:// and redis://:password@host:port)
            _redis_cache_client = redis.from_url(redis_url, decode_responses=True)
            # Test connection
            _redis_cache_client.ping()
            _redis_cache_available = True
            logger.info("✅ Redis connected successfully for caching")
        except Exception as e:
            logger.warning(f"⚠️ Redis connection failed: {e}. Caching will fall back to direct execution.")
            _redis_cache_client = None
            _redis_cache_available = False
    else:
        logger.info("ℹ️ REDIS_URL not set. Caching will fall back to direct execution.")
except ImportError:
    logger.warning("⚠️ redis package not installed. Caching will fall back to direct execution.")

# Voice debounce system (gTTS ONLY) - PHASE 2.2: 10s DEBOUNCE, SHA256 CACHE
_voice_debounce_cache: dict[str, float] = {}
_voice_debounce_seconds = 10.0  # Phase 2.2: 10-second debounce


async def get_cached(key: str, fallback_func: Callable[[], Awaitable[Any]], ttl_seconds: int) -> Any:
    """
    Distributed caching utility with Redis fallback.
    
    Attempts to fetch data from Redis cache. If not found or Redis is unavailable,
    executes the fallback function and stores the result in Redis with TTL.
    
    Args:
        key: Redis cache key (e.g., "user:123")
        fallback_func: Async callable that returns the data to cache
        ttl_seconds: Time-to-live in seconds for the cached value
    
    Returns:
        The cached value or the result from fallback_func
    
    Example:
        user_data = await get_cached(
            f"user:{user_id}",
            lambda: fetch_user_from_db(user_id),
            ttl_seconds=300
        )
    """
    # Try to fetch from Redis if available
    if _redis_cache_available and _redis_cache_client:
        try:
            cached_value = _redis_cache_client.get(key)
            if cached_value is not None:
                try:
                    # Try to parse as JSON (for dict/list values)
                    return json.loads(cached_value)
                except (json.JSONDecodeError, TypeError):
                    # If not JSON, return as string
                    return cached_value
        except Exception as e:
            logger.warning(f"Redis cache get failed for key '{key}': {e}. Executing fallback.")
    
    # Cache miss or Redis unavailable - execute fallback
    try:
        result = await fallback_func()
        
        # Try to store in Redis if available
        if _redis_cache_available and _redis_cache_client:
            try:
                # Serialize result to JSON if it's a dict/list, otherwise store as string
                if isinstance(result, (dict, list)):
                    cache_value = json.dumps(result)
                else:
                    cache_value = str(result)
                
                _redis_cache_client.setex(key, ttl_seconds, cache_value)
            except Exception as e:
                logger.warning(f"Redis cache set failed for key '{key}': {e}. Result not cached.")
        
        return result
    except Exception as e:
        logger.error(f"Fallback function failed for cache key '{key}': {e}")
        raise


async def require_feature_pro(current_user: dict, feature: str, endpoint: str, db: AsyncSession):
    """
    Feature gate: REMOVED - Always allows access (no paywall enforcement).
    Kept for backward compatibility but always returns None (allows access).
    
    - current_user: dict (ignored)
    - feature: short feature key, e.g. "upload", "mix", "release_pack" (ignored)
    - endpoint: endpoint path string for logging (ignored)
    - db: AsyncSession for database operations (ignored)
    """
    # Always allow access - no paywall enforcement
    return None


def get_session_media_path(session_id: str, user_id: Optional[str] = None) -> Path:
    """
    Get session media path (anonymous, no user_id required).
    user_id parameter kept for backward compatibility but ignored.
    """
    path = MEDIA_DIR / session_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_project_media_path(project_id: str) -> Path:
    """
    Get project media path.
    """
    path = MEDIA_DIR / project_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def log_endpoint_event(endpoint: str, session_id: Optional[str] = None, result: str = "success", details: Optional[dict] = None):
    """Log endpoint execution to app.log"""
    log_data = {
        "endpoint": endpoint,
        "session_id": session_id or "none",
        "result": result,
        "timestamp": datetime.now().isoformat()
    }
    if details:
        log_data.update(details)
    logger.info(f"{endpoint} | session={session_id} | {result} | {json.dumps(details or {})}")


def should_speak(persona: str, text: str) -> bool:
    """Phase 2.2: Debounce with 10-second window and SHA256 key"""
    # SHA256 cache key (Phase 2.2 requirement)
    key = hashlib.sha256(f"{persona}:{text}".encode()).hexdigest()
    now = time.time()
    last_time = _voice_debounce_cache.get(key, 0)
    if now - last_time < _voice_debounce_seconds:
        return False
    _voice_debounce_cache[key] = now
    return True


def gtts_speak(persona: str, text: str, session_id: Optional[str] = None, user_id: Optional[str] = None):
    """Phase 2.2: Generate speech using gTTS with SHA256 cache and 10s debounce (anonymous, no user_id required)"""
    # Generate session_id if not provided
    if not session_id:
        session_id = str(uuid.uuid4())
    
    # Generate SHA256 cache key (Phase 2.2 requirement)
    cache_key = hashlib.sha256(f"{persona}:{text}".encode()).hexdigest()
    
    # Create voices directory (anonymous, no user_id required)
    voices_dir = get_session_media_path(session_id, user_id) / "voices"
    voices_dir.mkdir(exist_ok=True, parents=True)
    
    output_file = voices_dir / f"{cache_key}.mp3"
    
    # Check debounce (but still return URL to cached file)
    is_debounced = not should_speak(persona, text)
    
    try:
        # Generate if not cached on disk
        if not output_file.exists():
            # Persona-specific accents (using only gTTS-supported TLDs)
            tld_map = {
                "nova": "com", "echo": "co.uk", "lyrica": "com.au",
                "tone": "ca", "aria": "co.in", "vee": "com", "pulse": "co.za"
            }
            tld = tld_map.get(persona, "com")
            
            tts = gTTS(text=text, lang="en", tld=tld, slow=False)
            tts.save(str(output_file))
        
        # Return URL whether debounced or not (spec requires playable asset)
        # Construct URL path relative to media directory (anonymous)
        url_path = f"/media/{session_id}/voices/{cache_key}.mp3"
        log_endpoint_event("/voices/say", session_id, "success", {"persona": persona, "cached": is_debounced})
        return success_response(
            data={
                "url": url_path,
                "persona": persona,
                "cached": is_debounced,
                "session_id": session_id
            },
            message="Voice cached (debounced)" if is_debounced else f"Voice generated for {persona}"
        )
    except Exception as e:
        log_endpoint_event("/voices/say", session_id, "error", {"error": str(e), "persona": persona})
        return error_response(f"gTTS failed: {str(e)}")

