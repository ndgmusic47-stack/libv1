from fastapi import APIRouter, UploadFile, File, Body

from backend.utils.responses import success_response, error_response
from services.release_service import ReleaseService

release_router = APIRouter(prefix="/api/release", tags=["release"])
service = ReleaseService()


@release_router.post("/{project_id}/cover")
async def upload_cover(project_id: str, file: UploadFile = File(...)):
    result = await service.save_cover(project_id, file)
    if result.get("is_error"):
        return error_response(result.get("error", "Unknown error"))
    return success_response(result["data"])


@release_router.post("/{project_id}/copy")
async def upload_copy(project_id: str, text: str = Body(...)):
    result = await service.save_release_copy(project_id, text)
    if result.get("is_error"):
        return error_response(result.get("error", "Unknown error"))
    return success_response(result["data"])


@release_router.post("/{project_id}/pdf")
async def upload_pdf(project_id: str, pdf_bytes: bytes = Body(...)):
    result = await service.save_lyrics_pdf(project_id, pdf_bytes)
    if result.get("is_error"):
        return error_response(result.get("error", "Unknown error"))
    return success_response(result["data"])


@release_router.post("/{project_id}/metadata")
async def upload_metadata(project_id: str, metadata: dict = Body(...)):
    result = await service.save_metadata(project_id, metadata)
    if result.get("is_error"):
        return error_response(result.get("error", "Unknown error"))
    return success_response(result["data"])


@release_router.get("/{project_id}/zip")
async def generate_zip(project_id: str):
    result = await service.generate_release_zip(project_id)
    if result.get("is_error"):
        return error_response(result.get("error", "Unknown error"))
    return success_response(result["data"])
