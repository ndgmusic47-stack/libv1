# VOCAL MODULE FULL BREAKDOWN

**Investigation Date:** 2024  
**Goal:** Determine why the Vocal/Voice module is "totally broken" using repo truth only  
**Investigation Type:** Code analysis - NO runtime testing, NO environment assumptions

---

## A) FRONTEND → VOCAL FLOW (ENTRY TO EXIT)

### Step 1: User Uploads/Records Vocal

**Component:** `frontend/src/components/stages/UploadStage.jsx`

**File Select Handler:**
- **Lines 124-135:** `handleFileSelect()` 
  - Validates file via `validateAudioFile()` (lines 22-39)
  - Calls `uploadFile(file)`

**Drag & Drop Handler:**
- **Lines 58-80:** `handleDrop()`
  - Finds audio file from dropped files
  - Validates via `validateAudioFile()`
  - Calls `uploadFile(audioFile)`

**Recording Handler:**
- **Lines 137-230:** `startRecording()` and `stopRecording()`
  - Creates MediaRecorder with WebM/OGG codecs
  - On stop (lines 196-217): Creates File blob, calls `uploadFile(file)`

### Step 2: Upload Function

**Function:** `uploadFile()` at **lines 82-122**

**Flow:**
1. **Line 101:** Calls `api.uploadRecording(file, sessionId)`
2. **Line 104:** Extracts URL via `normalizeMediaUrl(result.file_path)`
3. **Lines 107-111:** Updates sessionData:
   ```javascript
   updateSessionData({
     vocalFile: fileUrl,
     vocalUploaded: true,
     vocalSource: "guide"
   })
   ```
4. **Lines 114-116:** Auto-completes stage if `completeStage` exists

### Step 3: API Call

**File:** `frontend/src/utils/api.js`  
**Function:** `uploadRecording()` at **lines 215-226**

**API Call:**
- **Endpoint:** `POST ${API_BASE}/media/upload-audio`
- **Method:** FormData with `file` and optional `session_id`
- **Line 225:** Returns `handleResponse(response)`

### Step 4: Response Handling

**Function:** `handleResponse()` at **lines 33-69**

**Flow:**
1. **Lines 35-51:** If `!response.ok`, throws error
2. **Lines 53-65:** Parses JSON, checks `result.ok`, throws if false
3. **Line 68:** Returns `result.data || result`

**Expected Response Shape:**
- Backend returns: `{ok: true, data: {file_url, file_path, session_id}, message: "..."}`
- After `handleResponse`: `{file_url, file_path, session_id}`

### Step 5: URL Normalization

**Function:** `normalizeMediaUrl()` at **lines 5-29**

**Logic:**
- **Line 8:** If URL starts with `/api/media/`, return as-is
- **Lines 10-25:** If URL starts with `/media/`:
  - If `API_BASE` is absolute (http/https), prepends backend origin
  - If `API_BASE` is relative (`/api`), returns URL unchanged
- **Line 28:** Otherwise returns URL as-is

**Example:** `/media/session123/recordings/file.wav` → `/media/session123/recordings/file.wav` (when `API_BASE="/api"`)

### Step 6: State Update

**Lines 107-111 in UploadStage.jsx:**
- Sets `sessionData.vocalFile` to normalized URL
- Sets `sessionData.vocalUploaded = true`
- Sets `sessionData.vocalSource = "guide"`

### Step 7: Audio Playback

**Component:** `UploadStage.jsx`  
**Lines 495-510:** Audio player rendered when `sessionData.vocalFile` exists

```jsx
<audio
  src={sessionData.vocalFile}
  controls
  style={{ width: "100%", marginTop: "0.5rem" }}
>
```

**Expected URL Format:** `/media/{session_id}/recordings/{filename}`

---

## B) BACKEND → VOCAL FLOW (ROUTE TO STORAGE)

### Endpoint 1: Upload Audio

**Router:** `routers/media_router.py`  
**Route:** `@media_router.post("/upload-audio")` at **lines 51-117**

**Prefix Chain:**
- Router prefix: `/api/media` (line 29)
- Route path: `/upload-audio`
- **Final URL:** `/api/media/upload-audio`

**Handler Signature:**
```python
async def upload_audio(
    file: UploadFile = File(...),
    session_id: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
)
```

**Validation Steps:**
1. **Line 78:** `validate_uploaded_file(file)` - performs:
   - Filename sanitization (prevents path traversal)
   - File extension whitelist check
   - File size limit (50MB)
   - MIME type validation (content-based)

**Disk Write Location:**
- **Line 81:** `recordings_dir = MEDIA_DIR / session_id / "recordings"`
- **Line 85:** `file_path = recordings_dir / sanitized_filename`
- **Line 89-90:** Writes file using `aiofiles.open(file_path, "wb")`

**Project Memory Update:**
- **Lines 95-108:**
  ```python
  memory.project_data["assets"]["vocals"] = [{
      "url": file_url,
      "added_at": datetime.now().isoformat(),
      "metadata": {}
  }]
  memory.project_data["assets"]["song"] = {
      "url": file_url,
      "added_at": datetime.now().isoformat(),
      "metadata": {"source": "upload"}
  }
  ```

**Response:**
- **Lines 110-117:** Returns `success_response()` with:
  ```python
  data={
      "session_id": session_id,
      "file_url": file_url,  # "/media/{session_id}/recordings/{filename}"
      "file_path": file_url,  # Same as file_url
  }
  ```

### Endpoint 2: Generate AI Vocal (RVC)

**Router:** `routers/media_router.py`  
**Route:** `@voice_router.post("/generate-ai-vocal")` at **lines 366-505**

**Prefix Chain:**
- Router prefix: `/api/voice` (line 363)
- Route path: `/generate-ai-vocal`
- **Final URL:** `/api/voice/generate-ai-vocal`

**Handler Signature:**
```python
async def generate_ai_vocal(
    request: GenerateAiVocalRequest = Body(...),
    db: AsyncSession = Depends(get_db),
)
```

**Input:** `{session_id: str, speaker_id?: int, transpose?: float}`

**Guide Vocal Discovery:**
- **Lines 388-399:** Checks `memory.project_data["assets"]["vocals"][-1]` for URL
- **Lines 402-415:** Falls back to latest file in `recordings_dir` by mtime
- **Line 419:** Returns error if no guide vocal found

**RVC Processing:**
- **Lines 424-465:** Uses `RvcGradioService` to convert guide vocal
- **Line 456:** Output saved as `recordings_dir / "ai_vocals.wav"`

**Project Memory Update:**
- **Lines 477-491:**
  ```python
  memory.project_data["assets"]["vocals"] = [{
      "url": vocal_url,  # "/media/{session_id}/recordings/ai_vocals.wav"
      "added_at": datetime.now().isoformat(),
      "metadata": {"source": "rvc"}
  }]
  memory.project_data["assets"]["song"] = {
      "url": vocal_url,
      "added_at": datetime.now().isoformat(),
      "metadata": {"source": "rvc"}
  }
  ```

**Response:**
- **Lines 495-501:** Returns `success_response()` with:
  ```python
  data={
      "session_id": session_id,
      "vocal_url": vocal_url,  # "/media/{session_id}/recordings/ai_vocals.wav"
  }
  ```

### Endpoint 3: Generate Song (Replicate YuE)

**Router:** `routers/media_router.py`  
**Route:** `@media_router.post("/generate/song")` at **lines 219-359**

**Prefix Chain:**
- Router prefix: `/api/media` (line 29)
- Route path: `/generate/song`
- **Final URL:** `/api/media/generate/song`

**Handler Signature:**
```python
async def generate_song(
    request: GenerateSongRequest = Body(...),
    db: AsyncSession = Depends(get_db),
)
```

**Project Memory Update:**
- **Lines 329-341:**
  ```python
  memory.project_data["assets"]["song"] = {
      "url": file_url,
      "added_at": datetime.now().isoformat(),
      "metadata": {"source": "ai_song_replicate_yue"}
  }
  memory.project_data["assets"]["vocals"] = [{
      "url": file_url,
      "added_at": datetime.now().isoformat(),
      "metadata": {"source": "ai_song_replicate_yue"}
  }]
  ```

---

## C) PROJECT MEMORY CONTRADICTIONS

### Write Operations

**Location 1: Upload Audio**
- **File:** `routers/media_router.py`
- **Lines 98-107:**
  - Writes `assets.vocals = [{url, added_at, metadata}]` (ARRAY)
  - Writes `assets.song = {url, added_at, metadata}` (OBJECT)

**Location 2: Generate AI Vocal (RVC)**
- **File:** `routers/media_router.py`
- **Lines 477-491:**
  - Writes `assets.vocals = [{url, added_at, metadata}]` (ARRAY)
  - Writes `assets.song = {url, added_at, metadata}` (OBJECT)

**Location 3: Generate Song (Replicate)**
- **File:** `routers/media_router.py`
- **Lines 329-341:**
  - Writes `assets.vocals = [{url, added_at, metadata}]` (ARRAY)
  - Writes `assets.song = {url, added_at, metadata}` (OBJECT)

**Location 4: Generate Vocal (gTTS)**
- **File:** `routers/media_router.py`
- **Lines 191-202:**
  - Writes `assets.vocals = [{url, added_at, metadata}]` (ARRAY)
  - Writes `assets.song = {url, added_at, metadata}` (OBJECT)

**Summary of Writes:**
- ✅ `assets.vocals` = ARRAY (consistent)
- ✅ `assets.song` = OBJECT (consistent)

### Read Operations

**Location: syncProject()**
- **File:** `frontend/src/utils/api.js`
- **Lines 643-659:**

**Vocal File Read Logic:**
```javascript
// Priority 1: project.assets.vocals[0]
if (project.assets.vocals && project.assets.vocals.length > 0) {
  const vocal = project.assets.vocals[0];
  const chosenValue = vocal.url || vocal.path;
  if (chosenValue) {
    updates.vocalFile = normalizeMediaUrl(chosenValue);
  }
}
// Priority 2: Fallback to stems
else if (project.assets.stems && project.assets.stems.length > 0 && project.assets.stems[0]?.url) {
  updates.vocalFile = normalizeMediaUrl(project.assets.stems[0].url);
}

// Song file read
if (project.assets?.song?.url) {
  updates.songFile = normalizeMediaUrl(project.assets.song.url);
  if (!updates.vocalFile) updates.vocalFile = updates.songFile; // compat fallback
}
```

**Analysis:**
- ✅ Reads `assets.vocals[0].url` - **MATCHES** write format
- ✅ Reads `assets.song.url` - **MATCHES** write format
- ✅ Fallback chain: `vocals[0]` → `stems[0]` → `song.url`

**Status:** **MATCH** - Write and read formats are consistent.

---

## D) RESPONSE SHAPE & ERROR SURFACE

### Endpoint 1: /api/media/upload-audio

**Backend Response:**
- **File:** `routers/media_router.py`, lines 110-117
- **Shape:** 
  ```json
  {
    "ok": true,
    "data": {
      "session_id": "...",
      "file_url": "/media/...",
      "file_path": "/media/..."
    },
    "error": null,
    "message": "Vocal uploaded"
  }
  ```

**Frontend Parsing:**
- **File:** `frontend/src/utils/api.js`, line 225
- **Flow:** `handleResponse(response)` → returns `result.data || result`
- **Result:** `{session_id, file_url, file_path}`
- **Usage:** `UploadStage.jsx` line 104: `result.file_path`

**Analysis:**
- ✅ `handleResponse` extracts `data` wrapper
- ✅ Frontend accesses `result.file_path` correctly
- ✅ No error path identified

### Endpoint 2: /api/voice/generate-ai-vocal

**Backend Response:**
- **File:** `routers/media_router.py`, lines 495-501
- **Shape:**
  ```json
  {
    "ok": true,
    "data": {
      "session_id": "...",
      "vocal_url": "/media/..."
    },
    "error": null,
    "message": "AI vocal generated"
  }
  ```

**Frontend Parsing:**
- **File:** `frontend/src/utils/api.js`, lines 242-259
- **Flow:** `handleResponse(response)` → returns `result`
- **Result:** `{session_id, vocal_url}`
- **Usage:** Lines 254-258: Checks `result.vocal_url`, normalizes via `normalizeMediaUrl()`

**Analysis:**
- ✅ `handleResponse` extracts `data` wrapper
- ✅ Frontend accesses `result.vocal_url` correctly
- ✅ Normalization applied

### Endpoint 3: /api/media/generate/song

**Backend Response:**
- **File:** `routers/media_router.py`, lines 345-352
- **Shape:**
  ```json
  {
    "ok": true,
    "data": {
      "session_id": "...",
      "file_url": "/media/...",
      "file_path": "/media/..."
    },
    "error": null,
    "message": "AI song generated"
  }
  ```

**Frontend Parsing:**
- **File:** `frontend/src/components/stages/UploadStage.jsx`, line 274
- **Flow:** `api.generateSong()` → `handleResponse(response)`
- **Usage:** Line 277: `result.file_path`

**Analysis:**
- ✅ Response shape matches upload endpoint
- ✅ Frontend parses correctly

### Error Handling

**handleResponse() Error Cases:**
- **Lines 35-51:** HTTP error status → throws Error
- **Lines 56-65:** `result.ok === false` → throws Error
- **Line 53:** JSON parse failure → `await response.json().catch(() => ({}))` → returns `{}`

**Critical Error Case:**
- **Line 53:** If JSON parse fails, returns `{}`
- **Line 68:** `return result.data || result` → returns `{}`
- **UploadStage.jsx line 104:** `result.file_path` → **`undefined`**
- **Line 108:** `vocalFile: normalizeMediaUrl(undefined)` → `undefined`
- **Line 502:** `<audio src={undefined}>` → **BROKEN**

**Status:** **BROKEN** - Silent failure on JSON parse error.

---

## E) MEDIA SERVING & PLAYBACK PATH

### Backend Static Mount

**File:** `main.py`  
**Line 145:** 
```python
app.mount("/media", StaticFiles(directory=str(MEDIA_DIR)), name="media")
```

**Mount Order:**
- **Line 145:** `/media` mounted BEFORE API routers (line 208)
- Static file mount takes precedence over route handlers

**Directory Structure:**
- Files stored at: `MEDIA_DIR / session_id / recordings / filename`
- Served at: `/media/{session_id}/recordings/{filename}`

### Returned URL Format

**Backend Returns:**
- Upload: `file_url = "/media/{session_id}/recordings/{sanitized_filename}"`
- RVC: `vocal_url = "/media/{session_id}/recordings/ai_vocals.wav"`

**Frontend Receives:**
- After `handleResponse`: `{file_url: "/media/...", file_path: "/media/..."}`
- After normalization: `/media/...` (unchanged if `API_BASE="/api"`)

### Frontend URL Consumption

**Component:** `UploadStage.jsx`  
**Line 502:**
```jsx
<audio src={sessionData.vocalFile} controls />
```

**Expected:** `sessionData.vocalFile = "/media/session123/recordings/file.wav"`

### URL Resolution

**Browser Request:**
- If page is at `http://localhost:5173/` (dev) or `https://app.example.com/` (prod)
- Audio src `/media/...` → relative URL
- Resolves to: `http://localhost:5173/media/...` or `https://app.example.com/media/...`

**Backend Serving:**
- FastAPI serves `/media/...` via StaticFiles mount
- Should resolve correctly IF backend and frontend share same origin

**Potential Issue:**
- If frontend and backend are on different origins, relative `/media/...` URLs won't work
- **NOT VERIFIABLE** without runtime environment knowledge

**Status:** **UNVERIFIABLE** - Depends on deployment configuration (same-origin vs CORS).

---

## F) FAILURE POINT MATRIX

| Step | Component | Expected | Actual (from code) | Status |
|------|-----------|----------|-------------------|--------|
| 1. File Upload | `UploadStage.uploadFile()` | Upload file via FormData | ✅ Calls `api.uploadRecording(file, sessionId)` | WORKING |
| 2. API Request | `api.uploadRecording()` | POST to `/api/media/upload-audio` | ✅ POST to `${API_BASE}/media/upload-audio` | WORKING |
| 3. Backend Validation | `media_router.upload_audio()` | Validate file (size, type, sanitize) | ✅ `validate_uploaded_file()` called | WORKING |
| 4. File Storage | `media_router.upload_audio()` | Save to `media/{session_id}/recordings/` | ✅ Saved to `recordings_dir / sanitized_filename` | WORKING |
| 5. Project Memory Write | `media_router.upload_audio()` | Write `assets.vocals` and `assets.song` | ✅ Writes both with correct structure | WORKING |
| 6. Backend Response | `media_router.upload_audio()` | Return `{file_url, file_path}` | ✅ Returns `success_response(data={...})` | WORKING |
| 7. Response Parsing | `api.handleResponse()` | Extract `data` wrapper | ✅ Returns `result.data \|\| result` | WORKING |
| 8. URL Extraction | `UploadStage.uploadFile()` | Get URL from `result.file_path` | ✅ `normalizeMediaUrl(result.file_path)` | WORKING |
| 9. URL Normalization | `normalizeMediaUrl()` | Convert `/media/...` to consumable URL | ✅ Returns unchanged if `API_BASE="/api"` | WORKING* |
| 10. State Update | `updateSessionData()` | Set `vocalFile` to URL | ✅ Sets `vocalFile: fileUrl` | WORKING |
| 11. Audio Playback | `<audio src={vocalFile}>` | Play audio from URL | ✅ Uses `sessionData.vocalFile` as src | WORKING* |
| 12. Media Serving | FastAPI StaticFiles | Serve `/media/...` requests | ✅ Mounted at `/media` before routers | WORKING* |

**Legend:**
- ✅ **WORKING**: Code path is correct
- ⚠️ **WORKING***: Correct but depends on deployment (same-origin)
- ❌ **BROKEN**: Code issue identified

### Critical Failure Points

**1. JSON Parse Failure (Step 7)**
- **Location:** `api.js:53`
- **Issue:** If `response.json()` fails, returns `{}` silently
- **Impact:** `result.file_path` becomes `undefined`
- **Status:** **BROKEN**

**2. URL Resolution (Steps 9, 11, 12)**
- **Issue:** Relative URLs require same-origin backend/frontend
- **Impact:** Audio playback fails if cross-origin
- **Status:** **UNVERIFIABLE** (needs runtime check)

---

## G) ROOT CAUSE CANDIDATES (NO FIXES)

### Candidate 1: JSON Parse Failure Silent Error

**File:** `frontend/src/utils/api.js`  
**Line 53:** `const result = await response.json().catch(() => ({}))`

**What Breaks:**
- If backend returns invalid JSON or empty body, `result = {}`
- Line 68: `return result.data || result` → returns `{}`
- UploadStage line 104: `result.file_path` → **`undefined`**
- Line 108: `vocalFile: normalizeMediaUrl(undefined)` → **`undefined`**
- Line 502: `<audio src={undefined}>` → **Audio element broken, no error shown**

**Blocks:**
- ❌ Upload (silent failure)
- ❌ Playback (invalid src)

**Evidence:**
- Code path exists, no error logging for this case

---

### Candidate 2: Response Field Mismatch (Upload)

**File:** `frontend/src/components/stages/UploadStage.jsx`  
**Line 104:** `const fileUrl = normalizeMediaUrl(result.file_path);`

**Backend Returns:**
- `routers/media_router.py:114`: `"file_path": file_url`

**Frontend Expects:**
- `result.file_path`

**Analysis:**
- ✅ **MATCHES** - Backend provides `file_path`, frontend reads it
- **Status:** **NOT A ROOT CAUSE**

---

### Candidate 3: Response Field Mismatch (AI Vocal)

**File:** `frontend/src/components/stages/UploadStage.jsx`  
**Line 444:** `const vocalUrl = result.vocal_url || result.data?.vocal_url;`

**Backend Returns:**
- `routers/media_router.py:498`: `"vocal_url": vocal_url` (inside `data` wrapper)
- After `handleResponse`: `result.vocal_url` should exist

**Analysis:**
- ✅ **MATCHES** - `handleResponse` extracts `data`, so `result.vocal_url` exists
- **Status:** **NOT A ROOT CAUSE**

---

### Candidate 4: Project Memory Read/Write Mismatch

**Write Format:**
- `assets.vocals = [{url, added_at, metadata}]` (array)
- `assets.song = {url, added_at, metadata}` (object)

**Read Format:**
- `syncProject()` reads `assets.vocals[0].url` and `assets.song.url`

**Analysis:**
- ✅ **MATCHES** - Read logic matches write structure
- **Status:** **NOT A ROOT CAUSE**

---

### Candidate 5: URL Normalization Failure

**File:** `frontend/src/utils/api.js`  
**Lines 5-29:** `normalizeMediaUrl()`

**Logic:**
- If URL starts with `/media/` and `API_BASE` is relative (`/api`), returns URL unchanged
- Returns `/media/...` as-is

**Issue:**
- Relative URLs only work if frontend and backend share same origin
- If frontend is `https://app.example.com` and backend is `https://api.example.com`, `/media/...` resolves to `https://app.example.com/media/...` (WRONG)

**What Breaks:**
- Audio `<audio src="/media/...">` requests wrong origin
- Returns 404 or CORS error

**Blocks:**
- ❌ Playback (wrong URL resolution)

**Evidence:**
- Code assumes same-origin, no absolute URL construction for cross-origin

---

### Candidate 6: Missing Error Handling in UploadStage

**File:** `frontend/src/components/stages/UploadStage.jsx`  
**Lines 101-104:**
```javascript
const result = await api.uploadRecording(file, sessionId);
const fileUrl = normalizeMediaUrl(result.file_path);
```

**Issue:**
- No check if `result.file_path` exists
- If backend returns different shape or `file_path` is missing, `fileUrl` becomes `undefined`
- No validation before setting state

**What Breaks:**
- If `result.file_path` is missing, `vocalFile` becomes `undefined`
- Audio element fails silently

**Blocks:**
- ❌ Playback (invalid state)

**Evidence:**
- Code lacks defensive checks

---

### Candidate 7: Static File Mount Order Issue

**File:** `main.py`  
**Line 145:** `app.mount("/media", StaticFiles(...), name="media")`  
**Line 208:** `app.include_router(media_router)` (prefix `/api/media`)

**Analysis:**
- Static mount `/media` comes BEFORE router inclusion
- Router has prefix `/api/media`, so no conflict
- **Status:** **NOT A ROOT CAUSE** (mount order is correct)

---

### Candidate 8: handleResponse Double-Wrap Issue

**File:** `frontend/src/utils/api.js`  
**Line 68:** `return result.data || result;`

**Backend Response:**
- `{ok: true, data: {...}}`

**After handleResponse:**
- Returns `{...}` (data unwrapped)

**Issue:**
- If backend accidentally returns `{ok: true, data: {data: {...}}}`, double-wrap occurs
- **Status:** **UNLIKELY** - Backend consistently uses `success_response()` helper

---

## H) SEARCH LOG

### Grep Searches
```
rg uploadRecording
rg uploadVocal
rg vocalFile
rg songFile
rg assets.vocals
rg assets.song
rg assets.stems
rg StaticFiles
rg app.mount
rg generate-ai-vocal
rg generateAiVocal
rg <audio
rg audio.src
```

### Semantic Searches
1. "How does vocal upload work in the frontend? Where are uploadRecording and uploadVocal functions?"
2. "What backend routes handle vocal upload and audio file uploads?"
3. "How is assets.vocals or assets.song written to project memory?"
4. "How is vocal audio served and played back in the frontend? Where are audio URLs used?"
5. "Where is the voice router or generate-ai-vocal endpoint implemented?"
6. "How does syncProject read assets.vocals and assets.song from project memory?"

### Files Read
- `frontend/src/utils/api.js` (full)
- `frontend/src/components/stages/UploadStage.jsx` (full)
- `routers/media_router.py` (full)
- `main.py` (full)
- `backend/utils/responses.py` (full)
- `project_memory.py` (sections: 140-220, 340-416)
- `routers/projects_router.py` (full)

---

## SUMMARY

### Top 5 Root Cause Candidates (Code-Backed)

1. **JSON Parse Failure Silent Error** (`api.js:53`)
   - Returns `{}` on JSON parse failure
   - Causes `result.file_path` to be `undefined`
   - Blocks: Upload (silent), Playback (invalid src)

2. **URL Normalization Assumes Same-Origin** (`api.js:5-29`)
   - Returns relative URLs `/media/...` unchanged
   - Fails if frontend/backend are different origins
   - Blocks: Playback (wrong URL resolution)

3. **Missing Defensive Checks in UploadStage** (`UploadStage.jsx:101-104`)
   - No validation that `result.file_path` exists
   - Sets `vocalFile` to `undefined` if field missing
   - Blocks: Playback (invalid state)

4. **Response Shape Mismatch (Potential)** (`media_router.py` vs `api.js`)
   - Backend returns `{data: {file_url, file_path}}`
   - `handleResponse` extracts `data`
   - Frontend reads `result.file_path` ✅ (WORKS if response is valid)
   - **Status:** NOT A ROOT CAUSE (verified match)

5. **Error Handling in generateAiVocal** (`UploadStage.jsx:443-454`)
   - Line 444: Accesses `result.vocal_url || result.data?.vocal_url`
   - `handleResponse` already extracts `data`, so `result.data` is redundant
   - If `result.vocal_url` missing, falls back to `result.data?.vocal_url` (always undefined after handleResponse)
   - **Status:** REDUNDANT BUT NOT BROKEN (fallback never triggers)

### Critical Issues Ranking

1. **HIGHEST PRIORITY:** JSON parse failure silent error
2. **HIGH PRIORITY:** URL normalization same-origin assumption
3. **MEDIUM PRIORITY:** Missing defensive checks in UploadStage

---

## INVESTIGATION COMPLETE

**No fixes applied. Investigation only.**
