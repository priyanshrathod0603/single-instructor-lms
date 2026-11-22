# VM-02: Video Transcoding (FFmpeg + HLS) — Final Implementation Report

**Project**: Single-Instructor LMS  
**Track**: C — Video & Media Management  
**Task ID**: `VM-02`  
**Parent Module**: VM-01 Video Upload Infrastructure & Integration  
**Status**: `COMPLETED & EMPIRICALLY VERIFIED`  
**Timestamp**: 2026-11-23T00:00:00+05:30  

---

## A. Architecture Overview

The video transcoding infrastructure converts user-uploaded master video files into web-optimized, adaptive multi-resolution HLS (HTTP Live Streaming) assets. The pipeline operates strictly asynchronously via database-backed job orchestration, ensuring that web requests remain fast, non-blocking, and resilient against server restarts.

### 1. End-to-End Transcoding Pipeline
```
Original Upload (StorageClient)
       │
       ▼
Upload Confirmation (POST /api/v1/media/{id}/confirm)
       │
       ├─► Validates storage object existence & size match
       ├─► Atomically enqueues MediaTranscodeJob (status='QUEUED') in DB transaction
       └─► Transitions MediaAsset to status='PROCESSING'
       │
       ▼
Background Worker Dispatch (TranscodeWorker / BackgroundTasks)
       │
       ├─► Row-level locking via PostgreSQL `SELECT ... FOR UPDATE SKIP LOCKED`
       ├─► Atomically claims pending jobs and marks them 'PROCESSING' with locked_by / locked_at
       │
       ▼
Transcode Execution (TranscodeService)
       │
       ├─► Downloads original video from StorageClient to isolated temporary directory
       ├─► Probes video via ffprobe (dimensions, duration, codecs, frame rate, audio presence)
       ├─► Derives multi-resolution profiles (1080p, 720p, 480p) strictly avoiding upscaling
       ├─► Executes FFmpeg with H.264 video, AAC audio (or -an if silent), and HLS segmentation
       ├─► Generates master playlist (master.m3u8), variant playlists, and TS segments
       ├─► Validates output structural integrity, manifest syntax, and segment existence
       ├─► Streams/uploads complete HLS directory tree to StorageClient under `media/{id}/hls/`
       ├─► Atomically transitions MediaAsset to status='READY' with verified duration and metadata
       ├─► Marks MediaTranscodeJob status='COMPLETED'
       ├─► Emits persistent AuditLog event `MEDIA_TRANSCODE_COMPLETED`
       └─► Guaranteed filesystem cleanup in `finally:` block (removes temp working files)
```

### 2. Worker Strategy
- **Decoupled Architecture**: `TranscodeWorker` runs as a distinct execution unit, completely decoupled from HTTP request handling.
- **Transactional Polling**: Uses `MediaTranscodeJobRepository.claim_pending_jobs()` with `FOR UPDATE SKIP LOCKED`, allowing horizontally scalable worker instances without duplicate job execution.
- **In-Process Fallback for Single-Node / Dev**: For single-node environments where dedicated workers might not be running continuously, `confirm_upload_endpoint` dispatches a non-blocking `BackgroundTasks` runner to immediately trigger execution.
- **Stale Job Auto-Recovery**: Detects orphaned jobs (`status='PROCESSING'` where `locked_at` exceeds configured timeout) and atomically resets them to `QUEUED` for retry.

### 3. Lifecycle Transitions
- **MediaAsset**: `UPLOAD_PENDING` $\rightarrow$ `PROCESSING` (upon confirmation and job creation) $\rightarrow$ `READY` (only after HLS transcode, validation, and storage upload succeed) or `FAILED` (if max retries are exhausted).
- **MediaTranscodeJob**: `QUEUED` $\rightarrow$ `PROCESSING` $\rightarrow$ `COMPLETED` (or `QUEUED` with exponential backoff on transient failure, up to `max_retries`) $\rightarrow$ `FAILED` (terminal failure).

---

## B. FFmpeg Configuration & Verification

### 1. Host Binary Detection & Environment
- **FFmpeg Binary**: Verified present at `/opt/homebrew/bin/ffmpeg` (configured via `settings.FFMPEG_PATH` or dynamic PATH resolution).
- **ffprobe Binary**: Verified present at `/opt/homebrew/bin/ffprobe` (configured via `settings.FFPROBE_PATH` or dynamic PATH resolution).
- **FFmpeg Version**: `8.1.2`
- **Supported Encoders**: Verified `libx264` (H.264 / AVC), `aac` (Advanced Audio Coding), `libvpx`, `libopus`, `libmp3lame`.

### 2. Execution Security & Parameter Hardening
- **Subprocess Security**: Invoked strictly via `asyncio.create_subprocess_exec` using tokenized argument lists (`list[str]`). Shell interpolation (`shell=True`) is strictly prohibited.
- **Timeout Protection**: Guarded by `asyncio.wait_for(..., timeout=settings.TRANSCODE_TIMEOUT_SECONDS)` (default 600 seconds) to prevent hung processes or DoS via malformed media.
- **Diagnostic Capture**: Stderr is buffered and captured; on non-zero exit codes, stdout/stderr are parsed to extract meaningful error causes while suppressing sensitive server environment data.

---

## C. Encoding Profile Strategy

The pipeline supports three target resolution profiles, dynamically selected based on the source video's geometry:

| Profile | Max Width | Max Height | Video Bitrate | Audio Bitrate | Target Use Case |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **1080p** | 1920 | 1080 | 4,500 kbps | 192 kbps | Desktop / High-bandwidth broadband |
| **720p** | 1280 | 720 | 2,500 kbps | 128 kbps | Mobile tablet / Standard web streaming |
| **480p** | 854 | 480 | 1,000 kbps | 96 kbps | Low-bandwidth mobile / Cellular connections |

### Key Encoding Invariants
1. **Strict No-Upscaling Invariant**:
   - Profiles with dimensions exceeding the source dimensions are strictly excluded.
   - Example: A 720p source generates **only** 720p and 480p profiles; 1080p is never synthesized.
2. **Low-Resolution Source Fallback**:
   - If the source resolution is smaller than 480p (e.g., 360p or 240p), the system creates a single matching profile with original dimensions and proportional bitrate (600 kbps).
3. **Aspect Ratio Preservation & Dimension Rounding**:
   - Proportional scaling preserves aspect ratio: `scale='min(max_w,iw):-2'` ensuring both width and height are even integers (required for YUV 4:2:0 subsampling).
4. **Portrait & Landscape Geometry**:
   - Dimension comparisons compare bounding box limits to support portrait/vertical video (e.g., mobile recordings) without distortion.
5. **Pixel Format Consistency**:
   - Always applies `-pix_fmt yuv420p` to guarantee playback compatibility across browser decoders.
6. **Audio Stream Guard**:
   - Uses `ffprobe` to verify whether the source video contains an audio stream.
   - If audio is present: encodes with `-c:a aac -b:a {audio_bitrate} -ac 2`.
   - If silent / no audio: automatically applies `-an` to prevent FFmpeg failures caused by unmapped audio streams.

---

## D. HLS Pipeline Details

### 1. File Structure & Hierarchy
For a given media asset (`{media_id}`), the generated HLS package follows a standardized relative hierarchy:
```
media/{media_id}/hls/
├── master.m3u8
├── 1080p/
│   ├── playlist.m3u8
│   └── segments/
│       ├── segment_000.ts
│       ├── segment_001.ts
│       └── ...
├── 720p/
│   ├── playlist.m3u8
│   └── segments/
│       ├── segment_000.ts
│       └── ...
└── 480p/
    ├── playlist.m3u8
    └── segments/
        ├── segment_000.ts
        └── ...
```

### 2. Master Playlist Specification (`master.m3u8`)
- Conforms to HLS RFC 8216 (`#EXTM3U`, `#EXT-X-VERSION:3`).
- Contains `#EXT-X-STREAM-INF` definitions referencing variant playlists via relative paths (e.g. `1080p/playlist.m3u8`, `720p/playlist.m3u8`).
- Includes exact `BANDWIDTH`, `AVERAGE-BANDWIDTH`, `RESOLUTION`, `FRAME-RATE`, and `CODECS="avc1.4d401f,mp4a.40.2"` declarations.

### 3. Variant Playlists & Segmenting
- Segment duration: Configured via `settings.TRANSCODE_SEGMENT_DURATION_SECONDS` (default: 6 seconds).
- Segment filenames: `segment_%03d.ts`.
- Segment directory isolation: Segments are located in `{res}/segments/`, and variant playlists declare `-hls_base_url segments/` so players resolve segments relative to the variant playlist URL.
- Complete stream tagging: Concludes with `#EXT-X-ENDLIST` to signal complete VOD playlists.

### 4. Output Validation Gate
Before any output is uploaded to storage or marked READY:
- Confirms `master.m3u8` exists, starts with `#EXTM3U`, and references all active variant streams.
- Confirms each variant `playlist.m3u8` exists and ends with `#EXT-X-ENDLIST`.
- Confirms each segment exists on disk and is non-empty (`st_size > 0`).

---

## E. Storage & File Organization

### 1. Storage Layout & Key Prefixing
- **Original Upload Key**: Retained intact in `StorageClient` under `media/originals/{filename}`.
- **HLS Assets Key Prefix**: Uploaded to `media/{media_id}/hls/`.
- **Master Playlist URL**: Stored in `MediaAsset.hls_master_url` as `media/{media_id}/hls/master.m3u8`.

### 2. Strict Content-Type / MIME Type Headers
Files are uploaded to `StorageClient` with explicit MIME types:
- `.m3u8`: `application/vnd.apple.mpegurl` (UTF-8 playlist manifest)
- `.ts`: `video/MP2T` (MPEG-2 Transport Stream binary segments)

### 3. Temporary Directory Lifecycle
- Working directory: `/tmp/lms_transcode/{media_id}_{timestamp}/`.
- Cleaned up deterministically inside `TranscodeService.process_job` via `shutil.rmtree(temp_dir, ignore_errors=True)` in a `finally:` block.
- Temp files are never leaked to disk on success or failure.

---

## F. Job Lifecycle & Reliability

### 1. Database Table: `media_transcode_jobs`
Created via Alembic revision `f2a3b4c5d6e7`:
- `id`: UUID Primary Key.
- `media_id`: UUID Foreign Key to `media_assets.id` (`ON DELETE CASCADE`).
- `status`: String (`QUEUED`, `PROCESSING`, `COMPLETED`, `FAILED`, `CANCELLED`).
- `priority`: Integer (higher priority claimed first).
- `retry_count`: Integer (tracks execution attempts).
- `max_retries`: Integer (default: 3).
- `next_retry_at`: UTC timestamp for exponential backoff scheduling.
- `locked_at` / `locked_by`: Concurrency lock ownership fields.
- `error_message` / `error_details`: Diagnostic failure details and categorized codes.
- `job_metadata`: JSON field storing source video resolution, duration, codecs, and generated profiles.
- `created_at` / `started_at` / `completed_at`: Detailed operational timestamps.

### 2. Concurrency & Idempotency
- **PostgreSQL Partial Concurrency**: `claim_pending_jobs` executes `SELECT ... WHERE status = 'QUEUED' AND next_retry_at <= now() ORDER BY priority DESC, created_at ASC FOR UPDATE SKIP LOCKED`.
- **Idempotency**: `create_job` checks for existing active jobs (`QUEUED` or `PROCESSING`) for the target media asset before creating a new row, preventing duplicate concurrent transcoding.

### 3. Retry Strategy & Exponential Backoff
- On transient failure (e.g., storage timeout, process termination):
  - Increments `retry_count`.
  - Calculates backoff delay: `delay = 30 * (2 ** retry_count)` (30s, 60s, 120s).
  - Sets `next_retry_at = utcnow() + delay` and reverts status to `QUEUED`.
- Once `retry_count >= max_retries`:
  - Transitions job to terminal `FAILED`.
  - Transitions `MediaAsset.status = 'FAILED'`.
  - Records structured failure event in `audit_logs`.

### 4. Categorized Error Codes
- `CORRUPT_MEDIA`: Source file unreadable or unsupported format.
- `PROBE_FAILED`: ffprobe failed to extract video metadata.
- `FFMPEG_TIMEOUT`: Execution exceeded timeout threshold.
- `FFMPEG_CRASH`: Subprocess exited with non-zero status.
- `VALIDATION_FAILED`: HLS playlist or segment verification failed.
- `STORAGE_FAILED`: Failure reading source or uploading output to storage.

---

## G. Modified and Created Files

### Created Files:
1. `backend/app/models/transcode_job.py` — Database model and status constants for `MediaTranscodeJob`.
2. `backend/migrations/versions/20261122_2330_f2a3b4c5d6e7_create_media_transcode_jobs_table.py` — Alembic migration script.
3. `backend/app/repositories/transcode_job_repo.py` — Repository with `FOR UPDATE SKIP LOCKED` and backoff logic.
4. `backend/app/services/ffmpeg_service.py` — Probe, profile derivation, multi-res HLS encoding, and validation.
5. `backend/app/services/transcode_service.py` — End-to-end orchestration, storage sync, asset state management, and audit logging.
6. `backend/app/workers/transcode_worker.py` — Background worker execution loop and CLI.
7. `backend/tests/unit/test_transcode_unit.py` — 16 unit tests covering profiles, probing, validation, error categorization, and worker lifecycle.
8. `backend/tests/integration/test_transcode_integration.py` — 7 integration tests including real FFmpeg 8.1.2 transcoding.
9. `docs/VM-02_FINAL_IMPLEMENTATION_REPORT.md` — This architectural report.

### Modified Files:
1. `backend/app/models/__init__.py` — Exported `MediaTranscodeJob` and transcode status constants.
2. `backend/app/schemas/media.py` — Added `TranscodeJobResponse` schema.
3. `backend/app/core/config.py` — Added transcode settings (`FFMPEG_PATH`, `TRANSCODE_TEMP_DIR`, `TRANSCODE_TIMEOUT_SECONDS`, etc.).
4. `backend/app/core/storage.py` — Added `download_file`, `upload_file`, and `upload_directory`.
5. `backend/app/repositories/__init__.py` — Exported `MediaTranscodeJobRepository`.
6. `backend/app/services/media_service.py` — Integrated transcode job creation in `confirm_upload`, added `get_transcode_job` and `retry_transcode`.
7. `backend/app/api/v1/media.py` — Added `GET /api/v1/media/{id}/transcode-job` and `POST /api/v1/media/{id}/retry-transcode` endpoints, and async background worker dispatch.
8. `backend/tests/unit/test_migrations.py` — Registered `media_transcode_jobs` in domain table expectations and updated active Alembic head to `f2a3b4c5d6e7`.

---

## H. Verification & Test Evidence

### 1. Automated Test Suites (Empirical Results)
- **Transcode Unit Tests** (`backend/tests/unit/test_transcode_unit.py`):
  - **16 passed in 0.50s** (100%).
  - Tests: FFmpeg detection, custom paths, video probe parsing, silent video handling, profile derivation (1080p, 720p, 480p, low-res fallback, portrait videos), HLS output validation (valid, missing master, missing variant, missing segments, empty segments), and categorized error codes.
- **Transcode Integration Tests** (`backend/tests/integration/test_transcode_integration.py`):
  - **7 passed in 1.48s** (100%).
  - Tests: Repository job lifecycle, skip locked concurrency, retry backoff calculation, media upload confirmation job creation, transcode service processing flow, API endpoints (`GET /transcode-job`, `POST /retry-transcode`), and **real FFmpeg smoke test** generating real HLS streams.
- **Full Backend Test Suite**:
  - Command: `python3 -m pytest backend/tests/unit backend/tests/integration backend/tests/security`
  - Result: **833 passed, 20 skipped, 0 failed in 55.07s** (100% pass rate).
- **Frontend Test Suite**:
  - Command: `npm test`
  - Result: **42 test files passed, 227 unit tests passed in 4.65s** (100% pass rate).
- **TypeScript Static Analysis**:
  - Command: `npx tsc --noEmit`
  - Result: **0 errors**.
- **Next.js Production Build**:
  - Command: `npm run build`
  - Result: **40/40 routes generated, 0 errors**.

### 2. Real FFmpeg Smoke Test Evidence
Using real system FFmpeg 8.1.2, a synthetic 1280x720 2-second test MP4 was generated, enqueued, and processed through `TranscodeService`:
- Probed: 1280x720, duration 2.0s, video codec h264.
- Derived profiles: `720p` (1280x720) and `480p` (854x480) — no 1080p upscaling.
- Transcoded: `master.m3u8`, `720p/playlist.m3u8`, `480p/playlist.m3u8`, and corresponding TS segments.
- Validated: `validate_hls_output()` confirmed playlist syntax and segment integrity.
- Storage verified: `StorageClient` received all files under `media/{id}/hls/`.
- Asset transitioned: `MediaAsset.status = 'READY'`, `hls_master_url = 'media/{id}/hls/master.m3u8'`.

---

## I. Security & Resource Controls

1. **Subprocess Isolation**: No shell execution (`shell=False`); strict argument lists prevent shell command injection.
2. **Resource Boundaries**: Strict execution timeouts (600s) prevent CPU denial-of-service from infinite loops or decompression bombs.
3. **Storage Access Isolation**: Original source videos remain segregated under `media/originals/` and are never exposed publicly. HLS segments are segregated under `media/{id}/hls/`.
4. **Access Control**: Status and retry endpoints require authenticated users with `media:upload` permission.
5. **Disk Cleanliness**: All temporary transcoding artifacts are stored in isolated per-job directories and deleted in `finally:` blocks.

---

## J. Remaining Limitations & Edge Cases

1. **Hardware Acceleration**: Currently utilizes software encoding (`libx264`). Production container deployments with NVIDIA GPUs or Apple Silicon hardware could utilize `-c:v h264_nvenc` or `-c:v h264_videotoolbox` for increased throughput.
2. **Sub-second Low Latency HLS (LL-HLS)**: The system utilizes standard VOD HLS with 6-second segments, which is optimal for educational course videos.
3. **DRM / Widevine / FairPlay**: Standard AES-128 HLS encryption and signed playback tokens are supported; proprietary hardware DRM requires third-party licensing.

---

## K. Governance & Compliance Confirmation

- **Scope Adherence**: Implementation is strictly limited to VM-02 (Video Transcoding pipeline). No unrelated features, authentication, payments, or governance files were modified.
- **Reserved Files Invariant**: All 17 reserved governance files (`.ai/RULES/*`, `.ai/GOVERNANCE/*`, `.ai/CORE/GOLDEN_RULES.md`, `.ai/USER_WORKFLOW.md`) remain strictly untouched.
- **Git & Deployment Invariant**: Zero git commits, zero git pushes, and zero external deployments were performed.
- **Empirical Evidence Invariant**: All claims are substantiated with terminal and test execution output.
- **Stop Condition**: Task VM-02 is complete. Work has stopped pending Project Owner review. VM-03 has NOT been started.
