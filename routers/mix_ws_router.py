from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jobs.mix_job_manager import JOBS
from utils.mix.timeline import get_timeline
from services.transport_service import get_transport
import asyncio


router = APIRouter(prefix="/ws/mix", tags=["mix_ws"])


@router.websocket("/stream/{job_id}/{source}")
async def stream_audio(websocket: WebSocket, job_id: str, source: str):
    """
    Streams sequential audio chunks for:
      - tracks/<stem_name>
      - pre_master
      - post_master
    """
    await websocket.accept()
    job = JOBS.get(job_id)

    if not job:
        await websocket.send_json({"error": "Job not found"})
        return

    stream = job.extra.get("realtime_stream", {})
    
    # Resolve source
    if source == "pre_master":
        chunks = stream.get("pre_master", [])
    elif source == "post_master":
        chunks = stream.get("post_master", [])
    else:
        # treat source as a stem name: tracks/<stem_name>
        tracks = stream.get("tracks", {})
        chunks = tracks.get(source, [])

    # Sequential push
    try:
        for chunk in chunks:
            await websocket.send_json(chunk)
            await asyncio.sleep(0.01)
    except WebSocketDisconnect:
        pass


@router.websocket("/status/{job_id}")
async def mix_ws_status(websocket: WebSocket, job_id: str):
    await websocket.accept()
    try:
        while True:
            job = JOBS.get(job_id)
            if not job:
                await websocket.send_json({"error": "Job not found"})
                break


            payload = {
                "job_id": job.job_id,
                "state": job.state,
                "progress": job.progress,
                "message": job.message,
                "error": job.error,
                "visual": job.extra.get("visual", None) if hasattr(job, "extra") else None,
                "realtime_meters": job.extra.get("realtime_meters", None) if hasattr(job, "extra") else None,
                "realtime_spectra": job.extra.get("realtime_spectra", None) if hasattr(job, "extra") else None,
                "realtime_scope": job.extra.get("realtime_scope", None) if hasattr(job, "extra") else None,
                "timeline": [
                    {
                        "step": e.step,
                        "message": e.message,
                        "progress": e.progress,
                        "timestamp": e.timestamp.isoformat()
                    }
                    for e in get_timeline(job_id)
                ]
            }


            await websocket.send_json(payload)
            await asyncio.sleep(0.5)


    except WebSocketDisconnect:
        pass


@router.websocket("/transport/{job_id}")
async def transport_socket(websocket: WebSocket, job_id: str):
    await websocket.accept()

    t = get_transport(job_id)

    try:
        while True:
            await asyncio.sleep(0.05)

            # update position during playback
            if t.is_playing:
                now = asyncio.get_event_loop().time()
                delta = now - (t.last_update or now)
                t.position += delta * t.rate
                t.last_update = now

                # clamp
                if t.position > t.duration:
                    t.position = t.duration
                    t.is_playing = False

            await websocket.send_json({
                "is_playing": t.is_playing,
                "position": t.position,
                "duration": t.duration,
            })

    except WebSocketDisconnect:
        pass

