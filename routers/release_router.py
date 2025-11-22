from fastapi import APIRouter, UploadFile, File, Body

from services.release_service import ReleaseService

release_router = APIRouter(prefix="/api/release", tags=["release"])
service = ReleaseService()


@release_router.post("/{project_id}/cover")
async def upload_cover(project_id: str, file: UploadFile = File(...)):
    return {"path": await service.save_cover(project_id, file)}


@release_router.post("/{project_id}/copy")
async def upload_copy(project_id: str, text: str = Body(...)):
    return {"path": await service.save_release_copy(project_id, text)}


@release_router.post("/{project_id}/pdf")
async def upload_pdf(project_id: str, pdf_bytes: bytes = Body(...)):
    return {"path": await service.save_lyrics_pdf(project_id, pdf_bytes)}


@release_router.post("/{project_id}/metadata")
async def upload_metadata(project_id: str, metadata: dict = Body(...)):
    return {"path": await service.save_metadata(project_id, metadata)}


@release_router.get("/{project_id}/zip")
async def generate_zip(project_id: str):
    return {"zip": await service.generate_release_zip(project_id)}
