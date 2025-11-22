"""
Mix Router - API endpoints for audio mixing
"""
import logging
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from services.mix_service import MixService
from models.mix import MixRequest
from backend.utils.responses import success_response, error_response
from utils.shared_utils import log_endpoint_event

logger = logging.getLogger(__name__)

# Create router
mix_router = APIRouter(prefix="/api/projects", tags=["mix"])

# Service instance
mix_service = MixService()


@mix_router.post("/{project_id}/mix")
async def mix_audio(
    project_id: str,
    data: MixRequest = Body(...),
    db: AsyncSession = Depends(get_db)
):
    """Mix audio for a project"""
    try:
        result = await mix_service.mix_audio(project_id, data)
        log_endpoint_event(f"/projects/{project_id}/mix", project_id, "success", {})
        return result
    except Exception as e:
        logger.error(f"Mix failed for project {project_id}: {e}")
        log_endpoint_event(f"/projects/{project_id}/mix", project_id, "error", {"error": str(e)})
        return error_response("MIX_ERROR", 500, f"Failed to mix audio: {str(e)}")


@mix_router.get("/{project_id}/mix")
async def get_mix_status(
    project_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get the current mix status and file URL for a project"""
    try:
        mix_status = await mix_service.get_mix_status(project_id)
        log_endpoint_event(f"/projects/{project_id}/mix", project_id, "success", {})
        return success_response(
            data=mix_status,
            message="Mix status retrieved successfully"
        )
    except Exception as e:
        logger.error(f"Failed to get mix status for project {project_id}: {e}")
        log_endpoint_event(f"/projects/{project_id}/mix", project_id, "error", {"error": str(e)})
        return error_response("MIX_STATUS_ERROR", 500, f"Failed to get mix status: {str(e)}")

