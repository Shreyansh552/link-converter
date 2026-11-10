# Universal Media Link Converter (`linkconv`) — E2E Test Infrastructure Specification

**Document Version**: 1.0.0  
**Author**: Lead E2E Test Writer & Test Architect  
**Track**: E2E Testing Track (Tiers 1–4)  
**Target Milestone**: All Milestones (M1, M2, M3, M4)  

---

## 1. Architectural Philosophy & Principles

The `linkconv` project employs an **Opaque-Box Verification Track** running in parallel with feature implementation milestones. The testing framework is designed around four non-negotiable architectural tenets:

1. **100% Offline Determinism**:
   - Live media platforms (YouTube, Instagram, TikTok, Reddit) enforce aggressive anti-bot protections, Cloudflare challenges, ISP geoblocking, and rate limits.
   - All E2E test suites run completely decoupled from external network access by leveraging the embedded `MockMediaServer` (`tests/fixtures/mock_server.py`) and synthetic container generators (`tests/fixtures/sample_media.py`).
   - Zero test flakiness; tests pass identically in isolated CI runners, air-gapped environments, and developer machines.

2. **Sub-15-Second Execution Speed**:
   - The entire 4-tier E2E test suite executes from start to finish in less than 15 seconds.
   - Binary media payloads are synthetic 1-second streams (valid MP4 ISO base media format, valid MP3 sync frames, valid JFIF JPEGs), minimizing I/O overhead.

3. **Progressive Milestone Testability**:
   - Tests support progressive execution across development milestones (M1 Core Router/Extractors -> M2 Media Transcoding -> M3 Presentation -> M4 Hardening).
   - Test suites gracefully detect available module implementations in `src/linkconv/` and execute active assertions against implemented contracts while skipping pending milestone dependencies without breaking test suite discovery.

4. **Rigorous Test Integrity**:
   - No facade tests. Every test asserts genuine invariants, boundary conditions, or interface contracts defined in `PROJECT.md`.
   - Expected outputs are derived directly from authoritative specifications, mathematical/RFC invariants, and container standards.

---

## 2. Test Design Methodologies

The test architecture maps formal software testing theory into four distinct tiers:

```
┌────────────────────────────────────────────────────────────────────────┐
│                      TIER 4: REAL-WORLD WORKLOADS                      │
│   Persona-driven workflows: Playlist Archiver, Social Media Manager,   │
│   High-concurrency queue limits, Temp directory garbage collection     │
├────────────────────────────────────────────────────────────────────────┤
│                  TIER 3: CROSS-FEATURE COMBINATIONS                    │
│   Pairwise combinations: Unshorten + Transcode + Embed ID3 tags;       │
│   Shorts + 1080p Mux + Markdown; Carousel + Multi-Slide ZIP + Batch    │
├────────────────────────────────────────────────────────────────────────┤
│                   TIER 2: BOUNDARY & CORNER CASES                      │
│   Boundary Value Analysis: Zero-length, >4096 char URLs, Windows       │
│   MAX_PATH & illegal characters, Corrupt JSON, HTTP 403/404/429/500    │
├────────────────────────────────────────────────────────────────────────┤
│                      TIER 1: FEATURE COVERAGE                          │
│   Category-Partition Method: >=5 test cases per feature across all     │
│   17 features in PROJECT.md (Router, Extractors, FFmpeg, CLI, API)     │
└────────────────────────────────────────────────────────────────────────┘
```

### 2.1 Tier 1: Category-Partition Method (Feature Coverage)
- **Methodology**: Systematic decomposition of each feature's input domain into equivalence partitions (Valid/Invalid, Protocols, Platforms, Formats, Containers, Subcommands).
- **Coverage Requirement**: At least 5 distinct test cases per feature covering all 17 features defined in `PROJECT.md`:
  - `ROUTE-01`: Tracking parameter sanitization (`si`, `igsh`, `utm_*`, `fbclid`).
  - `ROUTE-02`: Shortlink expansion (`youtu.be`, `vm.tiktok.com`, `pin.it`, `t.co`, `bit.ly`).
  - `ROUTE-03`: Platform regex router & canonical ID extractor.
  - `EXT-YT`: YouTube standard video, Shorts, Music, Playlists, and embed metadata.
  - `EXT-IG`: Instagram Reels, Posts, Carousels, Stories, and session auth handling.
  - `EXT-MULTI`: Multi-platform extractors (TikTok, Twitter/X, Facebook, Reddit, Pinterest, Vimeo, SoundCloud, Generic).
  - `EXT-NET`: User-Agent rotation, proxy parsing, Netscape cookies, TLS impersonation options.
  - `PROC-FFMPEG`: FFmpeg 4-tier discovery (PATH -> Local AppData -> imageio -> Static installer).
  - `PROC-VIDEO`: Video muxing options, direct copy detection, container selection (MP4, WEBM, MKV).
  - `PROC-AUDIO`: Audio extraction pipeline (MP3 bitrates, M4A, WAV, FLAC, OPUS, ID3 tags).
  - `PROC-ASSET`: YouTube thumbnail cascade (placeholder detection) & Instagram carousel ZIP bundler.
  - `PROC-EMBED`: Markdown preview, HTML responsive iframe, oEmbed JSON/XML, and BBCode synthesizers.
  - `PROC-JOBS`: Asynchronous job engine lifecycle (Pending, Processing, Completed, Cancelled).
  - `UI-CLI`: Command line interface grammar, options, and JSON/human-readable outputs.
  - `UI-API`: FastAPI REST backend endpoints (`/health`, `/api/platforms`, `/api/expand`, `/api/info`, `/api/convert`, `/api/jobs/*`, `/api/embed`).
  - `UI-WEB`: Embedded zero-build Web dashboard assets (`index.html`, `app.js`, `style.css`).
  - `PKG-DEPLOY`: Windows filename sanitization, extended path prefixing, and packaging metadata.

### 2.2 Tier 2: Boundary Value Analysis & Negative Testing
- **Methodology**: Testing extreme edge conditions, malformed data, and fault injection.
- **Test Scenarios**:
  - Null, empty string `""`, whitespace-only strings `"   \t\n  "`.
  - Malformed URL schemes (`htp://`, `file:///`, `ftp://`, `javascript:`).
  - Extremely long query strings (>4096 characters with 500+ duplicate tracking tokens).
  - Unencoded Unicode URLs and emoji in media titles (`🎵🎥`).
  - Missing mandatory query parameters (YouTube URL without `v=`).
  - Missing shortcode path (Instagram `/reel//`).
  - Truncated streams and zero-byte file responses.
  - Upstream platform error responses (HTTP 403 Forbidden, 404 Not Found, 429 Rate Limited, 500 Internal Error).
  - Windows illegal filename characters (`\ / : * ? " < > |`) and reserved device names (`CON`, `PRN`, `AUX`, `NUL`).
  - Paths exceeding Windows `MAX_PATH` (260 characters).
  - Unsupported conversion formats (`--format xyz_nonexistent`).

### 2.3 Tier 3: Pairwise & Cross-Feature Combinations
- **Methodology**: Verifying that independent subsystems cooperate seamlessly when combined into end-to-end processing pipelines.
- **Key Combinations**:
  1. *Shortlink Expansion + Audio Extraction + ID3 Tagging*: `youtu.be` tracking link unshortened, extracted, transcoded to MP3 320k, tagged with artist/title/cover.
  2. *YouTube Shorts + 1080p Muxing + Responsive Embed*: Vertical format detection (1080x1920), remuxing separate DASH video and audio, and generating responsive HTML iframes.
  3. *Instagram Carousel + Asset Indexer + Bulk ZIP + Batch CLI*: Multi-slide post indexing, downloading all slides, packaging into an in-memory ZIP archive with manifest.
  4. *Reddit Post (Decoupled Streams) + Video Remuxing + Cover Thumbnail*: Remuxing separate Reddit video (`DASH_720.mp4`) and audio (`DASH_audio.mp4`) into MP4 while extracting post thumbnail.
  5. *Multi-Platform Batch Conversion*: Mixed playlist file containing YouTube, Instagram, TikTok, and direct MP4 URLs converted concurrently.
  6. *REST API Job Lifecycle + SSE Progress Streaming + Download*: Creating job via `POST /api/convert`, streaming live events via SSE, downloading converted artifact.
  7. *Format Ladder Filtering + Dual oEmbed Generation*: Filtering formats by resolution threshold (`<= 720p`) and generating synchronized oEmbed JSON and XML outputs.
  8. *Lossless Audio Transcode + Windows Filename Templating*: Transcoding to FLAC with dynamic template `{uploader} - {title} [{id}].flac`.

### 2.4 Tier 4: Real-World Workloads & Stress Scenarios
- **Methodology**: Emulating complete user personas, system resource constraints, and operational stress.
- **Scenarios**:
  1. *Content Creator Playlist Archiving*: Archiving an album/playlist into individual tagged MP3 tracks with embedded artwork.
  2. *Social Media Manager Campaign Embed Cards*: Bulk-generating embed snippets and responsive cards for cross-platform marketing campaigns.
  3. *Mobile User High-Res Asset Extractor*: Thumbnail cascade fallback when `maxresdefault.jpg` is a 120x90 placeholder.
  4. *CLI Batch Processing from Dirty File*: Parsing text files containing comments (`# comment`), blank lines, and irregular whitespace.
  5. *High-Concurrency Job Queue Limiting*: Enqueuing 10 jobs with concurrency limit 3, verifying queue progression and semaphore management.
  6. *Temporary File Garbage Collection*: Validating that intermediate transcode artifacts (`.part`, temp audio/video) are purged upon completion or failure.
  7. *Job Cancellation & Cleanup*: Cancelling an active conversion mid-execution, verifying process termination and temporary file cleanup.

---

## 3. Test Infrastructure Components

### 3.1 Mock HTTP Server (`tests/fixtures/mock_server.py`)
- Built on Python standard library `socketserver.TCPServer` and `http.server.BaseHTTPRequestHandler`.
- Starts automatically on an ephemeral OS-assigned port (`127.0.0.1:0`), guaranteeing no port collisions.
- Provides context manager support:
  ```python
  with MockMediaServer() as server:
      url = server.get_url("/media/sample.mp4")
      ...
  ```
- **Endpoints Provided**:
  | Route | Method | Description |
  | :--- | :--- | :--- |
  | `/health` | GET | Health and readiness check |
  | `/redirect?target=...` | GET/HEAD | Emulates 302 redirect for shortlink testing |
  | `/short/<slug>` | GET/HEAD | Emulates 301 redirect for shortlink testing |
  | `/media/sample.mp4` | GET/HEAD | Serves valid 1-second synthetic MP4 bytes |
  | `/media/sample.mp3` | GET/HEAD | Serves valid 1-second synthetic MP3 bytes with ID3 tag |
  | `/media/thumb.jpg` | GET/HEAD | Serves valid 1080p synthetic JPEG thumbnail |
  | `/media/thumb_small.jpg` | GET/HEAD | Serves 120x90 synthetic placeholder thumbnail (<2000 bytes) |
  | `/media/carousel.zip` | GET/HEAD | Serves valid multi-slide ZIP archive |
  | `/oembed?url=...&format=...` | GET | Serves oEmbed JSON and XML formats |
  | `/error/<code>` | GET | Injects simulated HTTP errors (403, 404, 429, 500) |
  | `/timeout?seconds=X` | GET | Simulates network latency/timeout |
  | `/metadata/<platform_key>` | GET | Returns standardized platform metadata payload |

### 3.2 Synthetic Media Generators (`tests/fixtures/sample_media.py`)
- Generates valid binary file headers and atom trees without requiring external binaries (`ffmpeg`, `imagemagick`, etc.):
  - `create_minimal_mp4_bytes()`: Generates `ftyp` (isom/mp42), `moov` (mvhd, trak), and `mdat` atoms.
  - `create_minimal_mp3_bytes(title, artist)`: Generates valid ID3v2.3 tags (`TIT2`, `TPE1`) followed by MPEG-1 Layer 3 audio frames (128kbps, 44.1kHz).
  - `create_minimal_jpeg_bytes()`: Generates valid JFIF JPEG with SOI, DQT, SOF0, DHT, SOS, and EOI markers.
  - `create_placeholder_jpeg_bytes()`: Generates a small (<1000 bytes) JPEG simulating YouTube's unavailable placeholder.
  - `create_mock_carousel_zip_bytes(slide_count)`: Generates an in-memory ZIP archive containing slide images and a `manifest.json`.

---

## 4. Test Runner Commands & Invocations

### 4.1 Running All E2E Tests (Standard Test Suite)
```powershell
python -m unittest discover -s tests/e2e -p "test_*.py" -v
```

### 4.2 Running Specific Test Tiers
```powershell
# Tier 1: Feature Coverage
python -m unittest tests.e2e.test_tier1_feature -v

# Tier 2: Boundary & Corner Cases
python -m unittest tests.e2e.test_tier2_boundary -v

# Tier 3: Cross-Feature Combinations
python -m unittest tests.e2e.test_tier3_combinations -v

# Tier 4: Real-World Workloads
python -m unittest tests.e2e.test_tier4_workloads -v
```

### 4.3 Running via Pytest (When Pytest is Installed)
```powershell
python -m pytest tests/e2e/ -v
```

---

## 5. Defect Escalation Protocol

When executing the test suite during verification:

1. **Test Defects (Test Suite Code Issues)**:
   - Handled directly by the Test Writer / QA Specialist.
   - Examples: Syntactic errors in test methods, broken mock server fixtures, incorrect assertion assumptions that do not match `PROJECT.md`.
2. **Implementation Defects (Bugs in `src/linkconv/`)**:
   - The Test Writer **MUST NOT** modify code in `src/linkconv/`.
   - Log the defect with:
     - Exact failing test case and command.
     - Expected output vs. actual output.
     - Relevant stack trace and file path in `src/`.
   - Escalate to the implementing agent (or Orchestrator) via `send_message` and record in the test handoff report.
