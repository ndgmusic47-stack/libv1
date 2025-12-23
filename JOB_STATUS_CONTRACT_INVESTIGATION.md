# Job Status Contract Investigation Report

## Scope
- `jobs/mix_job_manager.py` - `MixJobManager.get_job_status()`
- `routers/mix_router.py` - `GET /{project_id}/mix/job/{job_id}/status` endpoint only

---

## 1. Job States Actually Used

### States Set in Code:

| State | Location | Context |
|-------|----------|---------|
| `"queued"` | `mix_job_manager.py:115` (default), `mix_router.py:227` | Initial state, waiting for mixer slot |
| `"running"` | `mix_router.py:231` | Mix started, acquired semaphore |
| `"loading_stems"` | `mix_service.py:174` | Loading audio files |
| `"aligning_stems"` | `mix_service.py:195` | Synchronizing stems |
| `"processing_tracks"` | `mix_service.py:212` | Applying DSP to tracks |
| `"mixing"` | `mix_service.py:329` | Blending tracks |
| `"mastering"` | `mix_service.py:414` | Applying master chain |
| `"exporting"` | `mix_service.py:465` | Exporting final mix |
| `"complete"` | `mix_service.py:484`, `mix_job_manager.py:244` | Job finished successfully |
| `"error"` | `mix_router.py:244,247`, `mix_service.py:514`, `mix_job_manager.py:242` | Job failed |

### State Usage in Cleanup:
- `mix_job_manager.py:242-244` - Uses `"error"` and `"complete"` for TTL determination

---

## 2. MixJobManager.get_job_status() Output Schema

**Location:** `jobs/mix_job_manager.py:181-196`

### Success Case (job found):
```python
{
    "is_error": False,
    "data": {
        "job_id": str,
        "state": str,           # One of the states above
        "progress": int,        # 0-100
        "message": str,         # Status message
        "error": Optional[str], # None if no error, string if error occurred
        "created_at": str,      # ISO format datetime
        "updated_at": str       # ISO format datetime
    }
}
```

### Error Case (job not found):
```python
{
    "is_error": True,
    "error": "Job not found"
}
```

**Note:** `result_url` or `output_url` is **NOT** included in the response.

---

## 3. Router Endpoint Response Schema

**Location:** `routers/mix_router.py:115-139`

### Success Case (job found):
The router calls `MixJobManager.get_job_status(job_id)` and wraps it:

```python
# If job_status.get("is_error") is False:
{
    "ok": True,
    "data": {
        "job_id": str,
        "state": str,
        "progress": int,
        "message": str,
        "error": Optional[str],
        "created_at": str,
        "updated_at": str
    },
    "error": None,
    "message": "Job status retrieved successfully"
}
```

### Error Case (job not found):
```python
{
    "ok": False,
    "data": {},
    "error": "JOB_NOT_FOUND",
    "message": "Job not found"  # or job_status.get("error")
}
```

### Exception Case (unhandled error):
```python
{
    "ok": False,
    "data": {},
    "error": "JOB_STATUS_ERROR",
    "message": "Failed to get job status: {str(e)}"
}
```

---

## 4. Job Status Contract Table

| Field | Type | Required | Source | Meaning |
|-------|------|----------|--------|---------|
| `ok` | boolean | ✅ | Router wrapper | Overall response success |
| `data` | object | ✅ | Router wrapper | Job data container |
| `data.job_id` | string | ✅ | MixJobManager | Unique job identifier |
| `data.state` | string | ✅ | MixJobState | Current job state (queued/running/complete/error/etc.) |
| `data.progress` | integer | ✅ | MixJobState | Progress percentage (0-100) |
| `data.message` | string | ✅ | MixJobState | Human-readable status message |
| `data.error` | string \| null | ✅ | MixJobState | Error message if state is "error", null otherwise |
| `data.created_at` | string | ✅ | MixJobState | ISO format datetime when job was created |
| `data.updated_at` | string | ✅ | MixJobState | ISO format datetime when job was last updated |
| `error` | string \| null | ✅ | Router wrapper | Error code if ok=false, null if ok=true |
| `message` | string | ✅ | Router wrapper | Human-readable response message |
| `result_url` | string | ❌ | **MISSING** | URL to completed mix file (not provided) |
| `output_url` | string | ❌ | **MISSING** | Alternative name for result URL (not provided) |

---

## 5. Inconsistencies and Bugs Found

### Bug #1: Missing `result_url` in Job Status Response
**Location:** `jobs/mix_job_manager.py:181-196`
**Issue:** When `state === "complete"`, the frontend needs a URL to the mix file, but `get_job_status()` doesn't provide it.
**Impact:** Frontend must make a separate call to `/mix/preview` endpoint to get the file URL.
**Evidence:** 
- Frontend code (`MixStage.jsx:69-73`) checks `status.state === "complete"` then calls `getMixPreview()` separately
- No `result_url` field in `MixJobManager.get_job_status()` output

### Bug #2: Frontend API Endpoint Mismatch
**Location:** `frontend/src/utils/api.js:851-861`
**Issue:** Frontend calls `/projects/${projectId}/mix/status?job_id=${jobId}` but router has `/mix/${projectId}/mix/job/${jobId}/status`
**Impact:** This endpoint may not exist or may route to a different handler (`get_mix_status` in `mix_router.py:45` which doesn't use job_id)
**Evidence:**
- Frontend: `GET /api/projects/${projectId}/mix/status?job_id=${jobId}`
- Router: `GET /mix/${projectId}/mix/job/{job_id}/status` (no query param)

### Bug #3: Inconsistent Error Response Structure
**Location:** `routers/mix_router.py:129-130`
**Issue:** When `job_status.get("is_error")` is True, the router returns `error_response()` which has `ok: False`, but the `error` field from `MixJobManager` is lost (only `message` is preserved).
**Impact:** Frontend may not be able to distinguish between "job not found" vs other errors.
**Evidence:**
- `MixJobManager` returns `{"is_error": True, "error": "Job not found"}`
- Router converts to `{"ok": False, "error": "JOB_NOT_FOUND", "message": "Job not found"}`
- The original `error` string is used as `message`, but the structure changes

### Bug #4: Missing Progress/State Validation
**Location:** `jobs/mix_job_manager.py:181-196`
**Issue:** No validation that `progress` is 0-100 or that `state` is a valid enum value.
**Impact:** Invalid data could break frontend polling logic.
**Evidence:**
- `MixJobState` allows any string for `state` (defaults to "queued")
- `progress` is an int but no bounds checking

### Bug #5: `error` Field Always Present But May Be Null
**Location:** `jobs/mix_job_manager.py:192`
**Issue:** The `error` field is always included in the response, even when `null`. This is fine, but the contract should document that `error` is only meaningful when `state === "error"`.
**Impact:** Frontend must check both `state === "error"` AND `error !== null` to be safe.
**Evidence:**
- Response always includes `"error": job.error` which can be `None` (serialized as `null`)

---

## 6. Frontend Expectations vs Reality

### What Frontend Expects (from `MixStage.jsx:62-69`):
```javascript
{
    progress: number,  // ✅ Present
    state: string      // ✅ Present (checks for "complete")
}
```

### What Frontend Actually Gets:
```javascript
{
    ok: true,
    data: {
        job_id: string,
        state: string,      // ✅ Present
        progress: number,   // ✅ Present
        message: string,
        error: string | null,
        created_at: string,
        updated_at: string
    },
    error: null,
    message: string
}
```

**Note:** Frontend uses `handleResponse()` which returns `result.data || result`, so it likely receives the `data` object directly.

---

## 7. Recommendation: Minimal Patch to Standardize

### Single Minimal Patch:

**File:** `jobs/mix_job_manager.py`

**Change:** Add `result_url` to the success response when `state === "complete"`:

```python
@staticmethod
async def get_job_status(job_id):
    job = MixJobManager._get_job(job_id)
    if not job:
        return {"is_error": True, "error": "Job not found"}
    
    response_data = {
        "job_id": job.job_id,
        "state": job.state,
        "progress": job.progress,
        "message": job.message,
        "error": job.error,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
    }
    
    # Add result_url when job is complete
    if job.state == "complete":
        from config.settings import MEDIA_DIR
        from services.mix_service import STORAGE_MIX_OUTPUTS
        mix_path = STORAGE_MIX_OUTPUTS / job.session_id / "final_mix.wav"
        if mix_path.exists():
            # Generate URL path (relative to /media/)
            result_url = f"/media/{job.session_id}/mix_outputs/final_mix.wav"
            response_data["result_url"] = result_url
    
    return {
        "is_error": False,
        "data": response_data
    }
```

**Rationale:**
1. **Minimal change** - Only adds one field conditionally
2. **Backward compatible** - Existing code continues to work
3. **Fixes primary issue** - Frontend can get result URL from status response
4. **No breaking changes** - Router wrapper remains unchanged

**Additional Considerations:**
- The frontend endpoint mismatch (`/projects/.../mix/status?job_id=...` vs `/mix/.../mix/job/.../status`) should be fixed separately in the frontend API client.
- Error response structure inconsistency is acceptable as long as frontend handles both formats.

---

## Summary

The job status contract is **mostly consistent** between `MixJobManager` and the router, but:
1. **Missing `result_url`** when job is complete (primary issue)
2. **Frontend endpoint mismatch** (separate issue, not in scope)
3. **Error response structure** differs but is handled by router wrapper

The recommended patch adds `result_url` conditionally, making the contract complete for frontend polling needs.


