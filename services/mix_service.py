"""
Mix service for audio processing and mixing
"""
import logging
import asyncio
import numpy as np
from pathlib import Path
from typing import Optional, Dict, Any

from project_memory import get_or_create_project_memory
from config.settings import MEDIA_DIR
from utils.dsp.mix_pipeline import process_track, process_master_bus, blend_tracks
from utils.dsp.load import load_wav
from utils.dsp.export import save_wav
from utils.dsp.stereo import stereo_widen
from utils.dsp.scope import compute_scope
from utils.dsp.streamer import chunk_audio
from utils.dsp.timing import align_stems  # New DSP utility for alignment
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
from utils.dsp.spatial import spatial_pocket
from utils.mix.roles import detect_role
from utils.mix.mix_recipes import MIX_RECIPES
from utils.mix.config_apply import apply_recipe

from jobs.mix_job_manager import MixJobManager, JOBS
from services.transport_service import get_transport
from utils.mix_paths import STORAGE_MIX_OUTPUTS


logger = logging.getLogger(__name__)


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
        except Exception as e:
            logging.error(f"Tonal balance failed: {e}")
            return samples
    
    @staticmethod
    def apply_spatial_separation(stereo_samples: np.ndarray, role: str):
        try:
            return spatial_pocket(stereo_samples, role)
        except Exception as e:
            logging.error(f"Spatial separation failed: {e}")
            return stereo_samples
    
    @staticmethod
    def apply_frequency_masking(vocal_samples, beat_samples):
        try:
            from utils.dsp.masking import detect_masking, resolve_masking
            masked_freqs = detect_masking(vocal_samples, beat_samples)
            return resolve_masking(beat_samples, masked_freqs)
        except Exception as e:
            logging.error(f"Frequency masking failed: {e}")
            return beat_samples
    
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

            # === IMPLEMENTATION: STEM ALIGNMENT ===
            # Note: align_stems will detect the onset difference between the "beat" and "vocal" stems
            # and shift/pad the vocal stem to synchronize it with the beat.
            if "vocal" in audio_data_dict and "beat" in audio_data_dict:
                try:
                    # Perform alignment (returns the entire aligned dict)
                    audio_data_dict = await asyncio.to_thread(align_stems, audio_data_dict)
                except Exception as e:
                    logger.error(f"Stem alignment failed: {e}")
                    # Non-fatal: continue mixing without alignment
            # === END ALIGNMENT ===
            
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
            processed_tracks = {}  # Store as dict keyed by stem_name
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
                gain_role = role  # Default to detected role
                if config:
                    if hasattr(config, "tracks"):
                        track_cfg = config.tracks.get(stem_name) or {}
                        gain_role = track_cfg.get("role") if isinstance(track_cfg, dict) else (getattr(track_cfg, "role", None) or role)
                    else:
                        track_cfg = config.get("tracks", {}).get(stem_name, {})
                        gain_role = track_cfg.get("role", role)
                
                try:
                    audio_data = MixService.apply_auto_gain(audio_data, gain_role)
                except Exception as e:
                    logging.error(f"DSP step failed: {e}")
                    # Continue with original audio_data if auto gain fails
                # === END AI AUTO GAIN ===
                
                # === MICRO-DYNAMICS (AFTER GAIN, BEFORE EQ) ===
                try:
                    audio_data = MixService.apply_micro_dynamics(audio_data, role)
                except Exception as e:
                    logging.error(f"DSP step failed: {e}")
                    # Continue with original audio_data if micro-dynamics fails
                # === END MICRO-DYNAMICS ===
                
                # === TONAL BALANCE (AFTER MICRO-DYNAMICS, BEFORE EQ) ===
                try:
                    audio_data = MixService.apply_tonal_balance(audio_data, role)
                except Exception as e:
                    logging.error(f"DSP step failed: {e}")
                    # Continue with original audio_data if tonal balance fails
                # === END TONAL BALANCE ===
                
                # === SPATIAL SEPARATION (AFTER TONAL BALANCE, BEFORE EQ) ===
                try:
                    # Convert mono to [2, N] stereo placeholder if needed
                    if audio_data.ndim == 1:
                        stereo = np.vstack([audio_data, audio_data])
                    else:
                        stereo = audio_data
                    
                    stereo = MixService.apply_spatial_separation(stereo, role)
                    
                    # Keep stereo for downstream DSP
                    audio_data = stereo
                except Exception as e:
                    logging.error(f"DSP step failed: {e}")
                    # Continue with original audio_data if spatial separation fails
                # === END SPATIAL SEPARATION ===
                
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
                processed_tracks[stem_name] = processed_data
                track_meters[stem_name] = meter_data
                track_spectra[stem_name] = compute_track_spectrum(processed_data)
                
                # Generate per-track streaming chunks
                track_chunks = chunk_audio(processed_data)
                track_streams[stem_name] = track_chunks
            
            # Apply masking AFTER track DSP
            if "lead" in processed_tracks and "beat" in processed_tracks:
                try:
                    resolved = MixService.apply_frequency_masking(
                        processed_tracks["lead"],
                        processed_tracks["beat"]
                    )
                    processed_tracks["beat"] = resolved
                except Exception as e:
                    logging.error(f"Masking failed: {e}")
            
            # Mixing
            if job_id:
                MixJobManager.update(job_id, state="mixing", progress=65, message="Blending tracks…")
                await asyncio.sleep(0.05)
            
            # Blend tracks (convert dict to list)
            blended_audio = blend_tracks(list(processed_tracks.values()))
            
            # === MASTER LOUDNESS NORMALIZATION (BEFORE LIMITER) ===
            try:
                TARGET_MASTER_LUFS = -9.5
                master_gain = match_loudness(blended_audio, TARGET_MASTER_LUFS)
                blended_audio = blended_audio * master_gain
            except Exception as e:
                logging.error(f"DSP step failed: {e}")
                # Continue with original blended_audio if normalization fails
            # === END MASTER NORMALIZATION ===
            
            # Generate pre-master streaming chunks
            pre_master_chunks = chunk_audio(blended_audio)
            
            pre_master_scope = compute_scope(blended_audio)
            
            # Compute pre-master spectrum
            pre_master_spectrum = compute_track_spectrum(blended_audio)
            
            # Apply mix recipe to master bus
            if config and hasattr(config, "project_settings"):
                project_settings = config.project_settings or {}
            else:
                project_settings = config.get("project_settings", {}) if config else {}
            
            recipe = MIX_RECIPES.get(project_settings.get("mix_recipe", "default"), MIX_RECIPES["default"])
            
            # Handle recipe as Pydantic model or dict
            if hasattr(recipe, "master"):
                master_cfg = recipe.master
                # Convert Pydantic to dict if needed
                if hasattr(master_cfg, "model_dump"):
                    master_cfg_dict = master_cfg.model_dump()
                elif hasattr(master_cfg, "dict"):
                    master_cfg_dict = master_cfg.dict()
                else:
                    master_cfg_dict = master_cfg
            else:
                master_cfg_dict = recipe.get("master", {})
            
            # Extract values from master_cfg_dict (handle nested Pydantic models)
            recipe_eq = master_cfg_dict.get("eq", []) if isinstance(master_cfg_dict, dict) else (getattr(master_cfg, "eq", []) if hasattr(master_cfg, "eq") else [])
            recipe_compressor = master_cfg_dict.get("compressor") if isinstance(master_cfg_dict, dict) else (getattr(master_cfg, "compressor", None) if hasattr(master_cfg, "compressor") else None)
            recipe_limiter_threshold = master_cfg_dict.get("limiter_threshold", -1.0) if isinstance(master_cfg_dict, dict) else (getattr(master_cfg, "limiter_threshold", -1.0) if hasattr(master_cfg, "limiter_threshold") else -1.0)
            
            # Convert compressor to dict if it's a Pydantic model
            if recipe_compressor and not isinstance(recipe_compressor, dict):
                if hasattr(recipe_compressor, "model_dump"):
                    recipe_compressor = recipe_compressor.model_dump()
                elif hasattr(recipe_compressor, "dict"):
                    recipe_compressor = recipe_compressor.dict()
            
            # Apply mastering chain - adapt config format (recipe takes precedence, but allow user overrides)
            if config and hasattr(config, "master"):
                mastering_config_raw = config.master
                if hasattr(mastering_config_raw, "model_dump"):
                    mastering_config_raw = mastering_config_raw.model_dump()
                elif hasattr(mastering_config_raw, "dict"):
                    mastering_config_raw = mastering_config_raw.dict()
            else:
                mastering_config_raw = config.get("mastering_config", {}) if config else {}
            
            # Extract compressor settings
            user_compressor = mastering_config_raw.get("compressor", {}) if isinstance(mastering_config_raw, dict) else {}
            if user_compressor and not isinstance(user_compressor, dict):
                if hasattr(user_compressor, "model_dump"):
                    user_compressor = user_compressor.model_dump()
                elif hasattr(user_compressor, "dict"):
                    user_compressor = user_compressor.dict()
            
            mastering_config = {
                "eq": mastering_config_raw.get("eq_settings", recipe_eq) if isinstance(mastering_config_raw, dict) else recipe_eq,
                "threshold": user_compressor.get("threshold", recipe_compressor.get("threshold", -14)) if isinstance(user_compressor, dict) else (recipe_compressor.get("threshold", -14) if isinstance(recipe_compressor, dict) else -14),
                "ratio": user_compressor.get("ratio", recipe_compressor.get("ratio", 2.0)) if isinstance(user_compressor, dict) else (recipe_compressor.get("ratio", 2.0) if isinstance(recipe_compressor, dict) else 2.0),
                "attack": user_compressor.get("attack", recipe_compressor.get("attack", 10)) if isinstance(user_compressor, dict) else (recipe_compressor.get("attack", 10) if isinstance(recipe_compressor, dict) else 10),
                "release": user_compressor.get("release", recipe_compressor.get("release", 50)) if isinstance(user_compressor, dict) else (recipe_compressor.get("release", 50) if isinstance(recipe_compressor, dict) else 50),
                "ceiling": mastering_config_raw.get("limiter", {}).get("ceiling", recipe_limiter_threshold) if isinstance(mastering_config_raw, dict) and isinstance(mastering_config_raw.get("limiter"), dict) else recipe_limiter_threshold
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
            
            # Write to project memory
            memory = await get_or_create_project_memory(session_id, MEDIA_DIR, None)
            if "mix" not in memory.project_data:
                memory.project_data["mix"] = {}
            
            memory.project_data["mix"].update({
                "mix_url": final_url,
                "final_output": final_url,
                "completed": True
            })
            await memory.save()
            
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
                # Check for mix_url
                mix_url = mix_stage.get("mix_url")
                
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
                elif mix_stage.get("completed"):
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
    
