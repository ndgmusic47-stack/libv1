# Session/Project ID Validation Investigation

**Scope:** routers/mix_router.py, routers/content_router.py, routers/beat_router.py  
**Note:** voice_router.py does not exist in the codebase.

**Standard Guard Pattern (from content_router.py):**
```python
user = SessionManager.get_user(session_id)
if user is None:
    return error_response("Invalid session")
```

---

## Investigation Results

### routers/content_router.py

| Endpoint | Accepts session_id? | How Validated | Gap? |
|----------|---------------------|---------------|------|
| `POST /api/content/idea` | ✅ Optional (IdeaRequest.session_id) | ❌ **NO VALIDATION** | **CRITICAL** - Accepts session_id but never validates |
| `POST /api/content/analyze` | ❌ No | N/A | N/A |
| `POST /api/content/generate-text` | ✅ Optional (GenerateTextRequest.session_id) | ❌ **NO VALIDATION** | **CRITICAL** - Accepts session_id but never validates |
| `POST /api/content/schedule` | ✅ Required (ScheduleRequest.session_id) | ✅ Uses SessionManager.get_user() | ✅ Validated |
| `POST /api/content/save-scheduled` | ✅ Required (SaveScheduledRequest.sessionId) | ✅ Uses SessionManager.get_user() | ✅ Validated |
| `GET /api/content/get-scheduled` | ✅ Required (Query param session_id) | ✅ Uses SessionManager.get_user() | ✅ Validated |

**Summary:** 3 endpoints validate, 2 endpoints accept session_id but skip validation entirely.

---

### routers/mix_router.py

| Endpoint | Accepts project_id/session_id? | How Validated | Gap? |
|----------|-------------------------------|---------------|------|
| `GET /mix/{project_id}/mix/status` | ✅ project_id (path param) | ❌ **NO VALIDATION** | **CRITICAL** - No validation, treats project_id as session_id |
| `POST /mix/{project_id}/mix/start` | ✅ project_id (path param), uses as session_id | ❌ **NO VALIDATION** | **CRITICAL** - No validation, directly uses project_id |
| `GET /mix/projects/{project_id}/mix/status` | ✅ project_id (path param) | ❌ **NO VALIDATION** | **CRITICAL** - No validation |
| `GET /mix/{project_id}/mix/job/{job_id}/status` | ✅ project_id (path param) | ❌ **NO VALIDATION** | **CRITICAL** - No validation |
| `GET /mix/{project_id}/mix/preview` | ✅ project_id (path param), uses as session_id | ❌ **NO VALIDATION** | **CRITICAL** - No validation, file access by project_id |
| `GET /mix/timeline/{job_id}` | ❌ No (job_id only) | N/A | N/A |
| `GET /mix/visual/{job_id}` | ❌ No (job_id only) | N/A | N/A |
| `GET /mix/scope/{job_id}` | ❌ No (job_id only) | N/A | N/A |
| `GET /mix/streams/{job_id}` | ❌ No (job_id only) | N/A | N/A |
| `POST /mix/transport/{job_id}/play` | ❌ No (job_id only) | N/A | N/A |
| `POST /mix/transport/{job_id}/pause` | ❌ No (job_id only) | N/A | N/A |
| `POST /mix/transport/{job_id}/stop` | ❌ No (job_id only) | N/A | N/A |
| `POST /mix/transport/{job_id}/seek` | ❌ No (job_id only) | N/A | N/A |
| `GET /api/mix/config/schema` | ❌ No | N/A | N/A |
| `POST /api/mix/config/apply` | ✅ session_id (ApplyConfigRequest.session_id) | ❌ **NO VALIDATION** | **CRITICAL** - Accepts session_id but never validates |
| `POST /api/mix/run-clean` | ✅ project_id (Body param) | ❌ **NO VALIDATION** | **CRITICAL** - No validation, uses project_id as session_id |

**Summary:** 6 endpoints accept project_id/session_id but **NONE validate**. Most critical: `/mix/{project_id}/mix/preview` exposes file access without validation.

---

### routers/beat_router.py

| Endpoint | Accepts session_id? | How Validated | Gap? |
|----------|---------------------|---------------|------|
| `POST /api/beats/create` | ✅ Optional (BeatRequest.session_id, generates UUID if missing) | ❌ **NO VALIDATION** | **CRITICAL** - Accepts session_id but never validates, auto-generates if missing |
| `GET /api/beats/credits` | ❌ No | N/A | N/A |
| `GET /api/beats/status/{job_id}` | ❌ No (job_id only) | N/A | N/A |

**Summary:** 1 endpoint accepts session_id but **NO VALIDATION**. Accepts any session_id or auto-generates one.

---

## Inconsistencies Identified

1. **content_router.py**: Partial validation - only schedule-related endpoints validate, but `/idea` and `/generate-text` accept session_id without validation.

2. **mix_router.py**: **ZERO validation** - All endpoints that accept project_id/session_id skip validation entirely. Most critical:
   - `/mix/{project_id}/mix/preview` - File access without validation
   - `/mix/{project_id}/mix/start` - Initiates resource-intensive mix jobs without validation
   - `/api/mix/config/apply` - Accepts session_id but never validates

3. **beat_router.py**: **ZERO validation** - Accepts session_id or auto-generates, no validation.

4. **Pattern inconsistency**: 
   - `content_router.py` uses `SessionManager.get_user(session_id)` when it validates
   - Other routers either don't validate at all, or use project_id interchangeably with session_id without normalization

---

## Standard Guard Pattern

**Smallest standard guard pattern found in repo:**

```python
from utils.session_manager import SessionManager

user = SessionManager.get_user(session_id)
if user is None:
    return error_response("Invalid session")
```

**Location:** Used in 3 endpoints in `content_router.py`:
- `POST /api/content/schedule` (line 94-96)
- `POST /api/content/save-scheduled` (line 118-120)
- `GET /api/content/get-scheduled` (line 135-137)

**Behavior:**
- Validates session_id format (regex: `^[a-zA-Z0-9_-]{1,128}$`)
- Checks if session directory exists in MEDIA_DIR
- Returns user dict `{"id": session_id}` if valid, `None` if invalid
- Prevents path traversal attacks via format validation

---

## Recommendations

### Highest-Risk Public Endpoint to Patch First

**Recommendation: `GET /mix/{project_id}/mix/preview` in mix_router.py**

**Risk Level: CRITICAL**

**Reasoning:**
1. **File access vulnerability** - Directly serves files without any session validation
2. **Public endpoint** - No authentication barrier
3. **Path-based access** - Uses project_id directly as session_id to access filesystem
4. **Information disclosure** - Can access any project's mix output if project_id is known/guessed

**Endpoint details:**
- Route: `GET /mix/{project_id}/mix/preview`
- Lines: 172-200 in mix_router.py
- Behavior: Returns `final_mix.wav` file from `STORAGE_MIX_OUTPUTS / project_id / "final_mix.wav"`
- Validation: **NONE** - project_id is used directly without SessionManager validation

**Patch Priority:** **P0 - Patch immediately**

---

### Additional High-Risk Endpoints

1. **`POST /mix/{project_id}/mix/start`** (mix_router.py:64) - Resource-intensive operation without validation
2. **`POST /api/beats/create`** (beat_router.py:35) - Accepts any session_id, auto-generates if missing, no validation
3. **`POST /api/content/idea`** (content_router.py:31) - Accepts session_id but doesn't validate
4. **`POST /api/content/generate-text`** (content_router.py:70) - Accepts session_id but doesn't validate

---

## Summary Statistics

- **Total endpoints accepting session_id/project_id:** 14
- **Endpoints with validation:** 3 (21%)
- **Endpoints without validation:** 11 (79%)
- **Critical gaps:** 11 endpoints expose functionality without session validation


