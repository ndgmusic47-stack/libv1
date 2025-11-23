import uuid
import json
import logging
from pathlib import Path
from typing import Optional, Dict, List
from datetime import datetime

from fastapi.responses import JSONResponse

from project_memory import get_or_create_project_memory
from social_scheduler import SocialScheduler
from backend.utils.responses import success_response, error_response
from config.settings import settings, MEDIA_DIR
from utils.shared_utils import get_session_media_path

logger = logging.getLogger(__name__)


class ContentService:

    @staticmethod
    async def generate_idea(request):
        """Generate a simple, practical video idea"""
        # Handle None request (from Body(default=None))
        if request is None:
            session_id = str(uuid.uuid4())
            title = "My Track"
            lyrics = ""
            mood = "energetic"
            genre = "hip hop"
        else:
            session_id = request.session_id or str(uuid.uuid4())
            title = request.title or "My Track"
            lyrics = request.lyrics or ""
            mood = request.mood or "energetic"
            genre = request.genre or "hip hop"
        
        api_key = settings.openai_api_key
        
        # Validate API key is present
        if not api_key:
            logger.error("OpenAI API key not configured - cannot generate video idea")
            return {"error": "OpenAI API key is required for video idea generation. Please configure OPENAI_API_KEY in your environment.", "is_error": True}
        
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            
            prompt = f"""Generate a simple, practical video idea for a {mood} {genre} track titled "{title}".

Rules:
- NO cinematic jargon
- NO complex directions
- NO multi-shot filming
- Keep everything short and simple
- Make it practical and easy to film with a phone

Return a JSON object with:
- idea: A one-sentence description of what video to make
- hook: A simple opening line (first 3 seconds)
- script: One or two lines to say
- visual: Simple filming instructions (one sentence)

Example format:
{{
  "idea": "Do a talking-head explaining the meaning behind the chorus.",
  "hook": "This line hits harder when you know the story behind it...",
  "script": "Say one or two lines explaining what inspired the track.",
  "visual": "Record in a quiet space, chest-up, with your phone facing you."
}}"""
            
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a practical video content creator. Generate simple, actionable video ideas that are easy to film with a phone."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.8,
                response_format={"type": "json_object"}
            )
            
            result_text = response.choices[0].message.content.strip()
            idea_data = json.loads(result_text)
            
            # Validate structure
            if not all(key in idea_data for key in ["idea", "hook", "script", "visual"]):
                logger.error("OpenAI returned invalid response structure for video idea")
                return {"error": "AI service returned an invalid response structure. Please try again.", "is_error": True}
            
            return {"data": idea_data, "is_error": False}
            
        except Exception as e:
            logger.error(f"OpenAI idea generation failed: {e}", exc_info=True)
            return {"error": str(e), "is_error": True}

    @staticmethod
    async def analyze_text(request):
        """Analyze video transcript and return viral score + improvements"""
        api_key = settings.openai_api_key
        
        # Validate API key is present
        if not api_key:
            logger.error("OpenAI API key not configured - cannot analyze video")
            return {"error": "OpenAI API key is required for video analysis. Please configure OPENAI_API_KEY in your environment.", "is_error": True}
        
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            
            prompt = f"""Analyze this video transcript for viral potential on TikTok/Instagram Reels.

Transcript: {request.transcript[:1000]}
Title: {request.title or "Unknown"}
Lyrics: {request.lyrics or "N/A"}
Mood: {request.mood or "Unknown"}
Genre: {request.genre or "Unknown"}

Evaluate using these heuristics:
1. Hook strength (first 1.5 seconds)
2. First 1.5s engagement
3. Emotion/clarity
4. Simplicity
5. Retention potential
6. TikTok fit

Return a JSON object with:
- score: Number 0-100 (viral score)
- summary: One sentence summary
- improvements: Array of 3 specific, actionable improvement suggestions
- suggested_hook: A better opening line if needed
- thumbnail_suggestion: Simple thumbnail suggestion

Example format:
{{
  "score": 74,
  "summary": "Strong energy, intro slightly slow.",
  "improvements": [
    "Start speaking faster in the first second.",
    "Increase energy on key phrase.",
    "Try brighter lighting."
  ],
  "suggested_hook": "Let me tell you why this line matters...",
  "thumbnail_suggestion": "Use frame at 0:01"
}}"""
            
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a viral content analyst. Analyze videos for TikTok/Instagram Reels potential and provide actionable feedback."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                response_format={"type": "json_object"}
            )
            
            result_text = response.choices[0].message.content.strip()
            analysis_data = json.loads(result_text)
            
            # Validate structure
            if "score" not in analysis_data:
                logger.error("OpenAI returned invalid response structure for video analysis")
                return {"error": "AI service returned an invalid response structure. Please try again.", "is_error": True}
            
            return {"data": analysis_data, "is_error": False}
            
        except Exception as e:
            logger.error(f"Video analysis failed: {e}", exc_info=True)
            return {"error": str(e), "is_error": True}

    @staticmethod
    async def generate_text(request):
        """Generate captions, hashtags, hooks, posting strategy, and content ideas"""
        api_key = settings.openai_api_key
        
        # Validate API key is present
        if not api_key:
            logger.error("OpenAI API key not configured - cannot generate text content")
            return {"error": "OpenAI API key is required for text generation. Please configure OPENAI_API_KEY in your environment.", "is_error": True}
        
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            
            prompt = f"""Generate social media content for a {request.mood or "energetic"} {request.genre or "hip hop"} track titled "{request.title or "My Track"}".

Transcript: {request.transcript or "N/A"}
Lyrics: {request.lyrics or "N/A"}

Return a JSON object with:
- captions: Array of 3 different caption options
- hashtags: Array of 5-10 relevant hashtags
- hooks: Array of 3 hook options (opening lines)
- posting_strategy: One sentence posting strategy
- ideas: Array of 3 additional content ideas

Example format:
{{
  "captions": ["Caption 1", "Caption 2", "Caption 3"],
  "hashtags": ["#tag1", "#tag2", "#tag3"],
  "hooks": ["Hook 1", "Hook 2", "Hook 3"],
  "posting_strategy": "Post between 5-7pm.",
  "ideas": ["Idea 1", "Idea 2", "Idea 3"]
}}"""
            
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a social media content strategist. Generate engaging captions, hashtags, and content ideas for music promotion."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.8,
                response_format={"type": "json_object"}
            )
            
            result_text = response.choices[0].message.content.strip()
            text_data = json.loads(result_text)
            
            # Validate structure
            if not all(key in text_data for key in ["captions", "hashtags", "hooks", "posting_strategy", "ideas"]):
                logger.error("OpenAI returned invalid response structure for text generation")
                return {"error": "AI service returned an invalid response structure. Please try again.", "is_error": True}
            
            return {"data": text_data, "is_error": False}
            
        except Exception as e:
            logger.error(f"Text generation failed: {e}", exc_info=True)
            return {"error": str(e), "is_error": True}

    @staticmethod
    async def schedule_post(request):
        """Schedule video using GETLATE API"""
        session_id = request.session_id
        getlate_key = settings.getlate_api_key
        
        try:
            # Use SocialScheduler for GETLATE integration
            scheduler = SocialScheduler(session_id)
            
            # Combine caption and hashtags
            hashtag_string = " ".join(request.hashtags) if request.hashtags else ""
            full_caption = f"{request.caption}\n\n{hashtag_string}".strip()
            
            # Try GETLATE API if key available
            if getlate_key:
                result = await scheduler.schedule_with_getlate(
                    platform=request.platform,
                    content=full_caption,
                    scheduled_time=request.schedule_time,
                    api_key=getlate_key,
                    media_url=request.video_url,
                    hashtags=request.hashtags
                )
                
                if result.get("success"):
                    # Update project memory
                    memory = await get_or_create_project_memory(session_id, MEDIA_DIR)
                    await memory.update("contentScheduled", True)
                    await memory.advance_stage("content", "analytics")
                    
                    return {
                        "data": {
                            "post_id": result.get("post_id"),
                            "platform": request.platform,
                            "scheduled_time": request.schedule_time,
                            "status": "scheduled",
                            "provider": "getlate"
                        },
                        "is_error": False
                    }
                else:
                    logger.warning(f"GetLate API failed: {result.get('error')} - falling back to local")
            
            # FALLBACK: Local JSON storage
            session_path = get_session_media_path(session_id)
            schedule_file = session_path / "schedule.json"
            
            # Load existing schedule
            if schedule_file.exists():
                with open(schedule_file, 'r') as f:
                    schedule = json.load(f)
            else:
                schedule = []
            
            # Create post ID
            post_id = f"{request.platform}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            # Append new post
            post = {
                "post_id": post_id,
                "platform": request.platform,
                "video_url": request.video_url,
                "caption": full_caption,
                "hashtags": request.hashtags,
                "scheduled_time": request.schedule_time,
                "created_at": datetime.now().isoformat(),
                "provider": "local",
                "status": "scheduled"
            }
            schedule.append(post)
            
            # Save
            with open(schedule_file, 'w') as f:
                json.dump(schedule, f, indent=2)
            
            # Update project memory
            memory = await get_or_create_project_memory(session_id, MEDIA_DIR)
            await memory.update("contentScheduled", True)
            await memory.advance_stage("content", "analytics")
            
            return {
                "data": {
                    "post_id": post_id,
                    "platform": request.platform,
                    "scheduled_time": request.schedule_time,
                    "status": "scheduled",
                    "provider": "local"
                },
                "is_error": False
            }
            
        except Exception as e:
            logger.error(f"Video scheduling failed: {e}", exc_info=True)
            return {"error": str(e), "is_error": True}

    @staticmethod
    async def save_scheduled_post(request):
        """Save scheduled post to project memory"""
        session_id = request.sessionId
        # Validate required fields
        if not request.platform:
            return {"error": "Platform is required", "is_error": True}
        
        # Use dateTime if provided, otherwise fall back to time
        scheduled_time = request.dateTime or request.time
        if not scheduled_time:
            return {"error": "dateTime is required", "is_error": True}
        
        session_path = get_session_media_path(session_id)
        schedule_file = session_path / "schedule.json"
        
        # Load existing schedule
        if schedule_file.exists():
            with open(schedule_file, 'r') as f:
                schedule = json.load(f)
        else:
            schedule = []
        
        # Create post entry
        post = {
            "post_id": f"{request.platform}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "platform": request.platform,
            "dateTime": scheduled_time,
            "time": scheduled_time,  # Keep for backward compatibility
            "caption": request.caption or "",
            "created_at": datetime.now().isoformat(),
            "status": "scheduled"
        }
        schedule.append(post)
        
        # Save
        with open(schedule_file, 'w') as f:
            json.dump(schedule, f, indent=2)
        
        # Update project memory
        memory = await get_or_create_project_memory(session_id, MEDIA_DIR)
        await memory.update("contentScheduled", True)
        
        return {
            "data": {"post_id": post["post_id"], "status": "saved"},
            "is_error": False
        }

    @staticmethod
    async def get_scheduled_posts(session_id: str):
        """Get all scheduled posts for a session"""
        session_path = get_session_media_path(session_id)
        schedule_file = session_path / "schedule.json"
        
        if not schedule_file.exists():
            return {"data": [], "is_error": False}
        
        try:
            with open(schedule_file, 'r') as f:
                schedule = json.load(f)
            return {"data": schedule, "is_error": False}
        except Exception as e:
            logger.error(f"Failed to load schedule: {e}")
            return {"data": [], "is_error": False}

