from models.mix_job_state import MixJobState
from utils.mix.timeline import add_event
import uuid

JOBS = {}


class MixJobManager:

    @staticmethod
    async def enqueue_mix(session_id, stems, config):
        job_id = str(uuid.uuid4())
        job = MixJobState(job_id=job_id, session_id=session_id)
        # Store config in job.extra
        if not hasattr(job, 'extra'):
            job.extra = {}
        job.extra["config"] = config
        JOBS[job_id] = job
        return job_id

    @staticmethod
    def update(job_id, **kwargs):
        job = JOBS.get(job_id)
        if not job:
            return
        job.update(**kwargs)
        add_event(
            job_id,
            step=job.state,
            message=job.message,
            progress=job.progress
        )

    @staticmethod
    async def get_job_status(job_id):
        job = JOBS.get(job_id)
        if not job:
            return {"is_error": True, "error": "Job not found"}
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
            }
        }
