from models.mix_job_state import MixJobState
from utils.mix.timeline import add_event
from config.settings import MEDIA_DIR
from utils.mix_paths import STORAGE_MIX_OUTPUTS
import uuid
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# TTL constants for job cleanup
JOB_TTL_HOURS = 48  # Completed jobs expire after 48 hours
FAILED_JOB_TTL_HOURS = 24  # Failed jobs expire after 24 hours
MAX_JOBS_PER_SESSION = 50  # Optional: max jobs per session (not enforced yet)


# Placeholder for JOBS - will be initialized after MixJobManager is defined
JOBS = None


class MixJobManager:

    @staticmethod
    def _get_index_path(job_id: str) -> Path:
        """Get filesystem path for job_id → session_id index file"""
        index_dir = MEDIA_DIR / "jobs_index"
        index_dir.mkdir(parents=True, exist_ok=True)
        return index_dir / f"{job_id}.json"

    @staticmethod
    def _write_index(job_id: str, session_id: str):
        """Write job_id → session_id mapping to index"""
        index_path = MixJobManager._get_index_path(job_id)
        temp_path = index_path.with_suffix('.json.tmp')
        with open(temp_path, 'w') as f:
            json.dump({"session_id": session_id}, f)
        temp_path.replace(index_path)

    @staticmethod
    def _read_index(job_id: str) -> Optional[str]:
        """Read session_id from index for given job_id"""
        index_path = MixJobManager._get_index_path(job_id)
        if not index_path.exists():
            return None
        try:
            with open(index_path, 'r') as f:
                index_dict = json.load(f)
            return index_dict.get("session_id")
        except Exception:
            return None

    @staticmethod
    def _get_job_path(session_id: str, job_id: str) -> Path:
        """Get filesystem path for a job JSON file"""
        job_dir = MEDIA_DIR / session_id / "jobs"
        job_dir.mkdir(parents=True, exist_ok=True)
        return job_dir / f"{job_id}.json"

    @staticmethod
    def _save_job(job: MixJobState):
        """Atomically save job to filesystem (temp → rename)"""
        job_path = MixJobManager._get_job_path(job.session_id, job.job_id)
        temp_path = job_path.with_suffix('.json.tmp')
        
        # Serialize job to dict
        job_dict = {
            "job_id": job.job_id,
            "session_id": job.session_id,
            "state": job.state,
            "progress": job.progress,
            "message": job.message,
            "error": job.error,
            "created_at": job.created_at.isoformat(),
            "updated_at": job.updated_at.isoformat(),
            "extra": job.extra
        }
        
        # Write to temp file
        with open(temp_path, 'w') as f:
            json.dump(job_dict, f, indent=2)
        
        # Atomic rename
        temp_path.replace(job_path)

    @staticmethod
    def _load_job(job_id: str, session_id: Optional[str] = None) -> Optional[MixJobState]:
        """Load job from filesystem. If session_id not provided, resolve via index."""
        if session_id:
            # Direct path lookup
            job_path = MixJobManager._get_job_path(session_id, job_id)
            if job_path.exists():
                return MixJobManager._load_job_from_path(job_path)
        else:
            # Resolve session_id via index, then load direct path
            resolved_session_id = MixJobManager._read_index(job_id)
            if resolved_session_id:
                job_path = MixJobManager._get_job_path(resolved_session_id, job_id)
                if job_path.exists():
                    return MixJobManager._load_job_from_path(job_path)
        return None

    @staticmethod
    def _load_job_from_path(job_path: Path) -> Optional[MixJobState]:
        """Load job from a specific JSON file path"""
        try:
            with open(job_path, 'r') as f:
                job_dict = json.load(f)
            
            # Reconstruct MixJobState
            job = MixJobState(
                job_id=job_dict["job_id"],
                session_id=job_dict["session_id"],
                state=job_dict.get("state", "queued"),
                progress=job_dict.get("progress", 0),
                message=job_dict.get("message", ""),
                error=job_dict.get("error"),
                created_at=datetime.fromisoformat(job_dict["created_at"]),
                updated_at=datetime.fromisoformat(job_dict["updated_at"]),
                extra=job_dict.get("extra", {})
            )
            return job
        except Exception:
            return None

    @staticmethod
    def _get_job(job_id: str, session_id: Optional[str] = None) -> Optional[MixJobState]:
        """Get job from cache or filesystem"""
        # When session_id is provided, try direct path first for performance
        if session_id:
            job = MixJobManager._load_job(job_id, session_id)
            if job:
                # Cache it
                if JOBS is not None:
                    JOBS[job_id] = job
                return job
        # Use JOBS dict which auto-loads from filesystem via JobsDict.get()
        return JOBS.get(job_id) if JOBS is not None else MixJobManager._load_job(job_id, session_id)

    @staticmethod
    async def enqueue_mix(session_id, stems, config):
        # Clean up expired jobs opportunistically before enqueueing
        MixJobManager.cleanup_expired_jobs(session_id)
        
        job_id = str(uuid.uuid4())
        job = MixJobState(job_id=job_id, session_id=session_id)
        # Store config in job.extra
        if not hasattr(job, 'extra'):
            job.extra = {}
        job.extra["config"] = config
        
        # Save to filesystem and cache
        MixJobManager._save_job(job)
        # Write index for fast lookup
        MixJobManager._write_index(job_id, session_id)
        JOBS[job_id] = job
        return job_id

    @staticmethod
    def update(job_id, **kwargs):
        job = MixJobManager._get_job(job_id)
        if not job:
            return
        job.update(**kwargs)
        
        # Persist to filesystem
        MixJobManager._save_job(job)
        
        # Update cache
        JOBS[job_id] = job
        
        add_event(
            job_id,
            step=job.state,
            message=job.message,
            progress=job.progress
        )

    @staticmethod
    async def get_job_status(job_id):
        job = MixJobManager._get_job(job_id)
        if not job:
            return {"is_error": True, "error": "Job not found"}
        
        # Get session_id from job record
        session_id = job.session_id
        
        # Determine preview_url based on job state and file existence
        preview_url = None
        if job.state == "complete":
            # Check if preview file exists
            preview_path = STORAGE_MIX_OUTPUTS / session_id / "final_mix.wav"
            if preview_path.exists():
                preview_url = f"/mix/{session_id}/mix/preview"
        
        return {
            "is_error": False,
            "data": {
                "job_id": job.job_id,
                "state": job.state,
                "progress": job.progress,
                "message": job.message,
                "error": job.error,
                "created_at": job.created_at.isoformat(),
                "updated_at": job.updated_at.isoformat(),
                "preview_url": preview_url,
            }
        }

    @staticmethod
    def load_job(job_id: str, session_id: Optional[str] = None) -> Optional[MixJobState]:
        """Public method to load job (for compatibility)"""
        return MixJobManager._get_job(job_id, session_id)

    @staticmethod
    def cleanup_expired_jobs(session_id: str) -> int:
        """
        Clean up expired jobs for a session.
        
        Deletes:
        - Expired job JSONs from MEDIA_DIR/<session_id>/jobs/
        - Associated index files from MEDIA_DIR/jobs_index/
        
        Args:
            session_id: Session ID to clean up jobs for
            
        Returns:
            Number of jobs deleted
        """
        deleted_count = 0
        try:
            job_dir = MEDIA_DIR / session_id / "jobs"
            if not job_dir.exists():
                return 0
            
            # Get all job JSON files for this session
            job_files = list(job_dir.glob("*.json"))
            if not job_files:
                return 0
            
            now = datetime.utcnow()
            
            for job_path in job_files:
                try:
                    # Load job to check expiry
                    job = MixJobManager._load_job_from_path(job_path)
                    if not job:
                        # Corrupted or invalid job file - delete it
                        job_path.unlink(missing_ok=True)
                        deleted_count += 1
                        continue
                    
                    # Determine TTL based on job state
                    if job.state == "error":
                        ttl_hours = FAILED_JOB_TTL_HOURS
                    elif job.state == "complete":
                        ttl_hours = JOB_TTL_HOURS
                    else:
                        # Active/running jobs are not expired
                        continue
                    
                    # Check if job is expired based on updated_at
                    age = now - job.updated_at
                    if age > timedelta(hours=ttl_hours):
                        job_id = job.job_id
                        
                        # Delete job JSON
                        job_path.unlink(missing_ok=True)
                        
                        # Delete index file
                        index_path = MixJobManager._get_index_path(job_id)
                        index_path.unlink(missing_ok=True)
                        
                        # Remove from cache if present
                        if JOBS is not None and job_id in JOBS:
                            del JOBS[job_id]
                        
                        deleted_count += 1
                        logger.debug(f"Deleted expired job: {job_id} (state: {job.state}, age: {age})")
                        
                except Exception as e:
                    # Log error but continue with other jobs
                    logger.warning(f"Error processing job file {job_path}: {e}")
                    continue
            
            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} expired job(s) for session {session_id}")
            
        except Exception as e:
            logger.error(f"Error during job cleanup for session {session_id}: {e}")
        
        return deleted_count


class JobsDict(dict):
    """Dict-like wrapper that auto-loads jobs from filesystem on access"""
    
    def get(self, key, default=None):
        # Check in-memory cache first
        if key in self:
            return super().get(key, default)
        
        # Try to load from filesystem
        job = MixJobManager._load_job(key)
        if job:
            # Cache it
            super().__setitem__(key, job)
            return job
        
        return default
    
    def __getitem__(self, key):
        # Check in-memory cache first
        if key in self:
            return super().__getitem__(key)
        
        # Try to load from filesystem
        job = MixJobManager._load_job(key)
        if job:
            # Cache it
            super().__setitem__(key, job)
            return job
        
        # Raise KeyError if not found
        raise KeyError(key)


# Initialize JOBS dict after MixJobManager is defined
JOBS = JobsDict()
