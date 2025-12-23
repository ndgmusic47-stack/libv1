# Investigation: Render Stale Frontend Bundle

**Date:** 2025-01-22  
**Issue:** Live backend still receiving `POST /api/media/upload/vocal` after repo update to `/api/media/upload-audio` and rebuild-bump deployment.

**Investigation Type:** Source code analysis only (no runtime access)

---

## A) Current Source Truth

### A1) uploadRecording() Path Verification

**File:** `frontend/src/utils/api.js`

**Line 225-236:** Function definition
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

**Finding:** ✅ Source code uses `/api/media/upload-audio` (line 230)

### A2) UploadStage Usage Verification

**File:** `frontend/src/components/stages/UploadStage.jsx`

**Line 101:** Function call
```javascript
const result = await api.uploadRecording(file, sessionId);
```

**Finding:** ✅ UploadStage correctly calls `api.uploadRecording()`

**Conclusion:** Source code is **CORRECT** - both the function definition and its usage point to `/api/media/upload-audio`.

---

## B) Production Static File Serving

### B1) Frontend Serving Configuration

**File:** `main.py`

**Lines 223-230:** Frontend static file mounting
```python
# Correct location in Render runtime: /opt/render/project/src/frontend/dist
FRONTEND_DIST = Path(__file__).resolve().parent / "frontend" / "dist"

# Mount assets folder
app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

# Serve SPA fallback
app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="spa-root")
```

**Finding:** ✅ Backend serves frontend from `frontend/dist` directory via FastAPI `StaticFiles` mount.

### B2) Static Serving Disabled Check

**File:** `main.py`

**Lines 223-230:** Static file mounts are **unconditional** - no environment flags disable them.

**Finding:** ✅ Static file serving is **always enabled** - no conditional logic found.

### B3) Alternative Static Directories

**Search Results:**
- ❌ No `/static` directory found
- ❌ No `/public` directory found  
- ❌ No `/templates` directory found
- ❌ No other `frontend` folders found

**Finding:** ✅ Only one frontend bundle location: `frontend/dist`

---

## C) Render Config / Build Pipeline

### C1) Build Command Inspection

**File:** `render.yaml`

**Lines 5-8:** Build command
```yaml
buildCommand: |
  cd frontend && npm install && npm run build
  cd ..
  pip install -r requirements.txt
```

**Finding:** ✅ Build runs `npm run build` in `frontend/` directory, which outputs to `frontend/dist/` (per `vite.config.js:20`).

### C2) Build Location Verification

**File:** `frontend/vite.config.js`

**Lines 19-22:** Build output configuration
```javascript
build: {
  outDir: "dist",
  emptyOutDir: true,
},
```

**Finding:** ✅ Vite outputs to `frontend/dist/` with `emptyOutDir: true` (should clear directory before build).

### C3) Service Architecture

**File:** `render.yaml`

**Lines 1-13:** Single web service definition
```yaml
services:
  - type: web
    name: label-in-a-box
    env: python
    buildCommand: |
      cd frontend && npm install && npm run build
      cd ..
      pip install -r requirements.txt
    startCommand: uvicorn main:app --host 0.0.0.0 --port 8000
```

**Finding:** ✅ **Single service** - frontend build and backend run in the same service. No separate frontend service.

---

## D) Multi-Frontend Possibility

### D1) Additional Frontend Bundles

**Search Results:**
- ❌ No `/static` directory
- ❌ No `/public` directory
- ❌ No `/templates` directory
- ❌ No duplicate `frontend/` folders

**Finding:** ✅ Only one frontend source location: `frontend/`

### D2) Alternative API Client Code

**Search Pattern:** `uploadRecording` function calls

**Results:**
- ✅ `frontend/src/utils/api.js:225` - Function definition
- ✅ `frontend/src/utils/api.js:829` - Wrapper function `uploadVocal()` calls `api.uploadRecording()`
- ✅ `frontend/src/components/stages/UploadStage.jsx:101` - Component usage

**Search Pattern:** Direct fetch calls to `/api/media`

**Results:**
- ✅ `frontend/src/utils/api.js:230` - `fetch(\`${API_BASE}/media/upload-audio\`)`
- ✅ `frontend/src/utils/api.js:239` - `fetch(\`${API_BASE}/media/generate/song\`)`

**Finding:** ✅ **Single API client** - all upload calls go through `api.js`. No alternative client code found.

### D3) Service Worker / Cache

**File:** `frontend/src/workers/waveformWorker.ts`

**Finding:** ✅ Service worker only handles waveform rendering - no API calls.

**Search Pattern:** Service worker registration or cache manifests

**Results:** ❌ No service worker registration found in source code.

**Finding:** ✅ No service worker caching that could serve stale API endpoints.

---

## E) What Cannot Be Proven From Repo

### E1) Runtime Evidence Required

The repository **cannot prove** the contents of the deployed `frontend/dist/` bundle. The following runtime artifacts are needed to confirm the root cause:

#### Required Evidence:

1. **Deployed Bundle Contents**
   - **What:** Inspect the actual JavaScript bundle files in `frontend/dist/assets/*.js` on the Render service
   - **Why:** Verify if the compiled bundle contains `/api/media/upload/vocal` or `/api/media/upload-audio`
   - **How:** SSH into Render service and search bundle files for the endpoint string
   - **Command:** `grep -r "upload/vocal" /opt/render/project/src/frontend/dist/`

2. **Build Logs from Last Deployment**
   - **What:** Render deployment logs showing the build command execution
   - **Why:** Confirm if `npm run build` actually executed and completed successfully
   - **Where:** Render dashboard → Service → Deployments → Latest deployment logs
   - **Look for:** 
     - `cd frontend && npm install && npm run build`
     - Build completion messages
     - Any build errors or warnings

3. **Build Cache State**
   - **What:** Whether Vite's build cache or node_modules cache persisted stale artifacts
   - **Why:** `emptyOutDir: true` should clear `dist/`, but cache might preserve old chunks
   - **How:** Check Render build logs for cache restoration steps
   - **Evidence needed:** Logs showing `Restoring cache...` or `Cache hit...`

4. **Deployment Timestamp vs Code Change**
   - **What:** Exact timestamp when `/api/media/upload-audio` was committed vs when deployment ran
   - **Why:** Confirm deployment happened after code change
   - **Where:** Git commit history + Render deployment history
   - **Evidence needed:** Commit hash and deployment ID correlation

5. **Browser Network Tab Evidence**
   - **What:** Actual HTTP request URL from live site
   - **Why:** Confirm the browser is sending `/api/media/upload/vocal` (not a backend routing issue)
   - **How:** Open browser DevTools → Network tab → Filter for "upload" → Inspect request URL
   - **Evidence needed:** Screenshot showing `POST /api/media/upload/vocal` in request details

### E2) Most Likely Root Cause (Based on Evidence)

**Hypothesis:** Stale build artifact in `frontend/dist/`

**Evidence Supporting:**
- ✅ Source code is correct (uses `/api/media/upload-audio`)
- ✅ Only one frontend bundle location (`frontend/dist/`)
- ✅ Single service architecture (build + serve in same service)
- ✅ No alternative API clients found
- ✅ No service worker caching

**Evidence Missing:**
- ❌ Actual contents of deployed `frontend/dist/assets/*.js` files
- ❌ Build logs confirming successful build execution
- ❌ Confirmation that `emptyOutDir: true` cleared old files

**Conclusion:** The deployed `frontend/dist/` bundle likely contains **compiled JavaScript from before the endpoint change**, even though:
1. Source code was updated
2. A rebuild-bump was deployed
3. Vite config has `emptyOutDir: true`

**Possible Causes:**
1. Build cache preserved old chunks despite `emptyOutDir: true`
2. Build step failed silently and old dist/ was not replaced
3. Deployment used cached build artifacts from previous build
4. Build ran but Vite's code splitting preserved old chunk with `/upload/vocal`

---

## Summary

### ✅ Proven from Repository:

1. **Source code is correct:** `frontend/src/utils/api.js:230` uses `/api/media/upload-audio`
2. **Component usage is correct:** `UploadStage.jsx:101` calls `api.uploadRecording()`
3. **Backend serves from:** `main.py:224` mounts `frontend/dist/` as static files
4. **Build outputs to:** `frontend/vite.config.js:20` outputs to `frontend/dist/`
5. **Single service:** `render.yaml` shows one service (build + serve together)
6. **No alternative frontends:** Only one frontend source location found
7. **No alternative API clients:** All upload calls go through `api.js`

### ❌ Cannot Prove from Repository:

1. **Actual deployed bundle contents** - needs runtime inspection
2. **Build execution logs** - needs Render deployment logs
3. **Build cache state** - needs deployment cache logs
4. **Browser network requests** - needs live site inspection

### 🎯 Root Cause Hypothesis:

**Stale frontend bundle in `frontend/dist/`** - The compiled JavaScript bundle served to browsers contains the old `/api/media/upload/vocal` endpoint, despite source code being updated. This is a **build artifact issue**, not a source code issue.

### 📋 Next Steps (Runtime Verification):

1. SSH into Render service and inspect `frontend/dist/assets/*.js` for endpoint strings
2. Review Render deployment logs for build execution and cache hits
3. Check browser network tab on live site to confirm request URL
4. Force a clean rebuild by clearing Render build cache and redeploying



