# SessionManager Investigation & Patch Report

## Step 1 — Investigation (Read-Only)

### File Path
- **Implementation**: `utils/session_manager.py` (31 lines)

### Current Implementation

**Class**: `SessionManager`  
**Methods**:
- `get_user(session_id: str) -> Optional[Dict[str, Any]]` (static method)

**What it stores**: Nothing - pure placeholder returning `None`

**Placeholder/Failure Logic**: 
- Line 28-30: Always returns `None` unconditionally
- Comment explicitly states: "Placeholder implementation - returns None for now"

**Thread Safety**: 
- Static method with no shared state
- No concurrency issues (but also no functionality)

### Call Sites Map

#### 1. `routers/content_router.py:94` - `schedule_video` endpoint
```python
@router.post("/schedule")
async def schedule_video(request: ScheduleRequest):
    user = SessionManager.get_user(request.session_id)
    if user is None:
        return error_response("Invalid session")  # ← ALWAYS FAILS
```
- **Expects**: `Dict[str, Any]` with at least an `id` field (based on audit suggestion)
- **Error Handling**: Returns HTTP error response if `None`
- **Impact**: **GUARANTEED FAILURE** - endpoint always returns "Invalid session"

#### 2. `routers/content_router.py:118` - `save_scheduled` endpoint
```python
@router.post("/save-scheduled")
async def save_scheduled(request: SaveScheduledRequest):
    user = SessionManager.get_user(request.sessionId)
    if user is None:
        return error_response("Invalid session")  # ← ALWAYS FAILS
```
- **Expects**: `Dict[str, Any]` (user dict)
- **Error Handling**: Returns HTTP error response if `None`
- **Impact**: **GUARANTEED FAILURE** - endpoint always returns "Invalid session"

#### 3. `routers/content_router.py:135` - `get_scheduled` endpoint
```python
@router.get("/get-scheduled")
async def get_scheduled(session_id: str = Query(...)):
    user = SessionManager.get_user(session_id)
    if user is None:
        return error_response("Invalid session")  # ← ALWAYS FAILS
```
- **Expects**: `Dict[str, Any]` (user dict)
- **Error Handling**: Returns HTTP error response if `None`
- **Impact**: **GUARANTEED FAILURE** - endpoint always returns "Invalid session"

### Runtime Flow

**Instantiation**: Static class - no instantiation required, accessed via `SessionManager.get_user()`

**Must Support**:
- ✅ Concurrent requests (FastAPI with async)
- ✅ Multiple workers (Uvicorn/Gunicorn capable)
- ✅ Persistence across restarts (currently none, but validation can be filesystem-based)

### Failure Mode

**Exact Condition**: `SessionManager.get_user()` always returns `None` regardless of input

**Exception/Return**: 
- Method returns `None`
- All 3 call sites check `if user is None` and return `error_response("Invalid session")`
- HTTP status: 400 (inferred from error_response pattern)

**Breakage**: All content scheduling features completely broken:
- `POST /api/content/schedule` → Always returns "Invalid session"
- `POST /api/content/save-scheduled` → Always returns "Invalid session"  
- `GET /api/content/get-scheduled` → Always returns "Invalid session"

### SessionManager Contract (Inferred from Call Sites)

**Required Method**:
```python
@staticmethod
def get_user(session_id: str) -> Optional[Dict[str, Any]]:
    """
    Returns:
        - Dict with at least {"id": session_id} if session is valid
        - None if session is invalid
    """
```

**Required Data Fields in User Dict**:
- `id`: session_id string (minimum required based on audit doc suggestion)
- Optional: Any other fields can be added later without breaking call sites

**Expected Storage Semantics**:
- Anonymous sessions (no user_id required)
- Session validated by existence of `media/{session_id}/` directory
- Session IDs are UUIDs (generated client-side or server-side via `uuid.uuid4()`)
- No explicit session creation needed - sessions exist when directory is created (via other endpoints)

---

## Step 2 — Minimal Patch Design

### Implementation Strategy

**Storage**: Filesystem-based validation only
- Check if `MEDIA_DIR / session_id` directory exists
- No separate session storage file needed (session validity = directory exists)

**Session Validation**:
1. Validate `session_id` format (safe characters, prevent path traversal)
2. Check if `media/{session_id}/` directory exists
3. Return `{"id": session_id}` if valid, `None` if invalid

**Thread Safety**:
- Read-only filesystem checks - no locks needed
- Static method - no shared mutable state

**Concurrency**:
- Safe for concurrent requests (filesystem checks are atomic)
- Safe across multiple workers (filesystem is shared state)

**Backwards Compatibility**:
- Method signature unchanged
- Return type unchanged (Optional[Dict])
- Behavior: Returns dict instead of None for valid sessions

### Patch Requirements

✅ Keep method names/signatures unchanged  
✅ Add session_id validation (safe characters, path traversal prevention)  
✅ No new methods needed (call sites don't use get_or_create pattern)  
✅ Atomic reads (filesystem check is atomic)  
✅ No locks needed (read-only operations)  
✅ Clear validation logic with safe defaults

---

## Step 3 — Deliverable

### What Was Broken

**Root Cause**: `SessionManager.get_user()` is a placeholder that unconditionally returns `None`

**Guaranteed Failure Path**:
1. Any request to content scheduling endpoints calls `SessionManager.get_user(session_id)`
2. Method returns `None`
3. Call site checks `if user is None: return error_response("Invalid session")`
4. Request fails with HTTP 400 error

**Affected Endpoints**:
- `POST /api/content/schedule` - Schedule video posts
- `POST /api/content/save-scheduled` - Save scheduled posts
- `GET /api/content/get-scheduled` - Retrieve scheduled posts

### Call Sites & Expected Contract

See "Call Sites Map" section above. All call sites expect:
- `Optional[Dict[str, Any]]` return type
- Non-None dict for valid sessions (minimum `{"id": session_id}`)
- `None` for invalid sessions

### Unified Diff

**File**: `utils/session_manager.py`

```diff
--- a/utils/session_manager.py
+++ b/utils/session_manager.py
@@ -1,13 +1,45 @@
 """
-Session Manager - Placeholder for session → user mapping (Phase 4C)
+Session Manager - Validates sessions and returns user dict for anonymous sessions
 """
 
 from typing import Optional, Dict, Any
 import logging
+import re
+from pathlib import Path
+from config.settings import MEDIA_DIR
 
 logger = logging.getLogger(__name__)
 
+# Valid session_id format: UUID-like or alphanumeric with hyphens/underscores
+# Prevents path traversal and ensures safe directory names
+VALID_SESSION_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_-]{1,128}$')
+
 
 class SessionManager:
     """
-    Placeholder SessionManager for session → user mapping.
-    This is a placeholder that will be replaced with real authentication.
+    SessionManager validates sessions and returns user dict for anonymous sessions.
+    A session is valid if the session directory exists in the media folder.
     """
     
     @staticmethod
     def get_user(session_id: str) -> Optional[Dict[str, Any]]:
         """
         Get user from session ID.
         
         Args:
             session_id: Session ID to lookup
             
         Returns:
             User dict if session is valid, None otherwise
         """
-        # Placeholder implementation - returns None for now
-        # Real implementation will validate session and return user
-        return None
+        if not session_id or not isinstance(session_id, str):
+            logger.debug(f"Invalid session_id: {session_id} (empty or not string)")
+            return None
+        
+        # Validate session_id format to prevent path traversal and unsafe characters
+        if not VALID_SESSION_ID_PATTERN.match(session_id):
+            logger.warning(f"Invalid session_id format: {session_id} (contains unsafe characters)")
+            return None
+        
+        # Validate session exists by checking if media directory exists
+        # Sessions are anonymous - validity is determined by directory existence
+        session_path = MEDIA_DIR / session_id
+        
+        try:
+            # Check if session directory exists (atomic filesystem operation)
+            if session_path.exists() and session_path.is_dir():
+                # Return minimal user dict (anonymous session)
+                return {
+                    "id": session_id
+                }
+            else:
+                logger.debug(f"Session directory does not exist: {session_path}")
+                return None
+        except (OSError, PermissionError) as e:
+            # Handle filesystem errors gracefully
+            logger.error(f"Error checking session directory for {session_id}: {e}")
+            return None
```

### Manual Verification Checklist

**Pre-Verification Setup**:
1. Ensure server is running
2. Have a valid session_id that has been used (creates `media/{session_id}/` directory)

**Test Cases**:

1. **Valid Session**:
   ```bash
   # Use a session_id that exists (has media directory)
   curl -X GET "http://localhost:8000/api/content/get-scheduled?session_id=<valid_session_id>"
   ```
   **Expected**: Returns 200 with scheduled posts (empty array if none)

2. **Invalid Session (Nonexistent)**:
   ```bash
   curl -X GET "http://localhost:8000/api/content/get-scheduled?session_id=nonexistent-session-12345"
   ```
   **Expected**: Returns 400 with "Invalid session" error

3. **Invalid Session (Path Traversal Attempt)**:
   ```bash
   curl -X GET "http://localhost:8000/api/content/get-scheduled?session_id=../../../etc/passwd"
   ```
   **Expected**: Returns 400 with "Invalid session" error (rejected by format validation)

4. **POST Endpoint Test**:
   ```bash
   curl -X POST "http://localhost:8000/api/content/schedule" \
     -H "Content-Type: application/json" \
     -d '{"session_id": "<valid_session_id>", "video_url": "...", "caption": "...", "schedule_time": "2024-01-01T00:00:00", "platform": "tiktok"}'
   ```
   **Expected**: Returns 200 with scheduled post data (or API error, but not "Invalid session")

5. **Session Persistence**:
   - Create session via beat/lyrics endpoint (creates directory)
   - Restart server
   - Call content endpoint with same session_id
   **Expected**: Session still valid after restart

**Success Criteria**:
- ✅ Valid sessions return user dict, endpoints proceed normally
- ✅ Invalid sessions return None, endpoints return "Invalid session" error
- ✅ Path traversal attempts are blocked
- ✅ No crashes or exceptions in logs
- ✅ Works with concurrent requests
- ✅ Sessions persist across server restarts


