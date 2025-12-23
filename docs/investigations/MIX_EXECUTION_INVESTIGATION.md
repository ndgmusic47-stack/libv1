# Mix Execution / Job Runner Investigation

**Date:** 2024-12-19  
**Scope:** Mix execution path only (where mix actually runs)  
**Type:** Investigation only (NO code changes)

---

## Executive Summary

The mix execution path uses **asyncio.create_task()** to spawn background tasks from HTTP request handlers. All CPU-bound DSP operations run via **asyncio.to_thread()** using Python's default thread pool executor. There are **no concurrency limits, semaphores, queues, or worker pools** - jobs run unbounded in the background.

---

## 1. Where Mix Job is Executed

### Entry Point: HTTP Endpoint
**File:** `routers/mix_router.py`  
**Function:** `start_mix()` (line 58-106)

```python
@mix_router.post("/{project_id}/mix/start")
async def start_mix(...):
    # Enqueue mix job
    job_id = await MixJobManager.enqueue_mix(session_id, stems, request.config or {})
    
    # Start mix processing (async)
    asyncio.create_task(_process_mix_job(job_id, session_id, stems))
    
    return success_response({"job_id": job_id})
```

**Alternative Entry Point:**  
**File:** `routers/mix_router.py`  
**Function:** `run_clean_wrapper()` (line 293-330) - Same pattern at line 324

### Background Task Function
**File:** `routers/mix_router.py`  
**Function:** `_process_mix_job()` (line 213-229)

```python
async def _process_mix_job(job_id: str, session_id: str, stems: dict):
    """Background task to process mix job"""
    try:
        job = JOBS.get(job_id)
        config = job.extra.get("config")
        
        # Run mix (progress tracking is handled inside MixService.mix)
        result = await MixService.mix(session_id, stems, config=config, job_id=job_id)
        
        if result.get("is_error"):
            logger.error(f"Mix job {job_id} failed: {result.get('error')}")
        else:
            logger.info(f"Mix job {job_id} completed successfully")
    except Exception as e:
        MixJobManager.update(job_id, state="error", progress=100, message="Mix failed", error=str(e))
        logger.error(f"Mix job {job_id} failed with exception: {e}")
```

### Core Mix Execution
**File:** `services/mix_service.py`  
**Function:** `MixService.mix()` (line 141-515)

This is where the actual DSP processing happens. All blocking operations are wrapped in `asyncio.to_thread()`.

---

## 2. Execution Model

### Model: Background Task (Fire-and-Forget)

**Pattern:** `asyncio.create_task()` spawns a background coroutine that runs independently of the HTTP request.

**Characteristics:**
- ✅ **Non-blocking:** HTTP request returns immediately with `job_id`
- ✅ **Async:** Uses asyncio event loop
- ❌ **No queue:** Tasks are spawned directly, no persistent queue
- ❌ **No retry:** If task fails, it's logged but not retried
- ❌ **No monitoring:** No built-in way to track running tasks

### Thread Pool Usage

All CPU-bound DSP operations use **`asyncio.to_thread()`** which uses Python's **default ThreadPoolExecutor**.

**Thread Pool Details:**
- **Default size:** ~40 threads (Python's default: `min(32, (os.cpu_count() or 1) + 4)`)
- **No custom executor:** Uses default executor, no size configuration
- **No semaphore:** No limit on concurrent thread pool usage

**Blocking Operations Wrapped in `asyncio.to_thread()`:**

1. **File existence check** (`services/mix_service.py:168`)
   ```python
   exists = await asyncio.to_thread(stem_path_obj.exists)
   ```

2. **Audio loading** (`services/mix_service.py:188`)
   ```python
   audio_data = await asyncio.to_thread(load_wav, resolved_path)
   ```
   **Function:** `utils/dsp/load.py:load_wav()` - Synchronous WAV file I/O + resampling

3. **Stem alignment** (`services/mix_service.py:204`)
   ```python
   audio_data_dict = await asyncio.to_thread(align_stems, audio_data_dict)
   ```
   **Function:** `utils/dsp/timing.py:align_stems()` - CPU-bound onset detection + array operations

4. **File export** (`services/mix_service.py:474`)
   ```python
   await asyncio.to_thread(save_wav, str(output_path), master_audio)
   ```
   **Function:** `utils/dsp/export.py:save_wav()` - Synchronous WAV file I/O

5. **File existence check** (`services/mix_service.py:552`)
   ```python
   file_exists = await asyncio.to_thread(file_path.exists)
   ```

### In-Process DSP Operations (Not Threaded)

The following operations run **directly in the async coroutine** (not in thread pool):

- Auto gain (`MixService.apply_auto_gain()`)
- Micro-dynamics (`MixService.apply_micro_dynamics()`)
- Tonal balance (`MixService.apply_tonal_balance()`)
- Spatial separation (`MixService.apply_spatial_separation()`)
- Track DSP processing (`process_track()`)
- Frequency masking (`MixService.apply_frequency_masking()`)
- Track blending (`blend_tracks()`)
- Master bus processing (`process_master_bus()`)
- Visual data computation (`compute_waveform()`, `compute_fft_spectrum()`, etc.)

**Note:** These are NumPy operations that run in the async coroutine. They block the event loop but are typically fast enough not to cause issues.

---

## 3. Concurrency Limits

### ❌ NO CONCURRENCY LIMITS FOUND

**No Semaphores:**
- No `asyncio.Semaphore` limiting concurrent mix jobs
- No `asyncio.BoundedSemaphore` for resource protection

**No Queues:**
- No `asyncio.Queue` for job queuing
- No persistent job queue (Redis, database, etc.)
- Jobs are spawned directly via `asyncio.create_task()`

**No Worker Pools:**
- No custom `ThreadPoolExecutor` with size limits
- Uses Python's default thread pool executor (~40 threads)
- No `ProcessPoolExecutor` for CPU-intensive work

**No Timeouts:**
- No `asyncio.wait_for()` wrapping mix execution
- No timeout on `MixService.mix()` call
- No timeout on individual DSP operations

**No Rate Limiting:**
- No per-session mix job limits
- No global mix job limits
- Rate limiter exists (`utils/rate_limit.py`) but only for HTTP requests, not mix jobs

**Concurrency Impact:**
- **Unbounded concurrent mix jobs:** Each HTTP request spawns a background task
- **Thread pool exhaustion risk:** ~40 concurrent mix jobs can exhaust thread pool
- **Memory risk:** Each mix job loads full audio into memory (NumPy arrays)
- **No backpressure:** System will accept unlimited mix requests

---

## 4. Bottleneck Operations

### 4.1 Audio Loading
**File:** `utils/dsp/load.py:load_wav()`  
**Called via:** `asyncio.to_thread(load_wav, resolved_path)` at `services/mix_service.py:188`

**Operations:**
- Synchronous WAV file I/O (`wave.open()`)
- Full file read into memory
- NumPy array conversion
- Resampling if sample rate mismatch (linear interpolation)

**Bottleneck Factors:**
- File I/O is blocking (runs in thread pool)
- Large audio files can take seconds to load
- Resampling is CPU-intensive for large files

**Per-Stem:** Each stem (vocal, beat, etc.) is loaded sequentially in a loop

### 4.2 Onset Detection / Alignment
**File:** `utils/dsp/timing.py:align_stems()`  
**Called via:** `asyncio.to_thread(align_stems, audio_data_dict)` at `services/mix_service.py:204`

**Operations:**
- `detect_onset()` for beat stem (line 66)
- `detect_onset()` for vocal stem (line 67)
- Onset detection uses:
  - Mono conversion
  - Normalization
  - Sliding window convolution (10ms window)
  - Energy threshold search
- Array padding/trimming for alignment

**Bottleneck Factors:**
- Convolution operation: `np.convolve(mono ** 2, np.ones(window_size) / window_size, mode='same')`
- Runs on full audio length
- CPU-bound, runs in thread pool

### 4.3 Rendering/Export
**File:** `utils/dsp/export.py:save_wav()`  
**Called via:** `asyncio.to_thread(save_wav, str(output_path), master_audio)` at `services/mix_service.py:474`

**Operations:**
- Normalize audio to int16 range
- Convert NumPy array to bytes
- Synchronous WAV file write (`wave.open()`)

**Bottleneck Factors:**
- File I/O is blocking (runs in thread pool)
- Large files can take seconds to write
- No streaming/chunked write

### 4.4 Waveform Generation
**File:** `utils/dsp/analyze_audio.py:compute_waveform()`  
**Called at:** `services/mix_service.py:432` (NOT threaded, runs in async coroutine)

**Operations:**
- Downsample audio to 2000 samples
- Linear interpolation for sample selection
- Mean across channels (mono conversion)

**Bottleneck Factors:**
- Runs in async coroutine (blocks event loop)
- NumPy operations on full audio array
- Typically fast but can block for very long audio

**Other Visual Data (also not threaded):**
- `compute_fft_spectrum()` - FFT computation (line 433)
- `compute_levels()` - RMS/peak calculation (line 434)
- `compute_energy_curve()` - Segment-based energy (line 435)
- `compute_track_spectrum()` - Per-track FFT (line 310, 351, 425)

---

## 5. Exact Call Chain

### HTTP Endpoint → Mix Start → Compute → File Outputs

```
┌─────────────────────────────────────────────────────────────────┐
│ HTTP REQUEST: POST /{project_id}/mix/start                      │
│ File: routers/mix_router.py:58                                  │
│ Function: start_mix()                                            │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ 1. Enqueue Job                                                  │
│ File: jobs/mix_job_manager.py:142                               │
│ Function: MixJobManager.enqueue_mix()                           │
│ - Creates MixJobState                                            │
│ - Saves to filesystem (JSON)                                     │
│ - Writes index file                                              │
│ - Caches in JOBS dict                                            │
│ Returns: job_id                                                  │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. Spawn Background Task                                         │
│ File: routers/mix_router.py:99                                  │
│ Function: asyncio.create_task(_process_mix_job(...))             │
│ - NON-BLOCKING: Returns immediately                              │
│ - Task runs independently in event loop                          │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼ (Background task continues)
┌─────────────────────────────────────────────────────────────────┐
│ 3. Background Task Handler                                       │
│ File: routers/mix_router.py:213                                  │
│ Function: _process_mix_job(job_id, session_id, stems)           │
│ - Loads job config from JOBS dict                                │
│ - Calls MixService.mix()                                         │
│ - Handles errors (updates job state)                              │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ 4. Core Mix Execution                                           │
│ File: services/mix_service.py:141                                │
│ Function: MixService.mix(session_id, stems, config, job_id)      │
│                                                                   │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ 4.1 Validate Stems (BLOCKING in async coroutine)            │ │
│ │ - Loop through stems                                         │ │
│ │ - Check file existence via asyncio.to_thread()               │ │
│ │   → utils/dsp/load.py: N/A (just Path.exists())              │ │
│ │ - Update job: state="loading_stems", progress=10             │ │
│ └─────────────────────────────────────────────────────────────┘ │
│                            │                                      │
│                            ▼                                      │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ 4.2 Load Audio Files (THREADED)                            │ │
│ │ - Loop through stems                                         │ │
│ │ - await asyncio.to_thread(load_wav, resolved_path)          │ │
│ │   → utils/dsp/load.py:load_wav()                             │ │
│ │     • wave.open() - BLOCKING I/O                              │ │
│ │     • Read frames - BLOCKING I/O                              │ │
│ │     • NumPy conversion - CPU-bound                            │ │
│ │     • Resampling (if needed) - CPU-bound                      │ │
│ │ - Store in audio_data_dict                                    │ │
│ └─────────────────────────────────────────────────────────────┘ │
│                            │                                      │
│                            ▼                                      │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ 4.3 Align Stems (THREADED)                                   │ │
│ │ - Update job: state="aligning_stems", progress=25            │ │
│ │ - await asyncio.to_thread(align_stems, audio_data_dict)     │ │
│ │   → utils/dsp/timing.py:align_stems()                         │ │
│ │     • detect_onset(beat) - CPU-bound (convolution)            │ │
│ │     • detect_onset(vocal) - CPU-bound (convolution)            │ │
│ │     • Calculate offset                                         │ │
│ │     • Pad/trim vocal array - CPU-bound                         │ │
│ │     • Length matching - CPU-bound                             │ │
│ └─────────────────────────────────────────────────────────────┘ │
│                            │                                      │
│                            ▼                                      │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ 4.4 Process Tracks (BLOCKING in async coroutine)            │ │
│ │ - Update job: state="processing_tracks", progress=50         │ │
│ │ - Loop through audio_data_dict                               │ │
│ │ - Apply auto gain (NumPy ops) - BLOCKS EVENT LOOP            │ │
│ │ - Apply micro-dynamics (NumPy ops) - BLOCKS EVENT LOOP       │ │
│ │ - Apply tonal balance (NumPy ops) - BLOCKS EVENT LOOP         │ │
│ │ - Apply spatial separation (NumPy ops) - BLOCKS EVENT LOOP   │ │
│ │ - process_track() - BLOCKS EVENT LOOP                        │ │
│ │   → utils/dsp/mix_pipeline.py:process_track()                │ │
│ │     • apply_eq() - NumPy ops                                  │ │
│ │     • apply_compressor() - NumPy ops                          │ │
│ │     • apply_saturation() - NumPy ops                           │ │
│ │     • apply_gain() - NumPy ops                                │ │
│ │     • apply_deesser() - NumPy ops                              │ │
│ │     • add_air() - NumPy ops                                   │ │
│ │     • compute_scope() - NumPy ops                              │ │
│ │ - Compute track spectrum (FFT) - BLOCKS EVENT LOOP           │ │
│ │ - Generate track chunks - BLOCKS EVENT LOOP                   │ │
│ └─────────────────────────────────────────────────────────────┘ │
│                            │                                      │
│                            ▼                                      │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ 4.5 Apply Frequency Masking (BLOCKING in async coroutine)   │ │
│ │ - MixService.apply_frequency_masking()                       │ │
│ │   • detect_masking() - NumPy ops - BLOCKS EVENT LOOP          │ │
│ │   • resolve_masking() - NumPy ops - BLOCKS EVENT LOOP        │ │
│ └─────────────────────────────────────────────────────────────┘ │
│                            │                                      │
│                            ▼                                      │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ 4.6 Blend Tracks (BLOCKING in async coroutine)               │ │
│ │ - Update job: state="mixing", progress=65                    │ │
│ │ - blend_tracks() - NumPy ops - BLOCKS EVENT LOOP             │ │
│ │   → utils/dsp/mix_pipeline.py:blend_tracks()                 │ │
│ │     • align_tracks() - NumPy ops                              │ │
│ │     • np.sum() - NumPy ops                                    │ │
│ │     • Peak normalization - NumPy ops                         │ │
│ │ - Master loudness normalization - BLOCKS EVENT LOOP           │ │
│ │ - Compute pre-master chunks - BLOCKS EVENT LOOP                │ │
│ │ - Compute pre-master scope - BLOCKS EVENT LOOP                 │ │
│ │ - Compute pre-master spectrum - BLOCKS EVENT LOOP            │ │
│ └─────────────────────────────────────────────────────────────┘ │
│                            │                                      │
│                            ▼                                      │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ 4.7 Master Bus Processing (BLOCKING in async coroutine)      │ │
│ │ - Update job: state="mastering", progress=80                  │ │
│ │ - process_master_bus() - BLOCKS EVENT LOOP                    │ │
│ │   → utils/dsp/mix_pipeline.py:process_master_bus()           │ │
│ │     • apply_eq() - NumPy ops                                  │ │
│ │     • apply_compressor() - NumPy ops                          │ │
│ │     • apply_limiter() - NumPy ops                             │ │
│ │ - Apply stereo widening - BLOCKS EVENT LOOP                    │ │
│ └─────────────────────────────────────────────────────────────┘ │
│                            │                                      │
│                            ▼                                      │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ 4.8 Compute Visual Data (BLOCKING in async coroutine)       │ │
│ │ - compute_waveform() - BLOCKS EVENT LOOP                     │ │
│ │ - compute_fft_spectrum() - BLOCKS EVENT LOOP                  │ │
│ │ - compute_levels() - BLOCKS EVENT LOOP                        │ │
│ │ - compute_energy_curve() - BLOCKS EVENT LOOP                  │ │
│ │ - Update job.extra with visual data                           │ │
│ └─────────────────────────────────────────────────────────────┘ │
│                            │                                      │
│                            ▼                                      │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ 4.9 Export Final Mix (THREADED)                              │ │
│ │ - Update job: state="exporting", progress=90                  │ │
│ │ - Create output directory                                     │ │
│ │ - await asyncio.to_thread(save_wav, output_path, master_audio)│ │
│ │   → utils/dsp/export.py:save_wav()                            │ │
│ │     • Normalize to int16 - CPU-bound                           │ │
│ │     • Convert to bytes - CPU-bound                             │ │
│ │     • wave.open() - BLOCKING I/O                               │ │
│ │     • Write frames - BLOCKING I/O                              │ │
│ │ - Store duration in transport                                  │ │
│ └─────────────────────────────────────────────────────────────┘ │
│                            │                                      │
│                            ▼                                      │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ 4.10 Complete Job                                            │ │
│ │ - Update job: state="complete", progress=100                  │ │
│ │ - Write to project memory (JSON file)                         │ │
│ │ - Return success result                                        │ │
│ └─────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ 5. Background Task Completion                                    │
│ File: routers/mix_router.py:213-229                              │
│ Function: _process_mix_job()                                     │
│ - Logs success or error                                          │
│ - Task completes (no further action)                              │
└─────────────────────────────────────────────────────────────────┘
```

### Job Progress Updates

Job state is updated via `MixJobManager.update()` at these points:

1. **Line 174:** `state="loading_stems"`, `progress=10`
2. **Line 195:** `state="aligning_stems"`, `progress=25`
3. **Line 212:** `state="processing_tracks"`, `progress=50`
4. **Line 329:** `state="mixing"`, `progress=65`
5. **Line 414:** `state="mastering"`, `progress=80`
6. **Line 440:** `message="Visual data computed"` (no state change)
7. **Line 465:** `state="exporting"`, `progress=90`
8. **Line 484:** `state="complete"`, `progress=100`
9. **Line 514:** `state="error"`, `progress=100` (on exception)

**File:** `jobs/mix_job_manager.py:161`  
**Function:** `MixJobManager.update()`  
- Updates job state in memory
- Persists to filesystem (JSON)
- Updates cache (JOBS dict)
- Adds timeline event

### File Outputs

**Output Location:** `./storage/mix_outputs/{session_id}/final_mix.wav`

**Created at:** `services/mix_service.py:469-474`

**Project Memory Update:** `services/mix_service.py:492-501`
- Updates `memory.project_data["mix"]` with:
  - `mix_url`: `/storage/mix_outputs/{session_id}/final_mix.wav`
  - `final_output`: Same URL
  - `completed`: `True`

---

## Summary: Blocking vs Threaded Operations

### Threaded (via `asyncio.to_thread()`)
- ✅ File existence checks (`Path.exists()`)
- ✅ Audio loading (`load_wav()`)
- ✅ Stem alignment (`align_stems()`)
- ✅ Audio export (`save_wav()`)

### Blocking in Async Coroutine (Event Loop)
- ❌ Auto gain, micro-dynamics, tonal balance, spatial separation
- ❌ Track DSP processing (EQ, compressor, saturation, etc.)
- ❌ Frequency masking
- ❌ Track blending
- ❌ Master bus processing
- ❌ Visual data computation (waveform, FFT, levels, energy curve)

**Impact:** NumPy operations block the event loop, but are typically fast enough. However, under high concurrency, this can cause latency spikes.

---

## Findings

### ✅ What Works
1. **Non-blocking HTTP responses:** Requests return immediately with `job_id`
2. **Background processing:** Mix runs independently of HTTP request
3. **Progress tracking:** Job state updates throughout execution
4. **Error handling:** Exceptions are caught and job state updated

### ❌ Critical Issues
1. **No concurrency limits:** Unlimited concurrent mix jobs can exhaust resources
2. **Thread pool exhaustion risk:** ~40 concurrent mixes can exhaust default thread pool
3. **No job queue:** Jobs spawned directly, no persistence or retry mechanism
4. **No timeouts:** Mix jobs can run indefinitely if stuck
5. **Event loop blocking:** NumPy operations block event loop (though typically fast)
6. **No backpressure:** System accepts unlimited requests without queuing

### ⚠️ Performance Concerns
1. **Sequential stem loading:** Stems loaded one at a time (could be parallelized)
2. **Memory usage:** Full audio arrays kept in memory throughout processing
3. **File I/O blocking:** Even though threaded, large files can take seconds
4. **No streaming:** Full audio must be loaded before processing

---

## Recommendations (For Future Implementation)

1. **Add concurrency limits:** Use `asyncio.Semaphore` to limit concurrent mix jobs
2. **Implement job queue:** Use Redis or database-backed queue for persistence
3. **Add timeouts:** Wrap `MixService.mix()` with `asyncio.wait_for()`
4. **Parallelize stem loading:** Load stems concurrently instead of sequentially
5. **Consider ProcessPoolExecutor:** For CPU-intensive DSP, consider process pool
6. **Add monitoring:** Track running jobs, queue depth, thread pool usage
7. **Implement backpressure:** Reject requests when queue is full

---

**End of Investigation**


