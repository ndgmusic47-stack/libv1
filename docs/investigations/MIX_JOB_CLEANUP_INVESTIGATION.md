# Mix Job Cleanup Investigation Report

## Investigation Summary

### 1. Job Storage Paths

**Job JSON files:**
- Location: `MEDIA_DIR/<session_id>/jobs/<job_id>.json`
- Where `MEDIA_DIR = Path("./media")` (from `config/settings.py`)
- Example: `./media/abc123/jobs/uuid-here.json`

**Index files (job_id → session_id mapping):**
- Location: `MEDIA_DIR/jobs_index/<job_id>.json`
- Example: `./media/jobs_index/uuid-here.json`

**Mix output artifacts:**
- Location: `STORAGE_MIX_OUTPUTS/<session_id>/final_mix.wav`
- Where `STORAGE_MIX_OUTPUTS = Path("./storage/mix_outputs")` (from `services/mix_service.py`)
- Example: `./storage/mix_outputs/abc123/final_mix.wav`

### 2. Job Fields

**Existing fields in MixJobState:**
- `job_id: str` - Unique job identifier
- `session_id: str` - Session/project identifier
- `state: str` - Current job state (default: "queued")
- `progress: int` - Progress percentage (0-100)
- `message: str` - Status message
- `error: Optional[str]` - Error message if failed
- `created_at: datetime` - **Already exists** (ISO format in JSON)
- `updated_at: datetime` - **Already exists** (ISO format in JSON)
- `extra: dict` - Additional data (config, visual data, meters, etc.)

**Timestamps:**
- ✅ `created_at` is already set via `field(default_factory=datetime.utcnow)` in `MixJobState`
- ✅ `updated_at` is already updated in `MixJobState.update()` method
- ✅ Both are serialized to ISO format in `_save_job()` method

### 3. Read/Update Operations

**Write operations:**
- `_save_job(job: MixJobState)` - Atomically writes job JSON to `MEDIA_DIR/<session_id>/jobs/<job_id>.json`
- `_write_index(job_id, session_id)` - Writes index mapping to `MEDIA_DIR/jobs_index/<job_id>.json`
- `enqueue_mix()` - Creates new job and saves it

**Read operations:**
- `_load_job(job_id, session_id)` - Loads job from filesystem
- `_load_job_from_path(job_path)` - Loads job from specific path
- `_get_job(job_id, session_id)` - Gets job from cache or filesystem
- `get_job_status(job_id)` - Returns job status for API

**Update operations:**
- `update(job_id, **kwargs)` - Updates job fields and persists to filesystem
- `MixJobState.update()` - Updates fields and sets `updated_at = datetime.utcnow()`

### 4. Job Status Values

**Status strings used:**
- `"queued"` - Initial/default state
- `"loading_stems"` - Loading audio files
- `"aligning_stems"` - Aligning stems
- `"processing_tracks"` - Applying DSP
- `"mixing"` - Blending tracks
- `"mastering"` - Applying master chain
- `"exporting"` - Exporting final mix
- `"complete"` - **Final success state**
- `"error"` - **Final failure state**

**Completion indicators:**
- `state == "complete"` - Job completed successfully
- `state == "error"` - Job failed
- `progress == 100` - Job reached 100% (may be complete or error)

### 5. Artifacts Produced Per Job

**Per-job artifacts:**
1. **Job JSON**: `MEDIA_DIR/<session_id>/jobs/<job_id>.json`
   - Contains job state, progress, timestamps, config, visual data
   
2. **Index file**: `MEDIA_DIR/jobs_index/<job_id>.json`
   - Maps job_id → session_id for fast lookup
   
3. **Mix output audio**: `STORAGE_MIX_OUTPUTS/<session_id>/final_mix.wav`
   - Final mixed audio file (only created if job completes successfully)
   - Note: This is OUTSIDE the session directory structure
   
4. **Visual data**: Stored in `job.extra["visual"]` (in-memory, not a file)
   - Waveform, spectrum, levels, energy curve
   - Realtime meters, spectra, scope, streams

**Artifact locations summary:**
- Job JSONs: Inside session directory (`MEDIA_DIR/<session_id>/jobs/`)
- Index files: Outside session directory (`MEDIA_DIR/jobs_index/`)
- Mix outputs: Outside session directory (`STORAGE_MIX_OUTPUTS/<session_id>/`)

### 6. Existing Cleanup

**Current cleanup status:**
- ❌ No cleanup code exists in `jobs/mix_job_manager.py`
- ❌ No cleanup code exists in `services/mix_service.py`
- ❌ No cleanup code exists in any router
- ❌ No cron/scheduler for cleanup

**Conclusion:** Jobs and artifacts persist indefinitely with no automatic cleanup.

### 7. Concurrency Safety

**Current locking:**
- No explicit locks found in `mix_job_manager.py`
- File operations use atomic rename (temp → final) for safety
- Multiple processes could potentially:
  - Read the same job simultaneously (safe)
  - Update the same job simultaneously (race condition possible)
  - Delete jobs during active operations (unsafe)

**Recommendation:** Use file-based locking or ensure cleanup only runs when no active operations are in progress.

## Implementation Plan

### Minimal Patch Requirements

1. **Add TTL constants:**
   - `JOB_TTL_HOURS = 48` (completed jobs)
   - `FAILED_JOB_TTL_HOURS = 24` (failed jobs)

2. **Ensure timestamps exist:**
   - ✅ Already implemented - `created_at` and `updated_at` are present

3. **Add cleanup function:**
   - `cleanup_expired_jobs(session_id: str) -> int`
   - Deletes expired job JSONs from `MEDIA_DIR/<session_id>/jobs/`
   - Deletes associated index files from `MEDIA_DIR/jobs_index/`
   - Deletes mix output if it exists in `STORAGE_MIX_OUTPUTS/<session_id>/final_mix.wav`
   - Returns count of deleted jobs

4. **Call cleanup opportunistically:**
   - At start of `enqueue_mix()` - before creating new job
   - Optionally: when listing jobs (if method exists)

5. **Safety rules:**
   - Only delete inside session scope
   - Use file locking or ensure atomic operations
   - Be conservative with artifact deletion


