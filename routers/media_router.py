"""
Media router for file upload and file handling endpoints
"""
import uuid
import logging
import asyncio
from pathlib import Path
from typing import Optional
from datetime import datetime
from fastapi import APIRouter, File, UploadFile, Form, Depends, Body
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
import aiofiles

from database import get_db
from utils.security_utils import validate_uploaded_file
from project_memory import get_or_create_project_memory
from backend.utils.responses import success_response, error_response
from utils.shared_utils import gtts_speak
from config.settings import MEDIA_DIR

logger = logging.getLogger(__name__)

# Create router with /media prefix to correctly structure API calls (e.g., /api/media/...)
media_router = APIRouter(prefix="/api/media")


class GenerateVocalRequest(BaseModel):
    session_id: str
    text: str


# === FIX 1: Add alias route to match frontend calls ===
@media_router.post("/upload/vocal")
async def upload_vocal_alias(
    file: UploadFile = File(...),
    session_id: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """Alias for /upload-audio to match frontend expectation at /api/media/upload/vocal"""
    return await upload_audio(file, session_id, db)

# Existing upload route
@media_router.post("/upload-audio")
async def upload_audio(
    file: UploadFile = File(...),
    session_id: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Clean audio upload endpoint - receives file, saves to media/{session_id}/recordings/, returns file URL
    
    Security validations:
    - Filename sanitization (prevents path traversal)
    - File extension whitelist
    - File size limit (50MB)
    - MIME type validation (content-based)
    """
    # Generate session_id if not provided
    if not session_id:
        session_id = str(uuid.uuid4())
    
    user_id = None
    
    # CRITICAL SECURITY: Validate and sanitize uploaded file
    # This performs:
    # 1. Filename sanitization (removes path traversal, directory separators, null bytes)
    # 2. File extension validation (whitelist check)
    # 3. File size validation (50MB limit)
    # 4. MIME type validation (content-based detection)
    sanitized_filename, file_content = await validate_uploaded_file(file)
    
    # Create directory structure without user_id (anonymous)
    recordings_dir = MEDIA_DIR / session_id / "recordings"
    recordings_dir.mkdir(parents=True, exist_ok=True)
    
    # Use sanitized filename in file path and URL (prevents path traversal)
    file_path = recordings_dir / sanitized_filename
    file_url = f"/media/{session_id}/recordings/{sanitized_filename}"
    
    # Save file asynchronously using aiofiles (non-blocking I/O)
    async with aiofiles.open(file_path, "wb") as f:
        await f.write(file_content)
    
    logger.info(f"File uploaded successfully: {sanitized_filename} (size: {len(file_content)} bytes) for session {session_id}")
    
    # Phase 6: Auto-save to project memory
    memory = await get_or_create_project_memory(session_id, MEDIA_DIR, user_id)
    if "assets" not in memory.project_data:
        memory.project_data["assets"] = {}
    memory.project_data["assets"]["vocals"] = [{
        "url": file_url,
        "added_at": datetime.now().isoformat(),
        "metadata": {}
    }]
    memory.project_data["assets"]["song"] = {
        "url": file_url,
        "added_at": datetime.now().isoformat(),
        "metadata": {"source": "upload"}
    }
    await memory.save()
    
    return success_response(
        data={
            "session_id": session_id,
            "file_url": file_url,
            "file_path": file_url,  # <== FIX 2: Add file_path to satisfy frontend expectation
        },
        message="Vocal uploaded"
    )


@media_router.post("/generate/vocal")
async def generate_vocal(
    request: GenerateVocalRequest = Body(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate vocal audio using gTTS and save to recordings directory.
    
    Body: { session_id: str, text: str }
    Returns: { session_id, file_url, file_path }
    """
    # Validate text is not empty
    if not request.text or not request.text.strip():
        return error_response("Missing text", status=400)
    
    session_id = request.session_id
    text = request.text.strip()
    user_id = None
    
    try:
        # Call gtts_speak (run in thread pool since it's a sync function)
        voice_result = await asyncio.to_thread(gtts_speak, "nova", text, session_id, None)
        
        # Check if gtts_speak returned an error
        if not isinstance(voice_result, dict) or not voice_result.get("ok"):
            error_msg = voice_result.get("message") or voice_result.get("error") or "Failed to generate voice"
            return error_response(error_msg, status=500)
        
        # Extract voice_url from response
        voice_url = voice_result.get("data", {}).get("url")
        if not voice_url:
            return error_response("Failed to get voice URL from gTTS", status=500)
        
        # Extract the hash/filename from voice_url (e.g., /media/{session_id}/voices/{hash}.mp3)
        # Convert URL path to file system path
        rel = voice_url.replace("/media/", "", 1).lstrip("/")
        voice_path = MEDIA_DIR / rel
        
        # Check if source file exists
        if not voice_path.exists():
            return error_response(f"Generated voice file not found: {voice_path}", status=500)
        
        # Create recordings directory
        recordings_dir = MEDIA_DIR / session_id / "recordings"
        recordings_dir.mkdir(parents=True, exist_ok=True)
        
        # Use timestamped filename: ai_take_YYYYMMDD_HHMMSS.mp3 or just ai_take.mp3
        # Using simple ai_take.mp3 as specified, but can be timestamped if needed
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"ai_take_{timestamp}.mp3"
        destination_path = recordings_dir / filename
        file_url = f"/media/{session_id}/recordings/{filename}"
        
        # Copy the file asynchronously
        async with aiofiles.open(voice_path, "rb") as src:
            file_content = await src.read()
            async with aiofiles.open(destination_path, "wb") as dst:
                await dst.write(file_content)
        
        logger.info(f"AI vocal generated and copied: {filename} for session {session_id}")
        
        # Update project memory
        memory = await get_or_create_project_memory(session_id, MEDIA_DIR, user_id)
        if "assets" not in memory.project_data:
            memory.project_data["assets"] = {}
        
        # Set assets.song.url with source:"ai"
        memory.project_data["assets"]["song"] = {
            "url": file_url,
            "added_at": datetime.now().isoformat(),
            "metadata": {"source": "ai"}
        }
        
        # Set assets.vocals (compat format)
        memory.project_data["assets"]["vocals"] = [{
            "url": file_url,
            "added_at": datetime.now().isoformat(),
            "metadata": {}
        }]
        await memory.save()
        
        return success_response(
            data={
                "session_id": session_id,
                "file_url": file_url,
                "file_path": file_url,  # Match upload response format
            },
            message="Vocal generated"
        )
    
    except Exception as e:
        logger.error(f"Error generating vocal: {e}", exc_info=True)
        return error_response(f"Failed to generate vocal: {str(e)}", status=500)
