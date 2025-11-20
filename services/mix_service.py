"""
Mix service for audio processing and mixing
"""
import logging
import asyncio
from pathlib import Path
from pydub import AudioSegment
from pydub.effects import normalize
from pydub.exceptions import CouldntDecodeError

from project_memory import get_or_create_project_memory
from backend.utils.responses import error_response, success_response


def apply_basic_mix(vocal_path: str, beat_path: str, output_path: str):
    """Apply basic mix by overlaying vocal on beat"""
    from pydub import AudioSegment
    
    vocal = AudioSegment.from_file(vocal_path)
    beat = AudioSegment.from_file(beat_path)
    
    mixed = beat.overlay(vocal)
    mixed.export(output_path, format="mp3")
    
    return output_path

logger = logging.getLogger(__name__)

MAX_DURATION_MS = 10 * 60 * 1000  # 10 minutes


class MixService:
    """Service for handling audio mixing operations"""
    
    @staticmethod
    async def run_clean_mix(request, user_id: str) -> dict:
        """
        Clean mix: overlay vocal on beat using pydub
        
        Args:
            request: CleanMixRequest object with vocal_url, beat_url, session_id, etc.
            user_id: User ID for project memory updates
            
        Returns:
            Success or error response dict
        """
        logger.info("Running clean mix…")
        
        try:
            # Resolve file paths (handle both /media/... and ./media/... paths)
            vocal_path = request.vocal_url
            if vocal_path.startswith("/media/"):
                vocal_path = "." + vocal_path
            elif not vocal_path.startswith("./"):
                vocal_path = "./" + vocal_path.lstrip("/")
            
            beat_path = request.beat_url
            if beat_path.startswith("/media/"):
                beat_path = "." + beat_path
            elif not beat_path.startswith("./"):
                beat_path = "./" + beat_path.lstrip("/")
            
            # Validate files exist
            vocal_path_obj = Path(vocal_path)
            beat_path_obj = Path(beat_path)
            
            vocal_exists = await asyncio.to_thread(vocal_path_obj.exists)
            beat_exists = await asyncio.to_thread(beat_path_obj.exists)
            
            if not vocal_exists or not beat_exists:
                return error_response(
                    "INVALID_AUDIO",
                    400,
                    "The provided vocal or beat file is corrupted or unsupported."
                )
            
            # Load files
            try:
                beat = await asyncio.to_thread(AudioSegment.from_file, beat_path)
                vocal = await asyncio.to_thread(AudioSegment.from_file, vocal_path)
            except CouldntDecodeError:
                return error_response("INVALID_AUDIO", 400, "Could not decode audio")
            
            # Align durations
            if len(vocal) > len(beat):
                beat = beat.append(AudioSegment.silent(duration=len(vocal) - len(beat)))
            else:
                vocal = vocal.append(AudioSegment.silent(duration=len(beat) - len(vocal)))
            
            # Basic mixing
            mixed = beat.overlay(vocal)
            
            # Normalization
            mixed = normalize(mixed)
            
            # Save output
            session_dir = Path(f"./media/{user_id}/{request.session_id}")
            session_dir.mkdir(parents=True, exist_ok=True)
            output_path = session_dir / "mixed_output.wav"
            await asyncio.to_thread(mixed.export, output_path, format="wav")
            
            # Return JSON
            mix_url = f"/sessions/{request.session_id}/mixed_output.wav"
            
            # Update project memory
            MEDIA_DIR = Path("./media")
            memory = await get_or_create_project_memory(request.session_id, MEDIA_DIR, user_id)
            if "mix" not in memory.project_data:
                memory.project_data["mix"] = {}
            memory.project_data["mix"].update({
                "mix_url": mix_url,
                "completed": True
            })
            await memory.save()
            
            return success_response(
                data={"mix_url": mix_url},
                message="Mix generated successfully"
            )
            
        except CouldntDecodeError:
            return error_response(
                "INVALID_AUDIO",
                400,
                "Could not decode audio."
            )
        except Exception as e:
            logger.error(f"Clean mix failed: {e}")
            return error_response("UNEXPECTED_ERROR", 500, f"Failed to create clean mix: {str(e)}")
    
    @staticmethod
    async def mix_audio(user_id: str, session_id: str) -> dict:
        """
        Basic mix using apply_basic_mix function
        
        Args:
            user_id: User ID
            session_id: Session ID
            
        Returns:
            Success response dict with mix_url
        """
        # compute paths
        base = Path(f"./media/{user_id}/{session_id}")

        vocal_path = base / "vocal.wav"
        beat_path = base / "beat.mp3"
        output_path = base / "mix" / "mix.wav"

        # run DSP chain
        await asyncio.to_thread(
            apply_basic_mix,
            str(vocal_path),
            str(beat_path),
            str(output_path)
        )

        # update project.json
        result_url = f"/media/{user_id}/{session_id}/mix/mix.wav"
        MEDIA_DIR = Path("./media")
        memory = await get_or_create_project_memory(session_id, MEDIA_DIR, user_id)
        if "mix" not in memory.project_data:
            memory.project_data["mix"] = {}
        memory.project_data["mix"].update({
            "path": result_url,
            "processed": True
        })
        await memory.save()

        return success_response(
            data={"mix_url": result_url},
            message="Mix generated successfully"
        )
    
    @staticmethod
    async def get_mix_status(user_id: str, session_id: str) -> dict:
        """
        Get the current mix status and file URL for a session.
        
        Args:
            user_id: User ID
            session_id: Session ID
            
        Returns:
            Dict with status and mix_url (if available)
        """
        try:
            # Load project data from memory
            MEDIA_DIR = Path("./media")
            memory = await get_or_create_project_memory(session_id, MEDIA_DIR, user_id)
            mix_stage = memory.project_data.get("mix")
            
            # Check for mix URL in stage data
            mix_url = None
            status = "not_started"
            
            if mix_stage:
                # Check for mix_url (from run_clean_mix) or path (from mix_audio)
                mix_url = mix_stage.get("mix_url") or mix_stage.get("path")
                
                # If we have a URL, verify the file exists
                if mix_url:
                    # Convert URL to file path
                    if mix_url.startswith("/media/"):
                        file_path = Path("." + mix_url)
                    elif mix_url.startswith("./"):
                        file_path = Path(mix_url)
                    else:
                        file_path = Path(f"./media/{user_id}/{session_id}/mix/{mix_url}")
                    
                    # Check if file exists
                    file_exists = await asyncio.to_thread(file_path.exists)
                    if file_exists:
                        status = "completed"
                    else:
                        # URL exists in metadata but file is missing
                        status = "file_missing"
                        mix_url = None
                elif mix_stage.get("completed") or mix_stage.get("processed"):
                    # Stage marked as completed but no URL found
                    status = "completed_no_url"
                else:
                    status = "in_progress"
            
            return {
                "status": status,
                "mix_url": mix_url
            }
        except Exception as e:
            logger.error(f"Failed to get mix status: {e}")
            return {
                "status": "error",
                "mix_url": None
            }
    
    @staticmethod
    async def process_single_file(input_path: str, output_path: str, toggles: dict) -> dict:
        """
        Process a single audio file with optional mastering effects.
        
        Args:
            input_path: Path to input audio file
            output_path: Path to save processed output
            toggles: Dict with apply_eq, apply_compression, apply_limiter, apply_saturation
            
        Returns:
            Dict with processing results
        """
        try:
            # Load input audio
            audio = await asyncio.to_thread(AudioSegment.from_file, input_path)
            
            # Validate audio
            if len(audio) <= 0:
                raise ValueError("Empty audio file")
            if len(audio) > MAX_DURATION_MS:
                raise ValueError("Audio file exceeds maximum duration")
            
            # Apply effects based on toggles
            if toggles.get("apply_eq"):
                # Basic EQ: high-pass filter
                audio = audio.high_pass_filter(80)
            
            if toggles.get("apply_compression"):
                # Apply compression
                audio = audio.compress_dynamic_range()
            
            if toggles.get("apply_limiter"):
                # Apply limiter (normalize and reduce peak)
                audio = normalize(audio)
                if audio.max_dBFS > -1:
                    audio = audio - (audio.max_dBFS + 1)
            
            if toggles.get("apply_saturation"):
                # Apply saturation (subtle distortion)
                # Use gain staging for subtle saturation effect
                if audio.max_dBFS < -6:
                    audio = audio + 3
                    audio = audio.compress_dynamic_range()
                    audio = audio - 2
            
            # Final normalization
            audio = normalize(audio)
            
            # Ensure output directory exists
            output_dir = Path(output_path).parent
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Export processed audio
            await asyncio.to_thread(audio.export, output_path, format="wav")
            
            logger.info(f"Processed single file: {input_path} -> {output_path}")
            
            return {
                "success": True,
                "duration_ms": len(audio),
                "peak_dBFS": audio.max_dBFS
            }
            
        except CouldntDecodeError:
            raise ValueError("Could not decode audio file")
        except Exception as e:
            logger.error(f"Failed to process single file: {e}")
            raise

