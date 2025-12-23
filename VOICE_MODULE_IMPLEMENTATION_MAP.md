# VOICE MODULE IMPLEMENTATION MAP
**Label-in-a-Box MVP - Voice Module Investigation Report**  
**Date:** Generated from codebase analysis  
**Purpose:** Facts-only mapping for AI sung vocal stem implementation planning

---

## A) VOICE MODULE UI + STATE

### Frontend Component Location
**File:** `frontend/src/components/stages/UploadStage.jsx`

### Buttons & Functions

#### 1. **Record Button** (Lines 355-369)
- **Button Text:** "Record" / "Recording..."
- **Function:** `startRecording()`
- **Location:** Lines 134-227
- **Behavior:**
  - Requests microphone permission via `navigator.mediaDevices.getUserMedia({ audio: true })`
  - Uses `MediaRecorder` API with preferred codecs: `audio/webm;codecs=opus`, `audio/webm`, `audio/ogg;codecs=opus`, `audio/ogg`
  - Records to `recordedChunksRef.current`
  - On stop: converts blob to File, calls `uploadFile(file)`
  - Filename format: `vocal_recorded_{Date.now()}.webm` or `.ogg`

#### 2. **Stop Recording Button** (Lines 371-386)
- **Button Text:** "Stop"
- **Function:** `stopRecording()`
- **Location:** Lines 229-237
- **Behavior:**
  - Stops `mediaRecorderRef.current`
  - Triggers `recorder.onstop` handler (lines 193-214)
  - Releases microphone stream

#### 3. **File Upload (Drop Zone)** (Lines 318-350)
- **Accept Formats:** `audio/*,.wav,.mp3,.aiff,.webm,.ogg`
- **Function:** `handleDrop()` (lines 56-78) and `handleFileSelect()` (lines 121-132)
- **Validation:** `validateAudioFile()` (lines 19-37)
  - Max size: 50MB
  - Allowed extensions: `.wav, .mp3, .aiff, .webm, .ogg`
- **Upload Function:** `uploadFile()` (lines 80-119)

#### 4. **Generate AI Song Button** (Lines 393-412)
- **Button Text:** "Generate AI Song (Sung)"
- **Function:** `handleGenerateSong()` (lines 254-295)
- **Visibility:** Only shown if `sessionData?.lyricsData` exists (line 394)
- **Behavior:**
  - Extracts lyrics from `sessionData.lyricsData` via `getLyricsText()` (lines 239-252)
  - Calls `api.generateSong(sessionId, lyricsText)` (line 271)
  - Updates `sessionData` with `vocalFile` and `vocalUploaded: true` (lines 277-280)
  - Auto-completes upload stage (lines 286-288)

### State Management

#### React State (UploadStage.jsx)
- **Component State:**
  - `dragging` (boolean)
  - `uploading` (boolean)
  - `error` (string | null)
  - `generating` (boolean)
  - `generationStatus` (string | null)
  - `isRecording` (boolean)
- **Refs:**
  - `mediaRecorderRef` (MediaRecorder instance)
  - `mediaStreamRef` (MediaStream for cleanup)
  - `recordedChunksRef` (array of Blob chunks)

#### Session Data (AppPage.jsx, lines 34-42)
**Location:** `frontend/src/pages/AppPage.jsx`

**State Structure:**
```javascript
sessionData = {
  beatFile: null,          // URL to beat file
  lyricsData: null,        // Lyrics text or structured object
  vocalFile: null,         // URL to vocal stem file
  masterFile: null,        // URL to mastered output
  genre: 'hip hop',        // Genre metadata
  mood: 'energetic',       // Mood metadata
  trackTitle: 'My Track',  // Track title
}
```

**Update Function:** `updateSessionData()` (AppPage.jsx, line 98)
- Called from UploadStage via props
- Updates React state in parent component

### Module Loading & Data Sources

#### Current Project ID Source
- **Source:** `localStorage.getItem('session_id')` (AppPage.jsx, line 32)
- **Initialization:** Set in `main.jsx` (not shown, referenced)
- **Passed to UploadStage:** Via `sessionId` prop

#### Beat URL Loading
- **From sessionData:** `sessionData.beatFile` (UploadStage.jsx, line 441)
- **Display:** Shown in preview section (lines 441-449) if present
- **Source:** Synced from `project.assets.beat.url` via `api.syncProject()` (api.js, lines 610-699)

#### Lyrics Loading
- **From sessionData:** `sessionData.lyricsData` (UploadStage.jsx, line 452)
- **Display:** Shown in preview section (lines 452-464) if present
- **Extraction Logic:** `getLyricsText()` (lines 239-252)
  - Returns `sessionData.lyricsData` if string
  - Otherwise returns `sessionData.lyricsData.lyrics_text` if object
- **Source:** Synced from `project.lyrics.text` or `project.lyrics_text` via `api.syncProject()` (api.js, lines 672-688)

#### Project Memory / Persistence Calls

**Frontend Sync:**
- `api.syncProject(sessionId, updateSessionData)` (api.js, lines 610-699)
- Called on:
  - AppPage mount (line 73)
  - After stage completion (AppPage.jsx, line 85)

**Backend Persistence:**
- Upload saves to project memory: `routers/media_router.py`, lines 97-111
- Generate song saves to project memory: `routers/media_router.py`, lines 328-346

**Project Memory Keys (project_memory.py, lines 63-74):**
```python
assets = {
    "beat": None,           # Dict: {url, added_at, metadata}
    "lyrics": None,         # Dict or string
    "vocals": [],           # Array: [{url, added_at, metadata}, ...]
    "stems": [],            # Array (legacy/backup)
    "song": None,           # Dict: {url, added_at, metadata: {source}}
    "mix": None,
    "master": None,
    ...
}
```

---

## B) FRONTEND → BACKEND API CALLS (Voice-Related)

### 1. Upload Recording Endpoint

**Frontend Call:**
- **Function:** `api.uploadRecording(file, sessionId)` (api.js, lines 215-226)
- **URL:** `POST /api/media/upload/vocal`
- **Method:** POST
- **Body:** FormData
  - `file`: File object
  - `session_id`: string (optional)

**Backend Implementation:**
- **File:** `routers/media_router.py`
- **Endpoint:** `/api/media/upload/vocal` (line 44-51, alias)
- **Handler:** `upload_audio()` (lines 54-120)

**Request Body Schema:**
```
FormData:
  file: UploadFile (required)
  session_id: str (optional, generated if missing)
```

**Validation:**
- File sanitization: `validate_uploaded_file()` (security_utils.py, lines 201-240)
  - Filename sanitization (removes path traversal, null bytes)
  - Extension whitelist: `.wav, .mp3, .aiff, .webm, .ogg`
  - Size limit: 50MB
  - MIME type validation (content-based magic bytes)
- **Location:** `utils/security_utils.py`

**Storage:**
- **Directory:** `media/{session_id}/recordings/`
- **Filename:** Sanitized original filename
- **Path Construction:** Lines 84-88
```python
recordings_dir = MEDIA_DIR / session_id / "recordings"
file_path = recordings_dir / sanitized_filename
file_url = f"/media/{session_id}/recordings/{sanitized_filename}"
```

**Response Schema:**
```json
{
  "ok": true,
  "data": {
    "session_id": "string",
    "file_url": "/media/{session_id}/recordings/{filename}",
    "file_path": "/media/{session_id}/recordings/{filename}"  // Same as file_url
  },
  "message": "Vocal uploaded"
}
```

**URL Normalization:**
- Frontend uses `normalizeMediaUrl()` (api.js, lines 5-29)
- Handles `/media/` → `/api/media/` conversion for dev/prod
- Returns normalized URL to `sessionData.vocalFile`

**Project Memory Update:**
- Lines 98-111: Updates `project_memory.project_data["assets"]["vocals"]` and `["song"]`
```python
assets["vocals"] = [{
    "url": file_url,
    "added_at": datetime.isoformat(),
    "metadata": {}
}]
assets["song"] = {
    "url": file_url,
    "added_at": datetime.isoformat(),
    "metadata": {"source": "upload"}
}
```

---

### 2. Generate Song Endpoint

**Frontend Call:**
- **Function:** `api.generateSong(sessionId, lyrics, style)` (api.js, lines 228-240)
- **URL:** `POST /api/media/generate/song`
- **Method:** POST
- **Body:** JSON

**Request Body Schema:**
```json
{
  "session_id": "string",
  "lyrics": "string | null",
  "style": "string | null"  // Default: "motivational hip-hop / rock"
}
```

**Backend Implementation:**
- **File:** `routers/media_router.py`
- **Endpoint:** `/api/media/generate/song` (lines 222-362)
- **Handler:** `generate_song()` (lines 223-362)

**Lyrics Resolution Priority:**
1. `request.lyrics` (from request body)
2. `request.lyrics_url` (fetch from file path)
3. `memory.project_data["assets"]["lyrics"]` (project memory)
4. `memory.project_data["lyrics"]` (legacy location)
5. Error if none found (line 287)

**AI Generation Service:**
- **File:** `services/replicate_song_service.py`
- **Function:** `replicate_generate_song_yue(lyrics, style)` (lines 12-100)
- **Model:** Replicate `fofr/yue`
- **Returns:** Audio URL (string)

**Validation:**
- Lyrics required (line 286-287)
- Replicate API token required (replicate_song_service.py, line 28-29)

**Storage:**
- **Download:** Downloads audio from Replicate URL (lines 300-303)
- **Directory:** `media/{session_id}/recordings/`
- **Filename:** `ai_song_{timestamp}.{ext}` (lines 317-318)
- **Extension:** Detected from Replicate URL (.mp3 or .wav)

**Response Schema:**
```json
{
  "ok": true,
  "data": {
    "session_id": "string",
    "file_url": "/media/{session_id}/recordings/ai_song_{timestamp}.{ext}",
    "file_path": "/media/{session_id}/recordings/ai_song_{timestamp}.{ext}"
  },
  "message": "AI song generated"
}
```

**Project Memory Update:**
- Lines 332-345: Updates `assets["song"]` and `assets["vocals"]`
```python
assets["song"] = {
    "url": file_url,
    "added_at": datetime.isoformat(),
    "metadata": {"source": "ai_song_replicate_yue"}
}
assets["vocals"] = [{
    "url": file_url,
    "added_at": datetime.isoformat(),
    "metadata": {"source": "ai_song_replicate_yue"}
}]
```

---

### 3. Generate Vocal Endpoint (TTS - EXISTS BUT UNUSED)

**File:** `routers/media_router.py`
- **Endpoint:** `POST /api/media/generate/vocal` (lines 123-219)
- **Handler:** `generate_vocal()` (lines 124-219)
- **Status:** EXISTS but NOT called from UploadStage.jsx

**Request Schema:**
```json
{
  "session_id": "string",
  "text": "string"
}
```

**Implementation:**
- Uses `gtts_speak()` from `utils/shared_utils.py` (lines 166-212)
- Google Text-to-Speech (gTTS) - robotic TTS, not singing
- Saves to `media/{session_id}/voices/{hash}.mp3`
- Copies to `media/{session_id}/recordings/ai_take_{timestamp}.mp3`
- **NOTE:** This is the removed robotic TTS feature (still exists but unused)

---

## C) AUDIO FORMATS & STEM CONTRACT

### Accepted Upload Formats

**Frontend Validation (UploadStage.jsx, lines 19-37):**
- **Extensions:** `.wav, .mp3, .aiff, .webm, .ogg`
- **Size Limit:** 50MB
- **Validation:** File extension check only (frontend)

**Backend Validation (security_utils.py, lines 26, 95-110):**
- **Allowed Extensions:** `.wav, .mp3, .aiff, .wave, .webm, .ogg`
- **Allowed MIME Types:**
  - `audio/wav`, `audio/wave`, `audio/x-wav`
  - `audio/mpeg`, `audio/mp3`, `audio/mpeg3`, `audio/x-mpeg-3`
  - `audio/aiff`, `audio/x-aiff`
  - `audio/webm`
  - `audio/ogg`
- **Size Limit:** 50MB (line 29)
- **MIME Detection:** Content-based magic bytes (lines 113-151)

### Audio Processing (DSP Pipeline)

**Loading (utils/dsp/load.py, lines 6-27):**
- **Function:** `load_wav(path, target_sr=44100)`
- **Sample Rate Normalization:**
  - Target: 44100 Hz (hardcoded)
  - Resampling: Linear interpolation if `sr != target_sr` (lines 21-25)
- **Mono/Stereo Handling:**
  - Mono input: Converted to stereo via `np.stack([audio_np, audio_np], axis=1)` (line 18)
  - Stereo input: Kept as `[N, 2]` array (line 16)
  - **Output Format:** Always `[N, 2]` numpy array (stereo)

**Format Support:**
- **load_wav()** only handles `.wav` files (wave module)
- MP3/AIFF/WebM/OGG must be converted to WAV before DSP processing
- **Conversion:** Not explicitly shown in codebase (assumed handled by external tooling)

### Canonical Vocal Stem Format

**Storage Location:**
- **Path:** `media/{session_id}/recordings/{filename}`
- **URL Format:** `/media/{session_id}/recordings/{filename}`

**Filename Conventions:**
- **Upload:** Original sanitized filename
- **Recorded:** `vocal_recorded_{timestamp}.webm` or `.ogg`
- **AI Generated:** `ai_song_{timestamp}.mp3` or `.wav` (from Replicate)

**Downstream Mix Processing:**
- **Function:** `MixService.mix()` (services/mix_service.py, lines 141-293)
- **Loading:** Uses `load_wav()` which normalizes to:
  - **Sample Rate:** 44100 Hz
  - **Channels:** Stereo `[N, 2]`
  - **Data Type:** `float32` normalized to [-1.0, 1.0]

**Metadata Saved:**
- **Project Memory:** `assets.vocals[0].metadata` (project_memory.py, lines 152-157)
  - Currently: `{}` (empty) for uploads
  - For AI: `{"source": "ai_song_replicate_yue"}` or `{"source": "upload"}`
- **Not Stored:**
  - Duration (must be computed from file)
  - BPM (stored in `metadata.tempo`, not in vocal metadata)
  - Key (stored in `metadata.key`, not in vocal metadata)
  - Offset (handled dynamically in `align_stems()`)

---

## D) MIX MODULE DEPENDENCY CONTRACT

### Where Mix Reads Vocal Stem & Beat

**Mix Start Endpoint:**
- **File:** `routers/mix_router.py`
- **Endpoint:** `POST /mix/{project_id}/mix/start` (lines 58-106)
- **Handler:** `start_mix()` (lines 59-106)

**Stem Resolution Logic (lines 70-90):**
1. **From Request:** `request.vocal_url` and `request.beat_url` (if provided)
2. **From Project Memory (fallback):**
   - Vocal: `memory.project_data["assets"]["vocals"][0]["url"]` (line 85)
   - Beat: `memory.project_data["assets"]["beat"]["url"]` (line 87)
3. **Error if missing:** Raises HTTPException 400 if both sources fail

**Legacy Fallback (run-clean wrapper, lines 308-315):**
- Looks for `media/{session_id}/vocal.wav` and `media/{session_id}/beat.mp3`
- **Status:** Compatibility wrapper, not primary path

### Expected Keys in Project Memory

**For Vocal:**
```python
assets = {
    "vocals": [
        {
            "url": "/media/{session_id}/recordings/{filename}",
            "added_at": "ISO datetime",
            "metadata": {}
        }
    ],
    # OR legacy fallback:
    "stems": [
        {"url": "..."}  # Falls back to stems[0] if vocals empty (api.js, line 633)
    ]
}
```

**For Beat:**
```python
assets = {
    "beat": {
        "url": "/media/{session_id}/beat.mp3",  # or other path
        "added_at": "ISO datetime",
        "metadata": {}
    }
}
```

### Alignment Expectations

**Alignment Implementation:**
- **File:** `utils/dsp/timing.py`
- **Function:** `align_stems(audio_data_dict, sample_rate=44100)` (lines 43-122)
- **Called From:** `MixService.mix()` (services/mix_service.py, lines 198-208)

**Alignment Logic:**
1. **Onset Detection:** `detect_onset()` (lines 7-40)
   - Finds first energy threshold crossing
   - Works on mono (converts stereo to mono for detection)
2. **Vocal-to-Beat Sync:**
   - Calculates: `offset_samples = beat_onset - vocal_onset`
   - If positive: Pads vocal at beginning
   - If negative: Trims vocal at beginning
   - **Result:** Vocal aligned to beat onset
3. **Length Matching:**
   - Pads shorter stem with zeros to match longer stem
   - Both stems end up same length

**Key Point:**
- **Mix expects vocal start at 0** (relative to beat onset after alignment)
- No stored offset required - alignment is automatic
- Alignment happens in-memory during mix processing
- Original files remain unchanged

**Mix Output:**
- **Location:** `storage/mix_outputs/{session_id}/final_mix.wav`
- **Format:** WAV, 44100 Hz, stereo
- **Project Memory:** Saved to `assets.mix.url` (not shown in code, inferred)

---

## E) REMOVED ROBOTIC TTS FEATURE AUDIT

### Search Results

**Terms Searched:** `tts`, `speech`, `robot`, `preview`, `eleven`, `polly`, `gtts`, `coqui`, `speak`

### Remaining Code Found

#### 1. `/api/media/generate/vocal` Endpoint (UNUSED)
- **File:** `routers/media_router.py`, lines 123-219
- **Status:** EXISTS but NOT called from frontend
- **Implementation:** Uses `gtts_speak()` (Google TTS - robotic speech)
- **Purpose:** Text-to-speech (not singing)
- **Removal Recommendation:** Can be removed or left as dead code (no frontend calls)

#### 2. `gtts_speak()` Function (USED ELSEWHERE)
- **File:** `utils/shared_utils.py`, lines 166-212
- **Status:** ACTIVE but used in lyrics router, not voice module
- **Usage:**
  - `routers/lyrics_router.py`, line 106: Generates voice preview for lyrics (not vocal stem)
  - This is a preview feature for lyrics, not the vocal generation feature

#### 3. Frontend Button References
- **NO "preview" or "robotic" buttons found in UploadStage.jsx**
- **Current button:** "Generate AI Song (Sung)" (line 410) - calls `generateSong()` which uses Replicate YuE

### Dead Code Paths to Avoid

**DO NOT REUSE:**
1. `/api/media/generate/vocal` endpoint (TTS, not singing)
2. `gtts_speak()` for vocal stem generation (robotic speech)
3. The `voices/` directory structure (`media/{session_id}/voices/`) - this is for TTS previews

**SAFE TO USE:**
1. `/api/media/generate/song` endpoint (Replicate YuE - actual singing)
2. `replicate_generate_song_yue()` service function
3. `recordings/` directory structure

### Unused Endpoints Summary

| Endpoint | Status | Purpose | Recommendation |
|----------|--------|---------|----------------|
| `POST /api/media/generate/vocal` | Dead code | TTS (robotic) | Safe to remove, or leave unused |
| `POST /api/media/generate/song` | Active | AI singing (Replicate YuE) | Current implementation |
| `POST /api/media/upload/vocal` | Active | File upload | Current implementation |

---

## F) GAPS / MISSING HOOKS FOR "AI SUNG STEM" BUTTON

### Current State

**Existing "Generate AI Song" Button:**
- **Location:** UploadStage.jsx, line 410
- **Endpoint:** `/api/media/generate/song`
- **Service:** Replicate YuE model
- **Status:** WORKS but uses Replicate's `fofr/yue` model (may not be true singing)

### Missing Features for True AI Sung Vocal Stem

#### 1. Input Requirements
- **Current:** Only requires lyrics text
- **Missing:**
  - Melody/MIDI input (for pitch contour)
  - Reference vocal (for style transfer)
  - Beat alignment hints (BPM, key)
  - Style/genre specification (partially supported via `style` param)

#### 2. Output Format Requirements
- **Current:** MP3 or WAV from Replicate (variable format)
- **Missing:**
  - Guaranteed WAV format for downstream processing
  - Sample rate normalization (Mix expects 44100 Hz)
  - Stereo conversion (Mix expects stereo)

#### 3. Alignment Integration
- **Current:** Alignment happens in Mix stage
- **Missing:**
  - Pre-alignment hint storage (if AI generation should align to beat)
  - BPM metadata from beat used during generation

#### 4. Project Memory Metadata
- **Current:** Only `{"source": "ai_song_replicate_yue"}`
- **Missing:**
  - Generation model name
  - Generation parameters (style, pitch, etc.)
  - Duration metadata
  - Alignment offset (if pre-computed)

#### 5. Error Handling & User Feedback
- **Current:** Basic error messages
- **Missing:**
  - Progress polling for long-running generation
  - Job system integration (like Mix has)
  - Status updates during generation

#### 6. Voice Selection / Cloning
- **Current:** No voice selection
- **Missing:**
  - Voice model selection UI
  - Voice cloning input (reference audio)
  - Voice style parameters (vibrato, breathiness, etc.)

---

## SUMMARY: CRITICAL PATHS & CONTRACTS

### Voice Module Flow

```
User Action → Frontend (UploadStage.jsx)
  ├─ Record → MediaRecorder → uploadFile()
  ├─ Upload → uploadFile() → api.uploadRecording()
  └─ Generate → handleGenerateSong() → api.generateSong()

Frontend API Call → Backend (routers/media_router.py)
  ├─ POST /api/media/upload/vocal → upload_audio()
  └─ POST /api/media/generate/song → generate_song()

Backend → Storage & Memory
  ├─ Save file: media/{session_id}/recordings/{filename}
  ├─ Update: project_memory.assets.vocals[0].url
  └─ Update: project_memory.assets.song.url

Mix Stage Reads From:
  ├─ project_memory.assets.vocals[0].url
  └─ project_memory.assets.beat.url

Mix Processing:
  ├─ Load: load_wav() → 44100 Hz, stereo, float32
  ├─ Align: align_stems() → vocal aligned to beat onset
  └─ Process: DSP chain → final_mix.wav
```

### Data Contracts

**Vocal Stem URL Format:**
- Path: `/media/{session_id}/recordings/{filename}`
- Normalized: Frontend uses `normalizeMediaUrl()` for dev/prod

**Project Memory Vocal Asset:**
```python
assets["vocals"] = [
    {
        "url": "/media/{session_id}/recordings/{filename}",
        "added_at": "2025-01-XX...",
        "metadata": {
            "source": "upload" | "ai_song_replicate_yue" | ...
        }
    }
]
```

**Mix Stem Dictionary:**
```python
stems = {
    "vocal": "/media/{session_id}/recordings/{filename}",
    "beat": "/media/{session_id}/beat.mp3"
}
```

**Audio Format for Mix:**
- Input: Any format (converted to WAV by load_wav)
- Processing: 44100 Hz, stereo [N, 2], float32 [-1.0, 1.0]
- Alignment: Automatic (vocal aligned to beat onset, start at 0 after padding)

---

## END OF REPORT






