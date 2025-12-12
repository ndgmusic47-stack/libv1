from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from project_memory import get_or_create_project_memory
from config.settings import MEDIA_DIR

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("/{session_id}")
async def get_project(session_id: str, db: AsyncSession = Depends(get_db)):
    """
    Minimal endpoint to fetch or create project memory for a session.
    Used by frontend api.getProject / syncProject.
    """
    project = await get_or_create_project_memory(session_id, MEDIA_DIR, None, db)
    return {"ok": True, "project": project.project_data}


@router.post("/{session_id}/advance")
async def advance_project(session_id: str, db: AsyncSession = Depends(get_db)):
    """
    Minimal stub for advanceStage.
    For now, either advance workflow if helper exists,
    or just return the current project so the frontend can proceed.
    """
    # Try to import an advance helper if it exists
    try:
        from project_memory import advance_workflow_stage  # type: ignore
        project = await advance_workflow_stage(session_id=session_id, db=db)
    except ImportError:
        # Fallback: just return the existing project memory
        project = await get_or_create_project_memory(session_id, MEDIA_DIR, None, db)
    except Exception:
        # If anything goes wrong, fail soft for MVP
        project = await get_or_create_project_memory(session_id, MEDIA_DIR, None, db)

    return {"ok": True, "project": project.project_data}

