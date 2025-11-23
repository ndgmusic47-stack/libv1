"""
Clean ReleaseService V5 - project_id only
"""

import json
import zipfile
import logging
from pathlib import Path
from fastapi import UploadFile

from config.settings import MEDIA_DIR

logger = logging.getLogger(__name__)


class ReleaseService:
    """
    Brand-new ReleaseService.
    NO session_id.
    NO user_id.
    100% project_id-based.
    """

    def _project_path(self, project_id: str) -> Path:
        path = Path(MEDIA_DIR) / project_id / "release"
        path.mkdir(parents=True, exist_ok=True)
        return path

    async def save_cover(self, project_id: str, file: UploadFile):
        try:
            project_path = self._project_path(project_id)
            cover_path = project_path / "cover.jpg"
            with open(cover_path, "wb") as f:
                f.write(await file.read())
            return {"data": str(cover_path), "is_error": False}
        except Exception as e:
            logger.error(f"Failed to save cover: {e}", exc_info=True)
            return {"error": str(e), "is_error": True}

    async def save_release_copy(self, project_id: str, text: str):
        try:
            project_path = self._project_path(project_id)
            copy_path = project_path / "release_description.txt"
            with open(copy_path, "w", encoding="utf-8") as f:
                f.write(text)
            return {"data": str(copy_path), "is_error": False}
        except Exception as e:
            logger.error(f"Failed to save release copy: {e}", exc_info=True)
            return {"error": str(e), "is_error": True}

    async def save_lyrics_pdf(self, project_id: str, pdf_bytes: bytes):
        try:
            project_path = self._project_path(project_id)
            pdf_path = project_path / "lyrics.pdf"
            with open(pdf_path, "wb") as f:
                f.write(pdf_bytes)
            return {"data": str(pdf_path), "is_error": False}
        except Exception as e:
            logger.error(f"Failed to save lyrics PDF: {e}", exc_info=True)
            return {"error": str(e), "is_error": True}

    async def save_metadata(self, project_id: str, metadata: dict):
        try:
            project_path = self._project_path(project_id)
            metadata_path = project_path / "metadata.json"
            with open(metadata_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2)
            return {"data": str(metadata_path), "is_error": False}
        except Exception as e:
            logger.error(f"Failed to save metadata: {e}", exc_info=True)
            return {"error": str(e), "is_error": True}

    async def generate_release_zip(self, project_id: str):
        try:
            project_path = self._project_path(project_id)
            zip_path = project_path / f"{project_id}_release_pack.zip"

            with zipfile.ZipFile(zip_path, "w") as z:
                for file in project_path.glob("*"):
                    z.write(file, arcname=file.name)

            return {"data": str(zip_path), "is_error": False}
        except Exception as e:
            logger.error(f"Failed to generate release zip: {e}", exc_info=True)
            return {"error": str(e), "is_error": True}
