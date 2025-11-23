from models.mix_timeline_event import MixTimelineEvent


TIMELINE = {}


def add_event(job_id, step, message, progress):
    evt = MixTimelineEvent(
        job_id=job_id,
        step=step,
        message=message,
        progress=progress
    )
    if job_id not in TIMELINE:
        TIMELINE[job_id] = []
    TIMELINE[job_id].append(evt)


def get_timeline(job_id):
    return TIMELINE.get(job_id, [])

