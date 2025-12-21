# Vocal Module Runtime Truth Investigation

**Date:** 2024-12-19  
**Mode:** CTO Investigation (Read-Only)  
**Goal:** Remove ALL assumptions about why the Vocal module "doesn't work" by collecting repo-backed runtime entrypoints + environment truth + error-surface truth.

---

## Searches Run

The following ripgrep patterns were executed to gather evidence:

- `upload-audio|upload.*vocal|/media` (case-insensitive)
- `API_BASE|api.*base|baseURL` (case-insensitive)
- `vite.*proxy|proxy.*vite` (case-insensitive)
- `StaticFiles|CORSMiddleware|allow_origins|credentials` (case-insensitive)
- `Depends.*auth|Depends.*session|get_current_user|require.*auth` (case-insensitive)

---

## 1) CURRENT ENVIRONMENT TRUTH (repo-config + expected origins)

### Frontend API_BASE Configuration

**File:** `frontend/src/utils/api.js:2`
```javascript
const API_BASE = '/api';
```

**Finding:** API_BASE is hardcoded to `/api` (relative path). No environment variable or conditional logic exists to change this value between dev and production.

### Vite Proxy Configuration

**File:** `frontend/vite.config.js` (full file)
```javascript
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
```

**Finding:** NO Vite proxy is configured. The comment in `api.js:1` says "Use backend proxy via Vite dev server" but `vite.config.js` has no `server.proxy` section.

### Backend CORS Configuration

**File:** `main.py:130-136`
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**File:** `config/settings.py:54`
```python
frontend_url: Optional[str] = Field(default="http://localhost:5173", alias="FRONTEND_URL")
```

**Finding:** CORS is configured with:
- `allow_origins=[settings.frontend_url]` (single origin from `FRONTEND_URL` env var, defaults to `http://localhost:5173`)
- `allow_credentials=True` (cookies/credentials required)
- `allow_methods=["*"]` (all HTTP methods allowed)
- `allow_headers=["*"]` (all headers allowed)

### Expected Request Origins

**Dev Environment:**
- Frontend origin: `http://localhost:5173` (Vite default)
- API requests: `http://localhost:5173/api/...` (relative to frontend origin)
- **PROBLEM:** No Vite proxy configured, so `/api/...` requests will fail in dev unless backend is running on same origin or CORS allows it

**Production Environment (Render):**
- Frontend origin: Value of `FRONTEND_URL` environment variable (must be set in Render)
- API requests: `${FRONTEND_URL}/api/...` (relative to frontend origin)
- **ASSUMPTION:** In production, frontend is served from same origin as backend (SPA mount at `main.py:230`), so relative paths work

**Summary:**
- Dev: Frontend at `http://localhost:5173`, API_BASE=`/api` → requests go to `http://localhost:5173/api/...` (NO PROXY → will fail unless backend CORS allows `http://localhost:5173`)
- Prod: Frontend served from backend root, API_BASE=`/api` → requests go to `${BACKEND_ORIGIN}/api/...` (works if same-origin)

---

## 2) REQUEST PATH TRUTH (exact URLs the browser will hit)

### uploadRecording() Endpoint

**Frontend Call:** `frontend/src/utils/api.js:215-226`
```javascript
uploadRecording: async (file, sessionId = null) => {
  const formData = new FormData();
  formData.append('file', file);
  if (sessionId) formData.append('session_id', sessionId);

  const response = await fetch(`${API_BASE}/media/upload-audio`, {
    method: "POST",
    credentials: "include",
    body: formData,
  });
  return handleResponse(response);
},
```

**Backend Route:** `routers/media_router.py:29`
```python
media_router = APIRouter(prefix="/api/media")
```

**Backend Handler:** `routers/media_router.py:51`
```python
@media_router.post("/upload-audio")
async def upload_audio(
    file: UploadFile = File(...),
    session_id: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
```

**Router Mount:** `main.py:208`
```python
app.include_router(media_router)
```

**Computed Final URLs:**
- **Dev:** `http://localhost:5173/api/media/upload-audio` (relative to frontend origin, no proxy)
- **Prod:** `${BACKEND_ORIGIN}/api/media/upload-audio` (relative to backend origin where frontend is served)

### generateSong() Endpoint

**Frontend Call:** `frontend/src/utils/api.js:228-240`
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

**Backend Handler:** `routers/media_router.py:219`
```python
@media_router.post("/generate/song")
async def generate_song(
    request: GenerateSongRequest = Body(...),
    db: AsyncSession = Depends(get_db),
):
```

**Computed Final URLs:**
- **Dev:** `http://localhost:5173/api/media/generate/song`
- **Prod:** `${BACKEND_ORIGIN}/api/media/generate/song`

### generateAiVocal() Endpoint

**Frontend Call:** `frontend/src/utils/api.js:242-259`
```javascript
generateAiVocal: async (sessionId, speakerId = 0, transpose = 0) => {
  const response = await fetch(`${API_BASE}/voice/generate-ai-vocal`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ 
      session_id: sessionId, 
      speaker_id: speakerId,
      transpose: transpose
    }),
  });
  const result = await handleResponse(response);
  // Normalize vocal_url via normalizeMediaUrl
  if (result.vocal_url) {
    return { vocal_url: normalizeMediaUrl(result.vocal_url) };
  }
  return result;
},
```

**Backend Router:** `routers/media_router.py:363`
```python
voice_router = APIRouter(prefix="/api/voice")
```

**Backend Handler:** `routers/media_router.py:366`
```python
@voice_router.post("/generate-ai-vocal")
async def generate_ai_vocal(
    request: GenerateAiVocalRequest = Body(...),
    db: AsyncSession = Depends(get_db),
):
```

**Router Mount:** `main.py:209`
```python
app.include_router(voice_router)
```

**Computed Final URLs:**
- **Dev:** `http://localhost:5173/api/voice/generate-ai-vocal`
- **Prod:** `${BACKEND_ORIGIN}/api/voice/generate-ai-vocal`

### Media Playback URLs

**Backend Response:** `routers/media_router.py:86`
```python
file_url = f"/media/{session_id}/recordings/{sanitized_filename}"
```

**Backend Static Mount:** `main.py:145`
```python
app.mount("/media", StaticFiles(directory=str(MEDIA_DIR)), name="media")
```

**Media Directory:** `config/settings.py:18`
```python
MEDIA_DIR = Path("./media")
```

**Computed Final URLs:**
- **Dev:** `http://localhost:5173/media/{session_id}/recordings/{filename}` (relative to frontend origin)
- **Prod:** `${BACKEND_ORIGIN}/media/{session_id}/recordings/{filename}` (relative to backend origin)

**Note:** Media URLs returned by backend are `/media/...` paths. Frontend `normalizeMediaUrl()` function (`api.js:5-29`) handles conversion but only if `API_BASE` is absolute (which it never is in current code).

---

## 3) RESPONSE SHAPE TRUTH (upload handler)

### Backend Upload Handler Response

**Handler:** `routers/media_router.py:51-117`
- **Route Path:** `/upload-audio` (mounted at `/api/media` prefix)
- **Final URL:** `/api/media/upload-audio`
- **Handler Signature:**
  - `file: UploadFile = File(...)` (required)
  - `session_id: Optional[str] = Form(None)` (optional, generates UUID if missing)
  - `db: AsyncSession = Depends(get_db)` (database dependency)

**Response Shape:** `routers/media_router.py:110-117`
```python
return success_response(
    data={
        "session_id": session_id,
        "file_url": file_url,
        "file_path": file_url,
    },
    message="Vocal uploaded"
)
```

**success_response() Implementation:** `backend/utils/responses.py:4-13`
```python
def success_response(data=None, message="OK", status=200):
    return JSONResponse(
        status_code=status,
        content={
            "ok": True,
            "data": data or {},
            "error": None,
            "message": message,
        }
    )
```

**Exact JSON Response:**
```json
{
  "ok": true,
  "data": {
    "session_id": "...",
    "file_url": "/media/{session_id}/recordings/{filename}",
    "file_path": "/media/{session_id}/recordings/{filename}"
  },
  "error": null,
  "message": "Vocal uploaded"
}
```

### Frontend handleResponse() Behavior

**Implementation:** `frontend/src/utils/api.js:33-69`
```javascript
const handleResponse = async (response) => {
 // First check HTTP status
 if (!response.ok) {
   const result = await response.json().catch(() => ({}));
   
   // Handle 400 errors gracefully
   if (response.status === 400) {
     return { ok: false, error: result.message || result.error || "Invalid email or password" };
   }
   
   const error = new Error(result.detail || result.message || result.error || 'API request failed');
   error.status = response.status;
   // Phase 8.4: For upgrade_required errors, attach full error data to error object
   if (result.error === "upgrade_required") {
     error.errorData = result;
     error.isPaywall = true;
   }
   throw error;
 }

 const result = await response.json().catch(() => ({}));

 // Phase 8.4: Check for paywall errors even if response.ok is true (in case backend returns 403 but ok: false)
 if (!result.ok) {
   // Phase 8.4: For upgrade_required errors, attach full error data to error object
   const error = new Error(result.error || result.message || result.detail || 'API request failed');
   error.status = response.status;
   if (result.error === "upgrade_required") {
     error.errorData = result;
     error.isPaywall = true;
   }
   throw error;
 }

 // Return data directly for easier consumption
 return result.data || result;
};
```

**Conclusion:** 
- If `response.ok === true` AND `result.ok === true`, function returns `result.data || result`
- For upload endpoint, this means: `{ session_id, file_url, file_path }` (the `data` object)
- If `result.data` is falsy, returns `result` (full response object)

**Frontend Usage:** `frontend/src/components/stages/UploadStage.jsx:101-104`
```javascript
const result = await api.uploadRecording(file, sessionId);

// MVP PATCH: Extract file URL from 'file_path' returned by the FastAPI endpoint
const fileUrl = normalizeMediaUrl(result.file_path);
```

**Frontend Will Receive:**
- Shape: `{ session_id: string, file_url: string, file_path: string }`
- Evidence: `handleResponse()` returns `result.data` when `result.ok === true`, and backend returns `data: { session_id, file_url, file_path }`

---

## 4) COOKIE / SESSION DEPENDENCY TRUTH

### Auth Dependencies on Upload Endpoint

**Search Results:** No auth dependencies found on `/api/media/upload-audio` endpoint.

**Handler:** `routers/media_router.py:51-56`
```python
@media_router.post("/upload-audio")
async def upload_audio(
    file: UploadFile = File(...),
    session_id: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
```

**Finding:** No `Depends(get_current_user)` or similar auth dependency. Only dependency is `Depends(get_db)` for database session.

### Credentials Usage

**Frontend:** `frontend/src/utils/api.js:220-224`
```javascript
const response = await fetch(`${API_BASE}/media/upload-audio`, {
  method: "POST",
  credentials: "include",
  body: formData,
});
```

**Backend CORS:** `main.py:130-136`
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**Finding:** 
- Frontend sends `credentials: "include"` (cookies/credentials included)
- Backend CORS allows credentials (`allow_credentials=True`)
- **REQUIREMENT:** For `credentials: "include"` to work, CORS must allow the exact origin (not `*`), which is satisfied by `allow_origins=[settings.frontend_url]`

### SameSite/Secure Settings

**Search Results:** No explicit SameSite or Secure cookie settings found in backend code. FastAPI session cookies (if any) would use framework defaults.

**Finding:** No explicit cookie configuration found. If session cookies exist, they would use FastAPI defaults (likely `SameSite=lax`, `Secure` in HTTPS environments).

**NOT FOUND:** 
- No explicit `set_cookie()` calls with SameSite/Secure settings
- No session middleware configuration found
- Searches run: `SameSite`, `Secure`, `set_cookie`, `session.*cookie`

---

## 5) MEDIA SERVING TRUTH (/media reachability)

### Backend Media Route

**Mount:** `main.py:145`
```python
app.mount("/media", StaticFiles(directory=str(MEDIA_DIR)), name="media")
```

**Media Directory:** `config/settings.py:18`
```python
MEDIA_DIR = Path("./media")
```

**Finding:**
- Media is mounted at `/media` (NOT `/api/media`)
- Serves from `./media` directory on disk
- Mounted BEFORE API routers (line 145 vs line 208), so `/media` takes precedence over any `/media` route in routers

### Frontend normalizeMediaUrl() Behavior

**Implementation:** `frontend/src/utils/api.js:5-29`
```javascript
export const normalizeMediaUrl = (url) => {
  if (!url) return url;

  if (url.startsWith('/api/media/')) return url;

  if (url.startsWith('/media/')) {
    // Helper to strip trailing /api or /api/ from API_BASE
    const stripApiSuffix = (base) => {
      if (base.endsWith('/api/')) return base.slice(0, -5);
      if (base.endsWith('/api')) return base.slice(0, -4);
      return base;
    };

    // If API_BASE is absolute (starts with http:// or https://), derive backend origin
    if (API_BASE.startsWith('http://') || API_BASE.startsWith('https://')) {
      const backendOrigin = stripApiSuffix(API_BASE);
      return `${backendOrigin}${url}`;
    }

    // If API_BASE is relative, return url unchanged
    return url;
  }

  return url;
};
```

**Analysis:**
- If URL starts with `/api/media/`, returns as-is
- If URL starts with `/media/`:
  - If `API_BASE` is absolute (e.g., `https://api.example.com/api`), converts to `${backendOrigin}/media/...`
  - If `API_BASE` is relative (current case: `/api`), returns URL unchanged: `/media/...`

**Current Behavior:**
- Backend returns: `/media/{session_id}/recordings/{filename}`
- `normalizeMediaUrl()` receives: `/media/...`
- Since `API_BASE = '/api'` (relative), function returns: `/media/...` (unchanged)

### URL Resolution in Dev vs Prod

**Dev Environment:**
- Frontend origin: `http://localhost:5173`
- Media URL after normalizeMediaUrl: `/media/{session_id}/recordings/{filename}`
- Browser resolves to: `http://localhost:5173/media/{session_id}/recordings/{filename}`
- **PROBLEM:** Backend serves media at `http://localhost:8000/media/...` (assuming backend on port 8000), but frontend requests go to `http://localhost:5173/media/...` (frontend origin)
- **RESULT:** 404 unless Vite proxy configured OR backend CORS allows and serves from same origin

**Prod Environment:**
- Frontend served from backend root (`main.py:230`: `app.mount("/", StaticFiles(...))`)
- Media URL after normalizeMediaUrl: `/media/{session_id}/recordings/{filename}`
- Browser resolves to: `${BACKEND_ORIGIN}/media/{session_id}/recordings/{filename}`
- **RESULT:** Works (same-origin request)

**Conclusion:**
- **Dev:** Media URLs will NOT resolve correctly unless Vite proxy configured OR backend runs on same origin as frontend
- **Prod:** Media URLs will resolve correctly (same-origin)

---

## 6) CONTRADICTION LIST (only contradictions backed by evidence)

### Contradiction #1: Vite Proxy Missing (DEV ONLY)

**What Breaks:** All API requests in dev environment (`/api/...` paths)

**Evidence:**
- `frontend/vite.config.js`: No `server.proxy` configuration
- `frontend/src/utils/api.js:1`: Comment says "Use backend proxy via Vite dev server" but no proxy exists
- `frontend/src/utils/api.js:2`: `API_BASE = '/api'` (relative path)

**Dev Applicability:** YES - Requests to `http://localhost:5173/api/...` will fail (404) unless backend is on same origin

**Prod Applicability:** NO - In prod, frontend is served from backend root, so relative paths work

**How to Confirm:**
- Open browser DevTools Network tab
- Attempt upload in dev
- Observe: Request to `http://localhost:5173/api/media/upload-audio` returns 404 or CORS error
- Expected: Request should proxy to `http://localhost:8000/api/media/upload-audio`

**File Evidence:**
- `frontend/vite.config.js:1-10` (no proxy config)
- `frontend/src/utils/api.js:1-2` (comment vs reality)

---

### Contradiction #2: Media URLs Won't Resolve in Dev (DEV ONLY)

**What Breaks:** Media playback URLs (`/media/...` paths returned by backend)

**Evidence:**
- Backend returns: `/media/{session_id}/recordings/{filename}` (`routers/media_router.py:86`)
- `normalizeMediaUrl()` returns unchanged: `/media/...` (`api.js:24`)
- Browser resolves relative to frontend origin: `http://localhost:5173/media/...`
- Backend serves from: `http://localhost:8000/media/...` (assuming default port)

**Dev Applicability:** YES - Media URLs will 404 in dev

**Prod Applicability:** NO - Same-origin in prod

**How to Confirm:**
- Upload a file successfully
- Check returned `file_url`: `/media/{session_id}/recordings/{filename}`
- Attempt to play audio: `<audio src="/media/...">`
- Observe: 404 in Network tab
- Expected: Audio plays

**File Evidence:**
- `routers/media_router.py:86` (returns `/media/...`)
- `frontend/src/utils/api.js:24` (returns unchanged)
- `main.py:145` (serves from `/media` mount)

---

### Contradiction #3: CORS Origin Mismatch Risk (DEV ONLY)

**What Breaks:** API requests if `FRONTEND_URL` env var doesn't match actual frontend origin

**Evidence:**
- `main.py:132`: `allow_origins=[settings.frontend_url]` (single origin)
- `config/settings.py:54`: Defaults to `http://localhost:5173`
- If frontend runs on different port or `FRONTEND_URL` not set correctly, CORS will reject

**Dev Applicability:** YES - If backend `FRONTEND_URL` ≠ actual frontend origin

**Prod Applicability:** YES - If `FRONTEND_URL` env var in Render doesn't match actual frontend URL

**How to Confirm:**
- Check backend logs for CORS errors
- Verify `FRONTEND_URL` env var matches actual frontend origin
- Observe: CORS preflight fails or request rejected with CORS error

**File Evidence:**
- `main.py:132` (`allow_origins=[settings.frontend_url]`)
- `config/settings.py:54` (default value)

---

### Contradiction #4: handleResponse() Fallback Behavior

**What Breaks:** If backend returns `{ok: true, data: null}`, frontend receives `null` instead of full response

**Evidence:**
- `frontend/src/utils/api.js:68`: `return result.data || result;`
- If `result.data` is `null` or `undefined`, returns `result` (full object)
- If `result.data` is `{}` (empty object), returns `{}` (not full response)

**Dev Applicability:** YES - Edge case behavior

**Prod Applicability:** YES - Edge case behavior

**How to Confirm:**
- Backend returns `{ok: true, data: {}}`
- Frontend receives `{}` (empty object)
- If code expects `result.file_path`, will be `undefined`

**File Evidence:**
- `frontend/src/utils/api.js:68` (`return result.data || result;`)
- `backend/utils/responses.py:9` (`data: data or {}` - always returns object, never null)

**Note:** This is likely not a breaking issue since backend always returns `data: {...}` with at least one key.

---

## 7) NEXT MICRO PATCH RECOMMENDATION (exactly ONE)

### Recommendation: Add Vite Proxy Configuration for Dev

**File to Change:** `frontend/vite.config.js`

**Exact Lines to Change:**
```javascript
// BEFORE (current):
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});

// AFTER (proposed):
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        secure: false,
      },
      '/media': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        secure: false,
      },
    },
  },
});
```

**Expected Behavior Change:**
- Dev: All `/api/...` requests proxy to `http://localhost:8000/api/...`
- Dev: All `/media/...` requests proxy to `http://localhost:8000/media/...`
- Prod: No change (proxy only active in dev server)

**Rationale:**
- Fixes Contradiction #1 (missing Vite proxy)
- Fixes Contradiction #2 (media URLs in dev)
- Minimal change (adds proxy config only)
- No runtime code changes
- No breaking changes to existing behavior

**Evidence Justification:**
- `frontend/vite.config.js` has no proxy (evidence: file contents)
- `frontend/src/utils/api.js:1` comment implies proxy should exist (evidence: comment)
- All API calls use relative paths (evidence: `API_BASE = '/api'`)
- Backend serves on port 8000 by default (evidence: `main.py:234`: `uvicorn.run(app, host="0.0.0.0", port=8000)`)

**Alternative Considered:** Change `API_BASE` to absolute URL in dev
- **Rejected:** Requires environment detection, more complex, breaks relative path assumption

---

## Summary

**Key Findings:**
1. No Vite proxy configured → dev API requests fail
2. Media URLs won't resolve in dev (different origins)
3. CORS requires exact origin match (single origin, not wildcard)
4. No auth dependencies on upload endpoint
5. Response shape: `{session_id, file_url, file_path}` via `result.data`

**Critical Issues (Dev):**
- Missing Vite proxy → all `/api/...` requests 404
- Media URLs resolve to wrong origin → `/media/...` requests 404

**Critical Issues (Prod):**
- None identified (assumes `FRONTEND_URL` env var set correctly)

**Recommended Fix:**
- Add Vite proxy configuration for `/api` and `/media` paths in dev

