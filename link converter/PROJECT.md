# Project: Universal Media Link Converter (`linkconv`)

## Architecture
Decoupled Layered Architecture separating core domain logic, backend application services, and presentation controller adapters (CLI, REST API, Web UI):

```
                     ┌─────────────────────────────────────────────────────────┐
                     │                       User Clients                      │
                     │  CLI (`linkconv`)   │   REST API (/api)   │   Web UI    │
                     └─────────┬──────────────────────┬───────────────┬────────┘
                               │                      │               │
                               ▼                      ▼               ▼
                     ┌─────────────────────────────────────────────────────────┐
                     │                 Presentation Adapters                   │
                     │  linkconv.cli       │   linkconv.api      │ linkconv.web│
                     └─────────┬──────────────────────┬───────────────┬────────┘
                               │                      │               │
                               ▼                      ▼               ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                Application Services                                    │
│  - UrlRouterService (sanitization, shortlink unshortening, regex platform routing)      │
│  - MediaExtractionService (yt-dlp orchestrator, Node.js n-sig, cookie/proxy manager)    │
│  - TranscodingService (FFmpeg muxing, format conversion, audio extraction, progress)   │
│  - MediaAssetService (Thumbnail resolver, carousel ZIP bundler, avatar downloader)     │
│  - EmbedFormatterService (oEmbed JSON/XML, Markdown preview, HTML iframe, BBCode)      │
│  - FFmpegResolverService (Windows discovery, local cache, static binary provisioner)   │
│  - JobQueueService (In-memory asynchronous job runner with SSE event streaming)        │
└──────────────────────────────────────────┬─────────────────────────────────────────────┘
                                           │
                                           ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                     Core Domain                                        │
│  - Domain Models: MediaMetadata, MediaFormat, MediaAsset, ConversionRequest, JobStatus │
│  - Platform Extractors: YouTube, Instagram, TikTok, Twitter/X, Facebook, Reddit,       │
│                         Pinterest, Vimeo, SoundCloud, Generic HTML5                    │
│  - Anti-bot / Network: Node.js runtime hook, curl_cffi JA3 impersonation, headers      │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

## Feature Inventory
Every feature identified during the Survey phase is mapped below to an implementation milestone. No feature is left unassigned.

| # | Feature ID | Feature Name | Description | Milestone | Source |
|---|------------|--------------|-------------|-----------|--------|
| 1 | ROUTE-01 | URL Sanitization | Strip tracking parameters (`si`, `igsh`, `utm_*`, `fbclid`) while preserving functional query params | M1 | Survey |
| 2 | ROUTE-02 | Shortlink Expansion | Follow HTTP redirects for shortlinks (`youtu.be`, `vm.tiktok.com`, `pin.it`, `t.co`, `bit.ly`) to canonical URLs | M1 | Survey |
| 3 | ROUTE-03 | Platform Regex Router | Pattern matching engine resolving URLs to platform handlers with canonical ID extraction | M1 | Survey |
| 4 | EXT-YT | YouTube Extractor | Extract videos, Shorts, YouTube Music, playlists, channels, and embeds; pass `--js-runtimes node` for n-sig solver | M1 | Survey |
| 5 | EXT-IG | Instagram Extractor | Extract Reels, Posts, multi-slide Carousels, and Stories; support session cookies and graceful auth-error reporting | M1 | Survey |
| 6 | EXT-MULTI | Multi-Platform Extractors | Extract media from TikTok, Twitter/X, Facebook, Reddit (muxed audio+video), Pinterest, Vimeo, SoundCloud, and Generic HTML5 | M1 | Survey |
| 7 | EXT-NET | Network & Anti-Bot Hardening | Custom user-agent rotation, proxy routing (HTTP/SOCKS5), cookie loading (file/browser), and TLS impersonation fallback | M1 | Survey |
| 8 | PROC-FFMPEG | FFmpeg Windows Resolver | 4-tier discovery: PATH -> `%LOCALAPPDATA%\linkconv\bin` -> imageio-ffmpeg -> static binary auto-installer | M2 | Survey |
| 9 | PROC-VIDEO | Video Muxing Pipeline | Remux separate DASH video/audio streams into MP4, WEBM, MKV (4K to 360p); direct copy optimization for matching codecs | M2 | Survey |
| 10 | PROC-AUDIO | Audio Extraction Pipeline | Transcode to MP3 (128k-320k), M4A, WAV, FLAC, OPUS; zero-loss direct copy for Opus/M4A; embed cover art & ID3 tags | M2 | Survey |
| 11 | PROC-ASSET | Image & Asset Extraction | High-res YouTube thumbnail cascade with placeholder detection; Instagram carousel multi-slide indexer & ZIP bundler | M2 | Survey |
| 12 | PROC-EMBED | Embed & Share Synthesizer | Generate oEmbed JSON/XML, Markdown previews, responsive privacy-friendly HTML iframes, BBCode, and direct CDN links | M2 | Survey |
| 13 | PROC-JOBS | Asynchronous Job Engine | In-memory job queue with real-time FFmpeg/yt-dlp progress monitoring (`-progress pipe:1`) and state management | M2 | Survey |
| 14 | UI-CLI | Rich Command-Line Interface | `linkconv` CLI with subcommands `info`, `convert`, `download`, `embed`, `expand`, `batch`, `serve`, `interactive`, `setup-ffmpeg` | M3 | Survey |
| 15 | UI-API | FastAPI REST Backend | Endpoints `/health`, `/api/platforms`, `/api/expand`, `/api/info`, `/api/convert`, `/api/jobs/{id}`, `/api/jobs/{id}/stream` (SSE), `/api/jobs/{id}/download`, `/api/embed`, OpenAPI `/docs` | M3 | Survey |
| 16 | UI-WEB | Embedded Modern Web UI | Zero-build single-page responsive dashboard (HTML5 + Tailwind CDN + Vanilla ES6 JS) with live platform badge, preview card, 1-click format conversion | M3 | Survey |
| 17 | PKG-DEPLOY | Packaging & Windows Support | `pyproject.toml`, pure-Python dependency setup, console script entrypoint, and Windows path/filename sanitization | M3 | Survey |
| 18 | VERIF-E2E | 100% E2E Test Suite Pass | Pass all E2E test cases across Tiers 1-4 (Feature, Boundary, Combinatorial, Real-World) generated by E2E Testing Track | M4 | Survey |
| 19 | VERIF-HARDEN | Adversarial Coverage Hardening | White-box stress-testing and boundary verification (Tier 5) with zero gaps | M4 | Survey |

## Milestones

| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Core URL Router, Extractors & Metadata Models | `src/linkconv/core/`, `src/linkconv/extractors/`, domain models, URL sanitization/unshortening, YouTube/Instagram/Multi-platform extractors, network & anti-bot hardening | none | DONE |
| M2 | Media Transcoding, FFmpeg Integration & Conversion Services | `src/linkconv/services/`: FFmpeg discovery/provisioning, video muxing, audio extraction, image/carousel ZIP extraction, embed generation, async job queue | M1 | IN_PROGRESS |
| M3 | Presentation Layer: CLI, REST API & Web Dashboard | `src/linkconv/cli/`, `src/linkconv/api/`, `src/linkconv/web/`, `pyproject.toml`, entrypoint `linkconv`, interactive terminal, FastAPI endpoints with SSE, responsive web dashboard | M2 | PLANNED |
| M4 | Final Milestone: E2E Verification & Adversarial Hardening | Phase 1: 100% pass of E2E test suite (Tiers 1-4 from `TEST_READY.md`); Phase 2: Adversarial coverage hardening (Tier 5) | M3, E2E Testing Track | PLANNED |

## Interface Contracts

### 1. `linkconv.core.models` ↔ All Components
```python
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from enum import Enum

class Platform(str, Enum):
    YOUTUBE = "youtube"
    INSTAGRAM = "instagram"
    TIKTOK = "tiktok"
    TWITTER = "twitter"
    FACEBOOK = "facebook"
    REDDIT = "reddit"
    PINTEREST = "pinterest"
    VIMEO = "vimeo"
    SOUNDCLOUD = "soundcloud"
    GENERIC = "generic"

class MediaFormat(BaseModel):
    format_id: str
    ext: str
    resolution: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    fps: Optional[float] = None
    vcodec: Optional[str] = None
    acodec: Optional[str] = None
    abr: Optional[float] = None  # kbps
    vbr: Optional[float] = None
    filesize_approx: Optional[int] = None
    url: Optional[str] = None
    is_dash: bool = False
    needs_muxing: bool = False

class MediaAsset(BaseModel):
    asset_type: str  # "thumbnail", "image", "audio", "video", "subtitle"
    url: str
    label: Optional[str] = None
    dimensions: Optional[str] = None

class MediaMetadata(BaseModel):
    id: str
    platform: Platform
    original_url: str
    canonical_url: str
    title: str
    description: Optional[str] = None
    uploader: Optional[str] = None
    uploader_url: Optional[str] = None
    duration: Optional[float] = None  # seconds
    thumbnail_url: Optional[str] = None
    formats: List[MediaFormat] = Field(default_factory=list)
    assets: List[MediaAsset] = Field(default_factory=list)
    view_count: Optional[int] = None
    like_count: Optional[int] = None
    tags: List[str] = Field(default_factory=list)
    is_live: bool = False
    is_playlist: bool = False
    playlist_count: Optional[int] = None
    playlist_items: Optional[List[Dict[str, Any]]] = None
```

### 2. `UrlRouterService` ↔ Presentation & Extractors
```python
class UrlRouterService:
    def sanitize(self, url: str) -> str:
        """Strips tracking params (si, igsh, utm_*, fbclid) while preserving functional params."""
        ...
        
    async def expand(self, url: str) -> str:
        """Unshortens short URLs (youtu.be, vm.tiktok.com, pin.it, etc.) via HTTP HEAD/GET redirect resolution."""
        ...
        
    def resolve_platform(self, url: str) -> Tuple[Platform, str]:
        """Returns (Platform, extracted_media_id)."""
        ...
```

### 3. `MediaExtractionService` ↔ Presentation & Conversion
```python
class MediaExtractionService:
    async def extract_info(self, url: str, cookies: Optional[str] = None, proxy: Optional[str] = None) -> MediaMetadata:
        """Extracts complete metadata and format ladder using yt-dlp + Node.js n-sig solver."""
        ...
```

### 4. `TranscodingService` ↔ Conversion & Storage
```python
class ConversionOptions(BaseModel):
    target_format: str  # "mp4", "webm", "mkv", "mp3", "m4a", "wav", "flac", "opus"
    target_quality: Optional[str] = "best"  # "best", "1080p", "720p", "480p", "320k", "192k"
    extract_audio_only: bool = False
    embed_thumbnail: bool = True
    output_dir: Optional[str] = None
    filename_template: Optional[str] = None

class TranscodingService:
    async def convert(self, metadata: MediaMetadata, options: ConversionOptions, progress_callback = None) -> str:
        """Executes download and FFmpeg muxing/transcoding; returns output file path."""
        ...
```

### 5. `EmbedFormatterService` ↔ Presentation
```python
class EmbedFormatterService:
    def to_markdown(self, metadata: MediaMetadata) -> str: ...
    def to_html_iframe(self, metadata: MediaMetadata, responsive: bool = True) -> str: ...
    def to_oembed_json(self, metadata: MediaMetadata) -> Dict[str, Any]: ...
    def to_bbcode(self, metadata: MediaMetadata) -> str: ...
```

## Code Layout
```
c:\Users\Ditya Dubey\Desktop\link converter\
├── pyproject.toml
├── README.md
├── src\
│   └── linkconv\
│       ├── __init__.py
│       ├── __main__.py
│       ├── core\
│       │   ├── __init__.py
│       │   ├── models.py
│       │   ├── exceptions.py
│       │   └── router.py
│       ├── extractors\
│       │   ├── __init__.py
│       │   ├── base.py
│       │   ├── youtube.py
│       │   ├── instagram.py
│       │   ├── multi.py
│       │   └── engine.py
│       ├── services\
│       │   ├── __init__.py
│       │   ├── ffmpeg_resolver.py
│       │   ├── transcoding.py
│       │   ├── assets.py
│       │   ├── embeds.py
│       │   └── job_queue.py
│       ├── cli\
│       │   ├── __init__.py
│       │   ├── main.py
│       │   └── formatting.py
│       ├── api\
│       │   ├── __init__.py
│       │   ├── app.py
│       │   ├── routes.py
│       │   └── schemas.py
│       └── web\
│           ├── __init__.py
│           └── static\
│               ├── index.html
│               ├── app.js
│               └── style.css
└── tests\
    ├── fixtures\
    │   ├── mock_server.py
    │   └── sample_media.py
    ├── unit\
    │   ├── test_router.py
    │   ├── test_models.py
    │   ├── test_embeds.py
    │   └── test_ffmpeg_resolver.py
    └── e2e\
        ├── test_tier1_feature.py
        ├── test_tier2_boundary.py
        ├── test_tier3_combinations.py
        └── test_tier4_workloads.py
```
