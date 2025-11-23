"""
V23 ContentStage MVP Backend
Handles video idea generation, upload, analysis, caption generation, and scheduling.
"""

from typing import Optional, List

from fastapi import APIRouter, Body, Query
from pydantic import BaseModel, Field

from backend.utils.responses import success_response, error_response
from services.content_service import ContentService
from utils.session_manager import SessionManager

# Create router for content endpoints
router = APIRouter(prefix="/api/content", tags=["content"])

# Helper functions - removed, using shared_utils version

# ============================================================================
# STEP 1: POST /content/idea - Generate Video Idea
# ============================================================================

class IdeaRequest(BaseModel):
    session_id: Optional[str] = None
    title: Optional[str] = None
    lyrics: Optional[str] = None
    mood: Optional[str] = None
    genre: Optional[str] = None

@router.post("/idea")
async def generate_video_idea(request: IdeaRequest = Body(default=None)):
    """Generate a simple, practical video idea"""
    result = await ContentService.generate_idea(request)
    if result.get("is_error"):
        return error_response(result.get("error", "Unknown error"))
    return success_response(result["data"])

# ============================================================================
# STEP 3: POST /content/analyze - Analyze Video for Viral Score
# ============================================================================

class AnalyzeRequest(BaseModel):
    transcript: str = Field(..., description="Video transcript")
    title: Optional[str] = None
    lyrics: Optional[str] = None
    mood: Optional[str] = None
    genre: Optional[str] = None

@router.post("/analyze")
async def analyze_video(request: AnalyzeRequest):
    """Analyze video transcript and return viral score + improvements"""
    result = await ContentService.analyze_text(request)
    if result.get("is_error"):
        return error_response(result.get("error", "Unknown error"))
    return success_response(result["data"])

# ============================================================================
# STEP 4: POST /content/generate-text - Generate Captions & Hashtags
# ============================================================================

class GenerateTextRequest(BaseModel):
    session_id: Optional[str] = None
    title: Optional[str] = None
    transcript: Optional[str] = None
    lyrics: Optional[str] = None
    mood: Optional[str] = None
    genre: Optional[str] = None

@router.post("/generate-text")
async def generate_text(request: GenerateTextRequest):
    """Generate captions, hashtags, hooks, posting strategy, and content ideas"""
    result = await ContentService.generate_text(request)
    if result.get("is_error"):
        return error_response(result.get("error", "Unknown error"))
    return success_response(result["data"])

# ============================================================================
# STEP 5: POST /content/schedule - Schedule Video via GETLATE API
# ============================================================================

class ScheduleRequest(BaseModel):
    session_id: str = Field(..., description="Session ID")
    video_url: str = Field(..., description="Video file URL")
    caption: str = Field(..., description="Selected caption")
    hashtags: Optional[List[str]] = Field(default=[], description="Selected hashtags")
    platform: str = Field(default="tiktok", description="Platform (tiktok, shorts, reels)")
    schedule_time: str = Field(..., description="ISO datetime string for scheduling")

@router.post("/schedule")
async def schedule_video(request: ScheduleRequest):
    """Schedule video using GETLATE API"""
    # Normalize Session → User Lookup (Phase 4C)
    user = SessionManager.get_user(request.session_id)
    if user is None:
        return error_response("Invalid session")
    
    result = await ContentService.schedule_post(request)
    if result.get("is_error"):
        return error_response(result.get("error", "Unknown error"))
    return success_response(result["data"])

# ============================================================================
# POST /content/save-scheduled - Save Scheduled Post
# ============================================================================

class SaveScheduledRequest(BaseModel):
    sessionId: str = Field(..., description="Session ID")
    platform: str = Field(..., description="Platform (tiktok, shorts, reels)")
    dateTime: Optional[str] = Field(None, description="ISO datetime string")
    time: Optional[str] = Field(None, description="ISO datetime string (legacy)")
    caption: Optional[str] = Field(None, description="Caption text")

@router.post("/save-scheduled")
async def save_scheduled(request: SaveScheduledRequest):
    """Save scheduled post to project memory"""
    # Normalize Session → User Lookup (Phase 4C)
    user = SessionManager.get_user(request.sessionId)
    if user is None:
        return error_response("Invalid session")
    
    result = await ContentService.save_scheduled_post(request)
    if result.get("is_error"):
        return error_response(result.get("error", "Unknown error"))
    return success_response(result["data"])

# ============================================================================
# GET /content/get-scheduled - Get Scheduled Posts
# ============================================================================

@router.get("/get-scheduled")
async def get_scheduled(session_id: str = Query(..., description="Session ID")):
    """Get all scheduled posts for a session"""
    # Normalize Session → User Lookup (Phase 4C)
    user = SessionManager.get_user(session_id)
    if user is None:
        return error_response("Invalid session")
    
    result = await ContentService.get_scheduled_posts(session_id)
    if result.get("is_error"):
        return error_response(result.get("error", "Unknown error"))
    return success_response(result["data"])

