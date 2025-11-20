"""
Release Service - Business logic for release pack generation
"""
import json
import shutil
import zipfile
import re
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from io import BytesIO

from openai import OpenAI
from openai import AuthenticationError, RateLimitError, APIError
from PIL import Image
from pydub import AudioSegment

from project_memory import get_or_create_project_memory
from utils.shared_utils import get_session_media_path, log_endpoint_event
from crud.user import UserRepository
from config import settings

logger = logging.getLogger(__name__)

# Constants
MEDIA_DIR = Path("./media")


class ReleaseService:
    """Service class for release pack generation business logic"""
    
    def __init__(self):
        self.openai_api_key = settings.openai_api_key
    
    async def generate_cover_art(
        self,
        session_id: str,
        user_id: str,
        track_title: str,
        artist_name: str,
        genre: str,
        mood: str,
        style: Optional[str] = "realistic"
    ) -> Dict[str, Any]:
        """Generate AI cover art using OpenAI (3 images, 3000x3000, 1500x1500, 1080x1920)"""
        session_path = get_session_media_path(session_id, user_id)
        cover_dir = session_path / "release" / "cover"
        cover_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            # Input validation - ensure all required fields are present and non-empty
            if not track_title or not track_title.strip():
                log_endpoint_event("/release/cover", session_id, "error", {"error": "Missing required field: track_title"})
                return {
                    "success": False,
                    "error": "Missing required field: track_title",
                    "status_code": 400
                }
            
            if not artist_name or not artist_name.strip():
                log_endpoint_event("/release/cover", session_id, "error", {"error": "Missing required field: artist_name"})
                return {
                    "success": False,
                    "error": "Missing required field: artist_name",
                    "status_code": 400
                }
            
            if not genre or not genre.strip():
                log_endpoint_event("/release/cover", session_id, "error", {"error": "Missing required field: genre"})
                return {
                    "success": False,
                    "error": "Missing required field: genre",
                    "status_code": 400
                }
            
            if not mood or not mood.strip():
                log_endpoint_event("/release/cover", session_id, "error", {"error": "Missing required field: mood"})
                return {
                    "success": False,
                    "error": "Missing required field: mood",
                    "status_code": 400
                }
            
            # Sanitize inputs to prevent prompt injection issues
            track_title = track_title.strip()
            artist_name = artist_name.strip()
            genre = genre.strip()
            mood = mood.strip()
            style = (style or "realistic").strip()
            
            # Strengthened API key validation - check for None, empty string, or whitespace-only
            if not self.openai_api_key or not self.openai_api_key.strip():
                log_endpoint_event("/release/cover", session_id, "error", {"error": "OpenAI API key not configured"})
                return {
                    "success": False,
                    "error": "OpenAI API key not configured",
                    "status_code": 402
                }
            
            import base64
            
            client = OpenAI(api_key=self.openai_api_key)
            
            # Build prompt according to spec with validated inputs
            prompt = (
                f"High-quality album cover for the single '{track_title}' "
                f"by {artist_name}. Genre: {genre}. Mood: {mood}. "
                f"Style: {style}. Clean, cinematic, striking, professional. "
                "3000×3000 resolution, centered composition."
            )
            
            # Generate 3 images with base64 response
            response = client.images.generate(
                model="dall-e-2",  # Using dall-e-2 as it supports b64_json and n=3
                prompt=prompt,
                size="1024x1024",
                quality="standard",
                response_format="b64_json",
                n=3
            )
            
            generated_urls = []
            
            for i, img_data in enumerate(response.data):
                img_bytes = base64.b64decode(img_data.b64_json)
                img = Image.open(BytesIO(img_bytes)).convert("RGB")
                
                # Always upscale to 3000×3000
                img_3000 = img.resize((3000, 3000), Image.LANCZOS)
                
                # Derivative variants
                img_1500 = img_3000.resize((1500, 1500), Image.LANCZOS)
                img_vertical = img_3000.resize((1080, 1920), Image.LANCZOS)
                
                # Save all variants
                img_3000.save(cover_dir / f"cover_{i+1}.jpg", "JPEG", quality=95)
                img_1500.save(cover_dir / f"cover_{i+1}_1500.jpg", "JPEG", quality=95)
                img_vertical.save(cover_dir / f"cover_{i+1}_vertical.jpg", "JPEG", quality=95)
                
                generated_urls.append(
                    f"/media/{user_id}/{session_id}/release/cover/cover_{i+1}.jpg"
                )
            
            if not generated_urls:
                return {"success": False, "error": "Failed to generate any cover art images"}
            
            return {
                "success": True,
                "images": generated_urls
            }
        
        except AuthenticationError as e:
            logger.error(f"OpenAI authentication failed: {e}", exc_info=True)
            log_endpoint_event("/release/cover", session_id, "error", {"error": "OpenAI authentication failed", "type": "authentication"})
            return {
                "success": False,
                "error": "OpenAI API authentication failed. Please check your API key configuration.",
                "status_code": 402
            }
        except RateLimitError as e:
            logger.error(f"OpenAI rate limit exceeded: {e}", exc_info=True)
            log_endpoint_event("/release/cover", session_id, "error", {"error": "OpenAI rate limit exceeded", "type": "rate_limit"})
            return {
                "success": False,
                "error": "OpenAI API rate limit exceeded. Please try again later.",
                "status_code": 429
            }
        except APIError as e:
            logger.error(f"OpenAI API error: {e}", exc_info=True)
            log_endpoint_event("/release/cover", session_id, "error", {"error": f"OpenAI API error: {str(e)}", "type": "api_error"})
            return {
                "success": False,
                "error": f"OpenAI API error: {str(e)}",
                "status_code": 502
            }
        except Exception as e:
            logger.error(f"Cover art generation failed: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    async def select_cover_art(
        self,
        session_id: str,
        user_id: str,
        cover_url: str
    ) -> Dict[str, Any]:
        """Save selected cover art to final versions (3000, 1500, vertical) and update memory"""
        session_path = get_session_media_path(session_id, user_id)
        cover_dir = session_path / "release" / "cover"
        cover_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            # Validate cover_url is provided
            if not cover_url or not cover_url.strip():
                return {"success": False, "error": "Missing cover_url parameter"}
            
            # Extract index from cover_url (e.g., "/media/.../cover_1.jpg" -> 1)
            try:
                index = int(cover_url.split("cover_")[1].split(".")[0])
            except (IndexError, ValueError) as e:
                logger.error(f"Failed to extract cover index from URL {cover_url}: {e}")
                return {"success": False, "error": f"Invalid cover_url format: {cover_url}"}
            
            src_3000 = cover_dir / f"cover_{index}.jpg"
            src_1500 = cover_dir / f"cover_{index}_1500.jpg"
            src_vertical = cover_dir / f"cover_{index}_vertical.jpg"
            
            # Validate source files exist before copying
            if not src_3000.exists() or not src_3000.is_file():
                return {"success": False, "error": f"Source cover file not found: {src_3000.name}"}
            
            if not src_1500.exists() or not src_1500.is_file():
                return {"success": False, "error": f"Source cover file not found: {src_1500.name}"}
            
            if not src_vertical.exists() or not src_vertical.is_file():
                return {"success": False, "error": f"Source cover file not found: {src_vertical.name}"}
            
            dst_3000 = cover_dir / "final_cover_3000.jpg"
            dst_1500 = cover_dir / "final_cover_1500.jpg"
            dst_vertical = cover_dir / "final_cover_vertical.jpg"
            
            # Copy files with error handling
            try:
                shutil.copy2(src_3000, dst_3000)
                shutil.copy2(src_1500, dst_1500)
                shutil.copy2(src_vertical, dst_vertical)
            except Exception as copy_error:
                logger.error(f"Failed to copy cover art files: {copy_error}")
                return {"success": False, "error": f"Failed to copy cover art files: {str(copy_error)}"}
            
            # Update project memory
            memory = await get_or_create_project_memory(session_id, MEDIA_DIR, user_id)
            final_cover_url = f"/media/{user_id}/{session_id}/release/cover/final_cover_3000.jpg"
            await memory.update("release.cover_art", final_cover_url)
            
            return {
                "success": True,
                "final_cover": memory.project_data.get("release", {}).get("cover_art")
            }
        
        except Exception as e:
            logger.error(f"Failed to select cover art: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    async def generate_release_copy(
        self,
        session_id: str,
        user_id: str,
        track_title: str,
        artist_name: str,
        genre: str,
        mood: str,
        lyrics: str = ""
    ) -> Dict[str, Any]:
        """Generate release copy: release_description.txt, press_pitch.txt, tagline.txt"""
        session_path = get_session_media_path(session_id, user_id)
        copy_dir = session_path / "release" / "copy"
        copy_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            # Input validation - ensure all required fields are present and non-empty
            if not track_title or not track_title.strip():
                log_endpoint_event("/release/copy", session_id, "error", {"error": "Missing required field: track_title"})
                return {
                    "success": False,
                    "error": "Missing required field: track_title",
                    "status_code": 400
                }
            
            if not artist_name or not artist_name.strip():
                log_endpoint_event("/release/copy", session_id, "error", {"error": "Missing required field: artist_name"})
                return {
                    "success": False,
                    "error": "Missing required field: artist_name",
                    "status_code": 400
                }
            
            if not genre or not genre.strip():
                log_endpoint_event("/release/copy", session_id, "error", {"error": "Missing required field: genre"})
                return {
                    "success": False,
                    "error": "Missing required field: genre",
                    "status_code": 400
                }
            
            if not mood or not mood.strip():
                log_endpoint_event("/release/copy", session_id, "error", {"error": "Missing required field: mood"})
                return {
                    "success": False,
                    "error": "Missing required field: mood",
                    "status_code": 400
                }
            
            # Sanitize inputs
            track_title = track_title.strip()
            artist_name = artist_name.strip()
            genre = genre.strip()
            mood = mood.strip()
            
            # Handle lyrics safely - ensure it's a string and handle None/empty cases
            lyrics_text = ""
            if lyrics:
                lyrics_text = str(lyrics).strip()
                # Limit lyrics excerpt to 200 characters and escape special characters for prompt safety
                if lyrics_text:
                    lyrics_excerpt = lyrics_text[:200].replace('"', "'").replace('\n', ' ').replace('\r', ' ')
                else:
                    lyrics_excerpt = ""
            else:
                lyrics_excerpt = ""
            
            # Strengthened API key validation - check for None, empty string, or whitespace-only
            if not self.openai_api_key or not self.openai_api_key.strip():
                log_endpoint_event("/release/copy", session_id, "error", {"error": "OpenAI API key not configured"})
                return {
                    "success": False,
                    "error": "OpenAI API key not configured",
                    "status_code": 402
                }
            
            client = OpenAI(api_key=self.openai_api_key)
            
            prompt = f"""Generate professional release copy for:
Track: {track_title}
Artist: {artist_name}
Genre: {genre}
Mood: {mood}
{"Lyrics excerpt: " + lyrics_excerpt if lyrics_excerpt else ""}

Provide:
1. release_description.txt - Short, clean description (2-3 sentences)
2. press_pitch.txt - Professional press pitch (1 paragraph)
3. tagline.txt - Catchy one-liner tagline
4. genre_tags - 5-7 relevant genre/mood tags (comma-separated)

Format as JSON:
{{
  "release_description": "...",
  "press_pitch": "...",
  "tagline": "...",
  "genre_tags": ["tag1", "tag2", ...]
}}"""
            
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a professional music publicist. Generate concise, professional release copy."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.8
            )
            
            content = response.choices[0].message.content.strip()
            # Try to parse JSON
            try:
                json_match = re.search(r'\{.*\}', content, re.DOTALL)
                if json_match:
                    copy_data = json.loads(json_match.group())
                    release_desc = copy_data.get("release_description", "")
                    press_pitch = copy_data.get("press_pitch", "")
                    tagline = copy_data.get("tagline", "")
                    genre_tags = copy_data.get("genre_tags", [])
                else:
                    raise ValueError("No JSON found")
            except:
                # Fallback parsing
                lines = content.split('\n')
                release_desc = lines[0] if lines else ""
                press_pitch = lines[1] if len(lines) > 1 else ""
                tagline = lines[2] if len(lines) > 2 else ""
                genre_tags = [genre, mood]
            
            # Save files
            with open(copy_dir / "release_description.txt", 'w', encoding='utf-8') as f:
                f.write(release_desc)
            
            with open(copy_dir / "press_pitch.txt", 'w', encoding='utf-8') as f:
                f.write(press_pitch)
            
            with open(copy_dir / "tagline.txt", 'w', encoding='utf-8') as f:
                f.write(tagline)
            
            # Update project memory
            memory = await get_or_create_project_memory(session_id, MEDIA_DIR, user_id)
            copy_files = [
                f"/media/{user_id}/{session_id}/release/copy/release_description.txt",
                f"/media/{user_id}/{session_id}/release/copy/press_pitch.txt",
                f"/media/{user_id}/{session_id}/release/copy/tagline.txt"
            ]
            if not memory.project_data.get("release", {}).get("files"):
                await memory.update("release.files", [])
            current_files = memory.project_data.get("release", {}).get("files", [])
            for f in copy_files:
                if f not in current_files:
                    current_files.append(f)
            await memory.update("release.files", current_files)
            
            return {
                "success": True,
                "description_url": copy_files[0],
                "pitch_url": copy_files[1],
                "tagline_url": copy_files[2]
            }
        
        except AuthenticationError as e:
            logger.error(f"OpenAI authentication failed: {e}", exc_info=True)
            log_endpoint_event("/release/copy", session_id, "error", {"error": "OpenAI authentication failed", "type": "authentication"})
            return {
                "success": False,
                "error": "OpenAI API authentication failed. Please check your API key configuration.",
                "status_code": 402
            }
        except RateLimitError as e:
            logger.error(f"OpenAI rate limit exceeded: {e}", exc_info=True)
            log_endpoint_event("/release/copy", session_id, "error", {"error": "OpenAI rate limit exceeded", "type": "rate_limit"})
            return {
                "success": False,
                "error": "OpenAI API rate limit exceeded. Please try again later.",
                "status_code": 429
            }
        except APIError as e:
            logger.error(f"OpenAI API error: {e}", exc_info=True)
            log_endpoint_event("/release/copy", session_id, "error", {"error": f"OpenAI API error: {str(e)}", "type": "api_error"})
            return {
                "success": False,
                "error": f"OpenAI API error: {str(e)}",
                "status_code": 502
            }
        except Exception as e:
            logger.error(f"Release copy generation failed: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    async def generate_lyrics_pdf(
        self,
        session_id: str,
        user_id: str,
        title: Optional[str] = None,
        artist: Optional[str] = None,
        lyrics: Optional[str] = None
    ) -> Dict[str, Any]:
        """Generate lyrics.pdf if lyrics exist"""
        session_path = get_session_media_path(session_id, user_id)
        lyrics_dir = session_path / "release" / "lyrics"
        lyrics_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            lyrics_text = lyrics or ""
            
            # Check if lyrics exist in project
            if not lyrics_text:
                memory = await get_or_create_project_memory(session_id, MEDIA_DIR, user_id)
                lyrics_file = session_path / "lyrics.txt"
                if lyrics_file.exists():
                    with open(lyrics_file, 'r', encoding='utf-8') as f:
                        lyrics_text = f.read()
            
            if not lyrics_text or not lyrics_text.strip():
                return {
                    "success": True,
                    "skipped": True,
                    "message": "No lyrics found"
                }
            
            # Generate PDF using reportlab
            from reportlab.lib.pagesizes import letter
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import inch
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
            
            pdf_path = lyrics_dir / "lyrics.pdf"
            doc = SimpleDocTemplate(str(pdf_path), pagesize=letter)
            
            # Build content
            story = []
            styles = getSampleStyleSheet()
            
            # Title style
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Heading1'],
                fontSize=24,
                textColor='black',
                spaceAfter=30,
                alignment=1  # Center
            )
            
            # Normal style
            normal_style = ParagraphStyle(
                'CustomNormal',
                parent=styles['Normal'],
                fontSize=12,
                textColor='black',
                leading=18
            )
            
            # Title page
            title_text = title or "Untitled"
            artist_text = artist or "Unknown Artist"
            story.append(Paragraph(f"{artist_text}", title_style))
            story.append(Paragraph(f"{title_text}", title_style))
            story.append(PageBreak())
            
            # Lyrics content
            lines = lyrics_text.split('\n')
            for line in lines:
                if line.strip():
                    story.append(Paragraph(line.strip(), normal_style))
                else:
                    story.append(Spacer(1, 0.2*inch))
            
            doc.build(story)
            
            # Update project memory
            pdf_url = f"/media/{user_id}/{session_id}/release/lyrics/lyrics.pdf"
            memory = await get_or_create_project_memory(session_id, MEDIA_DIR, user_id)
            if not memory.project_data.get("release", {}).get("files"):
                await memory.update("release.files", [])
            current_files = memory.project_data.get("release", {}).get("files", [])
            if pdf_url not in current_files:
                current_files.append(pdf_url)
            await memory.update("release.files", current_files)
            
            return {
                "success": True,
                "pdf_url": pdf_url
            }
        
        except Exception as e:
            logger.error(f"Lyrics PDF generation failed: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    async def generate_metadata(
        self,
        session_id: str,
        user_id: str,
        user_plan: str,
        track_title: str,
        artist_name: str,
        genre: str,
        mood: str,
        explicit: bool,
        release_date: str,
        user_repo: Optional[UserRepository] = None
    ) -> Dict[str, Any]:
        """Generate metadata.json with track info"""
        session_path = get_session_media_path(session_id, user_id)
        metadata_dir = session_path / "release" / "metadata"
        metadata_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            # PHASE 8.4: Free tier limit enforcement - 1 release per 24 hours
            if user_plan == "free" and user_repo:
                try:
                    # Convert user_id string to integer
                    user_id_int = int(user_id)
                    user = await user_repo.get_user_by_id(user_id_int)
                    
                    if user and user.last_release_timestamp:
                        last_release_dt = datetime.fromisoformat(user.last_release_timestamp)
                        time_since_last_release = datetime.now() - last_release_dt
                        hours_since_last = time_since_last_release.total_seconds() / 3600
                        
                        if hours_since_last < 24:
                            log_endpoint_event("/release/metadata", session_id, "upgrade_required", {
                                "user_id": user_id,
                                "limit": "daily_release_limit",
                                "hours_since_last": hours_since_last
                            })
                            return {
                                "success": False,
                                "error": "upgrade_required",
                                "status_code": 403
                            }
                except (ValueError, TypeError) as e:
                    logger.warning(f"Invalid user_id format: {user_id}, error: {e}")
                except Exception as e:
                    logger.error(f"Error checking release limit: {e}", exc_info=True)
            
            # Get audio duration from mixed/master file
            duration_seconds = 0
            bpm = None
            key = None
            
            # Try to find audio file
            for filename in ["mix/mixed_mastered.wav", "mix.wav", "master.wav"]:
                audio_file = session_path / filename
                if audio_file.exists():
                    try:
                        audio = AudioSegment.from_file(str(audio_file))
                        duration_seconds = len(audio) / 1000.0
                        break
                    except:
                        pass
            
            # Get BPM and key from project memory
            memory = await get_or_create_project_memory(session_id, MEDIA_DIR, user_id)
            bpm = memory.project_data.get("metadata", {}).get("tempo")
            key = memory.project_data.get("metadata", {}).get("key")
            
            metadata = {
                "title": track_title,
                "artist": artist_name,
                "genre": genre,
                "mood": mood,
                "explicit": explicit,
                "release_date": release_date,
                "duration_seconds": round(duration_seconds, 2),
                "bpm": bpm,
                "key": key
            }
            
            metadata_file = metadata_dir / "metadata.json"
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2)
            
            # Update project memory with full release info
            metadata_url = f"/media/{user_id}/{session_id}/release/metadata/metadata.json"
            await memory.update("release.title", track_title)
            await memory.update("release.artist", artist_name)
            await memory.update("release.genre", genre)
            await memory.update("release.mood", mood)
            await memory.update("release.explicit", explicit)
            await memory.update("release.release_date", release_date)
            await memory.update("release.metadata_path", metadata_url)
            if not memory.project_data.get("release", {}).get("files"):
                await memory.update("release.files", [])
            current_files = memory.project_data.get("release", {}).get("files", [])
            if metadata_url not in current_files:
                current_files.append(metadata_url)
            await memory.update("release.files", current_files)
            
            # PHASE 8.4: Update last release timestamp for free tier tracking
            if user_plan == "free" and user_repo:
                try:
                    # Convert user_id string to integer
                    user_id_int = int(user_id)
                    user = await user_repo.get_user_by_id(user_id_int)
                    
                    if user:
                        await user_repo.update_user(user, {
                            "last_release_timestamp": datetime.now().isoformat()
                        })
                        # Commit the transaction
                        await user_repo.db.commit()
                except (ValueError, TypeError) as e:
                    logger.warning(f"Invalid user_id format: {user_id}, error: {e}")
                except Exception as e:
                    logger.error(f"Error updating release timestamp: {e}", exc_info=True)
                    # Rollback on error
                    await user_repo.db.rollback()
            
            return {
                "success": True,
                "metadata_url": metadata_url
            }
        
        except Exception as e:
            logger.error(f"Metadata generation failed: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    def build_release_pack(
        self,
        session_id: str,
        title: str,
        artist: str,
        mixed_file_path: Path,
        cover_prompt: Optional[str] = None,
        release_date: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> Dict:
        """
        Build complete release pack with standardized structure.
        This method uses the existing ReleaseService from backend.release.release_service
        """
        from backend.release.release_service import ReleaseService as BackendReleaseService
        
        backend_service = BackendReleaseService()
        return backend_service.build_release_pack(
            session_id=session_id,
            title=title,
            artist=artist,
            mixed_file_path=mixed_file_path,
            cover_prompt=cover_prompt,
            release_date=release_date,
            user_id=user_id
        )
    
    async def list_release_files(
        self,
        session_id: str,
        user_id: str
    ) -> Dict[str, Any]:
        """List all release files dynamically"""
        session_path = get_session_media_path(session_id, user_id)
        release_dir = session_path / "release"
        
        try:
            files = []
            
            # Audio files
            audio_dir = release_dir / "audio"
            if audio_dir.exists():
                audio_file = audio_dir / "mixed_mastered.wav"
                if audio_file.exists():
                    files.append(f"/media/{user_id}/{session_id}/release/audio/mixed_mastered.wav")
            
            # Cover art (final_cover_3000.jpg, final_cover_1500.jpg, final_cover_vertical.jpg)
            cover_dir = release_dir / "cover"
            if cover_dir.exists():
                # Scan for final cover files
                for file in cover_dir.glob("final_cover*.jpg"):
                    files.append(f"/media/{user_id}/{session_id}/release/cover/{file.name}")
            
            # Metadata
            metadata_dir = release_dir / "metadata"
            if metadata_dir.exists():
                metadata_file = metadata_dir / "metadata.json"
                if metadata_file.exists():
                    files.append(f"/media/{user_id}/{session_id}/release/metadata/metadata.json")
            
            # Copy files
            copy_dir = release_dir / "copy"
            if copy_dir.exists():
                for copy_file in copy_dir.glob("*.txt"):
                    files.append(f"/media/{user_id}/{session_id}/release/copy/{copy_file.name}")
            
            # Lyrics PDF
            lyrics_dir = release_dir / "lyrics"
            if lyrics_dir.exists():
                lyrics_file = lyrics_dir / "lyrics.pdf"
                if lyrics_file.exists():
                    files.append(f"/media/{user_id}/{session_id}/release/lyrics/lyrics.pdf")
            
            return {
                "success": True,
                "files": files
            }
        
        except Exception as e:
            logger.error(f"Failed to list release files: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    async def get_release_pack(
        self,
        session_id: str,
        user_id: str
    ) -> Dict[str, Any]:
        """Get complete release pack data: cover art, metadata, lyrics PDF, release copy, and audio"""
        session_path = get_session_media_path(session_id, user_id)
        release_dir = session_path / "release"
        
        try:
            result = {}
            
            # Cover art (prefer final_cover_3000.jpg)
            cover_dir = release_dir / "cover"
            if cover_dir.exists():
                final_cover = cover_dir / "final_cover_3000.jpg"
                if final_cover.exists():
                    result["coverArt"] = f"/media/{user_id}/{session_id}/release/cover/final_cover_3000.jpg"
                else:
                    # Fallback to any cover file
                    covers = list(cover_dir.glob("cover_*.jpg"))
                    if covers:
                        result["coverArt"] = f"/media/{user_id}/{session_id}/release/cover/{covers[0].name}"
            
            # Metadata
            metadata_dir = release_dir / "metadata"
            if metadata_dir.exists():
                metadata_file = metadata_dir / "metadata.json"
                if metadata_file.exists():
                    result["metadataFile"] = f"/media/{user_id}/{session_id}/release/metadata/metadata.json"
            
            # Lyrics PDF
            lyrics_dir = release_dir / "lyrics"
            if lyrics_dir.exists():
                lyrics_file = lyrics_dir / "lyrics.pdf"
                if lyrics_file.exists():
                    result["lyricsPdf"] = f"/media/{user_id}/{session_id}/release/lyrics/lyrics.pdf"
            
            # Release copy files
            copy_dir = release_dir / "copy"
            release_copy = {}
            if copy_dir.exists():
                desc_file = copy_dir / "release_description.txt"
                pitch_file = copy_dir / "press_pitch.txt"
                tagline_file = copy_dir / "tagline.txt"
                
                if desc_file.exists():
                    release_copy["description"] = f"/media/{user_id}/{session_id}/release/copy/release_description.txt"
                if pitch_file.exists():
                    release_copy["pitch"] = f"/media/{user_id}/{session_id}/release/copy/press_pitch.txt"
                if tagline_file.exists():
                    release_copy["tagline"] = f"/media/{user_id}/{session_id}/release/copy/tagline.txt"
            
            if release_copy:
                result["releaseCopy"] = release_copy
            
            # Release audio (from mix stage or release/audio)
            audio_dir = release_dir / "audio"
            if audio_dir.exists():
                audio_file = audio_dir / "mixed_mastered.wav"
                if audio_file.exists():
                    result["releaseAudio"] = f"/media/{user_id}/{session_id}/release/audio/mixed_mastered.wav"
            else:
                # Fallback to mix directory
                mix_audio = session_path / "mix" / "mixed_mastered.wav"
                if mix_audio.exists():
                    result["releaseAudio"] = f"/media/{user_id}/{session_id}/mix/mixed_mastered.wav"
            
            return {
                "success": True,
                "data": result
            }
        
        except Exception as e:
            logger.error(f"Failed to get release pack: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    async def download_all_release_files(
        self,
        session_id: str,
        user_id: str
    ) -> Dict[str, Any]:
        """Generate ZIP of all release files (desktop only)"""
        session_path = get_session_media_path(session_id, user_id)
        release_dir = session_path / "release"
        release_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            # Ensure audio files are in release/audio directory
            audio_dir = release_dir / "audio"
            audio_dir.mkdir(parents=True, exist_ok=True)
            
            # Copy mixed/master files to audio directory if they exist
            # Check multiple possible locations with proper path validation
            audio_found = False
            for source_file in ["mix/mixed_mastered.wav", "mix.wav", "master.wav", "release/audio/mixed_mastered.wav"]:
                source_path = session_path / source_file if not source_file.startswith("release/") else release_dir / source_file.replace("release/", "")
                
                # Validate path exists and is a file before attempting to copy
                if source_path.exists() and source_path.is_file():
                    try:
                        # Copy WAV
                        dest_wav = audio_dir / "mixed_mastered.wav"
                        shutil.copy2(source_path, dest_wav)
                        
                        # Export MP3
                        try:
                            audio = AudioSegment.from_file(str(source_path))
                            dest_mp3 = audio_dir / "mixed_mastered.mp3"
                            audio.export(str(dest_mp3), format="mp3", bitrate="320k")
                        except Exception as mp3_error:
                            logger.warning(f"Failed to export MP3: {mp3_error}")
                        
                        audio_found = True
                        break
                    except Exception as copy_error:
                        logger.warning(f"Failed to copy audio file from {source_path}: {copy_error}")
                        continue
            
            if not audio_found:
                logger.warning(f"No audio file found for session {session_id}, continuing with other files")
            
            zip_file = release_dir / "release_pack.zip"
            
            with zipfile.ZipFile(zip_file, 'w', zipfile.ZIP_DEFLATED) as zf:
                # Audio files - only add if they exist
                if audio_dir.exists():
                    for file in audio_dir.glob("*"):
                        if file.is_file() and file.exists():
                            try:
                                zf.write(file, f"audio/{file.name}")
                            except Exception as e:
                                logger.warning(f"Failed to add audio file {file.name} to ZIP: {e}")
                
                # Cover art - use final_cover_*.jpg files (created by select_cover_art)
                cover_dir = release_dir / "cover"
                if cover_dir.exists():
                    # Look for final cover files first (preferred)
                    final_cover_3000 = cover_dir / "final_cover_3000.jpg"
                    final_cover_1500 = cover_dir / "final_cover_1500.jpg"
                    final_cover_vertical = cover_dir / "final_cover_vertical.jpg"
                    
                    # If final covers exist, use them
                    if final_cover_3000.exists() and final_cover_1500.exists() and final_cover_vertical.exists():
                        try:
                            zf.write(final_cover_3000, "cover/cover_3000.jpg")
                            zf.write(final_cover_1500, "cover/cover_1500.jpg")
                            zf.write(final_cover_vertical, "cover/cover_vertical.jpg")
                        except Exception as e:
                            logger.warning(f"Failed to add final cover art to ZIP: {e}")
                    else:
                        # Fallback: try to find any cover and generate variants
                        # Look for cover_*.jpg files (from generate_cover_art)
                        covers = list(cover_dir.glob("cover_*.jpg"))
                        if covers:
                            # Find the base cover (not _1500 or _vertical variant)
                            base_covers = [c for c in covers if not c.name.endswith("_1500.jpg") and not c.name.endswith("_vertical.jpg")]
                            if base_covers:
                                selected_cover = base_covers[0]
                                try:
                                    # Generate and save variants if they don't exist
                                    cover_3000 = cover_dir / "cover_3000.jpg"
                                    cover_1500 = cover_dir / "cover_1500.jpg"
                                    cover_vertical = cover_dir / "cover_vertical.jpg"
                                    
                                    if not cover_3000.exists():
                                        shutil.copy2(selected_cover, cover_3000)
                                    
                                    if not cover_1500.exists() and cover_3000.exists():
                                        img = Image.open(cover_3000)
                                        img_1500 = img.resize((1500, 1500), Image.Resampling.LANCZOS)
                                        img_1500.save(cover_1500, "JPEG", quality=95)
                                    
                                    if not cover_vertical.exists() and cover_3000.exists():
                                        img = Image.open(cover_3000)
                                        img_vertical = img.resize((1080, 1920), Image.Resampling.LANCZOS)
                                        img_vertical.save(cover_vertical, "JPEG", quality=95)
                                    
                                    # Add to ZIP if they exist
                                    if cover_3000.exists():
                                        zf.write(cover_3000, "cover/cover_3000.jpg")
                                    if cover_1500.exists():
                                        zf.write(cover_1500, "cover/cover_1500.jpg")
                                    if cover_vertical.exists():
                                        zf.write(cover_vertical, "cover/cover_vertical.jpg")
                                except Exception as e:
                                    logger.warning(f"Failed to process cover art: {e}")
                
                # Lyrics - only add if directory and files exist
                lyrics_dir = release_dir / "lyrics"
                if lyrics_dir.exists() and lyrics_dir.is_dir():
                    for file in lyrics_dir.glob("*.pdf"):
                        if file.is_file() and file.exists():
                            try:
                                zf.write(file, f"lyrics/{file.name}")
                            except Exception as e:
                                logger.warning(f"Failed to add lyrics file {file.name} to ZIP: {e}")
                
                # Metadata - only add if directory and files exist
                metadata_dir = release_dir / "metadata"
                if metadata_dir.exists() and metadata_dir.is_dir():
                    for file in metadata_dir.glob("*.json"):
                        if file.is_file() and file.exists():
                            try:
                                zf.write(file, f"metadata/{file.name}")
                            except Exception as e:
                                logger.warning(f"Failed to add metadata file {file.name} to ZIP: {e}")
                
                # Copy files - only add if directory and files exist
                copy_dir = release_dir / "copy"
                if copy_dir.exists() and copy_dir.is_dir():
                    for file in copy_dir.glob("*.txt"):
                        if file.is_file() and file.exists():
                            try:
                                zf.write(file, f"copy/{file.name}")
                            except Exception as e:
                                logger.warning(f"Failed to add copy file {file.name} to ZIP: {e}")
            
            # Verify ZIP was created successfully
            if not zip_file.exists():
                logger.error(f"ZIP file was not created at {zip_file}")
                return {"success": False, "error": "Failed to create ZIP file"}
            
            zip_url = f"/media/{user_id}/{session_id}/release/release_pack.zip"
            
            return {
                "success": True,
                "zip_url": zip_url
            }
        
        except Exception as e:
            logger.error(f"ZIP generation failed: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    async def get_release_status(self, job_id: str) -> Dict[str, Any]:
        """Get the status of a release job"""
        # This is a stub implementation - would need actual job tracking
        job = None  # Would be retrieved from job storage
        
        if job is None:
            return {
                "success": False,
                "error": f"Release job {job_id} not found"
            }
        
        return {
            "success": True,
            "data": {
                "job_id": job_id,
                "status": job.get("status"),
                "progress": job.get("progress", 0),
                "assets": job.get("assets"),
                "cover_art": job.get("cover_art"),
                "package_path": job.get("package_path"),
                "message": job.get("message")
            }
        }

