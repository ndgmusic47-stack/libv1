"""
Mix Router - API endpoints for audio mixing
"""
import logging
import asyncio
import os
from pathlib import Path
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from services.mix_service import MixService
from models.mix import MixRequest
from models.mix_config import MixConfig
from utils.mix.role_presets import ROLE_PRESETS
from utils.mix.mix_recipes import MIX_RECIPES
from utils.mix.config_apply import apply_recipe
from pydantic import BaseModel
from backend.utils.responses import success_response, error_response
from utils.shared_utils import log_endpoint_event
from utils.session_manager import SessionManager
from jobs.mix_job_manager import MixJobManager, JOBS
from utils.mix.timeline import get_timeline
from services.transport_service import play, pause, stop, seek
from project_memory import get_or_create_project_memory
from config.settings import MEDIA_DIR

logger = logging.getLogger(__name__)

# Mix execution concurrency and timeout controls
MIX_MAX_CONCURRENT = int(os.getenv("MIX_MAX_CONCURRENT", "2"))
MIX_TIMEOUT_SECONDS = int(os.getenv("MIX_TIMEOUT_SECONDS", "1200"))  # 20 min default
MIX_SEMAPHORE = asyncio.Semaphore(MIX_MAX_CONCURRENT)

# Create router
mix_router = APIRouter(prefix="/mix", tags=["Mix & Mastering"])

# Create separate router for mix config endpoints
mix_config_router = APIRouter(prefix="/api/mix", tags=["mix"])

# Service instance
mix_service = MixService()


@mix_router.get("/{project_id}/mix/status")
async def get_mix_status(
    project_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get the current mix status and file URL for a project"""
    try:
        mix_status = await mix_service.get_mix_status(project_id)
        log_endpoint_event(f"/projects/{project_id}/mix/status", project_id, "success", {})
        return success_response(
            data=mix_status,
            message="Mix status retrieved successfully"
        )
    except Exception as e:
        logger.error(f"Failed to get mix status for project {project_id}: {e}")
        log_endpoint_event(f"/projects/{project_id}/mix/status", project_id, "error", {"error": str(e)})
        return error_response("MIX_STATUS_ERROR", 500, f"Failed to get mix status: {str(e)}")


@mix_router.post("/{project_id}/mix/start")
async def start_mix(
    project_id: str,
    request: MixRequest = Body(...),
    db: AsyncSession = Depends(get_db)
):
    """
    Start a mix job using the DSP engine.
    """
    user = SessionManager.get_user(project_id)
    if user is None:
        return error_response("Invalid session")
    
    try:
        session_id = project_id
        
        # Prepare stems from request
        stems = {}
        if request.vocal_url:
            stems["vocal"] = request.vocal_url
        if request.beat_url:
            stems["beat"] = request.beat_url
        
        # If stems are missing, try to find them from project memory
        if not stems.get("vocal") or not stems.get("beat"):
            memory = await get_or_create_project_memory(project_id, MEDIA_DIR, None, db)
            assets = (memory.project_data or {}).get("assets", {})
            vocals = assets.get("vocals") or []
            beat = assets.get("beat")
            
            if not stems.get("vocal") and vocals and len(vocals) > 0 and vocals[0].get("url"):
                stems["vocal"] = vocals[0]["url"]
            if not stems.get("beat") and beat and beat.get("url"):
                stems["beat"] = beat["url"]
            
            if not stems.get("vocal") or not stems.get("beat"):
                raise HTTPException(status_code=400, detail="Missing vocal or beat asset in project memory")
        
        if not stems:
            return error_response("NO_STEMS", 400, "No stems provided for mixing")
        
        # Enqueue mix job
        job_id = await MixJobManager.enqueue_mix(session_id, stems, request.config or {})
        
        # Start mix processing (async)
        asyncio.create_task(_process_mix_job(job_id, session_id, stems))
        
        log_endpoint_event(f"/projects/{project_id}/mix/start", project_id, "success", {"job_id": job_id})
        return success_response({"job_id": job_id})
    except Exception as e:
        logger.error(f"Failed to start mix for project {project_id}: {e}")
        log_endpoint_event(f"/projects/{project_id}/mix/start", project_id, "error", {"error": str(e)})
        return error_response("MIX_START_ERROR", 500, f"Failed to start mix: {str(e)}")


@mix_router.get("/projects/{project_id}/mix/status")
async def get_mix_status_with_job_id(
    project_id: str,
    job_id: str = Query(None, description="Job ID"),
    db: AsyncSession = Depends(get_db)
):
    """
    Check mix job status (alias endpoint for frontend compatibility).
    """
    try:
        if not job_id:
            return error_response("JOB_ID_REQUIRED", 400, "Job ID is required")
        
        job_status = await MixJobManager.get_job_status(job_id)
        log_endpoint_event(f"/projects/{project_id}/mix/status", project_id, "success", {})
        
        # MixJobManager.get_job_status already returns UI-safe format with is_error
        if job_status.get("is_error"):
            return error_response("JOB_NOT_FOUND", 404, job_status.get("error", "Job not found"))
        
        return success_response(
            data=job_status.get("data"),
            message="Job status retrieved successfully"
        )
    except Exception as e:
        logger.error(f"Failed to get job status for job {job_id}: {e}")
        log_endpoint_event(f"/projects/{project_id}/mix/status", project_id, "error", {"error": str(e)})
        return error_response("JOB_STATUS_ERROR", 500, f"Failed to get job status: {str(e)}")


@mix_router.get("/{project_id}/mix/job/{job_id}/status")
async def get_job_status(
    project_id: str,
    job_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Check mix job status.
    """
    try:
        job_status = await MixJobManager.get_job_status(job_id)
        log_endpoint_event(f"/projects/{project_id}/mix/job/{job_id}/status", project_id, "success", {})
        
        # MixJobManager.get_job_status already returns UI-safe format with is_error
        if job_status.get("is_error"):
            return error_response("JOB_NOT_FOUND", 404, job_status.get("error", "Job not found"))
        
        return success_response(
            data=job_status.get("data"),
            message="Job status retrieved successfully"
        )
    except Exception as e:
        logger.error(f"Failed to get job status for job {job_id}: {e}")
        log_endpoint_event(f"/projects/{project_id}/mix/job/{job_id}/status", project_id, "error", {"error": str(e)})
        return error_response("JOB_STATUS_ERROR", 500, f"Failed to get job status: {str(e)}")


@mix_router.get("/{project_id}/mix/preview")
async def get_mix_preview(
    project_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Returns final_mix.wav if exists.
    """
    user = SessionManager.get_user(project_id)
    if user is None:
        return error_response("Invalid session")
    
    try:
        from config.settings import MEDIA_DIR
        from services.mix_service import STORAGE_MIX_OUTPUTS
        
        session_id = project_id
        mix_path = STORAGE_MIX_OUTPUTS / session_id / "final_mix.wav"
        
        # Check if file exists
        if not mix_path.exists():
            return error_response("MIX_NOT_FOUND", 404, "Mix file not found")
        
        log_endpoint_event(f"/projects/{project_id}/mix/preview", project_id, "success", {})
        return FileResponse(
            path=str(mix_path),
            media_type="audio/wav",
            filename="final_mix.wav"
        )
    except Exception as e:
        logger.error(f"Failed to get mix preview for project {project_id}: {e}")
        log_endpoint_event(f"/projects/{project_id}/mix/preview", project_id, "error", {"error": str(e)})
        return error_response("MIX_PREVIEW_ERROR", 500, f"Failed to get mix preview: {str(e)}")


@mix_router.get("/timeline/{job_id}")
async def get_mix_timeline(job_id: str):
    events = get_timeline(job_id)
    return success_response([
        {
            "step": e.step,
            "message": e.message,
            "progress": e.progress,
            "timestamp": e.timestamp.isoformat()
        }
        for e in events
    ])


@mix_router.get("/visual/{job_id}")
async def get_mix_visual(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        return success_response(None, message="No data available (job missing or expired)")
    return success_response(job.extra.get("visual", None))


@mix_router.get("/scope/{job_id}")
async def get_scope(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        return success_response(None, message="No data available (job missing or expired)")
    return success_response(job.extra.get("realtime_scope", None))


@mix_router.get("/streams/{job_id}")
async def list_streams(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        return success_response(None, message="No data available (job missing or expired)")

    streams = job.extra.get("realtime_stream", {})
    return success_response({
        "available": {
            "tracks": list(streams.get("tracks", {}).keys()),
            "pre_master": "pre_master" in streams,
            "post_master": "post_master" in streams
        }
    })


async def _process_mix_job(job_id: str, session_id: str, stems: dict):
    """Background task to process mix job"""
    try:
        # Get config from job
        job = JOBS.get(job_id)
        config = job.extra.get("config")
        
        # Optional: Update job state to show waiting
        MixJobManager.update(job_id, state="queued", message="Waiting for mixer slot", progress=0)
        
        # Acquire semaphore to enforce concurrency limit
        async with MIX_SEMAPHORE:
            MixJobManager.update(job_id, state="running", message="Mix started", progress=1)
            
            # Run mix with timeout (progress tracking is handled inside MixService.mix)
            result = await asyncio.wait_for(
                MixService.mix(session_id, stems, config=config, job_id=job_id),
                timeout=MIX_TIMEOUT_SECONDS
            )
        
        if result.get("is_error"):
            logger.error(f"Mix job {job_id} failed: {result.get('error')}")
        else:
            logger.info(f"Mix job {job_id} completed successfully")
    except asyncio.TimeoutError:
        MixJobManager.update(job_id, state="error", progress=100, message="Mix timeout", error="Mix exceeded timeout")
        logger.error(f"Mix job {job_id} timed out after {MIX_TIMEOUT_SECONDS} seconds")
    except Exception as e:
        MixJobManager.update(job_id, state="error", progress=100, message="Mix failed", error=str(e))
        logger.error(f"Mix job {job_id} failed with exception: {e}")


@mix_router.post("/transport/{job_id}/play")
async def play_transport(job_id: str):
    await play(job_id)
    return success_response({"status": "playing"})


@mix_router.post("/transport/{job_id}/pause")
async def pause_transport(job_id: str):
    await pause(job_id)
    return success_response({"status": "paused"})


@mix_router.post("/transport/{job_id}/stop")
async def stop_transport(job_id: str):
    await stop(job_id)
    return success_response({"status": "stopped"})


@mix_router.post("/transport/{job_id}/seek")
async def seek_transport(job_id: str, position: float = Body(...)):
    await seek(job_id, position)
    return success_response({"status": "seeked", "position": position})


@mix_config_router.get("/config/schema")
async def get_mix_schema():
    # Serialize Pydantic models to dicts (compatible with both v1 and v2)
    def serialize_model(model):
        if hasattr(model, 'model_dump'):
            return model.model_dump()
        elif hasattr(model, 'dict'):
            return model.dict()
        return model
    
    return {
        "roles": list(ROLE_PRESETS.keys()),
        "recipes": list(MIX_RECIPES.keys()),
        "role_presets": {k: serialize_model(v) for k, v in ROLE_PRESETS.items()},
        "mix_recipes": {k: serialize_model(v) for k, v in MIX_RECIPES.items()},
    }


class ApplyConfigRequest(BaseModel):
    session_id: str
    recipe: str
    track_roles: dict


@mix_config_router.post("/config/apply")
async def apply_mix_config(request: ApplyConfigRequest):
    user = SessionManager.get_user(request.session_id)
    if user is None:
        return error_response("Invalid session")
    
    config = apply_recipe(request.recipe, request.track_roles)
    # Serialize Pydantic model to dict (compatible with both v1 and v2)
    if hasattr(config, 'model_dump'):
        config_dict = config.model_dump()
    elif hasattr(config, 'dict'):
        config_dict = config.dict()
    else:
        config_dict = config
    return {"success": True, "config": config_dict}


@mix_config_router.post("/run-clean")
async def run_clean_wrapper(
    project_id: str = Body(...),
    db: AsyncSession = Depends(get_db)
):
    """
    Temporary compatibility wrapper.
    Always triggers the DSP mix engine via the job system.
    """
    user = SessionManager.get_user(project_id)
    if user is None:
        return error_response("Invalid session")
    
    try:
        session_id = project_id
        
        # Prepare stems from default locations
        from config.settings import MEDIA_DIR
        base = MEDIA_DIR / session_id
        vocal_path = base / "vocal.wav"
        beat_path = base / "beat.mp3"
        
        stems = {}
        if vocal_path.exists():
            stems["vocal"] = str(vocal_path)
        if beat_path.exists():
            stems["beat"] = str(beat_path)
        
        if not stems:
            return error_response("NO_STEMS", 400, "No stems provided for mixing")
        
        # Enqueue mix job (same as start_mix)
        job_id = await MixJobManager.enqueue_mix(session_id, stems, {})
        
        # Start mix processing (async)
        asyncio.create_task(_process_mix_job(job_id, session_id, stems))
        
        log_endpoint_event("/api/mix/run-clean", project_id, "success", {"job_id": job_id})
        return success_response({"job_id": job_id})
    except Exception as e:
        logger.error(f"Failed to run clean mix for project {project_id}: {e}")
        log_endpoint_event("/api/mix/run-clean", project_id, "error", {"error": str(e)})
        return error_response("MIX_START_ERROR", 500, f"Failed to start mix: {str(e)}")