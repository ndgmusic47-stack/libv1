"""
Beat Service - Business logic for beat generation
"""
import uuid
import shutil
import asyncio
import logging
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
            logger.warning("BEATOVEN_API_KEY is not set. Proceeding to fallback logic.")
            return await self._handle_fallback_beat(
                session_path=session_path,
                session_id=session_id,
                bpm=bpm,
                mood=mood,
                genre=genre,
                duration_sec=duration_sec,
                db=db
            )
        
        # Try Beatoven API first (key is available at this point)
        try:
            # 1. Call Beatoven compose API
            task_id = await self._call_beatoven_compose(prompt_text)
            
            # 2. Store mood/genre in project memory for later use in status checks
            memory = await get_or_create_project_memory(session_id, MEDIA_DIR, None, db)
            await memory.update_metadata(mood=mood, genre=genre)
            
            # 3. Return immediately with processing status (encode session_id into job_id)
            job_id = f"{session_id}_{task_id}"
            log_endpoint_event("/beats/create", session_id, "processing", {"job_id": job_id, "task_id": task_id})
            
            return {
                "session_id": session_id,
                "job_id": job_id,
                "status": "processing",
                "provider": "beatoven",
                "progress": 0
            }
        except httpx.RequestError as e:
            logger.warning(f"Beatoven API request failed: {e} - falling back to demo beat")
        except Exception as e:
            logger.warning(f"Beatoven API failed: {e} - falling back to demo beat")
        
        # FALLBACK: Only for hard failures (no API key, auth errors, request errors)
        return await self._handle_fallback_beat(
            session_path=session_path,
            session_id=session_id,
            bpm=bpm,
            mood=mood,
            genre=genre,
            duration_sec=duration_sec,
            db=db
        )
    
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
            
            # Check if beat.mp3 already exists and has content
            if output_file.exists() and output_file.stat().st_size > 0:
                logger.warning(f"Fallback beat not applied because beat.mp3 already exists for session {session_id}")
                provider = "demo_skipped"
            else:
                shutil.copy(fallback, output_file)
                logger.info(f"⚠️ Beatoven unavailable, using fallback demo beat")
                provider = "demo"
            
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
                "provider": provider,
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
            
            log_endpoint_event("/beats/create", session_id, "success", {"source": provider, "mood": mood})
            
            return {
                "session_id": session_id,
                "url": beat_url,
                "beat_url": beat_url,
                "status": "ready",
                "provider": provider,
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
    
    async def get_beat_status(self, job_id: str, db: Optional[AsyncSession] = None) -> Optional[Dict[str, Any]]:
        """
        Get the status of a beat generation job.
        
        Args:
            job_id: Job ID in format "{session_id}_{task_id}"
            db: Optional database session
            
        Returns:
            Dict with job status: processing, ready, or error
        """
        if not self.api_key:
            return {
                "status": "error",
                "job_id": job_id,
                "message": "Beatoven API key not configured"
            }
        
        # Parse session_id and task_id from job_id
        # Format: {session_id}_{task_id}
        if "_" not in job_id:
            return {
                "status": "error",
                "job_id": job_id,
                "message": "Invalid job_id format"
            }
        
        session_id = job_id.rsplit("_", 1)[0]
        task_id = job_id.rsplit("_", 1)[1]
        session_path = get_session_media_path(session_id)
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        try:
            async with httpx.AsyncClient() as client:
                status_url = f"https://public-api.beatoven.ai/api/v1/tasks/{task_id}"
                status_res = await client.get(status_url, headers=headers, timeout=30)
                
                if not status_res.is_success:
                    if status_res.status_code in (401, 403):
                        return {
                            "status": "error",
                            "job_id": job_id,
                            "message": f"Beatoven API authentication failed: {status_res.status_code}"
                        }
                    return {
                        "status": "error",
                        "job_id": job_id,
                        "message": f"Beatoven status check failed: {status_res.status_code}"
                    }
                
                status_data = status_res.json()
                status = status_data.get("status")
                
                # Still composing/running/queued
                if status in ("composing", "running", "queued"):
                    return {
                        "status": "processing",
                        "job_id": job_id,
                        "progress": 50  # Estimate
                    }
                
                # Composed - download and finalize
                if status == "composed":
                    meta = status_data.get("meta", {})
                    audio_url = meta.get("track_url")
                    if not audio_url:
                        return {
                            "status": "error",
                            "job_id": job_id,
                            "message": "Beatoven: track_url missing"
                        }
                    
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
                    
                    # BPM from meta
                    extracted_bpm = meta.get("bpm") or meta.get("tempo")
                    if extracted_bpm:
                        extracted_bpm = int(extracted_bpm) if isinstance(extracted_bpm, (int, float)) else extracted_bpm
                        extracted_metadata["bpm"] = extracted_bpm
                    
                    # Key from meta
                    if meta.get("key"):
                        extracted_metadata["key"] = meta.get("key")
                    
                    # Get mood/genre from project memory metadata if available (or use defaults)
                    memory = await get_or_create_project_memory(session_id, MEDIA_DIR, None, db)
                    project_mood = memory.project_data.get("metadata", {}).get("mood", "energetic")
                    project_genre = memory.project_data.get("metadata", {}).get("genre", "hip-hop")
                    
                    # Update project memory
                    await memory.update_metadata(tempo=extracted_bpm, mood=project_mood, genre=project_genre)
                    beat_url = f"/media/{session_id}/beat.mp3"
                    await memory.add_asset("beat", beat_url, {"bpm": extracted_bpm, "mood": project_mood, "metadata": extracted_metadata})
                    await memory.advance_stage("beat", "lyrics")
                    
                    # Prepare beat_url and beat_meta for project memory
                    beat_meta = {
                        "bpm": extracted_bpm,
                        "mood": project_mood,
                        "genre": project_genre,
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
                    
                    log_endpoint_event("/beats/status", session_id, "success", {"source": "beatoven", "job_id": job_id})
                    
                    return {
                        "status": "ready",
                        "job_id": job_id,
                        "beat_url": beat_url,
                        "url": beat_url,
                        "provider": "beatoven",
                        "progress": 100,
                        "session_id": session_id
                    }
                
                # Failed or unexpected status
                return {
                    "status": "error",
                    "job_id": job_id,
                    "message": f"Unexpected Beatoven status: {status}"
                }
        
        except httpx.RequestError as e:
            logger.error(f"Beatoven status check request error: {e}")
            return {
                "status": "error",
                "job_id": job_id,
                "message": f"Beatoven API request failed: {str(e)}"
            }
        except Exception as e:
            logger.error(f"Beatoven status check error: {e}")
            return {
                "status": "error",
                "job_id": job_id,
                "message": f"Beatoven status check failed: {str(e)}"
            }

