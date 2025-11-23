import asyncio
from typing import Dict


class TransportState:
    def __init__(self):
        self.is_playing = False
        self.position = 0.0   # seconds
        self.rate = 1.0       # play speed
        self.last_update = None
        self.duration = 0.0   # set from audio length


TRANSPORT: Dict[str, TransportState] = {}


def get_transport(job_id: str) -> TransportState:
    if job_id not in TRANSPORT:
        TRANSPORT[job_id] = TransportState()
    return TRANSPORT[job_id]


async def play(job_id: str):
    t = get_transport(job_id)
    t.is_playing = True
    t.last_update = asyncio.get_event_loop().time()


async def pause(job_id: str):
    t = get_transport(job_id)
    if t.is_playing:
        now = asyncio.get_event_loop().time()
        delta = now - (t.last_update or now)
        t.position += delta * t.rate
    t.is_playing = False


async def stop(job_id: str):
    t = get_transport(job_id)
    t.is_playing = False
    t.position = 0.0


async def seek(job_id: str, position_seconds: float):
    t = get_transport(job_id)
    t.position = max(0.0, min(position_seconds, t.duration))

