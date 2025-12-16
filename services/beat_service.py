"""
Beat Service - Business logic for beat generation
"""
import uuid
import shutil
import asyncio
import logging
import json
from pathlib import Path
from typing import Optional, Dict, Any
import httpx
from pydub import AudioSegment

from project_memory import get_or_create_project_memory
from backend.utils.responses import success_response, error_response
from utils.shared_utils import get_session_media_path, log_endpoint_event
from config.settings import settings
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Constants
from config.settings import MEDIA_DIR
ASSETS_DIR = Path("./assets")


class BeatService:
    """Service class for beat generation business logic"""
    
    def __init__(self):
        self.api_key = settings.beatoven_api_key
    
    async def create_beat_track(
        self,
        session_id: str,
        prompt: Optional[str] = None,
        mood: str = "energetic",
        genre: str = "hip-hop",
        bpm: Optional[int] = None,
        duration_sec: Optional[int] = None,
        db: Optional[AsyncSession] = None
    ) -> Dict[str, Any]:
        """
        Create a beat track using Beatoven API with fallback logic.
        
        Returns:
            Dict with beat_url, status, provider, progress, and session_id
        """
        session_path = get_session_media_path(session_id)
        
        # Log request
        if duration_sec is not None:
            logger.info(f"🎵 Beat creation request: prompt={prompt[:50] if prompt else ''}..., mood={mood}, genre={genre}, bpm={bpm or 'AI-determined'}, duration={duration_sec}s, session={session_id}")
        else:
            logger.info(f"🎵 Beat creation request: prompt={prompt[:50] if prompt else ''}..., mood={mood}, genre={genre}, bpm={bpm or 'AI-determined'}, duration=AI-determined, session={session_id}")
        
        # Build prompt text
        if prompt:
            prompt_text = prompt
            if mood and mood != "energetic":
                prompt_text += f", {mood} mood"
            if genre and genre != "hip-hop":
                prompt_text += f", {genre} style"
        else:
            prompt_text = f"{mood} {genre} instrumental track"
        
        # Add duration to prompt if provided
        if duration_sec is not None:
            prompt_text = f"{duration_sec} seconds {prompt_text}"
        
        # Runtime check for API key before attempting to call Beatoven API
        if not self.api_key:
            logger.error("BEATOVEN_API_KEY is not set - cannot call Beatoven API.")
            # Explicit error instead of silent/demo fallback
            raise Exception("BEATOVEN_API_KEY missing")
        
        # Try Beatoven API (non-blocking: do not poll or fallback here)
        try:
            # 1. Call Beatoven compose API to get a task_id
            task_id = await self._call_beatoven_compose(prompt_text)
        except httpx.RequestError as e:
            logger.error(f"Beatoven API request failed: {e}")
            # Surface a clear error to the router / caller
            raise Exception(f"Beatoven API request failed: {e}") from e
        except Exception as e:
            logger.error(f"Beatoven API failed: {e}")
            # Let the router handle generic failures consistently
            raise

        # 1b. Persist minimal job manifest for later status lookups
        try:
            job_dir = MEDIA_DIR / task_id
            job_dir.mkdir(parents=True, exist_ok=True)
            manifest_path = job_dir / "job.json"
            manifest = {
                "session_id": session_id,
                "mood": mood,
                "genre": genre,
                "bpm": bpm,
                "duration_sec": duration_sec,
                "provider": "beatoven",
            }
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f)
            logger.info(f"Saved Beatoven job manifest for task {task_id} at {manifest_path}")
        except Exception as e:
            # Do not fail job creation if manifest persistence has issues
            logger.warning(f"Failed to write Beatoven job manifest for task {task_id}: {e}")
        
        # 2. Immediately return processing status so the client can poll
        return {
            "session_id": session_id,
            "job_id": task_id,
            "status": "processing",
            "provider": "beatoven",
            "progress": 5,
            # Keep legacy fields for compatibility (no URL until ready)
            "beat_url": None,
            "url": None,
        }
    
    async def _call_beatoven_compose(self, prompt_text: str) -> str:
        """
        Call Beatoven compose API to initiate beat generation.
        
        Args:
            prompt_text: The prompt text for beat generation
            
        Returns:
            task_id: The task ID returned by the API
            
        Raises:
            Exception: If the API call fails or returns an error
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {"prompt": {"text": prompt_text}, "format": "mp3", "looping": False}
        
        logger.info(f"🎵 Beatoven job started: {prompt_text}")
        
        compose_url = "https://public-api.beatoven.ai/api/v1/tracks/compose"
        async with httpx.AsyncClient() as client:
            compose_res = await client.post(compose_url, headers=headers, json=payload, timeout=30)
        
        # Handle HTTP errors gracefully
        if compose_res.status_code == 422:
            error_detail = compose_res.text
            logger.warning(f"Beatoven API returned 422 Unprocessable Content: {error_detail}")
            raise Exception(f"Beatoven API validation error: {error_detail}")
        elif compose_res.status_code == 401:
            logger.warning(f"Beatoven API returned 401 Unauthorized - invalid API key")
            raise Exception("Beatoven API authentication failed")
        elif not compose_res.is_success:
            error_detail = compose_res.text
            logger.warning(f"Beatoven API returned {compose_res.status_code}: {error_detail}")
            raise Exception(f"Beatoven API error {compose_res.status_code}: {error_detail}")
        
        compose_data = compose_res.json()
        task_id = compose_data.get("task_id")
        
        if not task_id:
            raise Exception("Beatoven: no task_id returned")
        
        logger.info(f"✅ Beatoven task started: {task_id}")
        return task_id
    
    async def _poll_beatoven_status(
        self,
        task_id: str,
        session_path: Path,
        session_id: str,
        mood: str,
        genre: str,
        bpm: Optional[int],
        db: Optional[AsyncSession] = None
    ) -> Dict[str, Any]:
        """
        Poll Beatoven API for task completion and finalize the beat.
        
        Args:
            task_id: The task ID from the compose API call
            session_path: Path to the session media directory
            session_id: Session ID
            mood: Mood of the beat
            genre: Genre of the beat
            bpm: Optional BPM value
            
        Returns:
            Dict with beat_url, status, provider, progress, and session_id
            
        Raises:
            Exception: If polling fails, times out, or encounters an error
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        # Poll for completion (up to 3 minutes)
        async with httpx.AsyncClient() as client:
            for attempt in range(60):
                await asyncio.sleep(3)
                status_url = f"https://public-api.beatoven.ai/api/v1/tasks/{task_id}"
                status_res = await client.get(status_url, headers=headers, timeout=30)
                
                if not status_res.is_success:
                    logger.warning(f"Beatoven status check failed: {status_res.status_code}")
                    raise Exception(f"Beatoven status check error: {status_res.status_code}")
                
                status_data = status_res.json()
                status = status_data.get("status")
                
                if status == "composed":
                    meta = status_data.get("meta", {})
                    audio_url = meta.get("track_url")
                    if not audio_url:
                        raise Exception("Beatoven: track_url missing")
                    
                    # Download the audio
                    output_file = session_path / "beat.mp3"
                    audio_data = await client.get(audio_url, timeout=60)
                    audio_data.raise_for_status()
                    with open(output_file, "wb") as f:
                        f.write(audio_data.content)
                    
                    logger.info(f"🎵 Beatoven track ready: {output_file}")
                    
                    # Extract metadata from Beatoven response
                    extracted_metadata = {}
                    if meta.get("duration"):
                        extracted_metadata["duration"] = int(meta.get("duration"))
                    elif meta.get("length"):
                        extracted_metadata["duration"] = int(meta.get("length"))
                    
                    # BPM from meta or use provided/calculated bpm
                    extracted_bpm = meta.get("bpm") or meta.get("tempo") or bpm
                    if extracted_bpm:
                        extracted_metadata["bpm"] = int(extracted_bpm) if isinstance(extracted_bpm, (int, float)) else extracted_bpm
                    
                    # Key from meta
                    if meta.get("key"):
                        extracted_metadata["key"] = meta.get("key")
                    
                    # Update project memory
                    memory = await get_or_create_project_memory(session_id, MEDIA_DIR, None, db)
                    await memory.update_metadata(tempo=extracted_bpm, mood=mood, genre=genre)
                    beat_url = f"/media/{session_id}/beat.mp3"
                    await memory.add_asset("beat", beat_url, {"bpm": extracted_bpm, "mood": mood, "metadata": extracted_metadata})
                    await memory.advance_stage("beat", "lyrics")
                    
                    # Prepare beat_url and beat_meta for project memory
                    beat_meta = {
                        "bpm": extracted_bpm,
                        "mood": mood,
                        "genre": genre,
                        "provider": "beatoven",
                        **extracted_metadata
                    }
                    
                    # Auto-save to project memory
                    if "beat" not in memory.project_data:
                        memory.project_data["beat"] = {}
                    memory.project_data["beat"].update({
                        "url": beat_url,
                        "meta": beat_meta,
                        "completed": True
                    })
                    await memory.save()
                    
                    log_endpoint_event("/beats/create", session_id, "success", {"source": "beatoven", "mood": mood})
                    
                    return {
                        "session_id": session_id,
                        "beat_url": beat_url,
                        "url": beat_url,
                        "status": "ready",
                        "provider": "beatoven",
                        "progress": 100
                    }
                
                elif status in ("composing", "running", "queued"):
                    logger.info(f"⏳ Beatoven status: {status} ({attempt+1}/60)")
                    continue
                else:
                    raise Exception(f"Unexpected Beatoven status: {status}")
        
        raise Exception("Beatoven generation timed out (3 minutes)")
    
    async def _handle_fallback_beat(
        self,
        session_path: Path,
        session_id: str,
        bpm: Optional[int],
        mood: str,
        genre: str,
        duration_sec: Optional[int],
        db: Optional[AsyncSession] = None
    ) -> Dict[str, Any]:
        """Create fallback beat (demo or silent)"""
        try:
            # Ensure demo_beats directory exists
            demo_beats_dir = MEDIA_DIR / "demo_beats"
            demo_beats_dir.mkdir(exist_ok=True, parents=True)
            fallback = demo_beats_dir / "default_beat.mp3"
            
            # Check if fallback exists, if not create it
            if not fallback.exists():
                # Try to copy from assets if it exists
                source_beat = ASSETS_DIR / "demo" / "beat.mp3"
                if source_beat.exists():
                    shutil.copy(source_beat, fallback)
                    logger.info(f"Created fallback beat at {fallback}")
                else:
                    # Create silent audio clip as fallback
                    logger.info(f"Creating silent fallback beat at {fallback}")
                    silent_audio = AudioSegment.silent(duration=180000)  # 180 seconds
                    silent_audio.export(str(fallback), format="mp3")
            
            # Copy fallback to session
            output_file = session_path / "beat.mp3"
            shutil.copy(fallback, output_file)
            
            logger.info(f"⚠️ Beatoven unavailable, using fallback demo beat")
            
            # Update project memory
            memory = await get_or_create_project_memory(session_id, MEDIA_DIR, None, db)
            demo_metadata = {"duration": 180, "bpm": bpm or 120, "key": "C"}
            await memory.update_metadata(tempo=bpm or 120, mood=mood, genre=genre)
            beat_url = f"/media/{session_id}/beat.mp3"
            await memory.add_asset("beat", beat_url, {"bpm": bpm or 120, "mood": mood, "source": "demo", "metadata": demo_metadata})
            await memory.advance_stage("beat", "lyrics")
            
            # Prepare beat_url and beat_meta for project memory
            beat_meta = {
                "bpm": bpm or 120,
                "mood": mood,
                "genre": genre,
                "provider": "demo",
                **demo_metadata
            }
            
            # Auto-save to project memory
            if "beat" not in memory.project_data:
                memory.project_data["beat"] = {}
            memory.project_data["beat"].update({
                "url": beat_url,
                "meta": beat_meta,
                "completed": True
            })
            await memory.save()
            
            log_endpoint_event("/beats/create", session_id, "success", {"source": "demo", "mood": mood})
            
            return {
                "session_id": session_id,
                "url": beat_url,
                "beat_url": beat_url,
                "status": "ready",
                "provider": "demo",
                "progress": 100
            }
        
        except Exception as e:
            # Ultimate fallback - create silent audio in session directory
            logger.error(f"Fallback beat creation failed: {e} - creating silent audio in session")
            try:
                output_file = session_path / "beat.mp3"
                silent_audio = AudioSegment.silent(duration=(duration_sec or 180) * 1000)
                silent_audio.export(str(output_file), format="mp3")
                
                memory = await get_or_create_project_memory(session_id, MEDIA_DIR, None, db)
                silent_metadata = {"duration": duration_sec or 180, "bpm": bpm or 120, "key": "C"}
                await memory.update_metadata(tempo=bpm or 120, mood=mood, genre=genre)
                beat_url = f"/media/{session_id}/beat.mp3"
                await memory.add_asset("beat", beat_url, {"bpm": bpm or 120, "mood": mood, "source": "silent_fallback", "metadata": silent_metadata})
                
                # Auto-save to project memory
                try:
                    if "beat" not in memory.project_data:
                        memory.project_data["beat"] = {}
                    memory.project_data["beat"].update({
                        "url": beat_url,
                        "meta": {
                            "bpm": bpm or 120,
                            "mood": mood,
                            "genre": genre,
                            "provider": "silent_fallback",
                            **silent_metadata
                        },
                        "completed": True
                    })
                    await memory.save()
                except Exception as e:
                    logger.warning(f"Failed to auto-save beat stage: {e}")
                
                log_endpoint_event("/beats/create", session_id, "success", {"source": "silent_fallback", "mood": mood})
                
                return {
                    "session_id": session_id,
                    "url": beat_url,
                    "beat_url": beat_url,
                    "status": "ready",
                    "provider": "silent_fallback",
                    "progress": 100
                }
            except Exception as final_error:
                logger.error(f"Complete beat generation failure: {final_error}")
                raise Exception(f"Beat generation failed: {final_error}")
    
    async def get_credits(self) -> Dict[str, Any]:
        """
        Get remaining credits from Beatoven API.
        Makes a real-time network call to fetch current credit balance.
        
        Returns:
            Dict with credits count and source
        """
        if not self.api_key:
            logger.warning("Beatoven API key not set – returning default credits")
            log_endpoint_event("/beats/credits", None, "success", {"credits": 10, "source": "default"})
            return {"credits": 10, "source": "default"}
        
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            credits_url = "https://public-api.beatoven.ai/api/v1/usage"
            async with httpx.AsyncClient() as client:
                credits_res = await client.get(credits_url, headers=headers, timeout=10)
                
                if credits_res.is_success:
                    credits_data = credits_res.json()
                    credits = credits_data.get("credits", credits_data.get("remaining", 10))
                    log_endpoint_event("/beats/credits", None, "success", {"credits": credits, "source": "beatoven"})
                    return {"credits": credits, "source": "beatoven"}
                else:
                    # API returned non-success status - fallback gracefully
                    logger.warning(f"Beatoven credits API returned {credits_res.status_code} – using fallback default")
                    log_endpoint_event("/beats/credits", None, "success", {"credits": 10, "source": "fallback"})
                    return {"credits": 10, "source": "fallback"}
        except (httpx.RequestError, httpx.TimeoutException, httpx.HTTPStatusError) as e:
            # Network errors or timeouts - fallback gracefully
            logger.warning(f"Beatoven credits API request failed: {e} – using fallback default")
            log_endpoint_event("/beats/credits", None, "success", {"credits": 10, "source": "fallback"})
            return {"credits": 10, "source": "fallback"}
        except Exception as e:
            # Any other unexpected errors - fallback gracefully
            logger.warning(f"Unexpected error fetching Beatoven credits: {e} – using fallback default")
            log_endpoint_event("/beats/credits", None, "success", {"credits": 10, "source": "fallback"})
            return {"credits": 10, "source": "fallback"}
    
    async def get_beat_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the status of a beat generation job.

        Behavior:
        - If a local beat file already exists at /media/{session_id}/beat.mp3 (from manifest) -> return ready.
        - Else, treat job_id as the Beatoven task_id and poll Beatoven's task endpoint.
        """
        # Try to load job manifest to recover session and metadata
        session_id: Optional[str] = None
        mood: Optional[str] = None
        genre: Optional[str] = None
        bpm: Optional[int] = None

        manifest_path = MEDIA_DIR / job_id / "job.json"
        if manifest_path.exists():
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    manifest_data = json.load(f)
                session_id = manifest_data.get("session_id")
                mood = manifest_data.get("mood")
                genre = manifest_data.get("genre")
                bpm = manifest_data.get("bpm")
            except Exception as e:
                logger.warning(f"Failed to read Beatoven job manifest for task {job_id}: {e}")

        # Primary ready check: session-based beat path from manifest
        if session_id:
            session_beat_file = MEDIA_DIR / session_id / "beat.mp3"
            if session_beat_file.exists():
                beat_url = f"/media/{session_id}/beat.mp3"
                return {
                    "job_id": job_id,
                    "session_id": session_id,
                    "status": "ready",
                    "provider": "beatoven",
                    "beat_url": beat_url,
                    "audio_url": beat_url,
                    "progress": 100,
                }

        # Backward-compatibility: if an old-style beat file exists under /media/{job_id}/beat.mp3,
        # continue to report ready, even if no manifest is present.
        beat_file = MEDIA_DIR / job_id / "beat.mp3"

        # If we've already materialized the beat locally, just report ready.
        if beat_file.exists():
            beat_url = f"/media/{job_id}/beat.mp3"
            return {
                "job_id": job_id,
                "status": "ready",
                "provider": "beatoven",
                "beat_url": beat_url,
                "audio_url": beat_url,
                "progress": 100,
            }

        # No local file yet – need to query Beatoven API for real-time status.
        if not self.api_key:
            logger.error("BEATOVEN_API_KEY is not set - cannot poll Beatoven task status.")
            return {
                "job_id": job_id,
                "session_id": session_id,
                "status": "error",
                "provider": "beatoven",
                "error": "BEATOVEN_API_KEY missing",
            }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        status_url = f"https://public-api.beatoven.ai/api/v1/tasks/{job_id}"

        try:
            async with httpx.AsyncClient() as client:
                status_res = await client.get(status_url, headers=headers, timeout=30)

                if not status_res.is_success:
                    logger.warning(f"Beatoven status check failed: {status_res.status_code}")
                    return {
                        "job_id": job_id,
                        "session_id": session_id,
                        "status": "error",
                        "provider": "beatoven",
                        "error": f"Beatoven status check error: {status_res.status_code}",
                    }

                status_data = status_res.json()
                status = status_data.get("status")

                if status == "composed":
                    meta = status_data.get("meta", {})
                    audio_url = meta.get("track_url")
                    if not audio_url:
                        logger.error("Beatoven: track_url missing in composed task response")
                        return {
                            "job_id": job_id,
                            "session_id": session_id,
                            "status": "error",
                            "provider": "beatoven",
                            "error": "Beatoven: track_url missing",
                        }

                    if not session_id:
                        logger.error(f"Beatoven task {job_id} composed but missing job manifest/session mapping")
                        return {
                            "job_id": job_id,
                            "status": "error",
                            "provider": "beatoven",
                            "error": "Missing job manifest (session mapping)",
                        }

                    # Download and persist audio under /media/{session_id}/beat.mp3
                    async with httpx.AsyncClient() as client_audio:
                        audio_data = await client_audio.get(audio_url, timeout=60)
                        audio_data.raise_for_status()

                    session_beat_file = MEDIA_DIR / session_id / "beat.mp3"
                    session_beat_file.parent.mkdir(parents=True, exist_ok=True)
                    with open(session_beat_file, "wb") as f:
                        f.write(audio_data.content)

                    beat_url = f"/media/{session_id}/beat.mp3"
                    logger.info(f"🎵 Beatoven task {job_id} composed and saved to {session_beat_file}")

                    # Update project memory with minimal metadata (from manifest)
                    try:
                        memory = await get_or_create_project_memory(session_id, MEDIA_DIR, None, None)
                        await memory.update_metadata(tempo=bpm, mood=mood, genre=genre)
                        await memory.add_asset("beat", beat_url, {"bpm": bpm, "mood": mood, "metadata": {}})
                        await memory.advance_stage("beat", "lyrics")

                        # Mirror legacy beat block structure
                        beat_meta = {
                            "bpm": bpm,
                            "mood": mood,
                            "genre": genre,
                            "provider": "beatoven",
                        }
                        if "beat" not in memory.project_data:
                            memory.project_data["beat"] = {}
                        memory.project_data["beat"].update({
                            "url": beat_url,
                            "meta": beat_meta,
                            "completed": True,
                        })
                        await memory.save()
                    except Exception as mem_err:
                        logger.warning(f"Failed to update project memory for Beatoven task {job_id}: {mem_err}")

                    return {
                        "job_id": job_id,
                        "session_id": session_id,
                        "status": "ready",
                        "provider": "beatoven",
                        "beat_url": beat_url,
                        "audio_url": beat_url,
                        "progress": 100,
                    }

                if status in ("composing", "running", "queued"):
                    logger.info(f"⏳ Beatoven task {job_id} status: {status}")
                    resp: Dict[str, Any] = {
                        "job_id": job_id,
                        "session_id": session_id,
                        "status": "processing",
                        "provider": "beatoven",
                    }
                    # Optional progress hint from provider, if present
                    progress = status_data.get("progress")
                    if isinstance(progress, (int, float)):
                        resp["progress"] = int(progress)
                    return resp

                # Any other status is treated as an error
                logger.warning(f"Unexpected Beatoven status for task {job_id}: {status}")
                return {
                    "job_id": job_id,
                    "session_id": session_id,
                    "status": "error",
                    "provider": "beatoven",
                    "error": f"Unexpected Beatoven status: {status}",
                }
        except Exception as e:
            logger.error(f"Error while polling Beatoven status for task {job_id}: {e}")
            return {
                "job_id": job_id,
                "session_id": session_id,
                "status": "error",
                "provider": "beatoven",
                "error": str(e),
            }

