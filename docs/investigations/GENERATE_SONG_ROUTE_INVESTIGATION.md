# Generate Song Route Investigation

**Date:** 2024-12-19  
**Scope:** `routers/media_router.py` `/api/media/generate/song` endpoint + frontend calls  
**Type:** Investigation Only (No Code Changes)

---

## 1. True Route + Handler

### Route Definition
- **Decorator:** `@media_router.post("/generate/song")` (line 219)
- **Router Prefix:** `/api/media` (line 29)
- **Full Path:** `/api/media/generate/song` ✅
- **Handler Name:** `generate_song` (line 220)

### Request Model
```python
class GenerateSongRequest(BaseModel):
    session_id: str                    # Required
    lyrics: Optional[str] = None        # Optional
    lyrics_url: Optional[str] = None    # Optional
    style: Optional[str] = "motivational hip-hop / rock"  # Optional
```
**Location:** `routers/media_router.py:37-41`

### Response Shape
```python
success_response(
    data={
        "session_id": session_id,
        "file_url": file_url,      # e.g., "/media/{session_id}/recordings/ai_song_{timestamp}.mp3"
        "file_path": file_url,     # Same as file_url
    },
    message="AI song generated"
)
```
**Location:** `routers/media_router.py:345-352`

---

## 2. Session ID Usage

### Extraction Point
**Line 230:** `session_id = request.session_id`
- Extracted directly from request body
- **NO VALIDATION** - Used as-is without sanitization

### Filesystem Path Construction
**Primary usage locations:**

1. **Line 235:** Project memory initialization
   ```python
   memory = await get_or_create_project_memory(session_id, MEDIA_DIR, user_id, db)
   ```
   - Passes `session_id` to `ProjectMemory.__init__()`
   - Inside `ProjectMemory`: `self.session_path = media_dir / session_id` (line 37)
   - Creates directory: `MEDIA_DIR / session_id` (no validation)

2. **Line 310:** Recordings directory creation
   ```python
   recordings_dir = MEDIA_DIR / session_id / "recordings"
   recordings_dir.mkdir(parents=True, exist_ok=True)
   ```
   - **CRITICAL:** Direct path construction without sanitization
   - Vulnerable to path traversal if `session_id` contains `../` or similar

3. **Line 317:** File URL construction
   ```python
   file_url = f"/media/{session_id}/recordings/{filename}"
   ```
   - Used in response and project memory
   - No validation on `session_id` format

### Security Guards

**❌ NO VALIDATION EXISTS**

- No `SessionManager.get_user()` call
- No regex validation (despite `utils/session_manager.py` having `VALID_SESSION_ID_PATTERN`)
- No path sanitization before filesystem operations
- No check for path traversal sequences (`..`, `/`, `\`)

**Comparison with other endpoints:**
- `upload_audio` (line 51): Generates UUID if missing, but no validation if provided
- `generate_vocal` (line 120): No validation
- `generate_ai_vocal` (line 366): No validation

**Available but unused:**
- `utils/session_manager.py` has `SessionManager.get_user()` with validation (lines 25-61)
- Pattern: `VALID_SESSION_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_-]{1,128}$')` (line 15)

---

## 3. External Calls

### Replicate Client
**Service:** `services/replicate_song_service.py`
**Call:** `await replicate_generate_song_yue(lyrics_text, request.style)` (line 289)

**Details:**
- Uses Replicate Python client (`replicate.Client`)
- Model: `"fofr/yue"`
- Input: `{"lyrics": lyrics_text}` (style parameter not currently sent)
- Returns: Audio URL (string)
- **No timeout configured** in service (relies on Replicate API defaults)
- **No retries** configured

**Error handling:**
- Raises `ValueError` if `REPLICATE_API_TOKEN` not set
- Raises generic `Exception` on generation failure
- Caught at line 354-359 in router

### URL Download
**Client:** `httpx.AsyncClient` (line 297)
**Configuration:**
- `follow_redirects=True`
- `timeout=300.0` (5 minutes)
- **No retries** configured
- **No size limit** on download (potential DoS risk)

**Usage:**
```python
async with httpx.AsyncClient(follow_redirects=True, timeout=300.0) as client:
    response = await client.get(audio_url)
    response.raise_for_status()
    audio_content = response.content
```

**Hazards:**
- Large file downloads could exhaust memory
- No validation of `audio_url` format (could be any URL)
- 300s timeout may be insufficient for large files

---

## 4. Frontend Calls

### API Function
**File:** `frontend/src/utils/api.js`
**Function:** `generateSong(sessionId, lyrics = null, style = null)` (line 238)

**Implementation:**
```javascript
generateSong: async (sessionId, lyrics = null, style = null) => {
  const response = await fetch(`${API_BASE}/media/generate/song`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ 
      session_id: sessionId, 
      lyrics: lyrics,
      style: style
    }),
  });
  return handleResponse(response);
},
```

**API_BASE:** `/api` (line 2)
**Full URL:** `/api/media/generate/song` ✅ **MATCHES backend route**

### Usage in Components
**File:** `frontend/src/components/stages/UploadStage.jsx`
**Function:** `handleGenerateSong()` (line 257)

**Flow:**
1. Checks if user has permission (`allowed` check, line 258)
2. Extracts lyrics text via `getLyricsText()` (line 263)
3. Validates lyrics exist (line 264-267)
4. Calls `api.generateSong(sessionId, lyricsText)` (line 274)
5. Normalizes response URL and updates session data (line 277-279)

**No mismatches found:**
- Frontend sends `session_id`, `lyrics`, `style` ✅
- Backend expects `session_id`, `lyrics`, `lyrics_url`, `style` ✅
- All frontend-sent fields match backend model ✅

---

## 5. Insertion Point for Guard

### Recommended Location
**After line 230, before line 233 (try block):**

```python
session_id = request.session_id
user_id = None

# INSERT VALIDATION HERE (before try:)
# Validate session_id format to prevent path traversal
from utils.session_manager import SessionManager
if not SessionManager.get_user(session_id):
    return error_response("Invalid session_id format or session does not exist", status=400)

try:
    # Load project memory
    memory = await get_or_create_project_memory(session_id, MEDIA_DIR, user_id, db)
    # ... rest of handler
```

**Why this location:**
- After extraction, before any filesystem operations
- Before `get_or_create_project_memory()` call (which creates directories)
- Early return prevents any side effects
- Consistent with validation pattern in other routers (if implemented)

**Alternative (more permissive):**
- Validate format only (allow new sessions)
- Use regex directly: `VALID_SESSION_ID_PATTERN.match(session_id)`
- Don't require directory existence (since `get_or_create_project_memory` creates it)

---

## 6. Hazards & Contradictions

### Critical Hazards

1. **Path Traversal Vulnerability**
   - `session_id` used directly in `MEDIA_DIR / session_id / "recordings"`
   - Malicious input like `../../../etc/passwd` could escape media directory
   - **No sanitization** before path construction

2. **Session ID Format Not Enforced**
   - Request model requires `session_id: str` but no format validation
   - Could accept empty strings, special characters, or extremely long values
   - `ProjectMemory` will create directory with any string value

3. **No Download Size Limit**
   - `httpx` download has no `max_bytes` or size check
   - Large Replicate responses could exhaust memory
   - No validation of `audio_content` size before writing

4. **Inconsistent Validation**
   - `utils/session_manager.py` exists with validation logic
   - Not used in `generate_song` handler
   - Other endpoints in same router also lack validation

### Contradictions

1. **Session ID Required vs Optional**
   - `GenerateSongRequest.session_id: str` is **required** (no `Optional`)
   - But no validation ensures it's valid format
   - Contradiction: Required but not validated

2. **Project Memory Creates vs Validates**
   - `get_or_create_project_memory()` will **create** directory if missing
   - But validation would check if directory **exists**
   - If validation requires existence, it prevents new sessions
   - If validation only checks format, it allows new sessions (current behavior)

3. **Style Parameter**
   - Frontend sends `style` parameter
   - Backend accepts it in `GenerateSongRequest`
   - But `replicate_generate_song_yue()` doesn't use it (service only sends `lyrics`)
   - Parameter accepted but ignored

### Minor Issues

1. **Error Messages**
   - Generic error messages don't distinguish validation vs generation failures
   - Line 356: `error_response(str(e), status=400)` - exposes internal errors

2. **Timeout Configuration**
   - 300s timeout hardcoded (line 297)
   - No configuration or environment variable
   - May be insufficient for slow Replicate responses

3. **File Extension Detection**
   - Simple string matching (lines 304-307)
   - Doesn't handle query parameters or complex URLs
   - Defaults to `.mp3` if no match

---

## Summary

### True Route Hit by Frontend
✅ **CONFIRMED:** Frontend calls `/api/media/generate/song` which matches backend route exactly.

### Insertion Point
**Lines 230-232** (after `session_id = request.session_id`, before `try:` block)

### Hazards
1. **CRITICAL:** Path traversal vulnerability - no `session_id` sanitization
2. **HIGH:** No download size limits - memory exhaustion risk
3. **MEDIUM:** Inconsistent validation - SessionManager exists but unused
4. **LOW:** Style parameter accepted but ignored

### Recommendations
1. Add `SessionManager.get_user(session_id)` validation before filesystem operations
2. Add download size limit (e.g., 100MB) to `httpx` client
3. Consider making validation format-only (not existence-based) to allow new sessions
4. Add retry logic for Replicate API calls
5. Validate `audio_url` format before downloading


