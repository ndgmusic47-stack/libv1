# Lyrics Stage Investigation Report

**Date:** Investigation Only (No Patches)  
**Scope:** End-to-end analysis of Lyrics stage: UI → API → Service → Provider → Project Memory → UI Render

---

## Executive Summary

1. **P0 - Critical:** `syncProject()` in `frontend/src/utils/api.js` does NOT map lyrics from project memory to `sessionData.lyricsData`, causing lyrics to disappear on page refresh
2. **P0 - Critical:** `generate_free_lyrics()` in `services/lyrics_service.py` does NOT save lyrics to project memory, so free lyrics are lost on refresh
3. **P1 - High:** `generate_lyrics_from_beat()` saves lyrics in multiple inconsistent locations: `project.json` (direct write), `project.assets.lyrics` (via `add_asset`), and `project.lyrics` (object with `text` key)
4. **P1 - High:** Frontend expects `sessionData.lyricsData` but project memory stores lyrics in `project.assets.lyrics.url` (file path) or `project.lyrics.text` (text), creating a read mismatch
5. **P2 - Medium:** `refine_lyrics()` does not persist refined lyrics back to project memory

---

## 1. Frontend Wiring Map

### Component Location
- **File:** `frontend/src/components/stages/LyricsStage.jsx`
- **Route:** Accessed via `AppPage.jsx` → Timeline → Stage click handler
- **Component:** `LyricsStage` (lines 109-409)

### UI Action Flow

#### Generate Lyrics Handler
- **Function:** `handleGenerateLyrics()` (lines 124-170)
- **Trigger:** Button click on "Generate Lyrics" button (line 267)
- **Conditions:** Requires either `sessionData.beatFile` OR `theme` input (line 130)

#### Two Generation Paths:

**Path A: From Beat (if `sessionData.beatFile` exists)**
1. Fetches beat blob from `sessionData.beatFile` URL (line 144)
2. Creates FormData with blob (lines 147-148)
3. Calls: `api.generateLyricsFromBeat(formData, sessionId)` (line 150)
4. **Expected response:** `{lyrics: string}` (line 159)
5. Sets local state: `setLyrics(result.lyrics)` (line 159)
6. Updates session: `updateSessionData({ lyricsData: result.lyrics })` (line 160)

**Path B: Free Lyrics (if no beat, uses theme)**
1. Calls: `api.generateFreeLyrics(theme)` (line 155)
2. **Expected response:** `{lyrics: string}` (line 159)
3. Sets local state: `setLyrics(result.lyrics)` (line 159)
4. Updates session: `updateSessionData({ lyricsData: result.lyrics })` (line 160)

#### Refine Lyrics Handler
- **Function:** `handleRefineLyrics()` (lines 180-223)
- **Trigger:** Button click on "Refine Lyrics" button (line 380)
- **Calls:** `api.refineLyrics(lyricsText, refineText, bpm, history, structuredLyrics, rhythmMap)` (lines 201-208)
- **Expected response:** `{lyrics: string}` (line 213)
- Updates: `setLyrics(result.lyrics)` and `updateSessionData({ lyricsData: result.lyrics })` (lines 213-214)

#### Lyrics Display
- **Source:** Local state `lyrics` (line 112), initialized from `sessionData.lyricsData` on mount (lines 118-122)
- **Rendering:** Lines 295-360
  - If `typeof lyrics === 'string'`: renders as plain text with line breaks
  - If object: renders structured sections (verse, chorus, bridge)

### API Client Functions

**File:** `frontend/src/utils/api.js`

| Function | Endpoint | Method | Request Payload | Response Extraction |
|----------|----------|--------|-----------------|---------------------|
| `generateLyricsFromBeat(fileOrFormData, sessionId)` | `/api/lyrics/from_beat` | POST | FormData: `file`, `session_id` | `handleResponse()` → `result.data` → expects `{lyrics: string}` |
| `generateFreeLyrics(theme)` | `/api/lyrics/free` | POST | JSON: `{theme: string}` | `handleResponse()` → `result.data` → expects `{lyrics: string}` |
| `refineLyrics(...)` | `/api/lyrics/refine` | POST | JSON: `{lyrics, instruction, bpm, history, structured_lyrics, rhythm_map}` | `handleResponse()` → `result.data` → expects `{lyrics: string}` |

**Response Handler:** `handleResponse()` (lines 6-42)
- Extracts `result.data || result` (line 41)
- Returns data directly (not wrapped)

---

## 2. Backend Routing & Call Chain

### Router Endpoints

**File:** `routers/lyrics_router.py`

| Endpoint | Method | Handler Function | Request Model |
|----------|--------|-----------------|---------------|
| `/lyrics/from_beat` | POST | `generate_lyrics_from_beat()` (lines 123-162) | `file: UploadFile`, `session_id: Optional[str]` (Form) |
| `/lyrics/free` | POST | `generate_free_lyrics()` (lines 165-180) | `FreeLyricsRequest` (JSON): `{theme: str}` |
| `/lyrics/refine` | POST | `refine_lyrics()` (lines 183-205) | `LyricRefineRequest` (JSON): `{lyrics, instruction, bpm, history, structured_lyrics, rhythm_map}` |

**Router Registration:** `main.py` line 207: `app.include_router(lyrics_router)`

### Response Format

**File:** `backend/utils/responses.py`

All endpoints return:
```json
{
  "ok": true,
  "data": { ... },
  "error": null,
  "message": "..."
}
```

### Service Layer

**File:** `services/lyrics_service.py`

#### `generate_lyrics_from_beat()`
- **Called by:** `routers/lyrics_router.py:141`
- **Flow:**
  1. Detects BPM from beat file (line 292)
  2. Analyzes mood (line 293)
  3. Generates lyrics via `generate_np22_lyrics()` (line 296)
  4. Writes `lyrics.txt` to disk (lines 304-305)
  5. **Writes directly to `project.json`** (lines 308-325):
     - Sets `project["lyrics"] = str(lyrics_path)` (file path)
     - Sets `project["lyrics_text"] = lyrics_text` (text)
  6. **Saves to project memory** (lines 328-336):
     - Creates/updates `memory.project_data["lyrics"]` as object: `{text: lyrics_text, meta: {}, completed: True}`
     - Calls `memory.save()`
  7. Returns: `{session_id, lyrics, filename, path, project_path, bpm, mood, timestamp}` (lines 340-349)

#### `generate_free_lyrics()`
- **Called by:** `routers/lyrics_router.py:169`
- **Flow:**
  1. Generates lyrics via `generate_np22_lyrics(theme=theme)` (line 358)
  2. **DOES NOT save to project memory** (no `get_or_create_project_memory` call)
  3. **DOES NOT write to disk**
  4. Returns: `{"lyrics": lyrics_text}` (line 362)

#### `refine_lyrics()`
- **Called by:** `routers/lyrics_router.py:187`
- **Flow:**
  1. Calls OpenAI to refine lyrics (lines 438-450)
  2. **DOES NOT save to project memory** (no persistence)
  3. Returns: `{"lyrics": refined_lyrics}` (line 453)

### Provider Integration

**OpenAI Integration:**
- **Model:** `gpt-4o-mini` (lines 100, 214, 442)
- **API Key:** `settings.openai_api_key` (line 27)
- **Fallback:** Returns hardcoded fallback lyrics if API key missing or call fails (lines 79-90, 177-193, 431)

**Environment Variable:**
- **Name:** `OPENAI_API_KEY`
- **Location:** `config/settings.py:38`
- **Required:** No (app continues with fallback lyrics)

---

## 3. Project Memory Storage

### Storage Locations

**File:** `project_memory.py`

#### Project JSON Structure (`/media/{session_id}/project.json`)

```json
{
  "session_id": "...",
  "created_at": "...",
  "updated_at": "...",
  "assets": {
    "lyrics": {
      "url": "/media/{session_id}/lyrics.txt",
      "added_at": "...",
      "metadata": {"genre": "...", "mood": "..."}
    }
  },
  "lyrics": {
    "text": "...",
    "meta": {},
    "completed": true
  },
  "lyrics_text": "..."  // Direct write from generate_lyrics_from_beat
}
```

**Note:** Multiple inconsistent storage locations:
1. `project.assets.lyrics` (object with `url` and `metadata`) - set by `add_asset("lyrics", ...)` in `write_song()` (line 264)
2. `project.lyrics` (object with `text`, `meta`, `completed`) - set by `generate_lyrics_from_beat()` (lines 329-335)
3. `project.lyrics_text` (string) - set by direct JSON write in `generate_lyrics_from_beat()` (line 322)

### Project Memory Methods

**File:** `project_memory.py`

- `add_asset("lyrics", url, metadata)` (line 150): Stores lyrics as asset with URL
- `memory.project_data["lyrics"]` (direct access): Used by `generate_lyrics_from_beat()` to store `{text, meta, completed}`

### Project Retrieval

**File:** `routers/projects_router.py`

- **Endpoint:** `GET /api/projects/{session_id}` (line 11)
- **Returns:** `{"ok": true, "project": project.project_data}` (line 18)
- **Frontend:** `api.getProject(sessionId)` in `frontend/src/utils/api.js:54-63`

---

## 4. Failure Points Analysis

### A) Frontend-to-Backend Mismatch

**Status:** ✅ **NO MISMATCH FOUND**

- **URL:** Correct (`/api/lyrics/from_beat`, `/api/lyrics/free`, `/api/lyrics/refine`)
- **Method:** Correct (POST)
- **Body Keys:** Correct (FormData for beat, JSON for free/refine)
- **Response Wrapper:** Correct (`handleResponse()` extracts `result.data`, which contains `{lyrics: string}`)

**Evidence:**
- `frontend/src/utils/api.js:210`: `return handleResponse(response)` → extracts `result.data`
- `frontend/src/components/stages/LyricsStage.jsx:159`: `result.lyrics` matches expected structure

### B) Backend Errors / Exceptions

**Status:** ⚠️ **PARTIAL - Graceful Fallback**

**Missing API Key:**
- **Location:** `services/lyrics_service.py:92-94`
- **Behavior:** Returns fallback lyrics (non-fatal)
- **Evidence:** `logger.warning("OpenAI API key not configured - using fallback lyrics")`

**Provider Failures:**
- **Location:** `services/lyrics_service.py:110-112`
- **Behavior:** Catches exception, returns fallback lyrics
- **Evidence:** `logger.warning(f"OpenAI lyrics generation failed: {e} - using fallback")`

**File IO Errors:**
- **Location:** `services/lyrics_service.py:304-305` (write to disk)
- **Risk:** No try/except around file write - could raise exception
- **Impact:** Would return 500 error to frontend

### C) Success but No Data (P0 - CRITICAL)

#### Issue 1: `syncProject()` Missing Lyrics Mapping

**Symptom:** Lyrics disappear on page refresh or when navigating away and back to Lyrics stage

**Root Cause:**
- **File:** `frontend/src/utils/api.js:623-679`
- **Function:** `syncProject()`
- **Problem:** Lines 631-661 sync assets (beat, vocals, mix, master, cover_art, release_pack) and metadata (mood, genre, track_title, artist_name), but **DOES NOT sync lyrics**
- **Evidence:** No code mapping `project.assets.lyrics` or `project.lyrics` or `project.lyrics_text` to `updates.lyricsData`

**Expected Behavior:** Should map:
- `project.assets.lyrics.url` → fetch file content → `updates.lyricsData`
- OR `project.lyrics.text` → `updates.lyricsData`
- OR `project.lyrics_text` → `updates.lyricsData`

**Impact:** P0 - User loses lyrics on refresh

#### Issue 2: `generate_free_lyrics()` No Persistence

**Symptom:** Free lyrics (generated without beat) are lost on refresh

**Root Cause:**
- **File:** `services/lyrics_service.py:351-362`
- **Function:** `generate_free_lyrics()`
- **Problem:** Returns `{"lyrics": lyrics_text}` but does NOT:
  - Save to project memory
  - Write to disk
  - Update `project.json`

**Evidence:** Lines 358-362 show only generation and return, no persistence calls

**Impact:** P0 - Free lyrics are ephemeral

#### Issue 3: `refine_lyrics()` No Persistence

**Symptom:** Refined lyrics are lost on refresh

**Root Cause:**
- **File:** `services/lyrics_service.py:364-457`
- **Function:** `refine_lyrics()`
- **Problem:** Returns refined lyrics but does NOT save to project memory

**Evidence:** Lines 450-453 show return only, no `get_or_create_project_memory()` call

**Impact:** P1 - Refined lyrics are ephemeral

#### Issue 4: Inconsistent Storage Locations

**Symptom:** Lyrics may be stored in multiple places, making retrieval ambiguous

**Root Cause:**
- **File:** `services/lyrics_service.py`
- **Problem:**
  - `write_song()` saves to `project.assets.lyrics` via `add_asset()` (line 264)
  - `generate_lyrics_from_beat()` saves to:
    1. `project.json` directly: `project["lyrics_text"]` (line 322)
    2. `project.json` directly: `project["lyrics"]` (file path, line 321)
    3. `memory.project_data["lyrics"]` (object with `text`, line 331)

**Evidence:**
- Line 264: `await memory.add_asset("lyrics", f"/media/{session_id}/lyrics.txt", {...})`
- Lines 321-322: Direct JSON write to `project.json`
- Lines 329-335: Direct write to `memory.project_data["lyrics"]`

**Impact:** P1 - Unclear which location is authoritative

### D) CORS / Auth / Session Gating

**Status:** ✅ **NO ISSUES FOUND**

- **CORS:** Configured in `main.py:130-136` with `allow_credentials=True`
- **Session ID:** Optional in endpoints, generated if missing (`routers/lyrics_router.py:130`)
- **Auth:** No auth middleware blocking lyrics endpoints

---

## 5. Reproduce Locally (Read-Only)

### Environment Variables

**Required for Lyrics Generation:**
- `OPENAI_API_KEY` (optional - falls back to hardcoded lyrics if missing)
  - **Location:** `config/settings.py:38`
  - **Referenced:** `services/lyrics_service.py:27`

**Other Required (for app startup):**
- `BEATOVEN_API_KEY` (for beat generation, not lyrics)
- `BUFFER_TOKEN` (for social, not lyrics)
- `DISTROKID_KEY` (for distribution, not lyrics)

### Startup Commands

**Backend:**
```bash
cd C:\Users\ncpow\Documents\libv1
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**Frontend:**
```bash
cd C:\Users\ncpow\Documents\libv1\frontend
npm install  # if needed
npm run dev
```

### Minimal curl Examples

#### Generate Free Lyrics
```bash
curl -X POST http://localhost:8000/api/lyrics/free \
  -H "Content-Type: application/json" \
  -d '{"theme": "success"}'
```

**Expected Response:**
```json
{
  "ok": true,
  "data": {
    "lyrics": "[Hook]\nRising up from the darkness..."
  },
  "error": null,
  "message": "Lyrics generated"
}
```

#### Generate Lyrics From Beat
```bash
curl -X POST http://localhost:8000/api/lyrics/from_beat \
  -F "file=@path/to/beat.wav" \
  -F "session_id=test-session-123"
```

**Expected Response:**
```json
{
  "ok": true,
  "data": {
    "session_id": "test-session-123",
    "lyrics": "[Hook]\n...",
    "filename": "lyrics.txt",
    "path": "...",
    "project_path": "...",
    "bpm": 140,
    "mood": "dark cinematic emotional",
    "timestamp": "..."
  },
  "error": null,
  "message": "Lyrics generated from beat"
}
```

#### Refine Lyrics
```bash
curl -X POST http://localhost:8000/api/lyrics/refine \
  -H "Content-Type: application/json" \
  -d '{
    "lyrics": "[Hook]\nOriginal lyrics...",
    "instruction": "make it darker",
    "bpm": 140,
    "history": [],
    "structured_lyrics": null,
    "rhythm_map": null
  }'
```

**Expected Response:**
```json
{
  "ok": true,
  "data": {
    "lyrics": "[Hook]\nRefined darker lyrics..."
  },
  "error": null,
  "message": "Lyrics refined"
}
```

### Logs Location

**Backend Logs:**
- **File:** `logs/app.log`
- **Format:** `%(asctime)s - %(name)s - %(levelname)s - %(message)s`

**Error Handling:**
- Uncaught exceptions logged to `logs/app.log` via `UncaughtExceptionMiddleware` (`main.py:65-74`)

---

## 6. Confirmed Breakpoints (Ranked)

### P0 - Critical (Data Loss)

1. **`syncProject()` Missing Lyrics Mapping**
   - **File:** `frontend/src/utils/api.js:623-679`
   - **Lines:** 631-661 (sync logic)
   - **Fix:** Add lyrics mapping to `updates` object:
     ```javascript
     // After line 661, add:
     if (project.assets?.lyrics?.url) {
       // Fetch lyrics file content or use project.lyrics.text
       updates.lyricsData = project.lyrics?.text || project.lyrics_text || null;
     }
     ```

2. **`generate_free_lyrics()` No Persistence**
   - **File:** `services/lyrics_service.py:351-362`
   - **Lines:** 351-362
   - **Fix:** Add project memory save after line 358:
     ```python
     # Add session_id parameter
     # Save to project memory similar to generate_lyrics_from_beat
     ```

### P1 - High (Inconsistency)

3. **`refine_lyrics()` No Persistence**
   - **File:** `services/lyrics_service.py:364-457`
   - **Lines:** 450-453 (return statement)
   - **Fix:** Add project memory save before return

4. **Inconsistent Storage Locations**
   - **Files:** `services/lyrics_service.py` (multiple locations)
   - **Fix:** Standardize on single location (recommend `project.assets.lyrics` with `text` field)

### P2 - Medium (Edge Cases)

5. **File IO Error Handling**
   - **File:** `services/lyrics_service.py:304-305`
   - **Fix:** Wrap file write in try/except

6. **Missing Session ID in `generate_free_lyrics()`**
   - **File:** `services/lyrics_service.py:351-362`
   - **Fix:** Add `session_id` parameter to enable persistence

---

## 7. Smallest Patch Surface

**Files Likely to Change (No Code Edits - Investigation Only):**

1. **`frontend/src/utils/api.js`** (syncProject function)
   - Add lyrics mapping logic (lines 631-661)

2. **`services/lyrics_service.py`**
   - `generate_free_lyrics()`: Add persistence (lines 351-362)
   - `refine_lyrics()`: Add persistence (lines 450-453)
   - Standardize storage location (multiple locations)

3. **`routers/lyrics_router.py`** (if adding session_id to free/refine)
   - Update request models to include `session_id` (lines 25-26, 28-34)

4. **`project_memory.py`** (if standardizing storage)
   - Ensure `add_asset("lyrics", ...)` stores text, not just URL (line 150)

---

## 8. Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│ FRONTEND: LyricsStage.jsx                                        │
│                                                                   │
│  handleGenerateLyrics()                                         │
│    ├─ Path A: api.generateLyricsFromBeat(formData, sessionId)  │
│    └─ Path B: api.generateFreeLyrics(theme)                     │
│                                                                   │
│  Response: {lyrics: string}                                     │
│    ├─ setLyrics(result.lyrics)                                  │
│    └─ updateSessionData({ lyricsData: result.lyrics })          │
│                                                                   │
│  Display: Reads from local state `lyrics`                       │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ API CLIENT: api.js                                               │
│                                                                   │
│  generateLyricsFromBeat() → POST /api/lyrics/from_beat         │
│  generateFreeLyrics() → POST /api/lyrics/free                   │
│  refineLyrics() → POST /api/lyrics/refine                       │
│                                                                   │
│  handleResponse() extracts result.data                           │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ BACKEND ROUTER: lyrics_router.py                                │
│                                                                   │
│  /lyrics/from_beat → generate_lyrics_from_beat()              │
│  /lyrics/free → generate_free_lyrics()                          │
│  /lyrics/refine → refine_lyrics()                               │
│                                                                   │
│  Returns: success_response(data={...})                          │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ SERVICE: lyrics_service.py                                       │
│                                                                   │
│  generate_lyrics_from_beat():                                   │
│    ├─ Detects BPM/mood                                          │
│    ├─ Generates lyrics (OpenAI or fallback)                      │
│    ├─ Writes lyrics.txt to disk                                 │
│    ├─ Writes to project.json (direct)                            │
│    ├─ Saves to project memory                                   │
│    └─ Returns {lyrics: string}                                  │
│                                                                   │
│  generate_free_lyrics():                                         │
│    ├─ Generates lyrics (OpenAI or fallback)                      │
│    └─ Returns {lyrics: string}  ❌ NO PERSISTENCE               │
│                                                                   │
│  refine_lyrics():                                               │
│    ├─ Refines via OpenAI                                         │
│    └─ Returns {lyrics: string}  ❌ NO PERSISTENCE               │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ PROJECT MEMORY: project_memory.py                                │
│                                                                   │
│  Storage Locations (INCONSISTENT):                              │
│    ├─ project.assets.lyrics (object with url)                   │
│    ├─ project.lyrics (object with text, meta, completed)        │
│    └─ project.lyrics_text (string)                              │
│                                                                   │
│  File: /media/{session_id}/project.json                         │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ FRONTEND: api.js syncProject()                                   │
│                                                                   │
│  Reads project via api.getProject(sessionId)                    │
│  Maps: beatFile, vocalFile, mixFile, masterFile, metadata      │
│  ❌ DOES NOT MAP lyricsData                                     │
│                                                                   │
│  Result: Lyrics lost on refresh                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 9. Evidence Citations

### Frontend Component
- **File:** `frontend/src/components/stages/LyricsStage.jsx`
- **Lines:** 109-409 (component), 124-170 (generate handler), 180-223 (refine handler)

### API Client
- **File:** `frontend/src/utils/api.js`
- **Lines:** 196-211 (generateLyricsFromBeat), 214-222 (generateFreeLyrics), 225-240 (refineLyrics), 623-679 (syncProject - MISSING lyrics)

### Backend Router
- **File:** `routers/lyrics_router.py`
- **Lines:** 123-162 (from_beat), 165-180 (free), 183-205 (refine)

### Service Layer
- **File:** `services/lyrics_service.py`
- **Lines:** 278-349 (generate_lyrics_from_beat), 351-362 (generate_free_lyrics - NO PERSISTENCE), 364-457 (refine_lyrics - NO PERSISTENCE)

### Project Memory
- **File:** `project_memory.py`
- **Lines:** 150-164 (add_asset), 120-141 (save)

### Project Retrieval
- **File:** `routers/projects_router.py`
- **Lines:** 11-18 (get_project endpoint)

---

## 10. Summary

**Primary Issue:** Lyrics are generated successfully and displayed in the UI, but are not persisted to project memory in a way that `syncProject()` can retrieve them. This causes data loss on page refresh.

**Root Causes:**
1. `syncProject()` does not map lyrics from project memory to `sessionData.lyricsData`
2. `generate_free_lyrics()` does not save to project memory
3. `refine_lyrics()` does not save to project memory
4. Inconsistent storage locations make retrieval ambiguous

**Minimal Fix:** Add lyrics mapping to `syncProject()` and add persistence to `generate_free_lyrics()` and `refine_lyrics()`.

---

**END OF INVESTIGATION REPORT**


