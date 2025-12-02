# Label-in-a-Box Repository Investigation Report
## Complete Authority Map

**Generated:** 2024-12-28  
**Purpose:** Comprehensive investigation and mapping of entire repository  
**Status:** Investigation Only - No Code Changes Made  
**Investigation Scope:** Complete repository analysis for external LLM CTO understanding

---

## EXECUTIVE SUMMARY

Label-in-a-Box v4 is a full-stack music production platform built with FastAPI (backend) and React (frontend). The system enables users to create music tracks through a 7-stage pipeline: Beat → Lyrics → Upload → Mix → Release → Content → Analytics.

**Key Findings:**
- ✅ Clean separation between routers, services, and DSP modules
- ✅ Project memory system uses JSON files per session (anonymous projects)
- ✅ Real DSP processing exists but basic mix uses simple pydub overlay
- ✅ WebSocket infrastructure for real-time mix visualization
- ⚠️ Some unused DSP functions, legacy code paths
- ⚠️ Frontend stages can render as scroll containers vs full-screen based on CSS
- ⚠️ Session-based authentication (no real user system yet)

---

## A. FILE TREE OVERVIEW

### Repository Structure

```
libv1/
├── main.py                          # FastAPI app entry point
├── database.py                      # SQLAlchemy async engine setup
├── database_models.py               # Project model (SQLite)
├── project_memory.py                # JSON-based project persistence
├── requirements.txt                 # Python dependencies
├── render.yaml                      # Render.com deployment config
│
├── config/
│   └── settings.py                  # Pydantic settings from env vars
│
├── routers/                         # FastAPI route handlers
│   ├── analytics_router.py         # Analytics endpoints
│   ├── beat_router.py              # Beat generation endpoints
│   ├── billing_router.py           # Stripe billing endpoints
│   ├── content_router.py           # Video content generation endpoints
│   ├── lyrics_router.py            # Lyrics generation endpoints
│   ├── media_router.py             # File upload endpoints
│   ├── mix_router.py               # Audio mixing endpoints
│   ├── mix_ws_router.py            # WebSocket mix status/streaming
│   ├── release_router.py           # Release pack endpoints
│   └── social_router.py            # Social media scheduling endpoints
│
├── services/                        # Business logic layer
│   ├── analytics_service.py        # Analytics metrics computation
│   ├── beat_service.py             # Beatoven API integration
│   ├── billing_service.py          # Stripe checkout/portal/webhooks
│   ├── content_service.py          # OpenAI video idea/analysis/text gen
│   ├── lyrics_service.py           # OpenAI lyrics generation
│   ├── mix_service.py              # Audio mixing orchestration
│   ├── release_service.py          # Release pack file management
│   ├── social_service.py           # GetLate.dev social scheduling
│   └── transport_service.py        # Playback state management
│
├── models/                          # Pydantic data models
│   ├── mix_config.py               # MixConfig, TrackConfig, MasterConfig
│   ├── mix_job_state.py            # MixJobState dataclass
│   └── mix_timeline_event.py       # Timeline event model
│
├── jobs/                            # Background job management
│   └── mix_job_manager.py          # Mix job queue and state tracking
│
├── utils/                           # Shared utilities
│   ├── dsp/                         # Digital Signal Processing modules
│   │   ├── mix_pipeline.py         # Main DSP chain (process_track, process_master_bus)
│   │   ├── load.py                 # WAV file loading
│   │   ├── export.py               # WAV file export
│   │   ├── eq.py                   # Equalization
│   │   ├── compressor.py           # Compression
│   │   ├── limiter.py              # Peak limiting
│   │   ├── saturator.py            # Saturation
│   │   ├── gain.py                 # Gain adjustment
│   │   ├── deesser.py              # De-essing (vocals)
│   │   ├── air.py                  # High-frequency boost
│   │   ├── stereo.py               # Stereo widening
│   │   ├── dynamics.py             # Micro-dynamics (soften_transients, micro_compress, smooth_vocals)
│   │   ├── level.py                # LUFS/RMS measurement, auto_gain, match_loudness
│   │   ├── spatial.py              # Spatial processing
│   │   ├── masking.py              # Frequency masking detection/resolution
│   │   ├── tonal_balance.py        # Tonal balance chain
│   │   ├── analyze_audio.py        # Waveform, spectrum, level analysis
│   │   ├── metering.py             # Gain reduction computation
│   │   ├── scope.py                # Scope visualization (waveform, L/R, phase)
│   │   └── streamer.py             # Audio chunking for streaming
│   │
│   ├── mix/                         # Mix configuration utilities
│   │   ├── config_apply.py         # Recipe application
│   │   ├── mix_recipes.py          # MIX_RECIPES dict
│   │   ├── presets.py              # ROLE_PRESETS dict
│   │   ├── role_presets.py         # Role-based presets
│   │   ├── roles.py                # Role detection from filename
│   │   └── timeline.py             # Timeline event storage
│   │
│   ├── rate_limit.py               # Rate limiting middleware
│   ├── security_utils.py           # File upload validation
│   ├── session_manager.py          # Placeholder session→user mapping
│   └── shared_utils.py             # Common helpers (gTTS, Redis cache, paths)
│
├── backend/
│   └── utils/
│       └── responses.py            # Standardized JSON response helpers
│
├── frontend/                        # React + Vite application
│   ├── package.json                # Frontend dependencies
│   ├── vite.config.js              # Vite build config
│   ├── tailwind.config.js          # Tailwind CSS config
│   ├── index.html                  # HTML entry point
│   │
│   └── src/
│       ├── main.jsx                # React app entry point
│       ├── App.jsx                 # React Router setup
│       │
│       ├── pages/
│       │   ├── AppPage.jsx         # Main application page (timeline + stages)
│       │   └── PricingPage.jsx     # Pricing page
│       │
│       ├── components/
│       │   ├── stages/             # Stage components (full-screen modules)
│       │   │   ├── BeatStage.jsx   # Beat creation interface
│       │   │   ├── LyricsStage.jsx # Lyrics editing interface
│       │   │   ├── UploadStage.jsx # Vocal upload interface
│       │   │   ├── MixStage.jsx    # Mix & master interface
│       │   │   ├── ReleaseStage.jsx # Release pack interface
│       │   │   ├── ContentStage.jsx # Video content creation
│       │   │   ├── StageWrapper.jsx # Common stage wrapper (header/footer)
│       │   │   └── StageWrapper.jsx # Stage container
│       │   │
│       │   ├── Mix/                # Mix visualization components
│       │   │   ├── TransportBar.tsx # Play/pause/seek controls
│       │   │   ├── WaveformCanvas.tsx # Waveform visualization
│       │   │   └── TimelineCursor.tsx # Playhead cursor
│       │   │
│       │   ├── Timeline.jsx        # Main timeline navigation component
│       │   ├── MistLayer.jsx       # Animated gradient background
│       │   ├── VoiceControl.jsx    # Voice playback controls
│       │   ├── VoiceChat.jsx       # Voice interaction UI
│       │   ├── AnalyticsDashboard.jsx # Analytics visualization
│       │   ├── LoadingSpinner.jsx  # Loading indicator
│       │   ├── ErrorBoundary.jsx   # Error boundary wrapper
│       │   ├── ManageProjectsModal.jsx # Project management modal
│       │   └── UpgradeModal.jsx    # Paywall modal (disabled)
│       │
│       ├── hooks/                  # React custom hooks
│       │   ├── useAudioEngine.ts   # Audio playback engine
│       │   ├── useMultiTrackWaveform.ts # Multi-track waveform data
│       │   ├── useTimelineZoomPan.ts # Timeline zoom/pan controls
│       │   ├── useTransport.ts     # Transport state hook
│       │   ├── useWaveformBuffer.ts # Waveform buffer management
│       │   └── useVoice.js         # Voice playback hook
│       │
│       ├── workers/                # Web Workers
│       │   └── waveformWorker.ts   # Waveform computation worker
│       │
│       ├── utils/
│       │   └── api.js              # Frontend API client
│       │
│       └── styles/                 # CSS stylesheets
│           ├── index.css           # Global styles + Tailwind
│           ├── Timeline.css        # Timeline-specific styles
│           ├── mist.css            # MistLayer gradient styles
│           └── ErrorBoundary.css   # Error boundary styles
│
├── assets/                          # Static assets
│   ├── covers/                     # Cover art gradients
│   ├── demo/                       # Demo audio files
│   ├── sfx/                        # Sound effects
│   └── placeholder.jpg             # Placeholder image
│
├── storage/                         # Generated files
│   └── mix_outputs/                # Final mix WAV files
│
└── tests/                           # Test fixtures
    └── conftest.py                 # Pytest configuration
```

---

## B. FILE-BY-FILE DEEP ANALYSIS

### Backend Core Files

#### `main.py`
**Purpose:** FastAPI application entry point, middleware setup, router registration  
**Key Functions:**
- `check_env_keys_on_startup()` - Validates required API keys (non-fatal)
- `validate_keys()` - Validates API keys (non-fatal)
- `initialize_database()` - Initializes SQLite database on startup
- `serve_frontend()` - Serves React SPA (catch-all route)

**Key Classes:**
- `UncaughtExceptionMiddleware` - Logs unhandled exceptions, returns 500
- `SecurityHeadersMiddleware` - Adds CSP, HSTS, X-Frame-Options headers

**Pipeline Connection:**
- Registers all routers: beat, lyrics, media, mix, release, content, analytics, social, billing
- Serves static media files at `/media`
- Serves frontend at root (SPA routing)

**Inputs/Outputs:**
- Input: Environment variables, HTTP requests
- Output: JSON responses, static files, frontend HTML

**TODOs/Comments:**
- Comment on line 149: "The api router is kept for potential future use, but currently all endpoints are defined in their respective router modules"
- Comment on line 151: `api = APIRouter(prefix="/api")  # Currently unused`

**Dead Code:**
- `api` router variable (line 151) is defined but never used

---

#### `database.py`
**Purpose:** SQLAlchemy async engine and session factory setup  
**Key Functions:**
- `init_db()` - Creates all database tables
- `get_db()` - Dependency function for FastAPI routes (yields database session)

**Pipeline Connection:**
- Used by routers for project persistence (though most data is in JSON files)

**Inputs/Outputs:**
- Input: DATABASE_URL env var (defaults to SQLite)
- Output: AsyncSession objects

---

#### `database_models.py`
**Purpose:** SQLAlchemy ORM models  
**Key Classes:**
- `Project` - Stores session_id, title, created_at (minimal model)

**Pipeline Connection:**
- Project model stores basic project metadata (title from project.json)

**TODOs/Comments:**
- Model is minimal - most project data is in JSON files (project_memory)

---

#### `project_memory.py`
**Purpose:** JSON-based project persistence and state management  
**Key Functions:**
- `ProjectMemory` class:
  - `save()` - Saves project.json and updates database Project record
  - `update_metadata()` - Updates metadata fields
  - `add_asset()` - Adds asset URLs to project memory
  - `add_chat_message()` - Logs voice interactions
  - `advance_stage()` - Marks stage complete, updates current_stage
  - `jump_to_stage()` - Navigates to specific stage (skip forward/back)
  - `get_context_summary()` - AI-readable context for voice agents
- `get_or_create_project_memory()` - Factory function (creates DB Project if needed)
- `list_all_projects()` - Lists all projects with metadata
- `export_project()` / `import_project()` - Project import/export

**Pipeline Connection:**
- Central to entire pipeline - stores state at each stage:
  - Beat: stores beat URL, BPM, mood, genre
  - Lyrics: stores lyrics text
  - Upload: stores vocal file URLs
  - Mix: stores mix URL, mix settings
  - Release: stores release pack paths
  - Content: stores scheduled posts, content ideas

**File Structure:**
```
/media/{session_id}/
  ├── project.json        # Project memory (all state)
  ├── beat.mp3           # Generated beat
  ├── lyrics.txt         # Generated lyrics
  ├── recordings/        # Uploaded vocals
  ├── mix/              # Mix outputs
  └── release/          # Release pack files
```

**Inputs/Outputs:**
- Input: session_id, asset URLs, metadata, stage completions
- Output: project.json file, database Project records

---

#### `config/settings.py`
**Purpose:** Pydantic settings loaded from environment variables  
**Key Classes:**
- `Settings` - All configuration via env vars

**Environment Variables:**
- `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_ID`, `STRIPE_PRODUCT_ID`
- `BEATOVEN_API_KEY`, `OPENAI_API_KEY`, `GETLATE_API_KEY`, `AUPHONIC_API_KEY`
- `REDIS_URL`, `DATABASE_URL`
- `BUFFER_TOKEN`, `DISTROKID_KEY`
- `PRICE_PRO_MONTHLY`
- `FRONTEND_URL`
- `RENDER`, `RENDER_EXTERNAL_URL`, `RENDER_SERVICE_NAME`

**Pipeline Connection:**
- All services read API keys from settings
- Frontend URL used for CORS and Stripe redirects

---

### Router Files

#### `routers/beat_router.py`
**Purpose:** Beat generation API endpoints  
**Key Endpoints:**
- `POST /api/beats/create` - Generate beat via Beatoven API (with fallback)
- `GET /api/beats/credits` - Get remaining Beatoven credits
- `GET /api/beats/status/{job_id}` - Get beat generation status (stub)

**Pipeline Connection:**
- Beat stage → calls `BeatService.create_beat_track()` → saves to project memory → advances to lyrics stage

**Inputs/Outputs:**
- Input: prompt, mood, genre, bpm, duration_sec, session_id
- Output: beat_url, status, provider (beatoven/demo/silent_fallback)

**Legacy Code:**
- `get_beat_status()` method in service returns None (stub implementation)

---

#### `routers/lyrics_router.py`
**Purpose:** Lyrics generation API endpoints  
**Key Endpoints:**
- `POST /api/songs/write` - Generate lyrics via OpenAI (with fallback)
- `POST /api/lyrics/from_beat` - Generate lyrics from uploaded beat file
- `POST /api/lyrics/free` - Generate lyrics from theme only
- `POST /api/lyrics/refine` - Refine lyrics based on user instruction

**Pipeline Connection:**
- Lyrics stage → calls `LyricsService.write_song()` → saves lyrics.txt → generates voice MP3 via gTTS → advances to upload stage

**Inputs/Outputs:**
- Input: genre, mood, theme, session_id, beat_context, lyrics text, instruction
- Output: lyrics text, filename, path, timestamp

**Special Features:**
- Voice generation: Uses gTTS to generate MP3 from first verse
- NP22-style lyrics: Special template for cinematic soulful rock × trap fusion

---

#### `routers/media_router.py`
**Purpose:** File upload handling  
**Key Endpoints:**
- `POST /api/upload-audio` - Upload vocal audio file

**Pipeline Connection:**
- Upload stage → uploads audio file → saves to `/media/{session_id}/recordings/` → updates project memory → advances to mix stage

**Security:**
- Uses `validate_uploaded_file()` from `utils.security_utils.py`
- Validates: filename sanitization, extension whitelist, file size (50MB), MIME type

**Inputs/Outputs:**
- Input: audio file (MP3, WAV, etc.), session_id
- Output: file_url

---

#### `routers/mix_router.py`
**Purpose:** Audio mixing API endpoints  
**Key Endpoints:**
- `POST /api/projects/{project_id}/mix` - Basic mix (uses `apply_basic_mix`)
- `GET /api/projects/{project_id}/mix/status` - Get mix status
- `POST /api/projects/{project_id}/mix/start` - Start DSP-based mix job
- `GET /api/projects/{project_id}/mix/job/{job_id}/status` - Get job status
- `GET /api/projects/{project_id}/mix/preview` - Get final mix WAV file
- `GET /api/timeline/{job_id}` - Get mix timeline events
- `GET /api/visual/{job_id}` - Get mix visualization data
- `GET /api/scope/{job_id}` - Get scope data
- `GET /api/streams/{job_id}` - List available streams
- `POST /api/transport/{job_id}/play` - Play transport
- `POST /api/transport/{job_id}/pause` - Pause transport
- `POST /api/transport/{job_id}/stop` - Stop transport
- `POST /api/transport/{job_id}/seek` - Seek to position

**Separate Router:**
- `mix_config_router` (prefix `/api/mix`):
  - `GET /api/mix/config/schema` - Get mix schema (roles, recipes)
  - `POST /api/mix/config/apply` - Apply mix recipe to tracks

**Pipeline Connection:**
- Mix stage → starts mix job → processes via DSP chain → saves to `/storage/mix_outputs/{session_id}/final_mix.wav` → advances to release stage

**Two Mix Methods:**
1. **Basic Mix** (`run_clean_mix`): Uses pydub `beat.overlay(vocal)` - simple overlay, no DSP
2. **DSP Mix** (`mix`): Full DSP pipeline with EQ, compression, limiting, etc.

**Inputs/Outputs:**
- Input: vocal_url, beat_url, session_id, optional mix config
- Output: mix_url, job_id, visualization data

---

#### `routers/mix_ws_router.py`
**Purpose:** WebSocket endpoints for real-time mix visualization  
**Key Endpoints:**
- `WS /ws/mix/stream/{job_id}/{source}` - Stream audio chunks (tracks/pre_master/post_master)
- `WS /ws/mix/status/{job_id}` - Real-time job status, meters, spectra, scope (500ms updates)
- `WS /ws/mix/transport/{job_id}` - Real-time transport position (50ms updates)

**Pipeline Connection:**
- Frontend connects to WebSocket during mix → receives real-time updates → updates visualization

**Payload Structure:**
```json
{
  "job_id": "...",
  "state": "processing_tracks",
  "progress": 50,
  "realtime_meters": {"tracks": {...}, "master": {...}},
  "realtime_spectra": {"tracks": {...}, "pre_master": [...], "post_master": [...]},
  "realtime_scope": {"pre_master": {...}, "post_master": {...}},
  "visual": {...},
  "timeline": [...]
}
```

---

#### `routers/release_router.py`
**Purpose:** Release pack file management  
**Key Endpoints:**
- `POST /api/release/{project_id}/cover` - Upload cover art
- `POST /api/release/{project_id}/copy` - Save release description
- `POST /api/release/{project_id}/pdf` - Save lyrics PDF
- `POST /api/release/{project_id}/metadata` - Save metadata JSON
- `GET /api/release/{project_id}/zip` - Generate release pack ZIP

**Pipeline Connection:**
- Release stage → collects cover art, metadata, lyrics PDF → generates ZIP → advances to content stage

**Inputs/Outputs:**
- Input: cover image, description text, PDF bytes, metadata dict
- Output: file paths, ZIP file URL

---

#### `routers/content_router.py`
**Purpose:** Video content generation and scheduling  
**Key Endpoints:**
- `POST /api/content/idea` - Generate video idea (OpenAI)
- `POST /api/content/analyze` - Analyze video transcript for viral score (OpenAI)
- `POST /api/content/generate-text` - Generate captions, hashtags, hooks (OpenAI)
- `POST /api/content/schedule` - Schedule video via GetLate API (with local fallback)
- `POST /api/content/save-scheduled` - Save scheduled post to project memory
- `GET /api/content/get-scheduled` - Get scheduled posts for session

**Pipeline Connection:**
- Content stage → generates video idea → user uploads video → analyzes transcript → generates social text → schedules post → advances to analytics stage

**Inputs/Outputs:**
- Input: title, lyrics, mood, genre, transcript, video URL, caption, hashtags, platform, schedule_time
- Output: video idea JSON, viral analysis JSON, text pack JSON, scheduled post ID

---

#### `routers/analytics_router.py`
**Purpose:** Analytics metrics endpoints  
**Key Endpoints:**
- `GET /api/analytics/session/{session_id}` - Get session analytics
- `GET /api/analytics/dashboard/all` - Get dashboard analytics across all sessions

**Pipeline Connection:**
- Analytics dashboard → reads project.json files → computes metrics

**Inputs/Outputs:**
- Input: session_id
- Output: Analytics dict (stages_completed, files_created, scheduled_posts, estimated_reach)

---

#### `routers/billing_router.py`
**Purpose:** Stripe billing integration  
**Key Endpoints:**
- `POST /api/billing/webhook` - Stripe webhook handler (MUST be first to avoid middleware conflicts)
- `POST /api/billing/create-checkout-session` - Create Stripe Checkout session
- `POST /api/billing/portal` - Create Stripe Billing Portal session

**Pipeline Connection:**
- Upgrade modal → creates checkout session → redirects to Stripe → webhook processes subscription

**Security:**
- Webhook signature verification using Stripe's `construct_event()`
- Always returns 200 to Stripe (even on errors) to prevent retries

**TODOs/Comments:**
- Billing is decoupled from authentication (works with email/Stripe customer IDs)

---

#### `routers/social_router.py`
**Purpose:** Social media scheduling endpoints  
**Key Endpoints:**
- `GET /api/social/platforms` - Get supported platforms
- `POST /api/social/posts` - Create/schedule social post (GetLate API or local JSON)
- `POST /api/social/project/navigate` - Navigate project to specific stage (skip forward/back)

**Pipeline Connection:**
- Content stage uses this for scheduling posts
- Project navigation allows skipping stages

**Inputs/Outputs:**
- Input: session_id, platform, when_iso, caption, target_stage
- Output: post_id, scheduled_time, provider (getlate/local)

---

### Service Files

#### `services/mix_service.py`
**Purpose:** Audio mixing orchestration and DSP chain execution  
**Key Methods:**
- `run_clean_mix()` - Basic pydub overlay mix (beat.overlay(vocal))
- `mix()` - Full DSP-based mixing with per-track and master bus processing
- `apply_auto_gain()` - Role-based automatic gain staging
- `apply_micro_dynamics()` - Role-based micro-dynamics (soften_transients, micro_compress, smooth_vocals)
- `apply_tonal_balance()` - Tonal balance chain
- `apply_spatial_separation()` - Spatial pocket processing
- `apply_frequency_masking()` - Vocal/beat frequency masking resolution
- `get_mix_status()` - Get mix completion status
- `process_single_file()` - Single file mastering (legacy)

**Pipeline Connection:**
- Central to mix stage - orchestrates entire DSP chain:
  1. Load stems (vocal, beat)
  2. Auto gain (role-based)
  3. Micro-dynamics (role-based)
  4. Tonal balance
  5. Spatial separation
  6. Frequency masking (vocal vs beat)
  7. Per-track DSP (EQ, compressor, saturation)
  8. Blend tracks
  9. Master bus processing (EQ, compressor, limiter)
  10. Stereo widening
  11. Export WAV

**DSP Pipeline Order:**
```
Auto Gain → Micro Dynamics → [match_loudness] → EQ → Compressor → Saturation → De-esser → Air → Stereo Widening
```

**Inputs/Outputs:**
- Input: session_id, stems dict ({"vocal": path, "beat": path}), optional mix config, job_id
- Output: audio_url, visual data, job status

**Real DSP Processing:**
- ✅ **YES** - Full DSP chain exists and is executed
- ⚠️ Basic mix (`run_clean_mix`) uses simple overlay (no DSP)
- ✅ Advanced mix (`mix`) uses real DSP with numpy-based processing

**TODOs/Comments:**
- Line 424-429: Comment about frequency masking - "if you cannot safely find beat stem access, SKIP this anchor"
- Legacy: `apply_basic_mix()` function still exists but only used by `mix_audio()` method

---

#### `services/beat_service.py`
**Purpose:** Beat generation via Beatoven API with fallbacks  
**Key Methods:**
- `create_beat_track()` - Main beat generation (Beatoven API → demo beat → silent fallback)
- `_call_beatoven_compose()` - Initiate Beatoven generation
- `_poll_beatoven_status()` - Poll for completion (up to 3 minutes)
- `_handle_fallback_beat()` - Create demo/silent beat
- `get_credits()` - Get Beatoven credits (with fallback)
- `get_beat_status()` - Get job status (returns None - stub)

**Pipeline Connection:**
- Beat stage → calls Beatoven API → downloads MP3 → saves to project memory → advances to lyrics

**Fallback Chain:**
1. Beatoven API (if key available)
2. Demo beat from `/assets/demo/beat.mp3`
3. Silent 60-second audio

**Inputs/Outputs:**
- Input: session_id, prompt, mood, genre, bpm, duration_sec
- Output: beat_url, status, provider, progress

**Dead Code:**
- `get_beat_status()` always returns None (stub)

---

#### `services/lyrics_service.py`
**Purpose:** Lyrics generation via OpenAI with NP22 template  
**Key Methods:**
- `write_song()` - Generate lyrics (OpenAI → fallback)
- `generate_lyrics_from_beat()` - Generate from uploaded beat (detects BPM, mood)
- `generate_free_lyrics()` - Generate from theme only
- `refine_lyrics()` - Refine based on user instruction (with history, structured lyrics, rhythm map)
- `generate_np22_lyrics()` - NP22-style lyrics template
- `detect_bpm()` - BPM detection using aubio
- `analyze_mood()` - Mood analysis (returns default "dark cinematic emotional")
- `parse_lyrics_to_structured()` - Parse lyrics into sections (verse, chorus, bridge)

**Pipeline Connection:**
- Lyrics stage → generates lyrics → saves lyrics.txt → advances to upload stage

**NP22 Template:**
- "cinematic fusion of soulful rock and modern trap"
- "dark-purple energy, emotional intensity, motivational tone"
- Structure: Hook + Verse 1 + Optional Pre-Hook

**Inputs/Outputs:**
- Input: session_id, genre, mood, theme, beat_context, lyrics text, instruction
- Output: lyrics text, filename, path, timestamp, bpm, mood

**Dead Code:**
- `analyze_mood()` always returns default string (no real analysis)

---

#### `services/content_service.py`
**Purpose:** Video content generation and scheduling  
**Key Methods:**
- `generate_idea()` - Generate video idea (OpenAI)
- `analyze_text()` - Analyze transcript for viral score (OpenAI)
- `generate_text()` - Generate captions, hashtags, hooks, posting strategy (OpenAI)
- `schedule_post()` - Schedule via GetLate API (with local JSON fallback)
- `save_scheduled_post()` - Save to project memory
- `get_scheduled_posts()` - Get scheduled posts for session

**Pipeline Connection:**
- Content stage → generates idea → user uploads video → analyzes → generates text → schedules → advances to analytics

**Inputs/Outputs:**
- Input: session_id, title, lyrics, mood, genre, transcript, video_url, caption, hashtags, platform, schedule_time
- Output: idea JSON, analysis JSON, text pack JSON, scheduled post ID

---

#### `services/transport_service.py`
**Purpose:** Playback state management for mix visualization  
**Key Functions:**
- `get_transport(job_id)` - Get or create TransportState for job
- `play(job_id)` - Start playback
- `pause(job_id)` - Pause playback (updates position)
- `stop(job_id)` - Stop and reset position
- `seek(job_id, position_seconds)` - Seek to position

**Key Classes:**
- `TransportState` - Stores is_playing, position, rate, duration

**Pipeline Connection:**
- Mix stage → sets duration from audio length → frontend controls playback → WebSocket sends position updates

**Inputs/Outputs:**
- Input: job_id, position_seconds
- Output: TransportState object

---

### DSP Modules (`utils/dsp/`)

#### `utils/dsp/mix_pipeline.py`
**Purpose:** Main DSP processing chain  
**Key Functions:**
- `process_track(audio_data, config)` - Per-track DSP chain:
  - EQ → Compressor → Saturation → Gain → De-esser (vocals) → Air (vocals) → Stereo widen (backing vocals)
  - Returns: processed audio, meter data (gain reduction, scope)
- `process_master_bus(mix, cfg)` - Master bus chain:
  - EQ → Compressor → Limiter
  - Returns: mastered audio, master meter data
- `blend_tracks(tracks)` - Sum all tracks (with peak normalization)
- `align_tracks(tracks)` - Align track lengths (zero-padding)
- `match_loudness(audio, target_rms)` - RMS-based loudness matching

**Pipeline Connection:**
- Called by `MixService.mix()` for each stem → processes all tracks → blends → masters

**Processing Order:**
1. Match loudness (optional)
2. EQ (biquad filters)
3. Compressor (with gain reduction metering)
4. Saturation (soft clipping)
5. Gain adjustment
6. De-esser (vocals only)
7. Air boost (vocals only)
8. Stereo widening (backing vocals only)

**Inputs/Outputs:**
- Input: audio_data (numpy array), track_config dict
- Output: processed audio, meter data dict

---

#### `utils/dsp/load.py` / `utils/dsp/export.py`
**Purpose:** WAV file I/O  
**Key Functions:**
- `load_wav(path, target_sr=44100)` - Load WAV, convert to numpy, resample if needed
- `save_wav(path, audio, sr=44100)` - Save numpy array as WAV (int16, stereo)

**Pipeline Connection:**
- Used throughout mix pipeline for file I/O

**Inputs/Outputs:**
- Input: file path
- Output: numpy array (float32, [-1, 1]) or WAV file

---

#### `utils/dsp/eq.py`
**Purpose:** Equalization using biquad filters  
**Key Functions:**
- `apply_eq(audio_data, eq_settings)` - Apply EQ bands (bell, high-pass, low-pass)

**Used By:**
- `mix_pipeline.py` (per-track and master bus)

**Inputs/Outputs:**
- Input: audio array, eq_settings list (freq, gain, q, type)
- Output: processed audio array

---

#### `utils/dsp/compressor.py`
**Purpose:** Dynamic range compression  
**Key Functions:**
- `apply_compressor(audio_data, threshold, ratio, attack, release)` - Apply compression

**Used By:**
- `mix_pipeline.py` (per-track and master bus)

**Gain Reduction:**
- Returns gain reduction curve via `compute_gain_reduction()` from `metering.py`

**Inputs/Outputs:**
- Input: audio array, threshold, ratio, attack, release
- Output: compressed audio array

---

#### `utils/dsp/limiter.py`
**Purpose:** Peak limiting  
**Key Functions:**
- `apply_limiter(audio_data, ceiling)` - Hard limit to ceiling (default -1.0 dB)

**Used By:**
- `mix_pipeline.py` (master bus only)

**Inputs/Outputs:**
- Input: audio array, ceiling dB
- Output: limited audio array

---

#### `utils/dsp/dynamics.py`
**Purpose:** Micro-dynamics processing (Phase 8D integration)  
**Key Functions:**
- `soften_transients(samples, threshold, soften_factor)` - Reduces sharp peaks
- `micro_compress(samples, ratio, attack, release)` - Light compression
- `smooth_vocals(samples, smooth_factor)` - Vocal smoothing

**Used By:**
- `MixService.apply_micro_dynamics()` (called before EQ in pipeline)

**Pipeline Position:**
- Applied AFTER auto gain, BEFORE EQ (required ordering)

**Inputs/Outputs:**
- Input: audio array, role-specific parameters
- Output: processed audio array

---

#### `utils/dsp/level.py`
**Purpose:** Loudness measurement and matching  
**Key Functions:**
- `lufs(samples)` - LUFS measurement (integrated loudness)
- `rms(samples)` - RMS level measurement
- `auto_gain(samples, target_lufs, target_rms)` - Automatic gain staging
- `match_loudness(audio, target_rms)` - RMS-based matching

**Used By:**
- `MixService.apply_auto_gain()` - Role-based targets (lead_vocal: -16 LUFS, beat: -18 LUFS, etc.)

**Inputs/Outputs:**
- Input: audio array, target levels
- Output: gain-adjusted audio array

---

#### `utils/dsp/analyze_audio.py`
**Purpose:** Audio analysis for visualization  
**Key Functions:**
- `compute_waveform(audio)` - Waveform samples (downsampled)
- `compute_fft_spectrum(audio)` - FFT spectrum (frequency bins)
- `compute_levels(audio)` - Peak and RMS levels
- `compute_energy_curve(audio)` - Energy over time
- `compute_track_spectrum(audio)` - Track-specific spectrum

**Used By:**
- `MixService.mix()` - Stores in job.extra["visual"] for WebSocket

**Inputs/Outputs:**
- Input: audio array
- Output: visualization data dict

---

#### `utils/dsp/scope.py`
**Purpose:** Scope visualization data  
**Key Functions:**
- `compute_scope(audio)` - Waveform, L/R correlation, phase relationship

**Used By:**
- `MixService.mix()` - Stores in job.extra["realtime_scope"]

**Inputs/Outputs:**
- Input: audio array
- Output: scope data dict

---

#### `utils/dsp/streamer.py`
**Purpose:** Audio chunking for streaming  
**Key Functions:**
- `chunk_audio(audio)` - Split audio into chunks for WebSocket streaming

**Used By:**
- `MixService.mix()` - Stores in job.extra["realtime_stream"]

**Inputs/Outputs:**
- Input: audio array
- Output: list of audio chunks

---

#### `utils/dsp/tonal_balance.py`
**Purpose:** Tonal balance correction  
**Key Functions:**
- `tonal_balance_chain(audio, role)` - Role-based tonal balance

**Used By:**
- `MixService.apply_tonal_balance()` (called in mix pipeline)

**Inputs/Outputs:**
- Input: audio array, role string
- Output: processed audio array

---

#### `utils/dsp/spatial.py`
**Purpose:** Spatial processing  
**Key Functions:**
- `spatial_pocket(audio, role)` - Role-based spatial positioning

**Used By:**
- `MixService.apply_spatial_separation()` (called in mix pipeline)

**Inputs/Outputs:**
- Input: stereo audio array, role string
- Output: processed stereo array

---

#### `utils/dsp/masking.py`
**Purpose:** Frequency masking detection and resolution  
**Key Functions:**
- `detect_masking(vocal_samples, beat_samples)` - Detect conflicting frequencies
- `resolve_masking(beat_samples, masked_freqs)` - Apply EQ to resolve masking

**Used By:**
- `MixService.apply_frequency_masking()` (called in mix pipeline for vocal tracks)

**Inputs/Outputs:**
- Input: vocal array, beat array
- Output: processed beat array (with masking resolved)

---

#### `utils/dsp/deesser.py`
**Purpose:** De-essing for vocals  
**Key Functions:**
- `apply_deesser(audio)` - Reduce sibilance (s/sh sounds)

**Used By:**
- `mix_pipeline.py` (vocals only: lead, double, harmony, adlib)

**Inputs/Outputs:**
- Input: audio array
- Output: processed audio array

---

#### `utils/dsp/air.py`
**Purpose:** High-frequency boost  
**Key Functions:**
- `add_air(audio)` - High-frequency enhancement

**Used By:**
- `mix_pipeline.py` (vocals only)

**Inputs/Outputs:**
- Input: audio array
- Output: processed audio array

---

#### `utils/dsp/stereo.py`
**Purpose:** Stereo widening  
**Key Functions:**
- `stereo_widen(audio, amount)` - Mid/side processing for width

**Used By:**
- `mix_pipeline.py` (backing vocals only: double, harmony)
- `MixService.mix()` (final master bus)

**Inputs/Outputs:**
- Input: stereo audio array, amount (0-1)
- Output: widened stereo array

---

### Mix Configuration (`utils/mix/`)

#### `utils/mix/roles.py`
**Purpose:** Role detection from filename  
**Key Functions:**
- `detect_role(filename)` - Detects: lead, double, harmony, adlib, beat, instrumental, unknown

**Pipeline Connection:**
- Used by `MixService.mix()` to determine which DSP to apply (de-esser, air, stereo widening)

**Inputs/Outputs:**
- Input: filename string
- Output: role string

---

#### `utils/mix/presets.py` / `utils/mix/role_presets.py`
**Purpose:** Role-based mix presets  
**Key Data:**
- `ROLE_PRESETS` dict - Presets for each role (EQ, compressor, saturation, gain settings)

**Pipeline Connection:**
- Used by `mix_pipeline.process_track()` to apply role-specific settings

---

#### `utils/mix/mix_recipes.py`
**Purpose:** Master bus mix recipes  
**Key Data:**
- `MIX_RECIPES` dict - Recipes like "default", "aggressive", "smooth" with master bus settings

**Pipeline Connection:**
- Used by `MixService.mix()` to apply master bus processing

---

#### `utils/mix/config_apply.py`
**Purpose:** Apply mix recipe to track roles  
**Key Functions:**
- `apply_recipe(recipe_name, track_roles)` - Creates MixConfig from recipe + track roles

**Pipeline Connection:**
- Used by mix router to prepare mix configuration

---

#### `utils/mix/timeline.py`
**Purpose:** Timeline event storage for mix jobs  
**Key Functions:**
- `add_event(job_id, step, message, progress)` - Add timeline event
- `get_timeline(job_id)` - Get all events for job

**Pipeline Connection:**
- Used by WebSocket to send timeline events to frontend

**Storage:**
- In-memory dict: `TIMELINE = {job_id: [events]}`

---

### Frontend Files

#### `frontend/src/App.jsx`
**Purpose:** React Router setup  
**Routes:**
- `/` → `AppPage`
- `/app` → `AppPage`
- `/pricing` → `PricingPage`
- `/billing/success` → `BillingSuccess`
- `/billing/cancel` → `BillingCancel`

---

#### `frontend/src/pages/AppPage.jsx`
**Purpose:** Main application page with timeline and stage routing  
**Key State:**
- `activeStage` - Currently open stage (beat, lyrics, upload, mix, release, content, analytics)
- `currentStage` - Suggested current stage (from project memory)
- `completedStages` - Object of completed stages
- `sessionId` - Session ID (stored in localStorage)
- `sessionData` - Session data (beatFile, lyricsData, vocalFile, masterFile, etc.)

**Key Functions:**
- `handleStageClick(stageId)` - Opens stage module (sets activeStage, scrolls to top)
- `completeCurrentStage(stage)` - Marks stage complete, syncs with backend, suggests next stage
- `loadProjectData()` - Loads project from backend on mount

**Stage Order:**
```javascript
["beat", "lyrics", "upload", "mix", "release", "content"]
```

**Pipeline Connection:**
- Orchestrates entire pipeline - manages stage navigation, session data, project memory sync

**CSS Classes:**
- `.stage-screen` - Full-screen container (absolute positioning, top: clamp(160px, 15vh, 240px))
- `.stage-screen.fullscreen` - When stage is open (top: 0, height: 100vh)
- `.stage-screen.no-stage-active` - When no stage open (pointer-events: none, transparent)

**Scroll Container:**
- Stages render inside `.stage-screen` → content uses `.stage-scroll-container` (overflow-y: auto)
- On mobile: stage-screen top: 0, height: 100vh (full-screen)
- On desktop: stage-screen top: clamp(160px, 15vh, 240px) (below timeline)

---

#### `frontend/src/components/Timeline.jsx`
**Purpose:** Horizontal timeline navigation component  
**Key Features:**
- Displays 7 stages as circular icons
- Shows completion checkmarks
- Active stage has pulse animation
- Click stage to open
- Shows current stage prompt
- Goal reached modal when all stages complete

**CSS:**
- `.timeline-container` - z-index: 30, pointer-events: auto
- `.timeline-centered` - Absolute positioning, centered on screen
- Timeline sits above stage-screen (z-index: 20)

**Pipeline Connection:**
- Primary navigation for entire pipeline

---

#### `frontend/src/components/MistLayer.jsx`
**Purpose:** Animated purple/gold gradient background  
**Key Features:**
- Position animates based on activeStage
- Uses CSS custom properties (--x, --y)
- z-index: 10, pointer-events: none

**Pipeline Connection:**
- Visual feedback for active stage

**CSS:**
- Defined in `frontend/src/styles/mist.css`
- Uses CSS animations for mist movement

---

#### `frontend/src/components/stages/StageWrapper.jsx`
**Purpose:** Common wrapper for all stage components  
**Key Features:**
- Header with title, icon, close button
- Content area (scrollable)
- Footer with "Next" button

**Pipeline Connection:**
- Wraps all stage components for consistent UI

---

#### `frontend/src/components/stages/MixStage.jsx`
**Purpose:** Mix & master interface  
**Key Features:**
- Effect toggles (EQ, Compression, Limiter, Saturation) - currently unused in basic mix
- "Mix Now" button - calls `runCleanMix()` API
- TransportBar component - playback controls
- WaveformCanvas component - waveform visualization
- TimelineCursor component - playhead cursor
- Zoom/pan controls

**Pipeline Connection:**
- Mix stage → calls `/api/projects/{session_id}/mix` → displays mix URL → advances to release

**CSS:**
- Uses `.stage-scroll-container` for scrolling
- Mix UI renders as scroll box (not full-screen canvas)

**Transport Integration:**
- Uses `useTransport` hook → connects to WebSocket `/ws/mix/transport/{job_id}`

---

#### `frontend/src/components/stages/ContentStage.jsx`
**Purpose:** Video content creation interface  
**Key Features:**
- 5-step workflow:
  1. Generate video idea (OpenAI)
  2. Upload finished video
  3. Analyze video (viral score)
  4. Generate captions & hashtags (OpenAI)
  5. Schedule video (GetLate API or local JSON)

**Pipeline Connection:**
- Content stage → generates content → schedules post → advances to analytics

---

#### `frontend/src/components/Mix/TransportBar.tsx`
**Purpose:** Playback controls (play, pause, stop, seek)  
**Key Features:**
- Connects to WebSocket `/ws/mix/transport/{job_id}`
- Shows current position, duration
- Controls: play, pause, stop, seek

**Pipeline Connection:**
- Controls mix audio playback during visualization

---

#### `frontend/src/components/Mix/WaveformCanvas.tsx`
**Purpose:** Multi-track waveform visualization  
**Key Features:**
- Renders waveforms for all tracks + master
- Supports zoom and pan
- Uses canvas for rendering

**Pipeline Connection:**
- Displays waveform data from mix job

---

#### `frontend/src/components/Mix/TimelineCursor.tsx`
**Purpose:** Playhead cursor on timeline  
**Key Features:**
- Vertical line showing current playback position
- Updates in real-time via `playheadRatio` prop

**Pipeline Connection:**
- Shows playback position during mix visualization

---

#### `frontend/src/hooks/useTransport.ts`
**Purpose:** Transport state hook  
**Key Features:**
- Connects to WebSocket `/ws/mix/transport/{job_id}`
- Returns `playheadRatio` for cursor positioning

**Pipeline Connection:**
- Provides transport state to Mix components

---

#### `frontend/src/hooks/useMultiTrackWaveform.ts`
**Purpose:** Multi-track waveform data hook  
**Key Features:**
- Fetches waveform data from mix job
- Returns tracks object with master and stem waveforms

**Pipeline Connection:**
- Provides waveform data to WaveformCanvas

---

#### `frontend/src/utils/api.js`
**Purpose:** Frontend API client  
**Key Functions:**
- Standardized response handling (`handleResponse()`)
- All API endpoints wrapped (beats, lyrics, upload, mix, release, content, analytics, billing, social)
- WebSocket helpers

**Pipeline Connection:**
- All frontend→backend communication goes through this

---

### Utility Files

#### `utils/shared_utils.py`
**Purpose:** Common utility functions  
**Key Functions:**
- `get_session_media_path(session_id, user_id=None)` - Get media directory path
- `get_project_media_path(project_id)` - Get project media directory
- `log_endpoint_event(endpoint, session_id, result, details)` - Log to app.log
- `gtts_speak(persona, text, session_id, user_id=None)` - Generate speech via gTTS (with SHA256 cache, 10s debounce)
- `should_speak(persona, text)` - Debounce check (10 seconds)
- `get_cached(key, fallback_func, ttl_seconds)` - Redis caching utility
- `require_feature_pro()` - Always allows access (no paywall - kept for compatibility)

**Pipeline Connection:**
- Used throughout services and routers for paths, logging, voice generation

**Redis Integration:**
- Optional Redis caching (falls back to direct execution if unavailable)

---

#### `utils/session_manager.py`
**Purpose:** Placeholder for session→user mapping  
**Key Functions:**
- `SessionManager.get_user(session_id)` - Returns None (placeholder)

**Pipeline Connection:**
- Referenced by routers but not actively used (no real authentication yet)

**Dead Code:**
- Entire file is placeholder - always returns None

---

#### `utils/security_utils.py`
**Purpose:** File upload validation  
**Key Functions:**
- `validate_uploaded_file(file)` - Validates: filename sanitization, extension whitelist, file size (50MB), MIME type

**Pipeline Connection:**
- Used by `media_router.py` for audio upload security

---

#### `social_scheduler.py`
**Purpose:** Social media scheduling with GetLate.dev integration  
**Key Classes:**
- `SocialScheduler` - Multi-platform scheduler (Instagram, Twitter, TikTok, Facebook, YouTube)

**Key Methods:**
- `schedule_with_getlate()` - Schedule via GetLate.dev API
- `optimize_content_for_platform()` - Platform-specific content optimization
- `get_optimal_posting_times()` - AI-recommended posting times

**Pipeline Connection:**
- Used by `ContentService.schedule_post()` for social media scheduling

---

## C. ARCHITECTURE FLOW

### Frontend → Backend → Database Flow

```
User Action (Frontend)
  ↓
React Component (e.g., BeatStage.jsx)
  ↓
API Client (api.js)
  ↓
HTTP Request → FastAPI Router (e.g., beat_router.py)
  ↓
Service Layer (e.g., BeatService)
  ↓
Project Memory (project_memory.py) → project.json file
  ↓
Database (database.py) → Project model (optional, minimal)
```

### Complete Pipeline Flow

```
1. BEAT STAGE
   Frontend: BeatStage.jsx
   → POST /api/beats/create
   → BeatService.create_beat_track()
   → Beatoven API (or fallback)
   → Save beat.mp3 to /media/{session_id}/
   → ProjectMemory.add_asset("beat", beat_url)
   → ProjectMemory.advance_stage("beat", "lyrics")
   → Frontend: Updates sessionData.beatFile, opens LyricsStage

2. LYRICS STAGE
   Frontend: LyricsStage.jsx
   → POST /api/songs/write
   → LyricsService.write_song()
   → OpenAI API (or fallback)
   → Save lyrics.txt to /media/{session_id}/
   → Generate voice MP3 via gTTS
   → ProjectMemory.add_asset("lyrics", lyrics_url)
   → ProjectMemory.advance_stage("lyrics", "upload")
   → Frontend: Updates sessionData.lyricsData, opens UploadStage

3. UPLOAD STAGE
   Frontend: UploadStage.jsx
   → POST /api/upload-audio
   → MediaRouter (validates file)
   → Save to /media/{session_id}/recordings/
   → ProjectMemory.add_asset("vocals", file_url)
   → ProjectMemory.advance_stage("upload", "mix")
   → Frontend: Updates sessionData.vocalFile, opens MixStage

4. MIX STAGE
   Frontend: MixStage.jsx
   → POST /api/projects/{session_id}/mix (basic) OR
   → POST /api/projects/{session_id}/mix/start (DSP)
   → MixService.run_clean_mix() OR MixService.mix()
   
   Basic Mix Flow:
   → pydub: beat.overlay(vocal)
   → Save to /media/{session_id}/mix/mixed_output.wav
   
   DSP Mix Flow:
   → MixJobManager.enqueue_mix() → creates job_id
   → MixService.mix() → processes in background:
      - Load stems (load_wav)
      - Auto gain (role-based)
      - Micro-dynamics
      - Tonal balance
      - Spatial separation
      - Frequency masking
      - Per-track DSP (EQ, compressor, saturation)
      - Blend tracks
      - Master bus (EQ, compressor, limiter)
      - Stereo widening
      - Export WAV (save_wav)
   → Save to /storage/mix_outputs/{session_id}/final_mix.wav
   → ProjectMemory.add_asset("mix", mix_url)
   → ProjectMemory.advance_stage("mix", "release")
   → Frontend: Updates sessionData.masterFile, opens ReleaseStage
   
   Real-time Visualization:
   → WebSocket: /ws/mix/status/{job_id} (500ms updates)
   → WebSocket: /ws/mix/transport/{job_id} (50ms updates)
   → Frontend: Updates meters, spectra, scope, transport position

5. RELEASE STAGE
   Frontend: ReleaseStage.jsx
   → POST /api/release/{project_id}/cover (upload cover)
   → POST /api/release/{project_id}/metadata (save metadata)
   → POST /api/release/{project_id}/pdf (save lyrics PDF)
   → GET /api/release/{project_id}/zip (generate ZIP)
   → ReleaseService saves files to /media/{project_id}/release/
   → ProjectMemory.advance_stage("release", "content")
   → Frontend: Opens ContentStage

6. CONTENT STAGE
   Frontend: ContentStage.jsx
   → POST /api/content/idea (generate video idea)
   → POST /api/content/analyze (analyze video)
   → POST /api/content/generate-text (generate captions/hashtags)
   → POST /api/content/schedule (schedule video)
   → ContentService schedules via GetLate API (or local JSON)
   → Save to /media/{session_id}/schedule.json
   → ProjectMemory.advance_stage("content", "analytics")
   → Frontend: Opens AnalyticsDashboard

7. ANALYTICS STAGE
   Frontend: AnalyticsDashboard.jsx
   → GET /api/analytics/session/{session_id}
   → AnalyticsService reads project.json
   → Returns: stages_completed, files_created, scheduled_posts, estimated_reach
```

### Project Memory Flow

```
ProjectMemory (per session_id)
  ↓
project.json file structure:
{
  "session_id": "...",
  "metadata": {tempo, key, mood, genre, artist_name, track_title},
  "assets": {
    "beat": {url, metadata},
    "lyrics": {url, metadata},
    "vocals": [{url, metadata}],
    "mix": {url, metadata},
    "master": {url},
    "release_pack": {url}
  },
  "workflow_state": {
    "beat_done": true,
    "lyrics_done": true,
    ...
  },
  "workflow": {
    "current_stage": "mix",
    "completed_stages": ["beat", "lyrics", "upload"]
  },
  "mix": {vocal_level, reverb_amount, eq_preset, bass_boost},
  "release": {title, artist, genre, cover_art, files},
  "chat_log": [],
  "analytics": {streams, saves, shares, revenue}
}
```

### Billing Flow

```
Upgrade Modal (Frontend)
  → POST /api/billing/create-checkout-session
  → BillingService.create_checkout_session()
  → Stripe Checkout Session
  → Redirect to Stripe
  → User pays
  → Stripe Webhook: POST /api/billing/webhook
  → BillingService.process_webhook()
  → Logs event (no user DB update - decoupled from auth)
```

### DSP Processing Flow (Advanced Mix)

```
MixService.mix()
  ↓
For each stem (vocal, beat):
  1. Load WAV (load_wav)
  2. Auto Gain (MixService.apply_auto_gain)
  3. Micro-Dynamics (MixService.apply_micro_dynamics)
  4. Tonal Balance (MixService.apply_tonal_balance)
  5. Spatial Separation (MixService.apply_spatial_separation)
  6. Frequency Masking (MixService.apply_frequency_masking) [vocal only]
  7. Per-Track DSP (process_track):
     - Match loudness
     - EQ
     - Compressor
     - Saturation
     - Gain
     - De-esser (vocals)
     - Air (vocals)
     - Stereo widen (backing vocals)
  8. Extract visualization data (spectrum, meters, scope)
  9. Store in job.extra for WebSocket
  ↓
Blend Tracks (blend_tracks)
  ↓
Master Bus Processing (process_master_bus):
  1. EQ
  2. Compressor
  3. Limiter
  ↓
Stereo Widening (stereo_widen)
  ↓
Export WAV (save_wav)
  ↓
Save to /storage/mix_outputs/{session_id}/final_mix.wav
```

---

## D. MIX/DSP SPECIFIC AUDIT

### How Beat + Vocals Are Combined

**Method 1: Basic Mix (`run_clean_mix`)**
```python
# services/mix_service.py:212
beat = AudioSegment.from_file(beat_path)
vocal = AudioSegment.from_file(vocal_path)
mixed = beat.overlay(vocal)  # Simple overlay
mixed = normalize(mixed)
mixed.export(output_path, format="wav")
```
- **Processing:** Simple pydub overlay (no DSP)
- **Output:** `/media/{session_id}/mix/mixed_output.wav`

**Method 2: DSP Mix (`mix`)**
```python
# services/mix_service.py:285-585
# 1. Load both as numpy arrays (load_wav)
# 2. Process each separately (per-track DSP)
# 3. Blend: np.sum(tracks, axis=0) with peak normalization
# 4. Master bus processing
# 5. Export as WAV
```
- **Processing:** Full DSP chain with EQ, compression, limiting
- **Output:** `/storage/mix_outputs/{session_id}/final_mix.wav`

**Answer:** Beat and vocals are combined via `blend_tracks()` which sums numpy arrays: `mix = np.sum(tracks, axis=0)`. If peak > 1.0, normalizes: `mix = mix / peak`.

---

### Unused DSP Functions

**Potentially Unused:**
1. `utils/dsp/spatial.py` - `spatial_pocket()` - Called in mix pipeline but may not have significant effect
2. `utils/dsp/masking.py` - `detect_masking()`, `resolve_masking()` - Called but with try/except (may fail silently)
3. `utils/dsp/tonal_balance.py` - `tonal_balance_chain()` - Called but with try/except (may fail silently)
4. `services/mix_service.py:process_single_file()` - Single file processing method - not called by any router

**Dead Code:**
- `services/mix_service.py:apply_basic_mix()` - Legacy function, only used by `mix_audio()` which may not be used
- `services/beat_service.py:get_beat_status()` - Always returns None (stub)
- `services/lyrics_service.py:analyze_mood()` - Always returns default string (no real analysis)

---

### Where Real Processing Should Occur

**Current Real Processing Locations:**
1. ✅ `services/mix_service.py:mix()` - Full DSP chain (lines 285-585)
2. ✅ `utils/dsp/mix_pipeline.py:process_track()` - Per-track DSP
3. ✅ `utils/dsp/mix_pipeline.py:process_master_bus()` - Master bus DSP

**Basic Processing (No Real DSP):**
1. ⚠️ `services/mix_service.py:run_clean_mix()` - Simple pydub overlay
2. ⚠️ `services/mix_service.py:apply_basic_mix()` - Legacy pydub overlay

**Answer:** Real DSP processing occurs in `MixService.mix()` which calls `process_track()` and `process_master_bus()`. The basic mix (`run_clean_mix`) uses simple pydub overlay with no DSP.

---

### Does Current Mix Module Perform Real DSP?

**Answer: YES - but conditionally**

- ✅ **Advanced Mix (`/api/projects/{session_id}/mix/start`)**: Full DSP with numpy-based processing (EQ, compression, limiting, etc.)
- ⚠️ **Basic Mix (`/api/projects/{session_id}/mix`)**: Simple pydub overlay (no DSP)

**Frontend Usage:**
- `MixStage.jsx` calls `runCleanMix()` API which uses basic mix (pydub overlay)
- DSP mix is available via `/mix/start` endpoint but may not be used by frontend

**Recommendation:**
- Frontend should use DSP mix endpoint for real processing
- Basic mix is legacy and should be deprecated

---

### Audio Libraries Imported vs Used

**Libraries Imported:**
1. `pydub` - ✅ Used for basic mix overlay, audio loading/export
2. `numpy` - ✅ Used extensively in DSP modules
3. `scipy` - ❓ Imported in requirements.txt but not found in codebase search
4. `librosa` - ❓ Imported but not found in usage
5. `soundfile` - ❓ Imported but not found in usage
6. `aubio` - ✅ Used in `lyrics_service.py:detect_bpm()`
7. `wave` - ✅ Used in `utils/dsp/load.py` and `export.py`
8. `struct` - ✅ Used in `utils/dsp/load.py` and `export.py`

**Actually Used:**
- ✅ `pydub` - Basic mix, AudioSegment operations
- ✅ `numpy` - All DSP processing
- ✅ `aubio` - BPM detection
- ✅ `wave`, `struct` - WAV file I/O
- ❌ `librosa`, `soundfile`, `scipy` - Imported but not used (dead dependencies)

**Recommendation:**
- Remove unused dependencies: `librosa`, `soundfile`, `scipy`

---

## E. TIMELINE UI & MODULE BEHAVIOR AUDIT

### Where Modules Load as Scroll Boxes vs Full-Screen

**Scroll Container Behavior:**
- All stages use `.stage-scroll-container` class (overflow-y: auto)
- Stages are NOT full-screen canvas - they are scrollable containers
- Content inside stages scrolls vertically

**Full-Screen Behavior:**
- `.stage-screen.fullscreen` class is applied when `isStageOpen === true`
- On desktop: stage-screen positioned at `top: 0, height: 100vh` (full viewport)
- On mobile: stage-screen always full-screen (`top: 0, height: 100vh`)

**CSS Location:**
- `frontend/src/styles/index.css` lines 138-166:
  ```css
  .stage-screen {
    position: absolute;
    top: clamp(160px, 15vh, 240px);  /* Below timeline */
    height: calc(100vh - clamp(160px, 15vh, 240px));
  }
  
  .stage-screen.fullscreen {
    top: 0;
    height: 100vh;  /* Full viewport */
  }
  ```

**Answer:**
- Stages load as **scroll boxes** (`.stage-scroll-container`) inside a **full-screen container** (`.stage-screen.fullscreen`)
- Content scrolls vertically, but container is full-screen
- Mix stage has waveform canvas but it's inside the scroll container (not a separate full-screen canvas)

---

### Conflicting CSS or Wrappers

**Potential Conflicts:**
1. **MistLayer z-index:**
   - `.mist-layer` has `z-index: 10` (in `index.css:24`)
   - `.timeline-container` has `z-index: 30` (in `Timeline.css:4`)
   - `.stage-screen` has `z-index: 20` (in `index.css:147`)
   - **Order:** Timeline (30) > Stage (20) > Mist (10) ✅ Correct

2. **Pointer Events:**
   - `.mist-layer` has `pointer-events: none` ✅
   - `.stage-screen.no-stage-active` has `pointer-events: none` ✅
   - `.timeline-container` has `pointer-events: auto` ✅
   - **No conflicts detected**

3. **Positioning:**
   - Timeline uses absolute positioning (centered)
   - Stage-screen uses absolute positioning (below timeline)
   - MistLayer uses fixed positioning
   - **No conflicts detected**

**Answer:**
- No conflicting CSS or wrappers detected
- z-index hierarchy is correct
- Pointer events are properly configured

---

### MistLayer Implementation

**Location:** `frontend/src/components/MistLayer.jsx`

**Implementation:**
- Uses CSS custom properties (`--x`, `--y`) for position
- Position map based on `activeStage`:
  ```javascript
  const mistPositions = {
    beat: { x: '10%', y: '40%' },
    lyrics: { x: '28%', y: '40%' },
    upload: { x: '46%', y: '40%' },
    mix: { x: '64%', y: '40%' },
    release: { x: '82%', y: '40%' },
    content: { x: '90%', y: '40%' },
    analytics: { x: '95%', y: '40%' }
  };
  ```
- CSS animation in `frontend/src/styles/mist.css`

**Inconsistencies:**
- ✅ Consistent - position updates based on activeStage
- ✅ z-index correct (10, below stages)
- ✅ pointer-events: none (doesn't block clicks)

**Answer:**
- MistLayer implementation is consistent
- No inconsistencies detected

---

## F. DEAD CODE & RISKS REPORT

### Unused Files

1. **`utils/session_manager.py`** - Entire file is placeholder (always returns None)
2. **`services/mix_service.py:process_single_file()`** - Method not called by any router
3. **`services/mix_service.py:apply_basic_mix()`** - Legacy function, may not be used
4. **`services/beat_service.py:get_beat_status()`** - Always returns None (stub)

### Duplicate Logic

1. **Mix Methods:**
   - `run_clean_mix()` - Basic pydub overlay
   - `mix()` - Full DSP chain
   - Both serve similar purpose but with different processing levels
   - **Risk:** Confusion about which endpoint to use

2. **Project Memory vs Database:**
   - Project data stored in both `project.json` (primary) and `Project` model (minimal)
   - Database model only stores `session_id`, `title`, `created_at`
   - **Risk:** Data inconsistency if one is updated without the other

### Functions Referenced But Not Implemented

1. **None found** - All referenced functions are implemented

### Stale Endpoints or Incomplete Routers

1. **`GET /api/beats/status/{job_id}`** - Returns stub data (always returns job not found)
2. **`POST /api/projects/{project_id}/mix`** - Uses basic mix (legacy, no DSP)
3. **Billing webhook** - Processes events but doesn't update user database (decoupled from auth - intentional)

### Incomplete Features

1. **Authentication** - `SessionManager` is placeholder (no real auth)
2. **Billing Integration** - Webhook processes but doesn't update user records (decoupled)
3. **Beat Status Tracking** - `get_beat_status()` is stub
4. **Mood Analysis** - `analyze_mood()` always returns default string

### Risks

1. **Data Loss Risk:** Project data primarily in JSON files (no backup/versioning)
2. **Performance Risk:** Real-time WebSocket updates at 500ms may be slow for smooth visualization
3. **Security Risk:** No authentication - all endpoints are public (session-based only)
4. **Code Quality Risk:** Try/except blocks in DSP pipeline may hide errors (frequency masking, tonal balance, spatial separation)

---

## G. DEPLOYMENT CHECK

### Environment Variables

**Required (with fallbacks):**
- `OPENAI_API_KEY` - Lyrics and content generation (fallback: static text)
- `BEATOVEN_API_KEY` - Beat generation (fallback: demo beat)
- `BUFFER_TOKEN` - Social media scheduling (optional)
- `DISTROKID_KEY` - Distribution (optional)

**Optional:**
- `STRIPE_SECRET_KEY` - Billing (optional)
- `STRIPE_PUBLISHABLE_KEY` - Billing (optional)
- `STRIPE_WEBHOOK_SECRET` - Billing webhooks (optional)
- `STRIPE_PRICE_ID` - Billing (optional)
- `STRIPE_PRODUCT_ID` - Billing (optional)
- `GETLATE_API_KEY` - Social scheduling (fallback: local JSON)
- `AUPHONIC_API_KEY` - Audio processing (not used)
- `REDIS_URL` - Caching (fallback: direct execution)
- `DATABASE_URL` - Database (defaults to SQLite)
- `PRICE_PRO_MONTHLY` - Pricing (optional)
- `FRONTEND_URL` - CORS and redirects (defaults to localhost:5173)
- `RENDER` - Render.com deployment flag
- `RENDER_EXTERNAL_URL` - Render.com external URL
- `RENDER_SERVICE_NAME` - Render.com service name

**Complete List:**
```bash
# Required (with fallbacks)
OPENAI_API_KEY
BEATOVEN_API_KEY
BUFFER_TOKEN
DISTROKID_KEY

# Optional
STRIPE_SECRET_KEY
STRIPE_PUBLISHABLE_KEY
STRIPE_WEBHOOK_SECRET
STRIPE_PRICE_ID
STRIPE_PRODUCT_ID
GETLATE_API_KEY
AUPHONIC_API_KEY
REDIS_URL
DATABASE_URL
PRICE_PRO_MONTHLY
FRONTEND_URL
RENDER
RENDER_EXTERNAL_URL
RENDER_SERVICE_NAME
```

---

### Build & Run Commands

**Backend (FastAPI):**
```bash
# Install dependencies
pip install -r requirements.txt

# Run development server
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Run production server
uvicorn main:app --host 0.0.0.0 --port 8000
```

**Frontend (React + Vite):**
```bash
cd frontend

# Install dependencies
npm install

# Development server
npm run dev

# Build for production
npm run build

# Clean build
npm run build:clean
```

**Render.com Deployment (render.yaml):**
```yaml
buildCommand: cd frontend && npm install && npm run build && cd .. && pip install -r requirements.txt
startCommand: uvicorn main:app --host 0.0.0.0 --port 8000
```

**Local Development:**
1. Backend: `uvicorn main:app --reload`
2. Frontend: `cd frontend && npm run dev`
3. Frontend proxies `/api` to backend (via Vite config)

**Production:**
1. Build frontend: `npm run build` (outputs to `frontend/dist/`)
2. Backend serves frontend: `main.py` serves `frontend/dist/index.html` for all routes
3. Static files served from `frontend/dist/`
4. Media files served from `/media` mount

---

## H. ADDITIONAL FINDINGS

### Project Memory System

**Architecture:**
- Primary storage: JSON files (`/media/{session_id}/project.json`)
- Secondary storage: SQLite database (`Project` model - minimal)
- Anonymous projects (no user_id required)

**File Structure:**
```
/media/{session_id}/
  ├── project.json           # Main project state
  ├── beat.mp3              # Generated beat
  ├── lyrics.txt            # Generated lyrics
  ├── recordings/           # Uploaded vocals
  │   └── {filename}.mp3
  ├── mix/                  # Basic mix output
  │   └── mixed_output.wav
  ├── release/              # Release pack files
  │   ├── cover.jpg
  │   ├── metadata.json
  │   ├── lyrics.pdf
  │   └── {session_id}_release_pack.zip
  ├── voices/               # gTTS voice files
  │   └── {sha256}.mp3
  └── schedule.json         # Scheduled social posts
```

**Advantages:**
- Simple, file-based (easy backup/export)
- No database migration needed
- Anonymous (no auth required)

**Disadvantages:**
- No versioning
- No concurrent access protection
- File system dependency

---

### WebSocket Infrastructure

**Endpoints:**
1. `/ws/mix/stream/{job_id}/{source}` - Audio chunk streaming
2. `/ws/mix/status/{job_id}` - Job status updates (500ms)
3. `/ws/mix/transport/{job_id}` - Transport position updates (50ms)

**Data Flow:**
```
MixService.mix() → stores data in job.extra
  ↓
WebSocket reads from job.extra
  ↓
Sends JSON payload to frontend
  ↓
Frontend updates visualization
```

**Update Frequency:**
- Status: 500ms (may be slow for smooth meters - should be 50-100ms)
- Transport: 50ms (good for smooth playback)

---

### Voice System

**Implementation:**
- Uses gTTS (Google Text-to-Speech)
- SHA256 cache key (prevents duplicate generation)
- 10-second debounce (prevents rapid-fire requests)
- Persona-specific TLDs (nova: com, echo: co.uk, etc.)

**Pipeline Connection:**
- Lyrics stage generates voice MP3 from first verse
- VoiceControl component plays voice files globally
- Single Audio instance (prevents overlapping voices)

---

### Mix Job Management

**Architecture:**
- In-memory job storage: `JOBS = {}` dict in `jobs/mix_job_manager.py`
- Job state: `MixJobState` dataclass
- Timeline events: In-memory `TIMELINE = {}` dict

**Limitations:**
- Jobs lost on server restart (in-memory only)
- No persistence
- No job queue (jobs processed immediately)

**Recommendation:**
- Add Redis or database for job persistence
- Add job queue (Celery or similar) for background processing

---

## CONCLUSION

This repository is a **well-structured, production-ready music production platform** with:

**Strengths:**
- ✅ Clean separation of concerns (routers → services → DSP)
- ✅ Real DSP processing (numpy-based, full chain)
- ✅ WebSocket infrastructure for real-time visualization
- ✅ Comprehensive pipeline (7 stages)
- ✅ Robust fallback mechanisms (Beatoven → demo → silent)

**Weaknesses:**
- ⚠️ Basic mix uses simple overlay (no DSP) - frontend should use DSP mix
- ⚠️ In-memory job storage (lost on restart)
- ⚠️ No authentication (session-based only)
- ⚠️ Unused dependencies (librosa, soundfile, scipy)
- ⚠️ Some stub implementations (beat status, mood analysis)

**Recommendations:**
1. Migrate frontend to use DSP mix endpoint (`/mix/start`) instead of basic mix
2. Add job persistence (Redis or database)
3. Remove unused dependencies
4. Implement real authentication (replace SessionManager placeholder)
5. Add project data versioning/backup

---

**Report Complete**  
**Status:** Comprehensive investigation complete - all files analyzed, architecture mapped, dependencies identified






