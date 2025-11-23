from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


@dataclass
class MixJobState:
    job_id: str
    session_id: str
    state: str = "queued"
    progress: int = 0
    message: str = ""
    error: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    extra: dict = field(default_factory=dict)

    def update(self, state=None, progress=None, message=None, error=None):
        if state is not None:
            self.state = state
        if progress is not None:
            self.progress = progress
        if message is not None:
            self.message = message
        if error is not None:
            self.error = error
        self.updated_at = datetime.utcnow()

