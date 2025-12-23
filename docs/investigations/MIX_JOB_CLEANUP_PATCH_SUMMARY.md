# Mix Job Cleanup Patch Summary

## Implementation Complete

### Changes Made to `jobs/mix_job_manager.py`

1. **Added TTL Constants** (lines 13-16):
   - `JOB_TTL_HOURS = 48` - Completed jobs expire after 48 hours
   - `FAILED_JOB_TTL_HOURS = 24` - Failed jobs expire after 24 hours
   - `MAX_JOBS_PER_SESSION = 50` - Reserved for future use

2. **Added Imports** (lines 7, 9):
   - `timedelta` from `datetime` for TTL calculations
   - `logging` for cleanup logging

3. **Added `cleanup_expired_jobs()` Method** (lines 203-290):
   - Scans `MEDIA_DIR/<session_id>/jobs/` for job JSON files
   - Checks expiry based on `updated_at` timestamp and job state
   - Deletes expired job JSONs
   - Deletes associated index files from `MEDIA_DIR/jobs_index/`
   - Deletes mix output files from `STORAGE_MIX_OUTPUTS/<session_id>/final_mix.wav` (only for completed jobs)
   - Removes jobs from in-memory cache
   - Returns count of deleted jobs
   - Handles errors gracefully (continues processing other jobs)

4. **Integrated Cleanup into `enqueue_mix()`** (line 144):
   - Calls `cleanup_expired_jobs()` opportunistically before creating new jobs
   - Ensures cleanup happens when new jobs are enqueued

## Safety Features

1. **Conservative Deletion**:
   - Only deletes jobs with final states ("complete" or "error")
   - Active/running jobs are never deleted
   - Mix outputs only deleted for "complete" jobs
   - Corrupted job files are cleaned up

2. **Session Scoping**:
   - Only operates within `MEDIA_DIR/<session_id>/jobs/`
   - Mix outputs are per-session, deletion is conservative

3. **Error Handling**:
   - Individual job processing errors don't stop cleanup
   - Logs warnings for individual failures
   - Logs info when cleanup completes successfully

4. **Cache Management**:
   - Removes deleted jobs from in-memory `JOBS` cache
   - Prevents stale cache entries

## Behavior

- **Completed jobs**: Expire after 48 hours from `updated_at`
- **Failed jobs**: Expire after 24 hours from `updated_at`
- **Active jobs**: Never expired (queued, loading_stems, aligning_stems, processing_tracks, mixing, mastering, exporting)
- **Cleanup trigger**: Runs opportunistically when `enqueue_mix()` is called

## Testing Recommendations

1. Create a test job and manually set `updated_at` to 49 hours ago with state="complete" - should be deleted
2. Create a test job with state="error" and `updated_at` 25 hours ago - should be deleted
3. Create a test job with state="mixing" and `updated_at` 100 hours ago - should NOT be deleted
4. Verify mix output files are deleted when completed jobs expire
5. Verify index files are deleted when jobs expire
6. Verify cleanup doesn't affect active jobs

## Notes

- No background scheduler - cleanup is opportunistic only
- No explicit file locking (relies on atomic file operations)
- Mix output deletion is conservative (only for completed jobs)
- The `MAX_JOBS_PER_SESSION` constant is defined but not enforced (as per requirements)


