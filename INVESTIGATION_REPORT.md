# Label-in-a-Box MVP Investigation Report

**Date:** Investigation performed on current codebase state  
**Purpose:** Factual status report of what works, what's broken, and why  
**Scope:** Full-stack investigation (Frontend React + Backend FastAPI)

---

## 1. Architecture Map

### Frontend:
- **Entry Point:** `frontend/src/main.jsx` → `App.jsx` → `AppPage.jsx`
- **State Management:** 
  - `ProjectContext.jsx` - Global project state via React Context
  - `AppPage.jsx` - Local state for `currentStage`, `activeStage`, `completedStages`, `sessionData`
- **Stage Components:** 
  - `BeatStage.jsx` - Beat generation (working)
  - `LyricsStage.jsx` - Lyrics generation (BROKEN - see Section 2)
  - `UploadStage.jsx` - Vocal upload
  - `MixStage.jsx` - Audio mixing
  - `ReleaseStage.jsx` - Release pack generation
  - `ContentStage.jsx` - Content/viral module
- **Navigation:** 
  - `Timeline.jsx` - Visual timeline with stage icons
  - `StageWrapper.jsx` - Common wrapper with Next/Previous buttons
  - Navigation logic in `AppPage.jsx` (`goToNextStage`, `handleStageClick`)
- **API Layer:** `frontend/src/utils/api.js` - All backend communication
- **Key Hooks:** `useVoice.js`, `useTransport.ts`, `useMultiTrackWaveform.ts`, `useTimelineZoomPan.ts`

### Backend:
- **Main App:** `main.py` - FastAPI application with middleware (CORS, security headers, rate limiting, exception handling)
- **Routers (all included in main.py):**
  - `routers/beat_router.py` - `/beats/*` - Beat generation endpoints
  - `routers/lyrics_router.py` - `/lyrics/*` and `/songs/write` - Lyrics generation
  - `routers/media_router.py` - `/media/*` - File uploads
  - `routers/mix_router.py` - `/mix/*` - Mixing endpoints
  - `routers/mix_config_router.py` - `/api/mix/*` - Mix configuration
  - `routers/release_router.py` - `/api/release/*` - Release pack generation
  - `routers/content_router.py` - `/api/content/*` - Content/viral module
  - `routers/analytics_router.py` - Analytics endpoints
  - `routers/billing_router.py` - Stripe billing
  - `routers/social_router.py` - Social media scheduling
- **Services:** `services/*.py` - Business logic (beat_service, lyrics_service, mix_service, etc.)
- **Project Memory:** `project_memory.py` - Persistent project state (JSON files + SQLite)
- **Database:** `database.py` + `database_models.py` - SQLite with async SQLAlchemy
- **DSP Engine:** `utils/dsp/*.py` - Audio processing (pydub, librosa, scipy)

### Legacy / Unclear:
- Multiple report files (`PHASE_*_REPORT.md`) - Historical documentation, not code
- `render.yaml` - Deployment config (may be outdated)
- `RENDER_DEPLOYMENT_INVESTIGATION.md` - Deployment notes
- `analytics_engine.py` - Standalone file, unclear if used
- `social_scheduler.py` - Standalone file, unclear if used

---

## 2. Frontend Functional Status

### Navigation (Next/Previous):
- **Current behavior:**
  - `StageWrapper.jsx` provides "Next →" button that calls `onNext` prop
  - `AppPage.jsx` implements `goToNextStage()` which finds next stage in `stageOrder` array
  - Navigation works by setting `activeStage` state, which triggers `renderStage()` to show the correct component
- **Errors seen:**
  - No obvious errors in navigation logic itself
  - However, navigation can fail if the target stage component crashes (see LyricsStage below)
- **Files involved:**
  - `frontend/src/pages/AppPage.jsx` (lines 130-136, 106-128)
  - `frontend/src/components/stages/StageWrapper.jsx` (lines 48-59)
  - `frontend/src/components/Timeline.jsx` (stage click handlers)

### Lyrics Module:
- **Current behavior:**
  - Component renders initially but **CRASHES IMMEDIATELY** due to undefined variables
  - Three generation modes: "Generate Lyrics From Beat", "Generate Free Lyrics", "Generate Lyrics From Session Beat"
  - Refinement feature available after lyrics are generated
- **Errors seen:**
  - **CRITICAL BUG:** `LyricsStage.jsx` references `allowed` and `message` variables that are NEVER DEFINED
    - Line 148: `if (!allowed)` - `allowed` is undefined
    - Line 179: `if (!allowed)` - `allowed` is undefined
    - Line 216: `if (!allowed)` - `allowed` is undefined
    - Line 259: `if (!allowed)` - `allowed` is undefined
    - Line 318: `{!allowed && (` - `allowed` is undefined
    - Line 321: `{message}` - `message` is undefined
  - This causes a `ReferenceError` when the component renders, triggering React ErrorBoundary
  - ErrorBoundary shows "Try Again" button (line 58 in `ErrorBoundary.jsx`)
  - This explains the "error, try again" notification the user sees
- **Files involved:**
  - `frontend/src/components/stages/LyricsStage.jsx` (BROKEN - missing variable definitions)
  - `frontend/src/components/ErrorBoundary.jsx` (catches the crash)
  - `frontend/src/utils/api.js` (API calls: `generateLyrics`, `generateLyricsFromBeat`, `generateFreeLyrics`, `refineLyrics`)

### Other modules (Upload, Mix, Cover, Release):
- **Upload Stage:**
  - Renders correctly (`allowed = true` is defined on line 8)
  - File upload validation works
  - API call to `/api/media/upload/vocal` should work if backend is running
- **Mix Stage:**
  - Renders correctly
  - Uses `startMix`, `getMixStatus`, `getMixPreview` API functions
  - Polls for mix job status every 1.5 seconds
  - Depends on `vocalFile` and `beatFile` being present in `sessionData`
- **Release Stage:**
  - Renders correctly (`allowed = true` is defined on line 7)
  - Multiple API calls for cover generation, metadata, lyrics PDF, release pack
- **Content Stage:**
  - Renders correctly
  - Uses content service endpoints

### Key console/network errors:
- **Primary Error:** `ReferenceError: allowed is not defined` in `LyricsStage.jsx`
- **Secondary:** Any API calls from LyricsStage will fail because component crashes before they can execute
- **Network:** No network errors observed in code inspection, but LyricsStage never reaches API call stage due to crash

---

## 3. Backend Functional Status

### Endpoints map:

#### Beat:
- **File:** `routers/beat_router.py`
- **Routes:**
  - `POST /beats/create` - Create beat (working - user confirmed)
  - `GET /beats/credits` - Get Beatoven credits
  - `GET /beats/status/{job_id}` - Get beat job status
- **Status:** ✅ Working (user confirmed beat generation works)

#### Lyrics:
- **File:** `routers/lyrics_router.py`
- **Routes:**
  - `POST /songs/write` - Generate lyrics (genre, mood, theme) - **NOTE:** Path is `/songs/write`, not `/lyrics/write`
  - `POST /lyrics/from_beat` - Generate lyrics from uploaded beat file
  - `POST /lyrics/free` - Generate free lyrics from theme
  - `POST /lyrics/refine` - Refine existing lyrics
- **Status:** ⚠️ Backend appears functional, but frontend never reaches these endpoints due to LyricsStage crash
- **Implementation:** Uses `LyricsService` which calls OpenAI API with fallback lyrics

#### Upload:
- **File:** `routers/media_router.py` (not read, but referenced)
- **Routes:**
  - `POST /api/media/upload/vocal` - Upload vocal recording
- **Status:** Unknown (file not inspected, but referenced in `api.js`)

#### Mix:
- **File:** `routers/mix_router.py`
- **Routes:**
  - `POST /mix/{project_id}/mix/start` - Start mix job
  - `GET /mix/{project_id}/mix/status` - Get mix status
  - `GET /mix/{project_id}/mix/job/{job_id}/status` - Get job status
  - `GET /mix/{project_id}/mix/preview` - Get mix preview file
  - `POST /api/mix/run-clean` - Compatibility wrapper for mix
- **Status:** ⚠️ Implementation exists, but depends on:
  - Vocal and beat files being present in `MEDIA_DIR/{session_id}/`
  - `MixJobManager` and `MixService` working correctly
  - DSP pipeline (`utils/dsp/mix_pipeline.py`) functioning

#### Release:
- **File:** `routers/release_router.py`
- **Routes:**
  - `POST /api/release/{project_id}/cover` - Upload cover
  - `POST /api/release/{project_id}/copy` - Upload copy
  - `POST /api/release/{project_id}/pdf` - Upload PDF
  - `POST /api/release/{project_id}/metadata` - Upload metadata
  - `GET /api/release/{project_id}/zip` - Generate release ZIP
- **Status:** Unknown (implementation not inspected in detail)

#### Other:
- **Content:** `/api/content/*` - Content/viral module endpoints
- **Analytics:** Analytics endpoints
- **Billing:** Stripe integration
- **Social:** Social media scheduling

### Lyrics endpoint:
- **Implementation summary:**
  - `POST /songs/write` expects: `{ genre, mood, theme?, session_id? }`
  - Returns: `{ ok: true, data: { lyrics, session_id, filename, path, ... } }`
  - Uses OpenAI GPT-4o-mini with fallback lyrics if API key missing
  - Saves lyrics to `MEDIA_DIR/{session_id}/lyrics.txt`
  - Updates project memory via `ProjectMemory.add_asset()`
- **Likely failure points:**
  - Frontend never calls this because `LyricsStage.jsx` crashes before API call
  - If called, would fail if OpenAI API key missing (but has fallback)
  - Project memory save could fail if `MEDIA_DIR` not writable

### Mix endpoint:
- **Implementation summary:**
  - `POST /mix/{project_id}/mix/start` expects: `MixRequest` body with `vocal_url`, `beat_url`, `config?`
  - If no URLs in request, looks for default files: `MEDIA_DIR/{session_id}/vocal.wav` and `beat.mp3`
  - Enqueues job via `MixJobManager.enqueue_mix()`
  - Background task `_process_mix_job()` calls `MixService.mix()`
  - Output saved to `storage/mix_outputs/{session_id}/final_mix.wav`
- **Likely failure points:**
  - Missing vocal or beat files (returns 400 "NO_STEMS")
  - DSP pipeline errors (would be caught and logged)
  - File I/O errors if storage directory not writable
  - Job polling in frontend might fail if WebSocket/status endpoint broken

### General issues:
- **CORS:** Configured in `main.py` line 129-135, uses `settings.frontend_url` (defaults to `http://localhost:5173`)
  - ⚠️ **Potential issue:** If deployed on Render, `FRONTEND_URL` env var must match actual frontend URL
- **Environment variables:** Many required keys (OpenAI, Beatoven, Stripe, etc.) - missing keys cause warnings but app continues
- **Error handling:** Most endpoints use `try/except` with `error_response()` helper
- **Project memory:** Uses both JSON files (`project.json`) and SQLite database - potential sync issues
- **API path inconsistencies:**
  - Some routes use `/api/*` prefix (content, release, mix config)
  - Others use direct paths (`/beats/*`, `/lyrics/*`, `/mix/*`)
  - Frontend `api.js` uses `/api` base, so routes without `/api` prefix may not work

---

## 4. Project State & Persistence

### Where project state is defined:
- **Backend:** `project_memory.py` - `ProjectMemory` class
  - Stores in: `MEDIA_DIR/{session_id}/project.json` (JSON file)
  - Also syncs to SQLite database via `database_models.Project` table
- **Frontend:** 
  - `ProjectContext.jsx` - React Context provider
  - `AppPage.jsx` - Local state (`sessionData`, `currentStage`, `completedStages`)

### How each stage writes to it:
- **Beat Stage:**
  - Calls `api.createBeat()` → Backend saves beat URL to project memory
  - Calls `api.syncProject()` to sync backend state to frontend
  - Updates `sessionData.beatFile` in frontend
- **Lyrics Stage:**
  - Should call `api.generateLyrics()` → Backend saves lyrics to `lyrics.txt` and updates project memory
  - **BUT:** Component crashes before any API calls
- **Upload Stage:**
  - Calls `api.uploadRecording()` → Backend saves vocal file
  - Calls `api.syncProject()` to sync state
- **Mix Stage:**
  - Calls `api.startMix()` → Backend creates mix job
  - Polls `api.getMixStatus()` → Backend updates project memory when complete
  - `projectData.mix.completed` is single source of truth for mix completion
- **Release Stage:**
  - Multiple API calls to save cover, metadata, lyrics PDF
  - Calls `api.getReleasePack()` to generate ZIP

### Known gaps / inconsistencies:
- **LyricsStage crash prevents any state updates** - lyrics are never saved to project memory
- **State sync issues:**
  - Frontend `sessionData` and backend `project.json` can get out of sync
  - `api.syncProject()` attempts to sync, but only called in some stages
- **Mix completion tracking:**
  - Uses `projectData.mix.completed` (backend state) as source of truth
  - But `completedStages` in `AppPage.jsx` uses different mechanism (object with stage keys)
  - Potential for inconsistency

### Impacted features (e.g., Release Pack generation):
- **Release Pack depends on:**
  - Beat file (✅ working)
  - Lyrics (❌ broken - never saved due to LyricsStage crash)
  - Vocal file (⚠️ depends on upload working)
  - Mix file (⚠️ depends on mix job completing)
  - Cover art (⚠️ depends on generation working)
- **If lyrics are missing, Release Pack may fail or be incomplete**

---

## 5. MVP Blockers (Prioritised)

### 1) LyricsStage Component Crash (CRITICAL)
- **Title:** Undefined variables `allowed` and `message` in LyricsStage.jsx
- **Module / files:** `frontend/src/components/stages/LyricsStage.jsx`
- **Exact symptom:** Component crashes with `ReferenceError: allowed is not defined` when rendering, triggering ErrorBoundary which shows "Try Again" button
- **Root cause:** Lines 148, 179, 216, 259, 318, 321 reference `allowed` and `message` variables that are never declared. Other stage components (BeatStage, UploadStage, ReleaseStage) define `allowed = true` at the top, but LyricsStage does not.
- **Fix type:** Frontend - Add missing variable declarations:
  ```javascript
  const allowed = true; // No auth - always allowed
  const message = ''; // Empty message or remove upgrade banner if not needed
  ```
- **Impact:** Blocks entire Lyrics stage, prevents lyrics from being generated and saved, breaks pipeline flow

### 2) API Path Mismatch for Lyrics Generation
- **Title:** Frontend calls `/api/songs/write` but router defines `/songs/write` (no `/api` prefix)
- **Module / files:** 
  - Frontend: `frontend/src/utils/api.js` line 180
  - Backend: `routers/lyrics_router.py` line 40
- **Exact symptom:** If LyricsStage were fixed, API call would return 404 because path doesn't match
- **Root cause:** `lyrics_router` is created with `prefix="/lyrics"`, but the route is `@lyrics_router.post("/songs/write")`, making full path `/lyrics/songs/write`. Frontend calls `/api/songs/write`.
- **Fix type:** Backend - Either:
  - Change router prefix to `/api/lyrics` and route to `/songs/write` (full path: `/api/lyrics/songs/write`)
  - OR change route to `@lyrics_router.post("/write")` and update frontend to call `/api/lyrics/write`
- **Impact:** Even if LyricsStage is fixed, lyrics generation API calls will fail

### 3) Navigation State Inconsistencies
- **Title:** Multiple state management systems for stage completion (frontend `completedStages` vs backend `project.workflow.completed_stages` vs `projectData.mix.completed`)
- **Module / files:** 
  - `frontend/src/pages/AppPage.jsx` (local state)
  - `frontend/src/context/ProjectContext.jsx` (context state)
  - `project_memory.py` (backend state)
- **Exact symptom:** Navigation icons may show incorrect completion status, or stages may not advance correctly
- **Root cause:** 
  - `AppPage.jsx` uses `completedStages` object (e.g., `{ beat: true, lyrics: true }`)
  - Backend uses `workflow.completed_stages` array (e.g., `["beat", "lyrics"]`)
  - Mix stage uses `projectData.mix.completed` boolean
  - Conversion between formats happens in `loadProjectData()` but may not be complete
- **Fix type:** State management - Unify state representation (prefer backend as source of truth, frontend reads from it)
- **Impact:** User confusion, incorrect UI state, potential navigation bugs

### 4) Missing Error Handling in Stage Navigation
- **Title:** `goToNextStage()` and `handleStageClick()` don't handle errors if target stage component crashes
- **Module / files:** `frontend/src/pages/AppPage.jsx` lines 130-136, 106-111
- **Exact symptom:** If a stage component crashes (like LyricsStage), navigation can leave app in broken state or freeze
- **Root cause:** No try/catch around stage rendering or navigation logic
- **Fix type:** Frontend - Add error boundaries around individual stages, or wrap navigation in try/catch
- **Impact:** App can freeze or become unresponsive when navigating to broken stages

### 5) Mix Job Dependency Chain
- **Title:** Mix stage depends on vocal and beat files existing, but no validation before starting mix
- **Module / files:** 
  - `frontend/src/components/stages/MixStage.jsx` line 111
  - `routers/mix_router.py` line 87
- **Exact symptom:** Mix job may fail silently or return "NO_STEMS" error if files missing
- **Root cause:** Frontend checks `sessionData.vocalFile` and `sessionData.beatFile` exist, but these may be URLs that don't resolve, or files may not exist on backend filesystem
- **Fix type:** Backend + Frontend - Add validation:
  - Backend: Check files exist before enqueueing job
  - Frontend: Verify files are accessible before showing "Mix Now" button
- **Impact:** Mix jobs fail without clear error messages

### 6) Project Memory Sync Gaps
- **Title:** Frontend `sessionData` and backend `project.json` can become out of sync
- **Module / files:** 
  - `frontend/src/pages/AppPage.jsx` (sessionData state)
  - `project_memory.py` (backend state)
  - `frontend/src/utils/api.js` (`syncProject` function)
- **Exact symptom:** User may see stale data, or changes may not persist
- **Root cause:** `syncProject()` is called inconsistently (some stages call it, others don't). Frontend updates `sessionData` but doesn't always sync to backend immediately.
- **Fix type:** State management - Implement consistent sync strategy:
  - Option A: Always sync to backend immediately after any state change
  - Option B: Use backend as single source of truth, frontend only reads
- **Impact:** Data loss, inconsistent UI state

---

## 6. Unknowns & Ambiguities

- **Media Router:** `routers/media_router.py` not inspected - upload endpoint implementation unknown
- **Mix Service:** `services/mix_service.py` not inspected - DSP pipeline implementation details unknown
- **Release Service:** `services/release_service.py` not inspected - ZIP generation logic unknown
- **Content Service:** `services/content_service.py` partially seen but not fully understood
- **Session Manager:** `utils/session_manager.py` referenced in content router but not inspected - session-to-user mapping unclear
- **DSP Pipeline:** `utils/dsp/mix_pipeline.py` and related files not inspected - audio processing implementation unknown
- **Environment Variables:** Many required keys (OpenAI, Beatoven, Stripe, etc.) - unclear which are critical vs optional for MVP
- **Database Schema:** `database_models.py` not fully inspected - unclear what tables exist and how they're used
- **WebSocket Mix Router:** `routers/mix_ws_router.py` not inspected - real-time mix updates unknown
- **Frontend Build:** `frontend/dist/` directory not checked - unclear if frontend is built and served correctly on Render
- **CORS Configuration:** `settings.frontend_url` defaults to `http://localhost:5173` - may be incorrect for Render deployment
- **Static File Serving:** `main.py` lines 220-226 serve frontend from `frontend/dist/` - unclear if this directory exists in production
- **Error Notification System:** User mentioned "error, try again" notification - this appears to be the ErrorBoundary "Try Again" button, but unclear if there are other notification systems (toasts, alerts, etc.)

---

## Summary

**Working:**
- Beat generation (user confirmed)
- Basic navigation structure
- ErrorBoundary catches crashes
- Backend API structure is in place

**Broken:**
- LyricsStage crashes immediately due to undefined variables (BLOCKER #1)
- API path mismatch for lyrics endpoint (BLOCKER #2)
- State synchronization inconsistencies (BLOCKER #3)

**Unclear:**
- Many backend services not fully inspected
- Deployment configuration (Render) not verified
- Full error handling flow not understood

**Recommended Next Steps:**
1. Fix LyricsStage undefined variables (5-minute fix)
2. Fix API path mismatch for lyrics endpoint (5-minute fix)
3. Test full pipeline: Beat → Lyrics → Upload → Mix → Release
4. Verify deployment configuration (CORS, static file serving, environment variables)
5. Add comprehensive error handling and user feedback

---

**End of Report**



