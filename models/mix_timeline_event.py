from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class MixTimelineEvent:
    job_id: str
    step: str
    message: str
    progress: int
    timestamp: datetime = field(default_factory=datetime.utcnow)

