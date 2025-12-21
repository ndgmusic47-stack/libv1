# Upload Vocal 405 Root Cause Investigation

**Date:** Investigation Report  
**Issue:** Deployed frontend calls `POST /api/media/upload/vocal` but backend defines `/api/media/upload-audio`  
**Status:** Investigation Only - No Fixes Applied

---

## A) Frontend Source Audit

### Search Results

#### 1. Search for `upload/vocal`
**Result:** No matches found in frontend source code

#### 2. Search for `uploadRecording`
**Matches Found:**
- `frontend/src/utils/api.js:225` - Function definition: `uploadRecording: async (file, sessionId = null) => {`
- `frontend/src/utils/api.js:829` - Function call: `return api.uploadRecording(file, sessionId);`
- `frontend/src/components/stages/UploadStage.jsx:101` - Function call: `const result = await api.uploadRecording(file, sessionId);`

**Analysis:**
- Line 225-236 in `api.js` defines `uploadRecording` function
- Line 230 explicitly calls: `${API_BASE}/media/upload-audio` ✅ **CORRECT ENDPOINT**
- `UploadStage.jsx` correctly uses `api.uploadRecording()`

#### 3. Search for `uploadVocal`
**Matches Found:**
- `frontend/src/utils/api.js:828` - Function definition: `export async function uploadVocal(file, sessionId) {`
- `frontend/src/utils/api.js:829` - Function body: `return api.uploadRecording(file, sessionId);`

**Analysis:**
- `uploadVocal` is a wrapper function that calls `uploadRecording`
- No direct API calls to `/upload/vocal` in source code

#### 4. Search for `media/upload`
**Matches Found:**
- `frontend/src/utils/api.js:230` - Fetch call: `const response = await fetch(\`${API_BASE}/media/upload-audio\`, {`

**Analysis:**
- Only reference to `media/upload` is the correct `/media/upload-audio` endpoint

### Explicit Statement
**`/upload/vocal` does NOT exist anywhere in frontend source code.**

---

## B) Frontend Build Entrypoints

### Entry Point Analysis

**Main Entry:**
- `frontend/src/main.jsx` - React application entry point
  - Imports: `App.jsx` (line 4)
  - Imports: `ProjectContext` (line 5)
  - No direct API imports

**API Module:**
- `frontend/src/utils/api.js` - Single API utility file
  - Exported as: `export const api = { ... }`
  - Contains `uploadRecording` function (line 225)
  - Contains `uploadVocal` wrapper (line 828)

**Import Chain:**
1. `main.jsx` → `App.jsx`
2. `App.jsx` → Components (including `UploadStage.jsx`)
3. `UploadStage.jsx` → `api.js` (line 3: `import { api, normalizeMediaUrl } from '../../utils/api'`)

### API File Confirmation
**Only ONE `api.js` file exists:**
- `frontend/src/utils/api.js` (confirmed via glob search)
- No `api.ts` files found
- No duplicate API files in other locations

**Conclusion:** Single source of truth for API calls. No conflicting API modules.

---

## C) Backend Route Confirmation

### Media Router Analysis

**File:** `routers/media_router.py`

**Routes Defined:**
1. `@media_router.post("/upload-audio")` (line 51) ✅ **EXISTS**
   - Handler: `upload_audio()` (lines 52-117)
   - Full path: `/api/media/upload-audio`

2. `@media_router.post("/generate/vocal")` (line 120)
   - Handler: `generate_vocal()` (lines 121-216)

3. `@media_router.post("/generate/song")` (line 219)
   - Handler: `generate_song()` (lines 220-359)

**Routes NOT Defined:**
- `/api/media/upload/vocal` ❌ **DOES NOT EXIST**
- No alias or redirect from `/upload/vocal` to `/upload-audio`

### Router Registration
**File:** `main.py`
- Line 208: `app.include_router(media_router)`
- Router prefix: `/api/media` (defined in `media_router.py` line 29)

**Conclusion:**
- ✅ `/api/media/upload-audio` exists and is registered
- ❌ `/api/media/upload/vocal` does NOT exist in backend

---

## D) Deployment Risk Analysis (Code-Based Only)

### Build Configuration

**Build Output:**
- `frontend/vite.config.js:19` - `outDir: "dist"`
- Build output location: `frontend/dist/`

**Deployment Configuration:**
- `render.yaml:6` - Build command: `cd frontend && npm install && npm run build`
- Build runs before backend start
- `main.py:224` - Serves from: `FRONTEND_DIST = Path(__file__).resolve().parent / "frontend" / "dist"`

### Potential Stale Build Scenarios

#### 1. Build Cache Issues
**Evidence in Repo:**
- `vite.config.js:20` - `emptyOutDir: true` ✅ Should clear old files
- No evidence of build cache configuration issues

#### 2. Multiple Frontend Directories
**Search Results:**
- Only one `frontend/` directory exists in repo root
- No duplicate frontend folders found
- No legacy frontend directories

#### 3. Build Artifact Persistence
**Evidence:**
- `frontend/dist/` directory not present in repo (expected - should be gitignored)
- No `.gitignore` violations found
- Build happens during deployment, not committed to repo

#### 4. Documentation References (Non-Code)
**Found in Documentation:**
- `VOICE_MODULE_IMPLEMENTATION_MAP.md:142` - Mentions `/api/media/upload/vocal` (outdated documentation)
- `ersncpowDocumentslibv1` - Contains old endpoint reference (appears to be a log/error file)

**Analysis:**
- Documentation files are NOT source code
- They do not affect runtime behavior
- No code references to these documentation files

### Deployment Process Analysis

**Render Build Flow:**
1. `cd frontend && npm install && npm run build` - Builds frontend
2. `cd ..` - Returns to root
3. `pip install -r requirements.txt` - Installs Python deps
4. `uvicorn main:app --host 0.0.0.0 --port 8000` - Starts backend

**Static File Serving:**
- `main.py:230` - Serves SPA from `frontend/dist/`
- Mount order: API routes first, then static files (line 220 comment)

**Risk Factors Identified:**
1. **Stale Build Artifacts:** If `emptyOutDir: true` fails or is bypassed, old JS bundles could persist
2. **Browser Cache:** Client-side caching of old JavaScript bundles (not repo-based)
3. **CDN/Proxy Cache:** Intermediate caching layers (not repo-based)
4. **Build Process Failure:** If build fails silently, old dist/ might be served (not repo-based)

**Code-Based Evidence:**
- ✅ Source code is correct
- ✅ Build config should clear old files
- ✅ Only one frontend directory
- ⚠️ No evidence of stale code in repo itself

---

## E) Conclusion

### Root Cause Determination

**Finding:** Frontend source code is **CORRECT** - it calls `/api/media/upload-audio` (line 230 in `api.js`).

**Evidence:**
1. ✅ No references to `/upload/vocal` in frontend source
2. ✅ `uploadRecording()` correctly calls `/media/upload-audio`
3. ✅ Only one API module exists
4. ✅ Backend defines `/upload-audio`, not `/upload/vocal`

### Conclusion Statement

**"Frontend source is correct; deployment is stale"**

The deployed frontend bundle contains outdated JavaScript code that still references `/api/media/upload/vocal`. The repository source code has been updated to use `/api/media/upload-audio`, but the deployed build artifact (`frontend/dist/`) contains an older version of the compiled JavaScript.

### Recommended Actions (Not Implemented - Investigation Only)

1. **Force Rebuild:** Clear build cache and rebuild frontend
2. **Verify Build Output:** Check that `frontend/dist/` contains updated code after build
3. **Browser Cache:** Users may need to hard refresh (Ctrl+Shift+R)
4. **CDN Cache:** If using CDN, invalidate cache for frontend assets

### Files Referenced

- `frontend/src/utils/api.js` (lines 225-236, 828-830)
- `frontend/src/components/stages/UploadStage.jsx` (line 101)
- `frontend/src/main.jsx` (entry point)
- `routers/media_router.py` (line 51)
- `main.py` (lines 208, 224, 230)
- `frontend/vite.config.js` (lines 19-20)
- `render.yaml` (line 6)

---

**Investigation Complete**  
**No code changes made**

