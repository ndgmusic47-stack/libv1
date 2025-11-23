"""
Mix service for audio processing and mixing
"""
import logging
import asyncio
import numpy as np
from pathlib import Path
from typing import Optional, Dict, Any, List
from pydub import AudioSegment
from pydub.effects import normalize
from pydub.exceptions import CouldntDecodeError

from project_memory import get_or_create_project_memory
from backend.utils.responses import error_response, success_response
from config.settings import MEDIA_DIR
from utils.dsp.mix_pipeline import process_track, process_master_bus, blend_tracks
from utils.dsp.load import load_wav
from utils.dsp.export import save_wav
from utils.dsp.stereo import stereo_widen
from utils.dsp.scope import compute_scope
from utils.dsp.streamer import chunk_audio
from utils.dsp.analyze_audio import (
    compute_waveform,
    compute_fft_spectrum,
    compute_levels,
    compute_energy_curve,
    compute_track_spectrum,
)
from utils.dsp.level import lufs, rms, auto_gain, match_loudness
from utils.dsp.dynamics import soften_transients, micro_compress, smooth_vocals
from utils.dsp.tonal_balance import tonal_balance_chain
from utils.dsp.masking import detect_masking, resolve_masking
from utils.dsp.spatial import spatial_pocket
from utils.mix.roles import detect_role
from utils.mix.recipes import MIX_RECIPES
from utils.mix.config_apply import apply_recipe
from models.mix_config import MixConfig, TrackConfig, MasterConfig
from jobs.mix_job_manager import MixJobManager, JOBS
from services.transport_service import get_transport


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

# Storage directory for mix outputs
STORAGE_MIX_OUTPUTS = Path("./storage/mix_outputs")


class MixService:
    """Service for handling audio mixing operations"""
    
    @staticmethod
    async def prepare_mix_config(session_id: str, recipe: str, track_roles: dict):
        return apply_recipe(recipe, track_roles)
    
    @staticmethod
    def analyze_track_levels(samples: np.ndarray) -> dict:
        return {
            "rms": rms(samples),
            "lufs": lufs(samples)
        }
    
    @staticmethod
    def apply_auto_gain(samples: np.ndarray, role: str) -> np.ndarray:
        # role-based targets
        role_targets = {
            "lead_vocal":  {"lufs": -16, "rms": 0.14},
            "adlib":       {"lufs": -18, "rms": 0.10},
            "bass":        {"lufs": -20, "rms": 0.12},
            "beat":        {"lufs": -18, "rms": 0.13},
            "default":     {"lufs": -17, "rms": 0.13},
        }
        
        # Map detected roles to target roles
        role_map = {
            "lead": "lead_vocal",
            "adlib": "adlib",
            "instrumental": "beat",
            "double": "default",
            "harmony": "default",
            "unknown": "default",
        }
        
        mapped_role = role_map.get(role, "default")
        tgt = role_targets.get(mapped_role, role_targets["default"])
        gain = auto_gain(samples, tgt["lufs"], tgt["rms"])
        return samples * gain
    
    @staticmethod
    def apply_micro_dynamics(samples: np.ndarray, role: str) -> np.ndarray:
        """
        Applies role-sensitive micro-dynamics shaping.
        """

        # Lead vocals need strongest smoothing
        if role in ["lead_vocal", "lead", "main_vocal"]:
            samples = soften_transients(samples, threshold=0.12, soften_factor=0.55)
            samples = micro_compress(samples, ratio=1.4)
            samples = smooth_vocals(samples, smooth_factor=0.12)

        # Adlibs / backing vocals — lighter treatment
        elif role in ["adlib", "backing_vocal"]:
            samples = soften_transients(samples, threshold=0.14, soften_factor=0.65)
            samples = micro_compress(samples, ratio=1.25)
            samples = smooth_vocals(samples, smooth_factor=0.08)

        # Beat elements — protect punch
        elif role in ["beat", "drums", "kick", "snare", "hi_hat"]:
            samples = soften_transients(samples, threshold=0.20, soften_factor=0.8)
            samples = micro_compress(samples, ratio=1.15)

        # Default
        else:
            samples = soften_transients(samples, threshold=0.16, soften_factor=0.7)
            samples = micro_compress(samples, ratio=1.2)

        return samples
    
    @staticmethod
    def apply_tonal_balance(samples: np.ndarray, role: str) -> np.ndarray:
        try:
            return tonal_balance_chain(samples, role)
        except Exception:
            return samples
    
    @staticmethod
    def apply_spatial_separation(stereo_samples: np.ndarray, role: str):
        try:
            return spatial_pocket(stereo_samples, role)
        except Exception:
            return stereo_samples
    
    @staticmethod
    def apply_frequency_masking(vocal_samples, beat_samples):
        try:
            masked_freqs = detect_masking(vocal_samples, beat_samples)
            return resolve_masking(beat_samples, masked_freqs)
        except Exception:
            return beat_samples
    
    @staticmethod
    async def run_clean_mix(request, project_id: Optional[str] = None) -> dict:
        """
        Clean mix: overlay vocal on beat using pydub
        
        Args:
            request: CleanMixRequest object with vocal_url, beat_url, session_id, etc.
            project_id: Project ID (session_id) for project memory updates
            
        Returns:
            Success or error response dict
        """
        logger.info("Running clean mix…")
        
        try:
            project_id = project_id or request.session_id
            
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
            session_dir = MEDIA_DIR / project_id
            session_dir.mkdir(parents=True, exist_ok=True)
            output_path = session_dir / "mix" / "mixed_output.wav"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(mixed.export, output_path, format="wav")
            
            # Return JSON
            mix_url = f"/media/{project_id}/mix/mixed_output.wav"
            
            # Update project memory
            memory = await get_or_create_project_memory(project_id, MEDIA_DIR, None)
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
    def _audio_segment_to_numpy(audio: AudioSegment) -> np.ndarray:
        """Convert AudioSegment to numpy array"""
        # Get array of samples
        samples = audio.get_array_of_samples()
        # Convert to numpy array
        samples_np = np.array(samples, dtype=np.float32)
        # Normalize to [-1, 1]
        samples_np = samples_np / 32768.0
        # Reshape for stereo (if channels > 1)
        if audio.channels > 1:
            samples_np = samples_np.reshape(-1, audio.channels)
        return samples_np
    
    @staticmethod
    def _numpy_to_audio_segment(audio_data: np.ndarray, frame_rate: int = 44100, channels: int = 2) -> AudioSegment:
        """Convert numpy array to AudioSegment"""
        # Flatten if 2D
        if audio_data.ndim > 1:
            audio_data = audio_data.flatten()
        # Denormalize from float32 [-1, 1] to int16
        samples_int = (np.clip(audio_data, -1.0, 1.0) * 32767.0).astype(np.int16)
        # Convert to bytes
        raw_data = samples_int.tobytes()
        # Create AudioSegment
        return AudioSegment(
            data=raw_data,
            sample_width=2,  # 16-bit = 2 bytes
            frame_rate=frame_rate,
            channels=channels
        )
    
    @staticmethod
    async def mix(session_id: str, stems: Dict[str, str], config: Optional[Dict[str, Any]] = None, job_id: Optional[str] = None) -> dict:
        """
        Real DSP-based mixing with per-track and master bus processing.
        
        Args:
            session_id: Session ID
            stems: Dict mapping stem names to file paths (e.g., {"vocal": "path/to/vocal.wav", "beat": "path/to/beat.wav"})
            config: Optional mix configuration with track_configs and mastering_config
            job_id: Optional job ID for progress tracking
            
        Returns:
            Success: {"data": {"url": final_url}, "is_error": False}
            Error: {"error": str(e), "is_error": True}
        """
        try:
            # Validate stems
            if not stems:
                return {"error": "No stems provided", "is_error": True}
            
            # Validate stem files exist
            for stem_name, stem_path in stems.items():
                stem_path_obj = Path(stem_path)
                if stem_path.startswith("/media/"):
                    stem_path_obj = Path("." + stem_path)
                elif not stem_path.startswith("./"):
                    stem_path_obj = Path("./" + stem_path.lstrip("/"))
                
                exists = await asyncio.to_thread(stem_path_obj.exists)
                if not exists:
                    return {"error": f"Stem file not found: {stem_name} at {stem_path}", "is_error": True}
            
            # Loading stems
            if job_id:
                MixJobManager.update(job_id, state="loading_stems", progress=10, message="Loading stems…")
                await asyncio.sleep(0.05)
            
            # Load audio files using load_wav
            audio_data_dict = {}
            for stem_name, stem_path in stems.items():
                # Resolve path
                resolved_path = stem_path
                if stem_path.startswith("/media/"):
                    resolved_path = "." + stem_path
                elif not stem_path.startswith("./"):
                    resolved_path = "./" + stem_path.lstrip("/")
                
                try:
                    audio_data = await asyncio.to_thread(load_wav, resolved_path)
                    audio_data_dict[stem_name] = audio_data
                except Exception as e:
                    return {"error": f"Could not load audio file: {stem_name} - {str(e)}", "is_error": True}
            
            # Aligning stems
            if job_id:
                MixJobManager.update(job_id, state="aligning_stems", progress=25, message="Aligning stems…")
                await asyncio.sleep(0.05)
            
            # Processing track DSP
            if job_id:
                MixJobManager.update(job_id, state="processing_tracks", progress=50, message="Applying DSP…")
                await asyncio.sleep(0.05)
            
            # Get config from job if available, otherwise use passed config
            if job_id:
                job = JOBS.get(job_id)
                if job and hasattr(job, 'config') and job.config:
                    config = job.config
                elif job and job.extra.get("config"):
                    config = job.extra.get("config")
            
            # Process per-track DSP chain
            processed_tracks = []
            track_meters = {}
            track_spectra = {}
            track_streams = {}
            default_track_config = {
                "eq_settings": [],
                "compressor": None,
                "saturation": None,
                "gain_db": 0.0
            }
            
            for stem_name, audio_data in audio_data_dict.items():
                
                # Get track config (from config parameter or use defaults)
                track_config_raw = default_track_config.copy()
                if config and "track_configs" in config and stem_name in config.get("track_configs", {}):
                    track_config_raw.update(config["track_configs"][stem_name])
                
                # Detect role from filename
                filename = stems[stem_name]
                role = detect_role(filename)
                track_config_raw["role"] = role
                
                # === AI AUTO GAIN (PRE-DSP) ===
                gain_role = "default"
                if config and hasattr(config, "tracks") and stem_name in config.tracks:
                    gain_role = config.tracks[stem_name].role or "default"
                
                try:
                    audio_data = MixService.apply_auto_gain(audio_data, gain_role)
                except Exception:
                    pass
                # === END AI AUTO GAIN ===
                
                # === MICRO-DYNAMICS (AFTER GAIN, BEFORE EQ) ===
                try:
                    audio_data = MixService.apply_micro_dynamics(audio_data, role)
                except Exception:
                    pass
                # === END MICRO-DYNAMICS ===
                
                # === TONAL BALANCE (AFTER MICRO-DYNAMICS, BEFORE EQ) ===
                try:
                    audio_data = MixService.apply_tonal_balance(audio_data, role)
                except Exception:
                    pass
                # === END TONAL BALANCE ===
                
                # === SPATIAL SEPARATION (AFTER TONAL BALANCE, BEFORE EQ) ===
                try:
                    # Convert mono to [2, N] stereo placeholder if needed
                    if audio_data.ndim == 1:
                        stereo = np.vstack([audio_data, audio_data])
                    else:
                        stereo = audio_data
                    
                    stereo = MixService.apply_spatial_separation(stereo, role)
                    
                    # Reduce back to mono for downstream DSP if required
                    audio_data = stereo.mean(axis=0)
                except Exception:
                    pass
                # === END SPATIAL SEPARATION ===
                
                # === FREQUENCY MASKING (VOCAL vs BEAT) ===
                try:
                    if role in ["lead_vocal", "lead", "main_vocal"]:
                        # Need beat samples to resolve masking
                        # Cursor: if you cannot safely find beat stem access, SKIP this anchor.
                        beat_samples = audio_data_dict.get("beat") if "beat" in audio_data_dict else None
                        if beat_samples is not None:
                            resolved_beat = MixService.apply_frequency_masking(audio_data, beat_samples)
                            # Cursor: only replace beat track if you can safely identify it in pipeline.
                            audio_data_dict["beat"] = resolved_beat
                except Exception:
                    pass
                # === END FREQUENCY MASKING ===
                
                # Adapt config format for new DSP functions
                track_config = {
                    "role": role,
                    "eq": track_config_raw.get("eq_settings", []),
                    "compressor": track_config_raw.get("compressor", {}),
                    "saturation": track_config_raw.get("saturation", {}).get("amount", 0.0) if isinstance(track_config_raw.get("saturation"), dict) else (track_config_raw.get("saturation") if isinstance(track_config_raw.get("saturation"), (int, float)) else 0.0),
                    "gain": track_config_raw.get("gain_db", 0.0)
                }
                
                # Apply per-track DSP chain
                processed_data, meter_data = process_track(audio_data, track_config)
                processed_tracks.append(processed_data)
                track_meters[stem_name] = meter_data
                track_spectra[stem_name] = compute_track_spectrum(processed_data)
                
                # Generate per-track streaming chunks
                track_chunks = chunk_audio(processed_data)
                track_streams[stem_name] = track_chunks
            
            # Mixing
            if job_id:
                MixJobManager.update(job_id, state="mixing", progress=65, message="Blending tracks…")
                await asyncio.sleep(0.05)
            
            # Blend tracks
            blended_audio = blend_tracks(processed_tracks)
            
            # === MASTER LOUDNESS NORMALIZATION (BEFORE LIMITER) ===
            try:
                TARGET_MASTER_LUFS = -9.5
                master_gain = match_loudness(blended_audio, TARGET_MASTER_LUFS)
                blended_audio = blended_audio * master_gain
            except Exception:
                pass
            # === END MASTER NORMALIZATION ===
            
            # Generate pre-master streaming chunks
            pre_master_chunks = chunk_audio(blended_audio)
            
            pre_master_scope = compute_scope(blended_audio)
            
            # Compute pre-master spectrum
            pre_master_spectrum = compute_track_spectrum(blended_audio)
            
            # Apply mix recipe to master bus
            project_settings = config.get("project_settings", {}) if config else {}
            recipe = MIX_RECIPES.get(project_settings.get("mix_recipe", "default"), MIX_RECIPES["default"])
            master_cfg = recipe["master"]
            
            # Apply mastering chain - adapt config format (recipe takes precedence, but allow user overrides)
            mastering_config_raw = config.get("mastering_config", {}) if config else {}
            mastering_config = {
                "eq": mastering_config_raw.get("eq_settings", master_cfg.get("eq", [])),
                "threshold": mastering_config_raw.get("compressor", {}).get("threshold", master_cfg.get("threshold", -14)) if isinstance(mastering_config_raw.get("compressor"), dict) else master_cfg.get("threshold", -14),
                "ratio": mastering_config_raw.get("compressor", {}).get("ratio", master_cfg.get("ratio", 2.0)) if isinstance(mastering_config_raw.get("compressor"), dict) else master_cfg.get("ratio", 2.0),
                "attack": mastering_config_raw.get("compressor", {}).get("attack", master_cfg.get("attack", 10)) if isinstance(mastering_config_raw.get("compressor"), dict) else master_cfg.get("attack", 10),
                "release": mastering_config_raw.get("compressor", {}).get("release", master_cfg.get("release", 50)) if isinstance(mastering_config_raw.get("compressor"), dict) else master_cfg.get("release", 50),
                "ceiling": mastering_config_raw.get("limiter", {}).get("ceiling", master_cfg.get("ceiling", -1.0)) if isinstance(mastering_config_raw.get("limiter"), dict) else master_cfg.get("ceiling", -1.0)
            }
            # Mastering
            if job_id:
                MixJobManager.update(job_id, state="mastering", progress=80, message="Applying master chain…")
                await asyncio.sleep(0.05)
            
            mastered_audio, master_meter = process_master_bus(blended_audio, mastering_config)
            
            # Generate post-master streaming chunks
            post_master_chunks = chunk_audio(mastered_audio)
            
            post_master_scope = compute_scope(mastered_audio)
            
            # Compute post-master spectrum
            post_master_spectrum = compute_track_spectrum(mastered_audio)
            
            # Apply stereo widening to final master
            master_audio = stereo_widen(mastered_audio, amount=0.15)
            
            # Compute visual data
            visual = {
                "waveform": compute_waveform(master_audio),
                "spectrum": compute_fft_spectrum(master_audio),
                "levels": compute_levels(master_audio),
                "energy_curve": compute_energy_curve(master_audio),
            }
            
            # Store visual data in job.extra
            if job_id:
                MixJobManager.update(job_id, message="Visual data computed")
                job = JOBS.get(job_id)
                if job:
                    job.extra["visual"] = visual
                    job.extra.setdefault("realtime_meters", {})
                    job.extra["realtime_meters"]["tracks"] = track_meters
                    job.extra["realtime_meters"]["master"] = master_meter
                    job.extra.setdefault("realtime_spectra", {})
                    job.extra["realtime_spectra"]["tracks"] = track_spectra
                    job.extra["realtime_spectra"]["pre_master"] = pre_master_spectrum
                    job.extra["realtime_spectra"]["post_master"] = post_master_spectrum
                    job.extra.setdefault("realtime_scope", {})
                    job.extra["realtime_scope"]["tracks"] = {
                        stem_name: meter_data.get("scope")
                        for stem_name, meter_data in track_meters.items()
                    }
                    job.extra["realtime_scope"]["pre_master"] = pre_master_scope
                    job.extra["realtime_scope"]["post_master"] = post_master_scope
                    job.extra.setdefault("realtime_stream", {})
                    job.extra["realtime_stream"]["pre_master"] = pre_master_chunks
                    job.extra["realtime_stream"]["post_master"] = post_master_chunks
                    job.extra["realtime_stream"]["tracks"] = track_streams
            
            # Exporting
            if job_id:
                MixJobManager.update(job_id, state="exporting", progress=90, message="Exporting final mix…")
                await asyncio.sleep(0.05)
            
            # Ensure output directory exists
            output_dir = STORAGE_MIX_OUTPUTS / session_id
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / "final_mix.wav"
            
            # Export as WAV using save_wav
            await asyncio.to_thread(save_wav, str(output_path), master_audio)
            
            # Store duration for transport system
            if job_id:
                SAMPLE_RATE = 44100
                t = get_transport(job_id)
                t.duration = len(master_audio) / SAMPLE_RATE
            
            # Complete
            if job_id:
                MixJobManager.update(job_id, state="complete", progress=100, message="Mix complete.")
                await asyncio.sleep(0.05)
            
            # Return URL
            final_url = f"/storage/mix_outputs/{session_id}/final_mix.wav"
            output_url = final_url
            
            return {
                "is_error": False,
                "data": {
                    "audio_url": output_url,
                    "visual": visual
                }
            }
            
        except Exception as e:
            logger.error(f"Mix failed for session {session_id}: {e}")
            if job_id:
                MixJobManager.update(job_id, state="error", progress=100, message="Mix failed", error=str(e))
            return {"is_error": True, "error": str(e)}
    
    @staticmethod
    async def mix_audio(project_id: str, data) -> dict:
        """
        Basic mix using apply_basic_mix function
        
        Args:
            project_id: Project ID (session_id)
            data: MixRequest object with optional vocal_url, beat_url
            
        Returns:
            Success response dict with mix_url
        """
        # Use project_id as session_id
        session_id = project_id
        
        # compute paths (anonymous, no user_id)
        base = MEDIA_DIR / session_id

        vocal_path = base / "vocal.wav"
        beat_path = base / "beat.mp3"
        output_path = base / "mix" / "mix.wav"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # run DSP chain
        await asyncio.to_thread(
            apply_basic_mix,
            str(vocal_path),
            str(beat_path),
            str(output_path)
        )

        # update project.json
        result_url = f"/media/{session_id}/mix/mix.wav"
        memory = await get_or_create_project_memory(session_id, MEDIA_DIR, None)
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
    async def get_mix_status(project_id: str) -> dict:
        """
        Get the current mix status and file URL for a project.
        
        Args:
            project_id: Project ID (session_id)
            
        Returns:
            Dict with status and mix_url (if available)
        """
        try:
            # Load project data from memory
            memory = await get_or_create_project_memory(project_id, MEDIA_DIR, None)
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
                        file_path = MEDIA_DIR / project_id / "mix" / mix_url
                    
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

