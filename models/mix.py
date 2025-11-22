"""
Mix-related request models
"""
from pydantic import BaseModel
from typing import Optional


class MixRequest(BaseModel):
    """Request model for mix operations"""
    vocal_url: Optional[str] = None
    beat_url: Optional[str] = None
    session_id: Optional[str] = None


class CleanMixRequest(BaseModel):
    """Legacy request model - kept for backward compatibility"""
    session_id: str
    vocal_url: str
    beat_url: str

