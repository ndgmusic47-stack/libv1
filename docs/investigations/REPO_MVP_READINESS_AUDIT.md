# Repo MVP Readiness Audit
**Target: Survive 500 users**  
**Date:** 2024  
**Type:** Investigation Only (No Patches)

---

## 1) EXEC SUMMARY

### What this repo DOES today (major features)
- **Beat Generation**: Integration with Beatoven API for AI-generated beats with async polling status checks (`routers/beat_router.py:35-88`, `services/beat_service.py:33-120`)
- **Lyrics Generation**: OpenAI-powered lyrics with structured parsing, refinement, and beat-to-lyrics analysis (`routers/lyrics_router.py:49-248`, `services/lyrics_service.py:160-500`)
- **Voice/Vocal Processing**: gTTS voice generation, RVC Gradio conversion for AI vocals, audio upload with security validation (`routers/media_router.py:51-505`, `utils/security_utils.py:201-240`)
- **Audio Mixing**: Full DSP pipeline with per-track processing, mastering chain, real-time job tracking via in-memory `JOBS` dict (`services/mix_service.py:141-575`, `jobs/mix_job_manager.py:8-51`)
- **Release Pack Generation**: Cover art, metadata, lyrics PDF, ZIP packaging (`routers/release_router.py:10-47`, `services/release_service.py:16-85`)
- **Content/Social Scheduling**: Video idea generation, caption/hashtag generation, GETLATE API integration (`routers/content_router.py:24-142`, `routers/social_router.py:48-126`)
- **Billing/Paywall**: Stripe Checkout integration, webhook handling, anonymous customer support (`routers/billing_router.py:34-171`, `services/billing_service.py:28-162`)
- **Project Memory**: File-based JSON persistence with SQLite/PostgreSQL backing for metadata (`project_memory.py:21-457`)
- **Analytics**: Session-based metrics, dashboard aggregation (`routers/analytics_router.py:17-55`)
- **Frontend**: React SPA with Vite, stage-based workflow UI (`frontend/src/components/stages/`)

### What it DOES NOT do
- **No authentication/authorization**: Session-based anonymous access only (`utils/session_manager.py:18-30` returns `None`)
- **No persistent job queue**: Mix jobs stored in in-memory `JOBS` dict, lost on restart (`jobs/mix_job_manager.py:5`, `JOBS = {}`)
- **No media cleanup/rotation**: Files accumulate indefinitely in `./media/{session_id}/` directories
- **No user management**: No user accounts, profiles, or multi-user isolation
- **No rate limiting per user/session**: Global IP-based rate limiting only (30 req/min) (`utils/rate_limit.py:38-157`)
- **No CDN/external media storage**: All media served directly from local filesystem
- **No database migrations**: Schema changes require manual intervention
- **No health checks/readiness probes**: No `/health` endpoint
- **No structured logging/metrics**: Basic Python logging to file, no APM integration

### Top 5 risks to stability
1. **In-memory job state loss**: `JOBS = {}` dict loses all mix job state on server restart (`jobs/mix_job_manager.py:5`, referenced in `services/mix_service.py:217`, `routers/mix_router.py:183-217`)
2. **Blocking DSP operations**: Heavy CPU-bound audio processing runs via `asyncio.to_thread()` in request handlers (`services/mix_service.py:188,204,474`), can exhaust thread pool
3. **Unbounded media accumulation**: No cleanup of `./media/{session_id}/` directories, storage grows indefinitely (evidenced in `project_memory.py:37`, `services/beat_service.py:92-94`)
4. **Missing request timeouts**: Several external API calls lack timeouts (Stripe customer.list in `services/billing_service.py:66`, some httpx calls default to 5s but long operations like Replicate use 300s `routers/media_router.py:297`)
5. **File system assumptions on Render**: Uses local filesystem for all storage (`config/settings.py:18 MEDIA_DIR = Path("./media")`), may fail on ephemeral filesystems

### MVP can handle: 5 users / 50 users / 500 users?

**5 users**: ✅ **YES** - Single-threaded request handling, in-memory jobs, file-based storage will work fine

**50 users**: ⚠️ **MARGINAL** - Evidence:
- In-memory `JOBS` dict (`jobs/mix_job_manager.py:5`) will accumulate entries, no cleanup (`services/mix_service.py:441-462` stores visual data in job.extra)
- Media accumulation in `./media/` (`project_memory.py:37`) with no cleanup strategy
- Blocking DSP in thread pool (`services/mix_service.py:188,204,474`) may exhaust pool under concurrent mix requests
- Rate limiting is per-IP, not per-session (`utils/rate_limit.py:134`), so 50 users behind same proxy = shared bucket

**500 users**: ❌ **NO** - Breaking points:
- **Job state loss on restart**: In-memory `JOBS` dict (`jobs/mix_job_manager.py:5`) means all active jobs disappear on deploy/restart
- **Storage exhaustion**: `./media/{session_id}/` directories (`project_memory.py:37`) accumulate indefinitely, no cleanup (`grep` search found no cleanup code)
- **Thread pool exhaustion**: Mix service uses `asyncio.to_thread()` for blocking DSP (`services/mix_service.py:188,204,474`), default thread pool size may be insufficient for concurrent requests
- **Database connection limits**: Single PostgreSQL connection pool (`database.py:21-25`) with no configured pool size, may exhaust connections
- **No horizontal scaling**: Job state in memory, file-based storage prevent multi-instance deployment

---

## 2) ARCHITECTURE MAP

### Backend stack + entrypoint
- **Framework**: FastAPI (`main.py:57`)
- **Entrypoint**: `main.py` → `uvicorn main:app --host 0.0.0.0 --port 8000` (`render.yaml:9`)
- **Async Runtime**: Python asyncio with uvicorn ASGI server
- **Dependencies**: See `requirements.txt` (FastAPI, httpx, librosa, numpy, scipy, sqlalchemy, aiosqlite/asyncpg, stripe, openai, replicate, gradio_client)

### Frontend stack + entrypoint
- **Framework**: React 18.2.0 (`frontend/package.json:12`)
- **Build Tool**: Vite 5.0.8 (`frontend/package.json:23`)
- **Routing**: React Router DOM 6.22.3 (`frontend/package.json:14`)
- **Styling**: Tailwind CSS 3.4.0 (`frontend/package.json:22`)
- **Entrypoint**: `frontend/src/main.jsx` → Vite dev server or built `frontend/dist/` served via FastAPI (`main.py:224-230`)
- **Deployment**: Build step in `render.yaml:6` → `npm run build`, served as static files (`main.py:227-230`)

### Data storage (DB, files, sessions)
- **Database**: 
  - SQLite (dev): `sqlite+aiosqlite:///./sql_app.db` (`database.py:15`)
  - PostgreSQL (prod): Enforced via `IS_PRODUCTION` check (`database.py:8-12`)
  - Model: `Project` table with `session_id` (indexed), `title`, `created_at` (`database_models.py:6-16`)
  - Connection: Async SQLAlchemy engine (`database.py:21-25`)
- **File Storage**:
  - Media files: `./media/{session_id}/` (`config/settings.py:18`, `project_memory.py:37`)
  - Mix outputs: `./storage/mix_outputs/{session_id}/` (`services/mix_service.py:41`)
  - Project memory: `./media/{session_id}/project.json` (`project_memory.py:39`)
  - Assets: `./assets/` (`main.py:139`)
- **Sessions**: 
  - Anonymous sessions via `session_id` UUID (`routers/beat_router.py:54`, `routers/media_router.py:68`)
  - No server-side session store, session_id passed in requests
  - Session manager placeholder (`utils/session_manager.py:18-30` returns `None`)

### Media pipeline (upload, processing, storage, serving)
- **Upload**: 
  - Endpoint: `POST /api/media/upload-audio` (`routers/media_router.py:51-117`)
  - Validation: Filename sanitization, MIME type check, 50MB limit (`utils/security_utils.py:201-240`)
  - Storage: `./media/{session_id}/recordings/{filename}` (`routers/media_router.py:81-90`)
- **Processing**:
  - Voice generation: gTTS via `gtts_speak()` → cached in `./media/{session_id}/voices/` (`utils/shared_utils.py:166-240`)
  - RVC conversion: Gradio client upload → conversion → download (`services/rvc_gradio_service.py:47-274`)
  - Mix processing: DSP pipeline via `MixService.mix()` → `asyncio.to_thread()` for blocking ops (`services/mix_service.py:141-515`)
- **Storage**: Files written to `./media/{session_id}/` or `./storage/mix_outputs/{session_id}/`
- **Serving**: Static file mounting via FastAPI (`main.py:145`) → `/media/{session_id}/...` URLs

### External dependencies (Beat services, AI, RunPod, etc.)
- **Beatoven API**: Beat generation (`services/beat_service.py:122-168`), status polling (`services/beat_service.py:457-651`), credits check (`services/beat_service.py:413-455`) - timeout: 30s compose, 30s status, 10s credits
- **OpenAI API**: Lyrics generation (`services/lyrics_service.py:99-112,213-225,466-499`), content generation (`services/content_service.py`) - no explicit timeout, uses OpenAI client default
- **Replicate API**: AI song generation via YuE model (`services/replicate_song_service.py:54-58`) - timeout: 300s (`routers/media_router.py:297`)
- **RVC Gradio**: Voice conversion service (`services/rvc_gradio_service.py:47-274`) - timeout: 300s upload, 300s conversion, 300s download
- **Stripe API**: Checkout sessions, webhooks, customer management (`services/billing_service.py:43-162`) - no explicit timeout, uses Stripe SDK default
- **GETLATE API**: Social media scheduling (`services/social_service.py`, `social_scheduler.py:310-311`) - timeout: 30s
- **Auphonic API**: Referenced in code comments but not actively used

---

## 3) MODULE INVENTORY

| Module | Endpoints | Core Files | State Stored | Dependencies | Known Failure Modes |
|--------|-----------|------------|--------------|--------------|---------------------|
| **Beat** | `POST /api/beats/create`<br>`GET /api/beats/status/{job_id}`<br>`GET /api/beats/credits` | `routers/beat_router.py`<br>`services/beat_service.py` | `./media/{task_id}/job.json`<br>`./media/{session_id}/beat.mp3`<br>Project memory JSON | Beatoven API (httpx), ProjectMemory | Missing API key → exception (`services/beat_service.py:72-75`)<br>Polling timeout (3min max, `services/beat_service.py:204`)<br>No retry on network errors (`services/beat_service.py:81-88`)<br>File I/O blocking in `_poll_beatoven_status` (`services/beat_service.py:226`) |
| **Lyrics** | `POST /api/lyrics/songs/write`<br>`POST /api/lyrics/from_beat`<br>`POST /api/lyrics/free`<br>`POST /api/lyrics/refine`<br>`POST /api/lyrics/clear` | `routers/lyrics_router.py`<br>`services/lyrics_service.py` | `./media/{session_id}/lyrics.txt`<br>Project memory JSON | OpenAI API, aubio (BPM detection), ProjectMemory | Missing API key → fallback lyrics (`services/lyrics_service.py:92-94`)<br>BPM detection can fail silently → default 140 (`services/lyrics_service.py:47-49`)<br>Blocking file I/O in `write_song` (`services/lyrics_service.py:229`) |
| **Voice/Vocal** | `POST /api/media/upload-audio`<br>`POST /api/media/generate/vocal`<br>`POST /api/media/generate/song`<br>`POST /api/voice/generate-ai-vocal` | `routers/media_router.py` | `./media/{session_id}/recordings/`<br>`./media/{session_id}/voices/`<br>Project memory JSON | gTTS, RVC Gradio, Replicate, aiofiles | gTTS blocking call via `asyncio.to_thread` (`routers/media_router.py:141`)<br>RVC service init can fail → 502 (`routers/media_router.py:425-428`)<br>Replicate 300s timeout may be insufficient (`routers/media_router.py:297`)<br>File size limit 50MB but no validation on Replicate downloads |
| **Mix** | `POST /{project_id}/mix/start`<br>`GET /{project_id}/mix/status`<br>`GET /{project_id}/mix/job/{job_id}/status`<br>`GET /{project_id}/mix/preview`<br>`GET /timeline/{job_id}`<br>`GET /visual/{job_id}`<br>`GET /scope/{job_id}`<br>`GET /streams/{job_id}`<br>`POST /transport/{job_id}/play`<br>`POST /transport/{job_id}/pause`<br>`POST /transport/{job_id}/stop`<br>`POST /transport/{job_id}/seek`<br>`POST /api/mix/run-clean`<br>`GET /api/mix/config/schema`<br>`POST /api/mix/config/apply` | `routers/mix_router.py`<br>`routers/mix_ws_router.py`<br>`services/mix_service.py`<br>`jobs/mix_job_manager.py` | In-memory `JOBS` dict (`jobs/mix_job_manager.py:5`)<br>`./storage/mix_outputs/{session_id}/final_mix.wav`<br>Project memory JSON | numpy, scipy, librosa, soundfile (DSP), ProjectMemory | **CRITICAL**: Job state lost on restart (`jobs/mix_job_manager.py:5`)<br>Blocking DSP in thread pool (`services/mix_service.py:188,204,474`)<br>No job cleanup/expiry (`jobs/mix_job_manager.py:5`)<br>WebSocket connections not tracked, can leak (`routers/mix_ws_router.py:11-117`) |
| **Release Pack** | `POST /api/release/{project_id}/cover`<br>`POST /api/release/{project_id}/copy`<br>`POST /api/release/{project_id}/pdf`<br>`POST /api/release/{project_id}/metadata`<br>`GET /api/release/{project_id}/zip` | `routers/release_router.py`<br>`services/release_service.py` | `./media/{project_id}/release/`<br>Project memory JSON | zipfile, reportlab (PDF), ProjectMemory | Blocking file I/O (`services/release_service.py:33-34,44-45,55-56`)<br>ZIP generation can fail on large files (`services/release_service.py:73-85`)<br>No cleanup of release files |
| **Content** | `POST /api/content/idea`<br>`POST /api/content/analyze`<br>`POST /api/content/generate-text`<br>`POST /api/content/schedule`<br>`POST /api/content/save-scheduled`<br>`GET /api/content/get-scheduled` | `routers/content_router.py`<br>`services/content_service.py` | Project memory JSON | OpenAI API, GETLATE API, SessionManager | SessionManager returns `None` (`routers/content_router.py:94,118,135`) → all requests fail<br>No timeout on OpenAI calls (`services/content_service.py`) |
| **Billing/Paywall** | `POST /api/billing/webhook`<br>`POST /api/billing/create-checkout-session`<br>`POST /api/billing/portal` | `routers/billing_router.py`<br>`services/billing_service.py` | Stripe (external), Database (Project table) | Stripe SDK | Webhook always returns 200, errors logged but not retried (`routers/billing_router.py:118-124`)<br>No timeout on Stripe API calls (`services/billing_service.py:66,87`)<br>Anonymous customers can accumulate in Stripe (`services/billing_service.py:76-81`) |
| **Auth/Sessions** | N/A (anonymous only) | `utils/session_manager.py` | None (placeholder) | None | SessionManager.get_user() returns `None` → breaks content scheduling (`routers/content_router.py:94,118,135`) |
| **Project Memory** | `GET /api/projects/{session_id}`<br>`POST /api/projects/{session_id}/advance` | `routers/projects_router.py`<br>`project_memory.py` | `./media/{session_id}/project.json`<br>Database `Project` table | aiofiles, sqlalchemy | JSON file corruption can break project load (`project_memory.py:47-49`)<br>No file locking → race conditions on concurrent saves (`project_memory.py:120-141`)<br>Database flush can fail silently (`project_memory.py:132-136`) |

---

## 4) RELIABILITY RED FLAGS (ranked)

### 1. **Blocking CPU tasks in request thread** (CRITICAL)
**Evidence:**
- Mix service runs heavy DSP operations via `asyncio.to_thread()` (`services/mix_service.py:188,204,474`)
  - `load_wav()` (librosa), `align_stems()`, `save_wav()` are CPU-bound
  - Default thread pool size (typically ~40 threads) can be exhausted under concurrent load
- Lyrics BPM detection uses blocking aubio library (`services/lyrics_service.py:29-49`)
- gTTS voice generation blocking (`routers/media_router.py:141`)
- File I/O operations not consistently async (e.g., `services/beat_service.py:226`, `services/release_service.py:33-34`)

**Impact:** Under 50+ concurrent users, thread pool exhaustion → requests hang → 500 errors

**Code locations:**
- `services/mix_service.py:188` - `await asyncio.to_thread(load_wav, resolved_path)`
- `services/mix_service.py:204` - `await asyncio.to_thread(align_stems, audio_data_dict)`
- `services/mix_service.py:474` - `await asyncio.to_thread(save_wav, str(output_path), master_audio)`
- `routers/media_router.py:141` - `await asyncio.to_thread(gtts_speak, "nova", text, session_id, None)`
- `services/lyrics_service.py:32-42` - aubio tempo detection (blocking)

### 2. **Missing job queue / background workers** (CRITICAL)
**Evidence:**
- Mix jobs stored in in-memory `JOBS = {}` dict (`jobs/mix_job_manager.py:5`)
- Jobs started via `asyncio.create_task()` in router (`routers/mix_router.py:99`)
- No persistence, no retry, no cleanup, no expiry

**Impact:** 
- Server restart → all active jobs lost
- No job history, no monitoring, no retry on failure
- Memory leak: jobs accumulate indefinitely (`services/mix_service.py:441-462` stores large visual data in job.extra)

**Code locations:**
- `jobs/mix_job_manager.py:5` - `JOBS = {}`
- `routers/mix_router.py:99` - `asyncio.create_task(_process_mix_job(job_id, session_id, stems))`
- `services/mix_service.py:441-462` - Visual data stored in job.extra (no cleanup)

### 3. **File system assumptions on Render** (HIGH)
**Evidence:**
- All storage uses local filesystem: `MEDIA_DIR = Path("./media")` (`config/settings.py:18`)
- Project memory JSON files in `./media/{session_id}/project.json` (`project_memory.py:39`)
- Mix outputs in `./storage/mix_outputs/` (`services/mix_service.py:41`)
- No S3/cloud storage integration

**Impact:** Render.com uses ephemeral filesystems that can be wiped on deploy → data loss

**Code locations:**
- `config/settings.py:18` - `MEDIA_DIR = Path("./media")`
- `project_memory.py:37-39` - `self.session_path = media_dir / session_id`, `self.project_file = self.session_path / "project.json"`
- `services/mix_service.py:41` - `STORAGE_MIX_OUTPUTS = Path("./storage/mix_outputs")`

### 4. **Missing timeouts/retries** (HIGH)
**Evidence:**
- Stripe API calls have no explicit timeout (`services/billing_service.py:66,87`)
- OpenAI API calls use client default timeout (no explicit setting in `services/lyrics_service.py:99-112,213-225`)
- Some httpx calls have timeouts (30s, 60s, 300s) but no retry logic
- Replicate calls use 300s timeout but may need longer (`routers/media_router.py:297`)

**Impact:** Hanging requests under network issues, API slowdowns

**Code locations:**
- `services/billing_service.py:66` - `stripe.Customer.list(email=email, limit=1)` (no timeout)
- `services/billing_service.py:87` - `stripe.checkout.Session.create(...)` (no timeout)
- `services/lyrics_service.py:99-112` - `client.chat.completions.create(...)` (no explicit timeout)
- `routers/media_router.py:297` - `httpx.AsyncClient(follow_redirects=True, timeout=300.0)` (long but fixed)

### 5. **Missing request limits (file size, rate limiting)** (MEDIUM)
**Evidence:**
- File upload limit: 50MB (`utils/security_utils.py:29`)
- Rate limiting: 30 requests/minute per IP (`utils/rate_limit.py:45`)
- No per-session rate limiting
- No request body size limits on FastAPI (default 1MB)
- No limit on number of concurrent mix jobs per session

**Impact:** 
- Single user can exhaust resources (start 100 mix jobs)
- Rate limiting ineffective for users behind same proxy
- Large request bodies can cause memory issues

**Code locations:**
- `utils/security_utils.py:29` - `MAX_FILE_SIZE = 50 * 1024 * 1024`
- `utils/rate_limit.py:45` - `requests_per_minute: int = 30`
- `main.py:57` - FastAPI app (no `max_request_size` configured)

### 6. **Unhandled exceptions and inconsistent response formats** (MEDIUM)
**Evidence:**
- Some endpoints return `error_response()` with different formats (`backend/utils/responses.py:16-25`)
- Some services return `{"is_error": True, "error": "..."}` dicts (`services/mix_service.py:511-515`)
- UncaughtExceptionMiddleware logs but returns generic 500 (`main.py:65-74`)
- Some exceptions caught and logged but not properly surfaced (e.g., `services/beat_service.py:106-108`)

**Impact:** Frontend error handling inconsistent, debugging difficult

**Code locations:**
- `main.py:65-74` - `UncaughtExceptionMiddleware` returns generic error
- `backend/utils/responses.py:16-25` - `error_response()` signature inconsistent (error_code vs message)
- `services/mix_service.py:511-515` - Returns `{"is_error": True, "error": str(e)}`
- `services/beat_service.py:106-108` - Manifest write failure logged but not surfaced

### 7. **CORS/cookie/session fragility** (LOW)
**Evidence:**
- CORS configured for single frontend URL (`main.py:130-136`)
- No cookie-based sessions, session_id passed in requests
- CORS credentials enabled but no actual cookies used

**Impact:** Frontend URL changes require code update, no session persistence across browser restarts

**Code locations:**
- `main.py:130-136` - `allow_origins=[settings.frontend_url]`, `allow_credentials=True`
- `routers/beat_router.py:54` - `session_id = request.session_id or str(uuid.uuid4())` (new UUID if missing)

### 8. **Concurrency hazards (shared temp dirs, filenames, global singletons)** (MEDIUM)
**Evidence:**
- `JOBS` dict is global singleton (`jobs/mix_job_manager.py:5`)
- Project memory JSON files have no locking (`project_memory.py:120-141`)
- Temporary files use UUIDs but concurrent writes to same session possible (`routers/media_router.py:147,173`)
- RVC service may have shared state (`services/rvc_gradio_service.py:47`)

**Impact:** 
- Race conditions on project.json saves
- Concurrent mix jobs for same session can conflict
- Global JOBS dict not thread-safe (though Python GIL helps)

**Code locations:**
- `jobs/mix_job_manager.py:5` - `JOBS = {}` (global dict)
- `project_memory.py:120-141` - `async def save(self):` (no file locking)
- `routers/media_router.py:173` - `filename = f"ai_take_{timestamp}.mp3"` (timestamp collision possible)

---

## 5) PERFORMANCE & SCALE ANALYSIS (code-based)

### Endpoints doing heavy compute synchronously

**Mix processing (`POST /{project_id}/mix/start`):**
- Evidence: `services/mix_service.py:188,204,474` - `asyncio.to_thread()` calls for:
  - `load_wav()` - librosa audio loading (CPU-bound, I/O-bound)
  - `align_stems()` - audio alignment algorithm (CPU-bound)
  - `save_wav()` - audio file writing (I/O-bound)
- Estimated time: 10-60 seconds per mix depending on audio length
- Impact at scale: Thread pool exhaustion → requests queue → timeouts

**Lyrics BPM detection (`POST /api/lyrics/from_beat`):**
- Evidence: `services/lyrics_service.py:29-49` - aubio tempo detection (blocking, CPU-bound)
- Estimated time: 1-5 seconds per detection
- Impact at scale: Minor, but adds latency

**Voice generation (gTTS):**
- Evidence: `routers/media_router.py:141` - `asyncio.to_thread(gtts_speak, ...)`
- Estimated time: 2-10 seconds depending on text length
- Impact at scale: Thread pool pressure

### Endpoints doing network calls without timeout

**Stripe API calls:**
- `services/billing_service.py:66` - `stripe.Customer.list(email=email, limit=1)` - No timeout
- `services/billing_service.py:87` - `stripe.checkout.Session.create(...)` - No timeout
- Impact: Hanging requests if Stripe API is slow/down

**OpenAI API calls:**
- `services/lyrics_service.py:99-112` - `client.chat.completions.create(...)` - Uses OpenAI client default (likely 60s)
- `services/lyrics_service.py:213-225` - Same
- `services/lyrics_service.py:466-499` - Same
- Impact: Moderate, OpenAI typically responsive but no explicit control

### Storage growth risks (media accumulation)

**Evidence of unbounded growth:**
- `project_memory.py:37` - `./media/{session_id}/` directories created for each session
- `services/beat_service.py:92-94` - Beat files saved to `./media/{session_id}/beat.mp3`
- `routers/media_router.py:81-90` - Uploads saved to `./media/{session_id}/recordings/`
- `services/mix_service.py:469-471` - Mix outputs saved to `./storage/mix_outputs/{session_id}/`
- No cleanup code found in codebase (grep search: no "cleanup", "delete", "purge", "remove" in storage context)

**Storage per user estimate:**
- Beat file: ~3-5 MB
- Vocal recording: ~1-10 MB
- Mix output: ~10-50 MB (WAV format)
- Project JSON: <1 KB
- **Total per session: ~15-65 MB**

**At 500 users:** ~7.5-32.5 GB (if all complete full pipeline)
**At 5000 sessions (abandoned + active):** ~75-325 GB

### DB bottlenecks or missing indexes

**Database schema:**
- `database_models.py:13-14` - `Project` table: `id` (primary key, indexed), `session_id` (unique, indexed), `title`, `created_at`
- Only one table, minimal queries
- Primary query: `select(Project).where(Project.session_id == project_id)` (`project_memory.py:349`)

**Potential bottlenecks:**
- No connection pool size configured (`database.py:21-25`) - defaults may be insufficient
- No prepared statements (SQLAlchemy handles this, but async execution overhead)
- `created_at` not indexed but not queried

**Missing indexes:** None identified (simple schema, single table)

### What breaks first at 5/50/500 users

**5 users:**
- Nothing breaks. Single-threaded request handling, in-memory jobs, file storage all adequate.

**50 users:**
- **Thread pool exhaustion** (most likely): Concurrent mix jobs exhaust thread pool → requests hang
  - Evidence: `services/mix_service.py:188,204,474` uses `asyncio.to_thread()` for blocking ops
  - Default thread pool: ~40 threads (CPUs * 5)
  - Mix job duration: 10-60s
  - Concurrent limit: ~40 active mixes before pool exhausted
- **Memory pressure from JOBS dict**: Jobs accumulate with visual data (`services/mix_service.py:441-462`)
  - Evidence: `jobs/mix_job_manager.py:5` - `JOBS = {}` never cleaned
  - Each job stores waveforms, spectra, scopes in `job.extra`
  - Estimate: ~10-50 MB per completed job
  - At 100 jobs: ~1-5 GB memory
- **Storage growth**: Media files accumulate, but 50 users × 50 MB = 2.5 GB (manageable)

**500 users:**
- **Job state loss on restart** (most critical): In-memory `JOBS` dict lost on deploy → all active jobs fail
  - Evidence: `jobs/mix_job_manager.py:5` - `JOBS = {}` in-memory only
  - Impact: User experience degradation, no retry mechanism
- **Storage exhaustion**: 500 users × 50 MB = 25 GB, but with abandoned sessions → 100-500 GB over time
  - Evidence: No cleanup code found
  - Impact: Disk full → new uploads fail, app crashes
- **Database connection pool exhaustion**: Unconfigured pool size, 500 concurrent requests may exhaust connections
  - Evidence: `database.py:21-25` - No `pool_size` configured
  - Impact: Database connection errors, 500 responses
- **Thread pool exhaustion**: Same as 50 users, but worse (more concurrent requests)
- **Rate limiting ineffective**: IP-based rate limiting (`utils/rate_limit.py:134`) means users behind same proxy share bucket
  - Evidence: `utils/rate_limit.py:53-59` - `_get_client_ip()` uses X-Forwarded-For or client.host
  - Impact: Legitimate users rate-limited unfairly

---

## 6) SECURITY & ABUSE RISK (MVP-level)

### Upload validation
**Evidence:** ✅ **GOOD**
- Filename sanitization: `utils/security_utils.py:32-79` - Removes path traversal (`..`), directory separators, null bytes
- File extension whitelist: `utils/security_utils.py:95-110` - Only `.wav`, `.mp3`, `.aiff`, `.wave`, `.webm`, `.ogg`
- File size limit: 50MB (`utils/security_utils.py:29`)
- MIME type validation: Content-based detection via magic bytes (`utils/security_utils.py:113-151`)
- Applied in: `routers/media_router.py:78` - `validate_uploaded_file(file)`

**Risks:**
- No virus/malware scanning
- MIME type detection fallback to extension if magic bytes fail (`utils/security_utils.py:191-198`)

### Auth protection on routes
**Evidence:** ❌ **NONE**
- No authentication middleware
- All endpoints public, session_id generated client-side or server-side
- `utils/session_manager.py:18-30` - `get_user()` returns `None` (placeholder)
- Content scheduling endpoints check session but always fail (`routers/content_router.py:94,118,135`)

**Risks:**
- Any user can access any session_id if they guess it (UUIDs are random but not secret)
- No authorization checks (e.g., user A can't access user B's data, but there's no user concept)

### Path traversal risks
**Evidence:** ✅ **MITIGATED**
- Filename sanitization removes `..` and separators (`utils/security_utils.py:55-59`)
- File paths constructed from sanitized filenames (`routers/media_router.py:85`)
- Session IDs are UUIDs, not user-controlled (`routers/beat_router.py:54`)

**Risks:**
- Low risk due to sanitization, but no additional path validation

### Exposed secrets
**Evidence:** ⚠️ **POTENTIAL**
- API keys loaded from environment variables (`config/settings.py:26-40`)
- No secrets in code (good)
- Logging may expose sensitive data (e.g., `services/beat_service.py:53` logs prompt text, but not API keys)

**Risks:**
- Log files may contain sensitive data (prompts, session IDs)
- Error messages may leak internal paths (`services/mix_service.py:170` - `f"Stem file not found: {stem_name} at {stem_path}"`)

### CORS/cookies
**Evidence:** ✅ **CONFIGURED**
- CORS middleware: `main.py:130-136` - `allow_origins=[settings.frontend_url]`, `allow_credentials=True`
- Security headers: CSP, HSTS, X-Frame-Options, X-Content-Type-Options (`main.py:93-123`)
- No actual cookies used (session_id in request body/params)

**Risks:**
- CORS allows credentials but no cookies → minor misconfiguration
- Single origin allowed → frontend URL change requires code update

### Rate limiting / abuse prevention
**Evidence:** ⚠️ **PARTIAL**
- Global rate limiting: 30 requests/minute per IP (`utils/rate_limit.py:45`)
- Redis-backed if available, in-memory fallback (`utils/rate_limit.py:65-112`)
- Applied to all routes via middleware (`main.py:126`)

**Risks:**
- Per-IP limiting ineffective for users behind same proxy (office, VPN)
- No per-session rate limiting (single user can create many sessions)
- No per-endpoint rate limiting (expensive endpoints like mix should have lower limits)
- No abuse detection (e.g., rapid session creation, repeated failures)

**Code locations:**
- `utils/rate_limit.py:38-157` - RateLimiterMiddleware
- `main.py:126` - Middleware registration

---

## 7) PROS / CONS

### 10 Pros (what is already strong)

1. **Clean async architecture**: FastAPI + asyncio throughout, proper use of `async/await` (`main.py:57`, routers use `async def`)
2. **Security utilities**: Comprehensive file upload validation (`utils/security_utils.py:201-240`) with sanitization, MIME checks, size limits
3. **Error handling middleware**: UncaughtExceptionMiddleware catches and logs all exceptions (`main.py:65-74`)
4. **Structured responses**: Standardized `success_response()` / `error_response()` helpers (`backend/utils/responses.py:4-25`)
5. **Security headers**: CSP, HSTS, X-Frame-Options, X-Content-Type-Options (`main.py:93-123`)
6. **Rate limiting infrastructure**: Redis-backed with in-memory fallback (`utils/rate_limit.py:38-157`)
7. **Project memory abstraction**: Clean separation of file-based storage and database (`project_memory.py:21-457`)
8. **External API timeouts**: Most httpx calls have explicit timeouts (30s, 60s, 300s) (`services/beat_service.py:146,207,224,434,534,573`)
9. **Logging**: Comprehensive logging throughout (`logging.getLogger(__name__)` in all modules)
10. **Database abstraction**: SQLAlchemy async with proper session management (`database.py:52-71`)

### 10 Cons (what is fragile / missing)

1. **In-memory job state**: `JOBS = {}` dict loses all state on restart (`jobs/mix_job_manager.py:5`)
2. **No persistent job queue**: Mix jobs use `asyncio.create_task()`, no retry, no monitoring (`routers/mix_router.py:99`)
3. **Blocking operations in request handlers**: DSP processing via `asyncio.to_thread()` can exhaust thread pool (`services/mix_service.py:188,204,474`)
4. **No media cleanup**: Files accumulate indefinitely in `./media/` and `./storage/` directories
5. **No authentication**: All endpoints public, session_id not validated (`utils/session_manager.py:18-30` returns `None`)
6. **File system storage**: Local filesystem used for all storage, not suitable for cloud/ephemeral environments (`config/settings.py:18`)
7. **No connection pool configuration**: Database pool size not set, may exhaust under load (`database.py:21-25`)
8. **Inconsistent error handling**: Mixed response formats (`{"is_error": True}` vs `error_response()`) (`services/mix_service.py:511-515` vs `backend/utils/responses.py:16-25`)
9. **No request body size limits**: FastAPI default 1MB may be insufficient for large payloads (`main.py:57`)
10. **Session manager placeholder breaks features**: Content scheduling fails because `SessionManager.get_user()` returns `None` (`routers/content_router.py:94,118,135`)

---

## 8) STABILIZATION ROADMAP (module-by-module)

### Phase 0: "Stop the bleeding" (top 5 quick wins)

**Priority 1: Persist mix job state**
- **What**: Move `JOBS` dict to Redis or database
- **Where**: `jobs/mix_job_manager.py:5` - Replace `JOBS = {}` with Redis/database backend
- **Files to change**:
  - `jobs/mix_job_manager.py` - Replace in-memory dict with Redis/database operations
  - `models/mix_job_state.py` - Add database model (if using DB)
  - `database_models.py` - Add `MixJob` table (if using DB)
- **Impact**: Prevents job loss on restart, enables job monitoring

**Priority 2: Add job cleanup/expiry**
- **What**: Clean up completed/failed jobs older than 24 hours
- **Where**: `jobs/mix_job_manager.py` - Add cleanup method, call on startup and periodically
- **Files to change**:
  - `jobs/mix_job_manager.py` - Add `cleanup_old_jobs()` method
  - `main.py` - Call cleanup on startup and schedule periodic cleanup
- **Impact**: Prevents memory leak from accumulated jobs

**Priority 3: Add request body size limits**
- **What**: Configure FastAPI `max_request_size`
- **Where**: `main.py:57` - Add `max_request_size` parameter to FastAPI app
- **Files to change**:
  - `main.py` - Configure `max_request_size=10 * 1024 * 1024` (10MB)
- **Impact**: Prevents memory exhaustion from large payloads

**Priority 4: Add explicit timeouts to Stripe calls**
- **What**: Wrap Stripe SDK calls with timeout
- **Where**: `services/billing_service.py:66,87` - Add timeout wrapper
- **Files to change**:
  - `services/billing_service.py` - Wrap `stripe.Customer.list()` and `stripe.checkout.Session.create()` with `asyncio.wait_for(timeout=10)`
- **Impact**: Prevents hanging requests if Stripe API is slow

**Priority 5: Fix SessionManager placeholder**
- **What**: Return dummy user dict or remove session checks
- **Where**: `utils/session_manager.py:18-30` - Return `{"id": session_id}` or remove checks
- **Files to change**:
  - `utils/session_manager.py` - Return `{"id": session_id}` instead of `None`
  - `routers/content_router.py:94,118,135` - Or remove session checks entirely
- **Impact**: Content scheduling endpoints become functional

### Phase 1: "Make core pipeline reliable" (Beat→Lyrics→Voice→Mix)

**Beat Module:**
- **Add retry logic**: `services/beat_service.py:81-88` - Retry on network errors (3 attempts, exponential backoff)
- **Add job persistence**: Store beat job status in database/Redis (currently only file manifest `services/beat_service.py:92-104`)
- **Files**: `services/beat_service.py`, `database_models.py` (add BeatJob table if using DB)

**Lyrics Module:**
- **Make BPM detection async**: `services/lyrics_service.py:29-49` - Wrap aubio in `asyncio.to_thread()`
- **Add fallback handling**: Better error messages when OpenAI fails (`services/lyrics_service.py:110-112`)
- **Files**: `services/lyrics_service.py`

**Voice Module:**
- **Add retry logic for RVC**: `services/rvc_gradio_service.py:47-274` - Retry on upload/conversion failures
- **Add timeout validation**: Ensure 300s timeout is sufficient, add progress callbacks
- **Files**: `services/rvc_gradio_service.py`

**Mix Module:**
- **Move to background job queue**: Replace `asyncio.create_task()` with proper job queue (Celery, RQ, or custom Redis queue)
- **Add progress persistence**: Store progress updates in database/Redis, not just in-memory
- **Add job retry**: Retry failed mix jobs automatically
- **Files**: `routers/mix_router.py:99`, `jobs/mix_job_manager.py`, `services/mix_service.py:141-515`

### Phase 2: "Monetizable MVP hardening" (billing, limits, logging)

**Billing Module:**
- **Add webhook idempotency**: Track processed webhook IDs to prevent duplicate processing (`routers/billing_router.py:34-124`)
- **Add billing event logging**: Log all billing events to database for audit trail
- **Files**: `routers/billing_router.py`, `services/billing_service.py`, `database_models.py` (add BillingEvent table)

**Rate Limiting:**
- **Add per-session rate limiting**: Complement IP-based with session-based limits (`utils/rate_limit.py:38-157`)
- **Add per-endpoint limits**: Lower limits for expensive endpoints (mix, voice generation)
- **Files**: `utils/rate_limit.py`, `main.py:126`

**Logging:**
- **Add structured logging**: Use JSON formatter for log aggregation (`main.py:40-47`)
- **Add request ID tracking**: Generate request IDs, include in all logs
- **Files**: `main.py:40-47`, `backend/utils/responses.py` (add request ID to responses)

**Storage Limits:**
- **Add per-session storage quotas**: Track storage per session, reject uploads if quota exceeded
- **Files**: `project_memory.py`, `routers/media_router.py:51-117`

### Phase 3: "Scale prep" (jobs, queues, storage, caching)

**Job Queue Infrastructure:**
- **Implement persistent job queue**: Use Celery, RQ, or custom Redis-based queue
- **Add job monitoring**: Dashboard/endpoint to view job status, retry failed jobs
- **Files**: New `jobs/queue.py`, `jobs/mix_job_manager.py` (refactor), `routers/mix_router.py`

**Storage Migration:**
- **Move to cloud storage**: S3, GCS, or Azure Blob for media files
- **Keep metadata in database**: Store file URLs in database, not just JSON files
- **Files**: New `utils/storage.py`, `project_memory.py` (refactor), `routers/media_router.py`, `services/mix_service.py`

**Media Cleanup:**
- **Implement cleanup job**: Periodic job to delete old/unused media files
- **Add retention policy**: Delete files older than 30 days, or after project completion + 7 days
- **Files**: New `jobs/cleanup_job.py`, `main.py` (schedule cleanup)

**Database Optimization:**
- **Configure connection pool**: Set `pool_size`, `max_overflow` in database engine (`database.py:21-25`)
- **Add database indexes**: Index `created_at` if querying by date, add composite indexes if needed
- **Files**: `database.py:21-25`, `database_models.py`

**Caching:**
- **Add Redis caching**: Cache project memory reads, API responses (credits, etc.)
- **Add CDN**: Use CDN for static media files (if moved to cloud storage)
- **Files**: New `utils/cache.py`, `project_memory.py` (add cache layer)

---

## 9) INVESTIGATION SEARCH LOG

The following searches were performed to gather evidence for this audit:

### Code structure exploration
```
list_dir(".")
glob_file_search("*.py")
glob_file_search("*.js")
glob_file_search("*.ts")
glob_file_search("*.json")
glob_file_search("*.md")
```

### Architecture understanding
```
read_file("main.py")
read_file("render.yaml")
read_file("requirements.txt")
read_file("config/settings.py")
read_file("database_models.py")
read_file("database.py")
```

### Router endpoint mapping
```
read_file("routers/beat_router.py")
read_file("routers/lyrics_router.py")
read_file("routers/media_router.py")
read_file("routers/mix_router.py")
read_file("routers/billing_router.py")
read_file("routers/projects_router.py")
read_file("routers/release_router.py")
read_file("routers/content_router.py")
read_file("routers/analytics_router.py")
read_file("routers/social_router.py")
read_file("routers/credits_router.py")
read_file("routers/mix_ws_router.py")
```

### Service logic analysis
```
read_file("services/beat_service.py")
read_file("services/lyrics_service.py")
read_file("services/mix_service.py")
read_file("jobs/mix_job_manager.py")
read_file("services/billing_service.py")
read_file("services/release_service.py")
read_file("project_memory.py")
read_file("utils/session_manager.py")
```

### Blocking operations search
```
grep("asyncio\.to_thread|run_in_executor|requests\.|httpx\.|timeout=", path=".")
codebase_search("Where are blocking CPU operations or synchronous I/O calls performed in request handlers?")
```

### Error handling patterns
```
codebase_search("What error handling patterns are used across routers and services?")
read_file("backend/utils/responses.py")
read_file("main.py") # UncaughtExceptionMiddleware
```

### Database and storage
```
grep("\.execute\(|\.query\(|SELECT|CREATE INDEX|CREATE TABLE", -i=True, path=".")
codebase_search("How are database indexes defined and what queries are performed on the database?")
grep("\.json|json\.dump|json\.load|project\.json", path=".", output_mode="files_with_matches")
codebase_search("How is file storage and media accumulation managed for user sessions?")
```

### Security and validation
```
read_file("utils/security_utils.py")
read_file("utils/rate_limit.py")
grep("validate_uploaded_file|sanitize_filename", path=".")
```

### External API calls
```
codebase_search("Where are external API calls made without timeout or retry logic?")
grep("httpx\.|stripe\.|openai\.|replicate\.", path=".")
```

### Job state management
```
grep("JOBS\[|JOBS\.get\(", path=".")
read_file("models/mix_job_state.py")
```

### Frontend structure
```
read_file("frontend/package.json")
list_dir("frontend/src")
```

---

**End of Audit Report**


