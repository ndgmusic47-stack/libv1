from fastapi import APIRouter

# We reuse the existing beat credits service
from services.beat_service import BeatService

router = APIRouter(prefix="/api", tags=["credits"])

# Service instance
beat_service = BeatService()


@router.get("/credits")
async def get_global_credits():
    """
    Simple proxy so frontend GET /api/credits works.
    Uses the existing beat credits implementation.
    Normalises to: { "credits": <number> }.
    """
    try:
        data = await beat_service.get_credits()
    except Exception:
        # Fail soft: return 0 if Beatoven or service fails
        return {"credits": 0}

    # Expecting something like: { "credits": N, "source": "beatoven" }
    if isinstance(data, dict) and "credits" in data:
        credits = data.get("credits", 0)
    else:
        credits = 0

    return {"credits": credits}

