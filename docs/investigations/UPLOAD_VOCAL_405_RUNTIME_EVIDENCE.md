# Upload Vocal 405 Runtime Evidence Investigation

**Date:** 2025-01-22  
**Issue:** Live system calls `POST /api/media/upload/vocal` (405) despite repo source using `/api/media/upload-audio`  
**Status:** Investigation Only - No Fixes Applied  
**Goal:** Prove with runtime artifacts why the live system still calls the old endpoint

---

## A) Render Deployment Evidence (Verbatim)

### A1) Most Recent Build Logs

**Status:** ⚠️ **NOT AVAILABLE** - Requires Render Dashboard Access

**Why Not Available:**
- Render build logs are only accessible via Render.com dashboard
- Cannot access Render account or deployment logs from repository
- Requires authentication to Render service

**Required Artifacts (to be filled manually):**
1. Frontend build command output (`npm run build`)
   - Should show Vite compilation
   - Should show bundle generation
   - Should show output directory creation
2. Backend start command (`uvicorn main:app`)
   - Should show FastAPI startup
   - Should show route registration
3. Cache messages
   - Any npm cache warnings
   - Any Vite cache messages
   - Any build cache indicators

**Manual Steps to Obtain:**
1. Log into Render.com dashboard
2. Navigate to service: `label-in-a-box`
3. Go to "Logs" tab
4. Filter by "Build" logs
5. Copy verbatim the most recent build output

**Placeholder for Artifact:**
```
[PASTE RENDER BUILD LOGS HERE - Include timestamps]
```

---

### A2) Most Recent Runtime Logs

**Status:** ⚠️ **NOT AVAILABLE** - Requires Render Dashboard Access

**Why Not Available:**
- Render runtime logs are only accessible via Render.com dashboard
- Cannot access live deployment logs from repository
- Requires authentication to Render service

**Required Artifacts (to be filled manually):**
1. POST /api/media/upload/vocal 405 errors
   - Exact timestamp of request
   - Request headers (if logged)
   - Response status code
   - Error message
2. Timestamps around those requests
   - Time before the 405 error
   - Time after the 405 error
   - Any related log entries

**Manual Steps to Obtain:**
1. Log into Render.com dashboard
2. Navigate to service: `label-in-a-box`
3. Go to "Logs" tab
4. Filter by "Runtime" logs
5. Search for "405" or "upload/vocal"
6. Copy verbatim the log entries with timestamps

**Placeholder for Artifact:**
```
[PASTE RENDER RUNTIME LOGS HERE - Include timestamps showing POST /api/media/upload/vocal 405]
```

---

## B) Browser Network Evidence (Verbatim)

**Status:** ⚠️ **NOT AVAILABLE** - Requires Live Browser Access

**Why Not Available:**
- Cannot access user's browser or live deployed site
- Network tab data is only available in browser DevTools
- Requires manual capture from live site

**Required Artifacts (to be filled manually):**

### B1) Request Details

1. **Exact Request URL:**
   ```
   [PASTE EXACT URL HERE - Should show /api/media/upload/vocal]
   ```

2. **Request Method:**
   ```
   [PASTE METHOD HERE - Should be POST]
   ```

3. **Status Code:**
   ```
   [PASTE STATUS CODE HERE - Should be 405]
   ```

4. **Response Headers:**
   ```
   [PASTE RESPONSE HEADERS HERE - At minimum include Content-Type]
   Content-Type: [value]
   [other headers]
   ```

5. **Response Body (Raw):**
   ```
   [PASTE RAW RESPONSE BODY HERE]
   ```

6. **Initiator / Call Stack:**
   ```
   [PASTE CALL STACK FROM CHROME DEVTOOLS]
   [Should show which JS file triggered the request]
   [Include file name and line number]
   ```

7. **Request Headers Section:**
   ```
   Origin: [value]
   Referer: [value]
   Cookie: [value - redact sensitive data if needed]
   [other request headers]
   ```

**Manual Steps to Obtain:**
1. Open live deployed site in Chrome/Edge
2. Open DevTools (F12)
3. Go to "Network" tab
4. Clear network log
5. Trigger vocal upload action
6. Find the failed request (should show 405)
7. Click on the request
8. Copy verbatim all sections listed above

**Placeholder for Artifact:**
```
[PASTE COMPLETE NETWORK REQUEST DETAILS HERE]
```

---

## C) Frontend Asset Evidence (Verbatim)

**Status:** ⚠️ **NOT AVAILABLE** - Requires Live Browser Access

**Why Not Available:**
- Cannot access live deployed site's Network tab
- Asset filenames and headers are only visible in browser DevTools
- Requires manual capture from live site

**Required Artifacts (to be filled manually):**

### C1) Main JS Bundle Files

1. **Bundle Filenames:**
   ```
   [PASTE FULL FILENAMES HERE]
   Example: assets/index-abc123.js
   Example: assets/vendor-def456.js
   [List all main JS bundles loaded]
   ```

2. **Response Headers for Each Bundle:**
   ```
   For assets/index-xxxxx.js:
   cache-control: [value]
   etag: [value]
   last-modified: [value if present]
   
   For assets/vendor-xxxxx.js:
   cache-control: [value]
   etag: [value]
   last-modified: [value if present]
   
   [Repeat for all main bundles]
   ```

**Manual Steps to Obtain:**
1. Open live deployed site in Chrome/Edge
2. Open DevTools (F12)
3. Go to "Network" tab
4. Filter by "JS"
5. Reload page (Ctrl+R or F5)
6. Identify main bundle files (usually `index-*.js`, `vendor-*.js`)
7. Click on each bundle file
8. Go to "Headers" tab
9. Copy verbatim the response headers listed above

**Placeholder for Artifact:**
```
[PASTE BUNDLE FILENAMES AND RESPONSE HEADERS HERE]
```

---

## D) In-Bundle String Check (Manual, Not Code)

**Status:** ⚠️ **NOT AVAILABLE** - Requires Live Bundle Access

**Why Not Available:**
- Cannot download or inspect live deployed JS bundles
- Bundle inspection requires either:
  - Downloading the bundle from live site
  - Using browser DevTools Sources tab
- Requires manual inspection

**Required Artifacts (to be filled manually):**

### D1) String Search Results

**Search String:** `/api/media/upload/vocal`

**Result:**
```
[ ] FOUND
[ ] NOT FOUND
```

**If FOUND:**
```
[PASTE SURROUNDING CODE HERE - Max 20 lines]
[Include context before and after the string]
[Example:
  const response = await fetch(`${API_BASE}/api/media/upload/vocal`, {
    method: "POST",
    credentials: "include",
    body: formData,
  });
]
```

**If NOT FOUND:**
```
NOT FOUND - The string "/api/media/upload/vocal" does not exist in the loaded JS bundle.
```

**Manual Steps to Obtain:**

**Method 1: Browser DevTools Sources Tab**
1. Open live deployed site in Chrome/Edge
2. Open DevTools (F12)
3. Go to "Sources" tab
4. Find the main JS bundle file (e.g., `assets/index-xxxxx.js`)
5. Press Ctrl+F to open search
6. Search for: `/api/media/upload/vocal`
7. If found, copy surrounding lines (max 20)
8. If not found, record "NOT FOUND"

**Method 2: Download and Search**
1. Open live deployed site in Chrome/Edge
2. Open DevTools (F12)
3. Go to "Network" tab
4. Reload page
5. Find main JS bundle file
6. Right-click → "Open in new tab"
7. Copy the JS content
8. Search for: `/api/media/upload/vocal`
9. If found, copy surrounding lines (max 20)
10. If not found, record "NOT FOUND"

**Placeholder for Artifact:**
```
[PASTE SEARCH RESULTS HERE]
```

---

## E) Source Code Baseline (For Reference)

**Status:** ✅ **AVAILABLE** - From Repository

### E1) Current Frontend Source

**File:** `frontend/src/utils/api.js`

**Line 230:**
```javascript
const response = await fetch(`${API_BASE}/media/upload-audio`, {
  method: "POST",
  credentials: "include",
  body: formData,
});
```

**Conclusion:** Source code uses `/api/media/upload-audio` ✅

### E2) Current Backend Source

**File:** `routers/media_router.py`

**Line 51:**
```python
@media_router.post("/upload-audio")
async def upload_audio(
    file: UploadFile = File(...),
    session_id: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
```

**Conclusion:** Backend defines `/api/media/upload-audio` ✅

### E3) Search Results

**Grep for `/upload/vocal` in frontend:**
```
No matches found
```

**Grep for `upload-audio` in frontend:**
```
frontend/src/utils/api.js:230 - const response = await fetch(`${API_BASE}/media/upload-audio`, {
```

**Conclusion:** No references to `/upload/vocal` in source code ✅

---

## F) Conclusion (Based on Available Evidence)

**Status:** ⚠️ **INCOMPLETE** - Awaiting Runtime Artifacts

### Current Evidence Summary

**From Repository (Available):**
- ✅ Frontend source code uses `/api/media/upload-audio` (correct)
- ✅ Backend source code defines `/api/media/upload-audio` (correct)
- ✅ No references to `/upload/vocal` in frontend source
- ✅ Build configuration appears correct (`emptyOutDir: true`)

**From Runtime (Not Available):**
- ⚠️ Render build logs - NOT AVAILABLE (requires dashboard access)
- ⚠️ Render runtime logs - NOT AVAILABLE (requires dashboard access)
- ⚠️ Browser Network tab - NOT AVAILABLE (requires live browser access)
- ⚠️ Frontend asset headers - NOT AVAILABLE (requires live browser access)
- ⚠️ In-bundle string check - NOT AVAILABLE (requires bundle inspection)

### Possible Root Causes (To Be Determined)

Based on the investigation structure, the root cause will be ONE of:

1. **Browser is loading an old cached JS bundle**
   - Evidence needed: Old `etag` or `last-modified` dates in asset headers
   - Evidence needed: Browser cache headers showing long cache times
   - Evidence needed: Bundle contains `/upload/vocal` string

2. **Render is serving an old dist directory**
   - Evidence needed: Build logs showing build completed but old files persist
   - Evidence needed: Bundle contains `/upload/vocal` string
   - Evidence needed: Build timestamp vs. bundle timestamp mismatch

3. **Another frontend (different app/domain) is hitting this backend**
   - Evidence needed: Network tab shows different Origin/Referer
   - Evidence needed: Request coming from different domain
   - Evidence needed: Bundle does NOT contain `/upload/vocal` (proving different source)

4. **The live JS bundle truly contains /upload/vocal**
   - Evidence needed: Bundle string search finds `/upload/vocal`
   - Evidence needed: Build logs show successful build but bundle is old
   - Evidence needed: Source code mismatch (unlikely given repo audit)

### Next Required Action

**INVESTIGATION ONLY - No Fixes**

1. **Obtain Render Build Logs:**
   - Access Render dashboard
   - Copy verbatim build output showing frontend compilation
   - Copy verbatim runtime logs showing 405 errors

2. **Obtain Browser Network Evidence:**
   - Open live site in browser
   - Capture complete network request details for failed upload
   - Document exact URL, headers, and call stack

3. **Obtain Frontend Asset Evidence:**
   - Document all JS bundle filenames
   - Document cache headers (cache-control, etag, last-modified)

4. **Perform In-Bundle String Check:**
   - Search loaded JS bundle for `/api/media/upload/vocal`
   - Document FOUND/NOT FOUND with surrounding code if found

5. **Update This Report:**
   - Fill in all placeholder sections with verbatim artifacts
   - Update Conclusion section with definitive root cause
   - Document which of the 4 possible causes is confirmed

---

## G) Report Completion Checklist

- [ ] Section A1: Render build logs pasted (verbatim)
- [ ] Section A2: Render runtime logs pasted (verbatim)
- [ ] Section B: Browser Network tab details pasted (verbatim)
- [ ] Section C: Frontend asset filenames and headers pasted (verbatim)
- [ ] Section D: In-bundle string search results documented
- [ ] Section F: Conclusion updated with definitive root cause
- [ ] All artifacts are verbatim (not summarized or paraphrased)

---

**Investigation Report Created:** 2025-01-22  
**Report Status:** Awaiting Runtime Artifacts  
**No Code Changes Made**



