"""
Media router for file upload and mixing endpoints
"""
import uuid
import logging
from pathlib import Path
from typing import Optional
from datetime import datetime
from fastapi import APIRouter, File, UploadFile, Form, Depends
from sqlalchemy.ext.asyncio import AsyncSession
import aiofiles

from auth import get_current_user
from database import get_db
from models.mix import CleanMixRequest
from services.mix_service import MixService
from utils.shared_utils import require_feature_pro, get_session_media_path
from utils.security_utils import validate_uploaded_file
from project_memory import get_or_create_project_memory
from backend.utils.responses import success_response

logger = logging.getLogger(__name__)

# Create router with /api prefix (will be included in main.py)
media_router = APIRouter(prefix="/api")


@media_router.post("/upload-audio")
async def upload_audio(
    file: UploadFile = File(...),
    session_id: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user),
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
    # Phase 8A: Feature gate for clean upload
    deny = await require_feature_pro(current_user, feature="upload", endpoint="/upload-audio", db=db)
    if deny is not None:
        return deny
    
    # Generate session_id if not provided
    if not session_id:
        session_id = str(uuid.uuid4())
    
    user_id = current_user.get("user_id")
    
    # CRITICAL SECURITY: Validate and sanitize uploaded file
    # This performs:
    # 1. Filename sanitization (removes path traversal, directory separators, null bytes)
    # 2. File extension validation (whitelist check)
    # 3. File size validation (50MB limit)
    # 4. MIME type validation (content-based detection)
    sanitized_filename, file_content = await validate_uploaded_file(file)
    
    # Create directory structure with user_id
    recordings_dir = Path("./media") / user_id / session_id / "recordings"
    recordings_dir.mkdir(parents=True, exist_ok=True)
    
    # Use sanitized filename in file path and URL (prevents path traversal)
    file_path = recordings_dir / sanitized_filename
    file_url = f"/media/{user_id}/{session_id}/recordings/{sanitized_filename}"
    
    # Save file asynchronously using aiofiles (non-blocking I/O)
    async with aiofiles.open(file_path, "wb") as f:
        await f.write(file_content)
    
    logger.info(f"File uploaded successfully: {sanitized_filename} (size: {len(file_content)} bytes) by user {user_id}")
    
    # Phase 6: Auto-save to project memory
    MEDIA_DIR = Path("./media")
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


@media_router.post("/mix/run-clean")
async def run_clean_mix(
    request: CleanMixRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Clean mix with DSP processing: overlay processed vocal on beat"""
    # Phase 8A: Feature gate for clean mix
    deny = await require_feature_pro(current_user, feature="mix", endpoint="/mix/run-clean", db=db)
    if deny is not None:
        return deny
    
    # Use user_id from current_user, fallback to request.user_id
    user_id = current_user.get("user_id") or request.user_id
    if not user_id:
        from backend.utils.responses import error_response
        return error_response("MISSING_USER_ID", 400, "User ID is required")
    
    # Update request with user_id if not set
    if not request.user_id:
        request.user_id = user_id
    
    # Call service method
    return await MixService.run_clean_mix(request, user_id)


@media_router.get("/mix/{session_id}")
async def get_mix_status(
    session_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get the current mix status and file URL for a session.
    
    Returns:
        Success response with status and mix_url (if available)
    """
    user_id = current_user.get("user_id")
    if not user_id:
        from backend.utils.responses import error_response
        return error_response("MISSING_USER_ID", 400, "User ID is required")
    
    mix_status = await MixService.get_mix_status(user_id, session_id)
    return success_response(
        data=mix_status,
        message="Mix status retrieved successfully"
    )


@media_router.post("/mix/{user_id}/{session_id}")
async def mix_audio(user_id: str, session_id: str):
    """Basic mix endpoint using apply_basic_mix"""
    return await MixService.mix_audio(user_id, session_id)


@media_router.post("/mix/process-single/{user_id}")
async def process_single_mix(
    user_id: str,
    file: UploadFile = File(...),
    apply_eq: bool = Form(False),
    apply_compression: bool = Form(False),
    apply_limiter: bool = Form(False),
    apply_saturation: bool = Form(False),
    session_id: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Process a single audio file with optional mastering effects.
    
    Args:
        user_id: User ID (path parameter)
        file: Audio file to process
        apply_eq: Enable EQ processing
        apply_compression: Enable compression
        apply_limiter: Enable limiter
        apply_saturation: Enable saturation
        session_id: Optional session ID (if not provided, extracted from user_id)
    
    Returns:
        Success response with mix_url
    """
    from backend.utils.responses import error_response
    
    # Verify user_id matches authenticated user
    authenticated_user_id = current_user.get("user_id")
    if not authenticated_user_id or authenticated_user_id != user_id:
        return error_response("UNAUTHORIZED", 403, "User ID mismatch")
    
    # Generate session_id if not provided
    if not session_id:
        session_id = str(uuid.uuid4())
    
    # Validate and sanitize uploaded file
    sanitized_filename, file_content = await validate_uploaded_file(file)
    
    # Ensure input directory exists
    input_dir = Path(f"./media/{user_id}/mix")
    input_dir.mkdir(parents=True, exist_ok=True)
    
    # Save input file
    input_path = input_dir / "input.wav"
    async with aiofiles.open(input_path, "wb") as f:
        await f.write(file_content)
    
    # Output path
    output_path = input_dir / "master.wav"
    
    # Prepare toggles dict
    toggles = {
        "apply_eq": apply_eq,
        "apply_compression": apply_compression,
        "apply_limiter": apply_limiter,
        "apply_saturation": apply_saturation,
    }
    
    # Process file
    try:
        result = await MixService.process_single_file(
            str(input_path),
            str(output_path),
            toggles
        )
        
        # Generate public URL
        mix_url = f"/media/{user_id}/mix/master.wav"
        
        # Update project memory
        MEDIA_DIR = Path("./media")
        memory = await get_or_create_project_memory(session_id, MEDIA_DIR, user_id)
        if "mix" not in memory.project_data:
            memory.project_data["mix"] = {}
        memory.project_data["mix"].update({
            "masterFile": mix_url,
            "completed": True
        })
        await memory.save()
        
        return success_response(
            data={"mix_url": mix_url},
            message="Mix processed successfully"
        )
    except Exception as e:
        logger.error(f"Failed to process single mix: {e}")
        return error_response("PROCESSING_ERROR", 500, f"Failed to process audio: {str(e)}")
