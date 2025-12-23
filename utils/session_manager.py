"""
Session Manager - Validates sessions and returns user dict for anonymous sessions
"""

from typing import Optional, Dict, Any
import logging
import re
from pathlib import Path
from config.settings import MEDIA_DIR

logger = logging.getLogger(__name__)

# Valid session_id format: UUID-like or alphanumeric with hyphens/underscores
# Prevents path traversal and ensures safe directory names
VALID_SESSION_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_-]{1,128}$')


class SessionManager:
    """
    SessionManager validates sessions and returns user dict for anonymous sessions.
    A session is valid if the session directory exists in the media folder.
    """
    
    @staticmethod
    def get_user(session_id: str) -> Optional[Dict[str, Any]]:
        """
        Get user from session ID.
        
        Args:
            session_id: Session ID to lookup
            
        Returns:
            User dict if session is valid, None otherwise
        """
        if not session_id or not isinstance(session_id, str):
            logger.debug(f"Invalid session_id: {session_id} (empty or not string)")
            return None
        
        # Validate session_id format to prevent path traversal and unsafe characters
        if not VALID_SESSION_ID_PATTERN.match(session_id):
            logger.warning(f"Invalid session_id format: {session_id} (contains unsafe characters)")
            return None
        
        # Validate session exists by checking if media directory exists
        # Sessions are anonymous - validity is determined by directory existence
        session_path = MEDIA_DIR / session_id
        
        try:
            # Check if session directory exists (atomic filesystem operation)
            if session_path.exists() and session_path.is_dir():
                # Return minimal user dict (anonymous session)
                return {
                    "id": session_id
                }
            else:
                logger.debug(f"Session directory does not exist: {session_path}")
                return None
        except (OSError, PermissionError) as e:
            # Handle filesystem errors gracefully
            logger.error(f"Error checking session directory for {session_id}: {e}")
            return None

