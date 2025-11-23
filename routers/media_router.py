"""
Media router for file upload and file handling endpoints
"""
import uuid
import logging
from pathlib import Path
from typing import Optional
from datetime import datetime
from fastapi import APIRouter, File, UploadFile, Form, Depends
from sqlalchemy.ext.asyncio import AsyncSession
import aiofiles

from database import get_db
from utils.security_utils import validate_uploaded_file
from project_memory import get_or_create_project_memory
from backend.utils.responses import success_response
from config.settings import MEDIA_DIR

logger = logging.getLogger(__name__)

# Create router with /api prefix (will be included in main.py)
media_router = APIRouter(prefix="/api")


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
    await memory.save()
    
    return success_response(
        data={
            "session_id": session_id,
            "file_url": file_url
        },
        message="Vocal uploaded"
    )


