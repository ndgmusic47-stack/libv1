# Phase 6C Readiness Report
## Deep Structural Investigation

**Generated:** 2024  
**Scope:** Complete repository analysis for Phase 6C (Real-time Mix Visualization) integration  
**Status:** Investigation Only - No Changes Made

---

## Executive Summary

The codebase is **structurally ready** for Phase 6C integration with well-defined DSP chains, WebSocket infrastructure, and job management. However, **no real-time visualization infrastructure exists** yet. The mix pipeline processes audio in batch mode, and WebSocket updates are limited to job state/progress only.

**Key Findings:**
- ✅ Clean DSP chain architecture with clear separation
- ✅ WebSocket infrastructure exists but needs enhancement for real-time meter data
- ✅ Job state management is robust and extensible
- ❌ No gain-reduction meter taps in compressor/limiter
- ❌ No per-track spectrum extraction during processing
- ❌ No bus-level FFT/scope infrastructure
- ❌ Missing visualization modules (scope, meters, spectrum)

---

## 1. Mix Engine Structure

### 1.1 DSP Chain Architecture

**Location:** `utils/dsp/mix_pipeline.py`

**Current Flow:**
```
process_track() → per-track chain:
  1. match_loudness()
  2. apply_eq()
  3. apply_compressor()
  4. apply_saturation()
  5. apply_gain()
  6. apply_deesser() [vocals only]
  7. add_air() [vocals only]
  8. stereo_widen() [backing vocals only]

blend_tracks() → sum all processed tracks

process_master_bus() → master chain:
  1. apply_eq()
  2. apply_compressor()
  3. apply_limiter()
```

**Track Routing (lead→double→harm→adlib→bus):**
- **Role Detection:** `utils/mix/roles.py` → `detect_role()` identifies track roles from filename
- **Preset Application:** `utils/mix/presets.py` → `ROLE_PRESETS` applies role-specific configs
- **Vocal Chain:** lead, double, harmony, adlib → deesser + air + stereo widening
- **Instrumental:** beat/instrumental → minimal processing
- **Blending:** All tracks summed in `blend_tracks()` → master bus

### 1.2 Safe Interception Points

#### ✅ **Per-Track Frequency Analysis**
**Location:** `services/mix_service.py:256-279` (track processing loop)

**Safe Injection Point:**
```python
# Line 278: After process_track() but before appending to processed_tracks
processed_data = process_track(audio_data, track_config)

# ✅ SAFE: Insert per-track spectrum extraction here
# track_spectrum = extract_track_spectrum(processed_data, stem_name)
# processed_tracks.append(processed_data)
```

**Recommendation:**
- Extract spectrum **after** full track DSP chain (post-compressor, post-EQ)
- Store in `job.extra["track_spectra"][stem_name]` for WebSocket push

#### ✅ **Bus-Level FFT**
**Location:** `services/mix_service.py:287-309` (master bus processing)

**Safe Injection Points:**
1. **Pre-Master Bus:** After `blend_tracks()` (line 287)
   ```python
   blended_audio = blend_tracks(processed_tracks)
   # ✅ SAFE: Extract pre-master spectrum
   # pre_master_spectrum = compute_fft_spectrum(blended_audio)
   ```

2. **Post-Master Bus:** After `process_master_bus()` (line 309)
   ```python
   mastered_audio = process_master_bus(blended_audio, mastering_config)
   # ✅ SAFE: Extract post-master spectrum
   # post_master_spectrum = compute_fft_spectrum(mastered_audio)
   ```

3. **Final Output:** After stereo widening (line 312)
   ```python
   master_audio = stereo_widen(mastered_audio, amount=0.15)
   # ✅ SAFE: Extract final scope data
   # final_scope = compute_scope(master_audio)
   ```

#### ✅ **Gain-Reduction Meter Signals**
**Current State:** ❌ **NOT IMPLEMENTED**

**Required Modifications:**
- `utils/dsp/compressor.py`: Add GR meter tap
- `utils/dsp/limiter.py`: Add GR meter tap

**Safe Injection Points:**
1. **Per-Track Compressor:** `utils/dsp/compressor.py:apply_compressor()`
   - Currently returns only processed audio
   - **Need:** Return tuple `(processed_audio, gr_meter_data)`
   - GR data: `{"gain_reduction_db": float, "envelope": np.array}`

2. **Master Bus Compressor:** Same as above, but in master chain
   - Location: `utils/dsp/mix_pipeline.py:87-93`

3. **Limiter:** `utils/dsp/limiter.py:apply_limiter()`
   - Currently returns only processed audio
   - **Need:** Return tuple `(processed_audio, gr_meter_data)`

**Implementation Pattern:**
```python
# Example modification needed:
def apply_compressor(audio_data, threshold=-18, ratio=4.0, attack=5, release=50):
    # ... existing processing ...
    gr_db = 20 * np.log10(gain + 1e-9)  # Gain reduction in dB
    return out, {"gain_reduction_db": gr_db, "envelope": env}
```

#### ✅ **Mix-Bus Scope Taps**
**Location:** `services/mix_service.py:312` (after stereo widening)

**Safe Injection Point:**
```python
master_audio = stereo_widen(mastered_audio, amount=0.15)
# ✅ SAFE: Extract scope data (waveform, L/R correlation, phase)
# scope_data = compute_scope(master_audio, window_size=1024)
```

**Recommendation:**
- Create `utils/dsp/scope.py` with `compute_scope()` function
- Extract: waveform samples, L/R correlation, phase relationship
- Downsample for real-time transmission (e.g., 512 samples per update)

### 1.3 Master Bus Output Location

**Primary Output:** `services/mix_service.py:340`
```python
await asyncio.to_thread(save_wav, str(output_path), master_audio)
```

**File Path:** `storage/mix_outputs/{session_id}/final_mix.wav`

**Insertion Points for Visualization:**
1. **Before export** (line 339): Extract final visualization data
2. **During processing** (lines 247-312): Extract intermediate data for real-time updates

---

## 2. WebSocket & Timeline Integration

### 2.1 WebSocket Router

**Location:** `routers/mix_ws_router.py`

**Current Implementation:**
- Endpoint: `/ws/mix/status/{job_id}`
- Update Frequency: **0.5 seconds** (line 41: `await asyncio.sleep(0.5)`)
- Payload Structure:
  ```json
  {
    "job_id": "...",
    "state": "...",
    "progress": 0-100,
    "message": "...",
    "error": null,
    "visual": {...},  // Currently only final visual data
    "timeline": [...]
  }
  ```

**Current Limitations:**
- ❌ No real-time meter data in payload
- ❌ No per-track spectrum updates
- ❌ No bus-level scope updates
- ❌ Visual data only sent after completion (line 327 in mix_service.py)

### 2.2 MixJobState Integrity

**Location:** `models/mix_job_state.py`

**Structure:**
```python
@dataclass
class MixJobState:
    job_id: str
    session_id: str
    state: str
    progress: int
    message: str
    error: Optional[str]
    created_at: datetime
    updated_at: datetime
    extra: dict  # ✅ Extensible for real-time data
```

**✅ Safe for Phase 6C:**
- `extra` dict can store:
  - `extra["realtime_meters"]` → per-track + master GR meters
  - `extra["realtime_spectra"]` → per-track + bus spectra
  - `extra["realtime_scope"]` → bus-level scope data

**Update Mechanism:**
- `MixJobManager.update()` (line 18 in `jobs/mix_job_manager.py`)
- Updates job state and triggers timeline event
- **Safe to extend** with real-time data updates

### 2.3 Timeline Event Order

**Location:** `utils/mix/timeline.py`

**Current Implementation:**
- In-memory storage: `TIMELINE = {}` (dict of job_id → list of events)
- Events appended in order
- Events created via `add_event()` in `MixJobManager.update()`

**✅ Integrity:**
- Events are append-only (no modification)
- Timestamped automatically
- Ordered by insertion (FIFO)

**Phase 6C Consideration:**
- Real-time meter updates should **NOT** create timeline events (too frequent)
- Use `job.extra["realtime_meters"]` for live data
- Timeline events remain for major state transitions only

### 2.4 WebSocket Update Frequency Safety

**Current:** 0.5 seconds (500ms)

**Phase 6C Requirements:**
- Meter updates: **10-30 FPS** (33-100ms intervals)
- Spectrum updates: **5-10 FPS** (100-200ms intervals)
- Scope updates: **10-20 FPS** (50-100ms intervals)

**⚠️ Risk:**
- Current 500ms update rate is **too slow** for smooth real-time visualization
- Need to reduce to **50-100ms** for responsive meters

**Recommendation:**
- Add separate WebSocket endpoint: `/ws/mix/realtime/{job_id}`
- Or: Reduce sleep interval to 50ms and batch updates
- Consider: Separate channels for meters vs. spectrum vs. scope

### 2.5 Capacity for "realtime_meter" Payload Blocks

**Current Payload Size:**
- Minimal (job state, progress, message)
- Visual data only sent once at completion

**Phase 6C Payload Structure:**
```json
{
  "job_id": "...",
  "state": "...",
  "progress": 0-100,
  "realtime_meters": {
    "tracks": {
      "vocal": {"gain_reduction_db": -3.2, "rms": 0.45, "peak": 0.89},
      "beat": {"gain_reduction_db": -1.1, "rms": 0.32, "peak": 0.67}
    },
    "master": {
      "gain_reduction_db": -2.5,
      "limiter_gr_db": -0.8,
      "rms": 0.52,
      "peak": 0.95
    }
  },
  "realtime_spectra": {
    "tracks": {
      "vocal": [0.1, 0.2, ..., 0.05],  // 256 bins
      "beat": [0.3, 0.4, ..., 0.1]
    },
    "pre_master": [0.5, 0.6, ..., 0.2],
    "post_master": [0.48, 0.58, ..., 0.19]
  },
  "realtime_scope": {
    "waveform": [0.1, -0.2, ..., 0.05],  // 512 samples
    "l_r_correlation": 0.85,
    "phase": [0.1, 0.2, ..., -0.1]  // 512 samples
  }
}
```

**Payload Size Estimate:**
- Meters: ~200 bytes
- Spectra (4 tracks + 2 buses, 256 bins each): ~6KB
- Scope (512 samples): ~4KB
- **Total: ~10KB per update**

**✅ Capacity:**
- WebSocket can handle 10KB updates at 10-20 FPS
- Consider compression for spectrum/scope arrays (base64 or gzip)

---

## 3. DSP Chain Layout

### 3.1 Lead→Double→Harm→Adlib→Bus Route

**Role Detection:** `utils/mix/roles.py:detect_role()`
- Filename-based detection (lead, double, harmony, adlib, beat/instrumental)

**Processing Order:** Determined by `stems` dict iteration order in `mix_service.py:256`
- **Current:** No guaranteed order (dict iteration is unordered in Python <3.7, ordered in 3.7+)
- **Recommendation:** Sort stems by role priority for consistent processing

**Vocal Chain Application:** `utils/dsp/mix_pipeline.py:74-80`
```python
if role in ["lead", "double", "harmony", "adlib"]:
    processed = apply_deesser(processed)
    processed = add_air(processed)

if role in ["double", "harmony"]:
    processed = stereo_widen(processed)
```

**Blending:** `utils/dsp/mix_pipeline.py:98-105`
- All tracks summed: `mix = np.sum(tracks, axis=0)`
- Peak normalization if > 1.0

### 3.2 GR Meter Tap Locations

**Required Modifications:**

1. **Per-Track Compressor** (`utils/dsp/compressor.py`)
   - **Current:** Returns only `out` (processed audio)
   - **Need:** Return `(out, gr_data)` where `gr_data = {"gain_reduction_db": float, "envelope": np.array}`
   - **Tap Location:** Line 31 (after gain calculation)

2. **Master Bus Compressor** (`utils/dsp/mix_pipeline.py:87-93`)
   - Same modification as above
   - **Tap Location:** After `apply_compressor()` call

3. **Limiter** (`utils/dsp/limiter.py`)
   - **Current:** Returns only processed audio
   - **Need:** Return `(processed_audio, gr_data)` where `gr_data = {"gain_reduction_db": float}`
   - **Tap Location:** Line 13 (after gain calculation)

**Implementation Pattern:**
```python
# Modified compressor signature:
def apply_compressor(audio_data, threshold=-18, ratio=4.0, attack=5, release=50, return_gr=False):
    # ... existing processing ...
    if return_gr:
        gr_db = 20 * np.log10(gain + 1e-9)
        return out, {"gain_reduction_db": gr_db, "envelope": env}
    return out
```

### 3.3 Pre/Post Chain Visual Taps

**Per-Track Pre/Post:**
- **Pre:** Before `process_track()` (raw audio_data)
- **Post:** After `process_track()` (processed_data)
- **Location:** `services/mix_service.py:278`

**Master Bus Pre/Post:**
- **Pre:** After `blend_tracks()` (blended_audio)
- **Post:** After `process_master_bus()` (mastered_audio)
- **Location:** `services/mix_service.py:287, 309`

**Final Output:**
- **Post:** After `stereo_widen()` (master_audio)
- **Location:** `services/mix_service.py:312`

**Safe Tap Points:**
1. **Line 232:** After loading each stem → extract raw spectrum
2. **Line 278:** After process_track() → extract processed spectrum
3. **Line 287:** After blend_tracks() → extract pre-master spectrum
4. **Line 309:** After process_master_bus() → extract post-master spectrum
5. **Line 312:** After stereo_widen() → extract final scope

---

## 4. File Structure

### 4.1 Missing Folders for Phase 6C

**Required Directories:**
- ❌ `utils/dsp/scope.py` - Scope computation module
- ❌ `utils/dsp/meters.py` - Meter computation module (optional, can be in compressor/limiter)
- ❌ `utils/visualization/` - Visualization utilities (optional, can use existing `analyze_audio.py`)

**Current Structure:**
```
utils/dsp/
  - analyze_audio.py  ✅ (has compute_fft_spectrum, compute_waveform)
  - compressor.py     ⚠️  (needs GR meter tap)
  - limiter.py        ⚠️  (needs GR meter tap)
  - mix_pipeline.py   ✅ (main chain)
  - ... (other modules)
```

**Recommendation:**
- **Create:** `utils/dsp/scope.py` for scope computation
- **Extend:** `utils/dsp/analyze_audio.py` with real-time spectrum extraction
- **Modify:** `compressor.py` and `limiter.py` to return GR data

### 4.2 Conflicts from Previous Phases

**No Conflicts Detected:**
- Clean separation between DSP modules
- No duplicate functionality
- No legacy code blocking Phase 6C

**Potential Naming Conflicts:**
- `compute_fft_spectrum()` in `analyze_audio.py` - ✅ Safe, can be reused
- `compute_waveform()` in `analyze_audio.py` - ✅ Safe, can be reused for scope

### 4.3 Duplicated/Legacy Modules

**No Duplicates Found:**
- All DSP modules are single-purpose
- No conflicting implementations
- Clean module structure

**Legacy Code:**
- `apply_basic_mix()` in `mix_service.py:31` - Legacy pydub-based mixing
- **Status:** Still used by `mix_audio()` method (line 366)
- **Impact:** None for Phase 6C (Phase 6C uses DSP-based `mix()` method)

---

## 5. MixService Safe Regions

### 5.1 Per-Track Spectrum Extraction

**Safe Region:** `services/mix_service.py:256-279`

**Exact Location:**
```python
# Line 278: After process_track()
processed_data = process_track(audio_data, track_config)

# ✅ SAFE INSERTION POINT:
# Extract spectrum for this track
track_spectrum = compute_fft_spectrum(processed_data, bins=256)
if job_id:
    job = JOBS.get(job_id)
    if job:
        if "realtime_spectra" not in job.extra:
            job.extra["realtime_spectra"] = {"tracks": {}}
        job.extra["realtime_spectra"]["tracks"][stem_name] = track_spectrum

processed_tracks.append(processed_data)
```

**Considerations:**
- Extract **after** full DSP chain (includes EQ, compressor, saturation)
- Store in `job.extra` for WebSocket access
- Update frequency: Every track (not real-time during processing, but per-track)

### 5.2 Bus-Level Scope Computation

**Safe Region:** `services/mix_service.py:287-312`

**Exact Locations:**

1. **Pre-Master Bus** (line 287):
```python
blended_audio = blend_tracks(processed_tracks)
# ✅ SAFE: Extract pre-master scope
pre_master_scope = compute_scope(blended_audio, window_size=1024)
if job_id:
    job = JOBS.get(job_id)
    if job:
        if "realtime_scope" not in job.extra:
            job.extra["realtime_scope"] = {}
        job.extra["realtime_scope"]["pre_master"] = pre_master_scope
```

2. **Post-Master Bus** (line 309):
```python
mastered_audio = process_master_bus(blended_audio, mastering_config)
# ✅ SAFE: Extract post-master scope
post_master_scope = compute_scope(mastered_audio, window_size=1024)
if job_id:
    job = JOBS.get(job_id)
    if job:
        job.extra["realtime_scope"]["post_master"] = post_master_scope
```

3. **Final Output** (line 312):
```python
master_audio = stereo_widen(mastered_audio, amount=0.15)
# ✅ SAFE: Extract final scope
final_scope = compute_scope(master_audio, window_size=1024)
if job_id:
    job = JOBS.get(job_id)
    if job:
        job.extra["realtime_scope"]["final"] = final_scope
```

**Note:** `compute_scope()` function needs to be created in `utils/dsp/scope.py`

### 5.3 Gain-Reduction Visual Data Attachment

**Safe Region:** Requires DSP module modifications

**Per-Track GR:**
- Modify `process_track()` in `mix_pipeline.py` to collect GR from compressor
- Store in `job.extra["realtime_meters"]["tracks"][stem_name]`

**Master Bus GR:**
- Modify `process_master_bus()` in `mix_pipeline.py` to collect GR from compressor + limiter
- Store in `job.extra["realtime_meters"]["master"]`

**Exact Location in MixService:**
```python
# Line 278: After process_track() - need to modify process_track() to return GR
processed_data, gr_data = process_track(audio_data, track_config, return_gr=True)
if job_id:
    job = JOBS.get(job_id)
    if job:
        if "realtime_meters" not in job.extra:
            job.extra["realtime_meters"] = {"tracks": {}}
        job.extra["realtime_meters"]["tracks"][stem_name] = gr_data
```

### 5.4 Real-Time Frames into WebSocket

**Current WebSocket:** `routers/mix_ws_router.py:10-45`

**Safe Enhancement Location:**
```python
# Line 21-37: Payload construction
payload = {
    "job_id": job.job_id,
    "state": job.state,
    "progress": job.progress,
    "message": job.message,
    "error": job.error,
    "visual": job.extra.get("visual", None),
    # ✅ SAFE: Add real-time data blocks
    "realtime_meters": job.extra.get("realtime_meters", None),
    "realtime_spectra": job.extra.get("realtime_spectra", None),
    "realtime_scope": job.extra.get("realtime_scope", None),
    "timeline": [...]
}
```

**Update Frequency:**
- Current: 500ms (line 41)
- **Need:** 50-100ms for smooth real-time visualization
- **Recommendation:** Reduce to 50ms or create separate high-frequency endpoint

**Consideration:**
- Real-time data only available **during processing** (state: "processing_tracks", "mixing", "mastering")
- After completion, send final visual data only

---

## 6. Safety / No-Touch Zones

### 6.1 DSP Math - ⛔ DO NOT MODIFY

**Protected Modules:**
- `utils/dsp/compressor.py` - Core compression algorithm (lines 4-33)
- `utils/dsp/eq.py` - Biquad filter math (lines 15-44)
- `utils/dsp/limiter.py` - Peak limiting algorithm (lines 4-15)
- `utils/dsp/saturator.py` - Soft clipping (lines 4-10)
- `utils/dsp/gain.py` - Gain application (lines 4-6)
- `utils/dsp/deesser.py` - De-essing algorithm (lines 3-26)
- `utils/dsp/air.py` - High-frequency boost (lines 3-23)
- `utils/dsp/stereo.py` - Mid/side processing (lines 3-23)

**Safe Modification:**
- ✅ **Return values:** Can modify functions to return additional data (GR meters) without changing math
- ✅ **Function signatures:** Can add optional parameters (e.g., `return_gr=False`)
- ❌ **Algorithm logic:** Do not modify core DSP calculations

### 6.2 Existing mix_pipeline - ⚠️ CAREFUL MODIFICATION

**Protected Functions:**
- `match_loudness()` - RMS matching (lines 14-19)
- `align_tracks()` - Track alignment (lines 22-31)
- `blend_tracks()` - Track summing (lines 98-105)

**Safe Modifications:**
- ✅ **process_track():** Can add GR meter collection (lines 34-82)
- ✅ **process_master_bus():** Can add GR meter collection (lines 85-95)
- ✅ **Function signatures:** Can add optional return parameters

**⚠️ Risk Areas:**
- Modifying `blend_tracks()` could affect mix balance
- Modifying `match_loudness()` could affect track levels

### 6.3 Presets, Recipes, Role Routing - ⛔ DO NOT MODIFY

**Protected Files:**
- `utils/mix/presets.py` - `ROLE_PRESETS` dict (lines 1-55)
- `utils/mix/recipes.py` - `MIX_RECIPES` dict (lines 1-39)
- `utils/mix/roles.py` - `detect_role()` function (lines 4-24)

**Rationale:**
- Presets define track processing parameters
- Recipes define master bus settings
- Role routing determines which effects apply to which tracks
- **Modifying these will change mix behavior**

**Safe Usage:**
- ✅ **Read-only access:** Can read presets/recipes for visualization context
- ✅ **Metadata extraction:** Can extract parameter names for UI labels

### 6.4 Audio Loaders/Exporters - ⛔ DO NOT MODIFY

**Protected Files:**
- `utils/dsp/load.py` - `load_wav()` function (lines 6-27)
- `utils/dsp/export.py` - `save_wav()` function (lines 6-24)

**Rationale:**
- Core I/O functions must remain stable
- Changes could break file compatibility

**Safe Usage:**
- ✅ **Read-only:** Use loaded audio data for visualization
- ✅ **Metadata:** Can extract sample rate, channels for visualization setup

---

## 7. Missing Modules Needed for Phase 6C

### 7.1 Required New Modules

1. **`utils/dsp/scope.py`**
   - Function: `compute_scope(audio, window_size=1024)`
   - Returns: `{"waveform": np.array, "l_r_correlation": float, "phase": np.array}`
   - Purpose: Extract scope data for visualization

2. **Enhanced `utils/dsp/compressor.py`**
   - Add: `return_gr=False` parameter
   - Return: `(processed_audio, gr_data)` when `return_gr=True`
   - GR data: `{"gain_reduction_db": float, "envelope": np.array}`

3. **Enhanced `utils/dsp/limiter.py`**
   - Add: `return_gr=False` parameter
   - Return: `(processed_audio, gr_data)` when `return_gr=True`
   - GR data: `{"gain_reduction_db": float}`

4. **Enhanced `utils/dsp/mix_pipeline.py`**
   - Modify: `process_track()` to accept `return_gr=False` and return GR data
   - Modify: `process_master_bus()` to accept `return_gr=False` and return GR data
   - Purpose: Collect GR meters from compressor/limiter calls

5. **Enhanced `utils/dsp/analyze_audio.py`** (optional)
   - Add: `extract_realtime_spectrum(audio, bins=256, hop_size=1024)`
   - Purpose: Extract spectrum with configurable hop size for real-time updates

### 7.2 Optional Enhancements

1. **`utils/visualization/realtime.py`** (optional)
   - Centralized real-time data extraction
   - Batch processing for efficiency

2. **WebSocket payload compression** (optional)
   - Compress spectrum/scope arrays before transmission
   - Reduce bandwidth for high-frequency updates

---

## 8. Recommended Patch Sequence (6C → 6D → 6E)

### Phase 6C: Real-Time Meters & Basic Spectrum

**Priority: HIGH**

**Steps:**
1. ✅ Modify `compressor.py` to return GR data (optional parameter)
2. ✅ Modify `limiter.py` to return GR data (optional parameter)
3. ✅ Modify `mix_pipeline.py` to collect GR from compressor/limiter
4. ✅ Update `mix_service.py` to store GR in `job.extra["realtime_meters"]`
5. ✅ Update WebSocket router to include `realtime_meters` in payload
6. ✅ Reduce WebSocket update frequency to 50-100ms
7. ✅ Extract per-track spectrum after `process_track()` (post-DSP)
8. ✅ Extract bus-level spectrum after `blend_tracks()` and `process_master_bus()`
9. ✅ Store spectra in `job.extra["realtime_spectra"]`
10. ✅ Update WebSocket payload to include `realtime_spectra`

**Deliverables:**
- Real-time gain-reduction meters (per-track + master)
- Per-track spectrum visualization
- Bus-level spectrum visualization

### Phase 6D: Advanced Scope Visualization

**Priority: MEDIUM**

**Steps:**
1. ✅ Create `utils/dsp/scope.py` with `compute_scope()` function
2. ✅ Extract scope data at pre-master, post-master, and final output points
3. ✅ Store scope in `job.extra["realtime_scope"]`
4. ✅ Update WebSocket payload to include `realtime_scope`
5. ✅ Optimize scope data size (downsample, compression)

**Deliverables:**
- Waveform scope visualization
- L/R correlation meter
- Phase relationship visualization

### Phase 6E: Real-Time Processing & Optimization

**Priority: LOW**

**Steps:**
1. ✅ Implement chunked processing for real-time updates during mix
2. ✅ Add frame-by-frame spectrum extraction (not just per-track)
3. ✅ Optimize WebSocket payload size (compression, batching)
4. ✅ Add separate high-frequency WebSocket endpoint for meters
5. ✅ Implement client-side buffering for smooth visualization

**Deliverables:**
- Frame-by-frame real-time updates
- Optimized bandwidth usage
- Smooth 30+ FPS visualization

---

## 9. Zero-Touch Zones Summary

### ⛔ **ABSOLUTELY DO NOT MODIFY:**

1. **DSP Algorithm Core:**
   - `compressor.py` - compression math (lines 11-31)
   - `eq.py` - biquad filter math (lines 15-44)
   - `limiter.py` - peak limiting math (lines 9-15)
   - `saturator.py` - soft clipping math (lines 9-10)
   - `deesser.py` - de-essing algorithm (lines 10-26)
   - `air.py` - high-frequency boost (lines 10-23)
   - `stereo.py` - mid/side processing (lines 8-16)

2. **Audio I/O:**
   - `load.py` - `load_wav()` function
   - `export.py` - `save_wav()` function

3. **Mix Configuration:**
   - `presets.py` - `ROLE_PRESETS` dict
   - `recipes.py` - `MIX_RECIPES` dict
   - `roles.py` - `detect_role()` function

4. **Core Mix Logic:**
   - `match_loudness()` - RMS matching
   - `align_tracks()` - track alignment
   - `blend_tracks()` - track summing (unless adding visualization taps)

### ✅ **SAFE TO MODIFY:**

1. **Function Return Values:**
   - Add optional return parameters (e.g., `return_gr=False`)
   - Return tuples with additional data

2. **Job State Management:**
   - `job.extra` dict for storing real-time data
   - WebSocket payload structure

3. **Visualization Extraction:**
   - Add spectrum/scope extraction after DSP processing
   - Store in `job.extra` for WebSocket access

4. **WebSocket Infrastructure:**
   - Update frequency
   - Payload structure
   - Separate endpoints for different data types

---

## 10. Risk Assessment

### 10.1 High Risk Areas

1. **Modifying DSP Return Signatures**
   - **Risk:** Breaking existing code that expects single return value
   - **Mitigation:** Use optional parameters (`return_gr=False`) with default behavior
   - **Impact:** Low if done carefully

2. **WebSocket Update Frequency**
   - **Risk:** High-frequency updates may overwhelm client or server
   - **Mitigation:** Implement batching, compression, and client-side buffering
   - **Impact:** Medium - can cause performance issues if not optimized

3. **Real-Time Data During Processing**
   - **Risk:** Extracting data during processing may slow down mix
   - **Mitigation:** Use efficient numpy operations, downsample data
   - **Impact:** Low - spectrum/scope extraction is fast

### 10.2 Medium Risk Areas

1. **Job State Memory Usage**
   - **Risk:** Storing large spectrum/scope arrays in `job.extra` may use memory
   - **Mitigation:** Downsample data, use efficient data types (float32)
   - **Impact:** Low - arrays are relatively small (~10KB per update)

2. **WebSocket Payload Size**
   - **Risk:** Large payloads may cause latency
   - **Mitigation:** Compress arrays, send only changed data
   - **Impact:** Medium - can cause lag if not optimized

### 10.3 Low Risk Areas

1. **Adding New Modules**
   - **Risk:** Minimal - new modules don't affect existing code
   - **Impact:** None

2. **Extending Job State**
   - **Risk:** Minimal - `job.extra` is designed for extensibility
   - **Impact:** None

---

## 11. Conclusion

### ✅ **Ready for Phase 6C:**
- Clean DSP chain architecture
- Extensible job state management
- WebSocket infrastructure in place
- Clear separation of concerns

### ⚠️ **Required Before Phase 6C:**
- Modify compressor/limiter to return GR data
- Create scope computation module
- Enhance WebSocket update frequency
- Add real-time data extraction points

### 🎯 **Recommended Approach:**
1. Start with Phase 6C (meters + basic spectrum)
2. Test with single track to validate architecture
3. Scale to multi-track + master bus
4. Optimize for performance
5. Proceed to Phase 6D (scope) and 6E (optimization)

### 📊 **Estimated Complexity:**
- **Phase 6C:** Medium (2-3 days)
- **Phase 6D:** Low-Medium (1-2 days)
- **Phase 6E:** Medium-High (3-5 days)

---

**Report Complete**  
**Status:** Ready for Phase 6C implementation with recommended modifications

