"""Domain models for linkconv media converter.

Defines core models: Platform, MediaFormat, MediaAsset, MediaMetadata,
ConversionOptions, ConversionRequest, and JobStatus.
"""
from __future__ import annotations

from enum import Enum
import json
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Set, Tuple, Union
import uuid

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


class LinkConvBaseModel(BaseModel):
    """Base class for all linkconv domain models providing serialization helpers."""
    model_config = ConfigDict(
        populate_by_name=True,
        validate_assignment=True,
        extra="ignore",
        str_strip_whitespace=True,
    )

    def to_dict(self, exclude_none: bool = False) -> Dict[str, Any]:
        """Serialize model to a standard Python dictionary."""
        return self.model_dump(mode="json", exclude_none=exclude_none)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Any:
        """Instantiate model from a Python dictionary."""
        return cls.model_validate(data)

    def to_json(self, indent: Optional[int] = None) -> str:
        """Serialize model to JSON string."""
        return self.model_dump_json(indent=indent)

    @classmethod
    def from_json(cls, json_str: str) -> Any:
        """Instantiate model from a JSON string."""
        return cls.model_validate_json(json_str)

    def save_to_file(self, file_path: Union[str, Path], indent: int = 2) -> None:
        """Write model JSON to a local file with UTF-8 encoding."""
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(indent=indent), encoding="utf-8")

    @classmethod
    def load_from_file(cls, file_path: Union[str, Path]) -> Any:
        """Load model from a local JSON file."""
        content = Path(file_path).read_text(encoding="utf-8")
        return cls.from_json(content)


class Platform(str, Enum):
    """Supported media platforms."""
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

    @classmethod
    def from_str(cls, val: str) -> Platform:
        """Resolve string or common alias to canonical Platform enum."""
        if not isinstance(val, str):
            raise ValueError(f"Platform value must be a string, got {type(val)}")
        cleaned = val.strip().lower()
        alias_map = {
            "youtube": cls.YOUTUBE,
            "yt": cls.YOUTUBE,
            "youtu.be": cls.YOUTUBE,
            "instagram": cls.INSTAGRAM,
            "ig": cls.INSTAGRAM,
            "insta": cls.INSTAGRAM,
            "tiktok": cls.TIKTOK,
            "tt": cls.TIKTOK,
            "twitter": cls.TWITTER,
            "x": cls.TWITTER,
            "tw": cls.TWITTER,
            "facebook": cls.FACEBOOK,
            "fb": cls.FACEBOOK,
            "reddit": cls.REDDIT,
            "pinterest": cls.PINTEREST,
            "pin": cls.PINTEREST,
            "vimeo": cls.VIMEO,
            "soundcloud": cls.SOUNDCLOUD,
            "sc": cls.SOUNDCLOUD,
            "generic": cls.GENERIC,
            "direct": cls.GENERIC,
            "html5": cls.GENERIC,
        }
        if cleaned in alias_map:
            return alias_map[cleaned]
        for item in cls:
            if item.value == cleaned:
                return item
        valid = ", ".join(sorted(set(alias_map.keys())))
        raise ValueError(f"Unknown platform '{val}'. Valid options/aliases: {valid}")

    @property
    def display_name(self) -> str:
        """Canonical formatted display name."""
        names = {
            self.YOUTUBE: "YouTube",
            self.INSTAGRAM: "Instagram",
            self.TIKTOK: "TikTok",
            self.TWITTER: "Twitter / X",
            self.FACEBOOK: "Facebook",
            self.REDDIT: "Reddit",
            self.PINTEREST: "Pinterest",
            self.VIMEO: "Vimeo",
            self.SOUNDCLOUD: "SoundCloud",
            self.GENERIC: "Generic / Direct",
        }
        return names.get(self, self.value.capitalize())

    @property
    def badge_color(self) -> str:
        """Brand hex color code for UI & terminal badges."""
        colors = {
            self.YOUTUBE: "#FF0000",
            self.INSTAGRAM: "#E1306C",
            self.TIKTOK: "#00F2FE",
            self.TWITTER: "#1DA1F2",
            self.FACEBOOK: "#1877F2",
            self.REDDIT: "#FF4500",
            self.PINTEREST: "#BD081C",
            self.VIMEO: "#1AB7EA",
            self.SOUNDCLOUD: "#FF5500",
            self.GENERIC: "#6C757D",
        }
        return colors.get(self, "#4B5563")


class MediaFormat(LinkConvBaseModel):
    """Specification of an available media stream/rendition."""
    format_id: str
    ext: str
    resolution: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    fps: Optional[float] = None
    vcodec: Optional[str] = None
    acodec: Optional[str] = None
    abr: Optional[float] = None
    vbr: Optional[float] = None
    filesize_approx: Optional[int] = None
    url: Optional[str] = None
    is_dash: bool = False
    needs_muxing: bool = False
    format_note: Optional[str] = None
    http_headers: Optional[Dict[str, str]] = None

    @property
    def is_video(self) -> bool:
        """True if format has a valid video stream."""
        return bool(self.vcodec and self.vcodec.lower() != "none")

    @property
    def is_audio_only(self) -> bool:
        """True if format contains audio and no video."""
        has_no_video = not self.vcodec or self.vcodec.lower() == "none"
        has_audio = bool(self.acodec and self.acodec.lower() != "none")
        return has_no_video and has_audio

    @property
    def filesize_mb(self) -> Optional[float]:
        """Estimated filesize in megabytes."""
        if self.filesize_approx is not None and self.filesize_approx >= 0:
            return round(self.filesize_approx / (1024 * 1024), 2)
        return None

    @property
    def display_label(self) -> str:
        """User-friendly representation of the format quality."""
        if self.is_audio_only:
            bitrate = f"{int(self.abr)}kbps" if self.abr else "audio"
            return f"{bitrate} ({self.ext})"
        res = self.resolution or (f"{self.height}p" if self.height else "video")
        fps_str = f"{int(self.fps)}" if (self.fps and self.fps > 30) else ""
        res_full = f"{res}{fps_str}" if fps_str and not str(res).endswith(fps_str) else str(res)
        return f"{res_full} ({self.ext})"

    @property
    def quality_score(self) -> int:
        """Numerical score for ranking formats from best to worst."""
        if self.is_video:
            h = self.height or 0
            f = int(self.fps or 30)
            b = int(self.vbr or 0)
            return (h * 10000) + (f * 100) + b
        return int((self.abr or 0) * 10)


class MediaAsset(LinkConvBaseModel):
    """Ancillary asset such as thumbnail, image, or subtitle."""
    asset_type: str
    url: str
    label: Optional[str] = None
    dimensions: Optional[str] = None
    ext: Optional[str] = None
    filesize_approx: Optional[int] = None
    slide_index: Optional[int] = None
    language: Optional[str] = None


class MediaMetadata(LinkConvBaseModel):
    """Complete canonical metadata for an extracted media item."""
    id: str
    platform: Platform
    original_url: str
    canonical_url: str
    title: str
    description: Optional[str] = None
    uploader: Optional[str] = None
    uploader_url: Optional[str] = None
    duration: Optional[float] = None
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
    extra_info: Dict[str, Any] = Field(default_factory=dict)

    def best_video_format(self, preferred_ext: Optional[str] = None) -> Optional[MediaFormat]:
        """Return highest quality video format matching optional extension."""
        video_formats = [f for f in self.formats if f.is_video]
        if preferred_ext:
            pext = preferred_ext.lower().lstrip(".")
            matching = [f for f in video_formats if f.ext.lower() == pext]
            if matching:
                video_formats = matching
        if not video_formats:
            return None
        return max(video_formats, key=lambda f: f.quality_score)

    def best_audio_format(self, preferred_ext: Optional[str] = None) -> Optional[MediaFormat]:
        """Return highest bitrate audio format matching optional extension."""
        audio_formats = [f for f in self.formats if f.is_audio_only or (f.acodec and f.acodec.lower() != "none")]
        if preferred_ext:
            pext = preferred_ext.lower().lstrip(".")
            matching = [f for f in audio_formats if f.ext.lower() == pext]
            if matching:
                audio_formats = matching
        if not audio_formats:
            return None
        return max(audio_formats, key=lambda f: (f.abr or 0.0))

    def get_format_by_id(self, format_id: str) -> Optional[MediaFormat]:
        """Locate format by format_id."""
        for f in self.formats:
            if f.format_id == format_id:
                return f
        return None

    def filter_formats(
        self,
        video_only: bool = False,
        audio_only: bool = False,
        max_height: Optional[int] = None,
    ) -> List[MediaFormat]:
        """Filter formats by media type and max resolution."""
        res = list(self.formats)
        if video_only:
            res = [f for f in res if f.is_video]
        elif audio_only:
            res = [f for f in res if f.is_audio_only]
        if max_height is not None:
            res = [f for f in res if (f.height or 0) <= max_height]
        return sorted(res, key=lambda f: f.quality_score, reverse=True)

    @property
    def duration_formatted(self) -> str:
        """Formatted duration string (HH:MM:SS or MM:SS)."""
        if not self.duration or self.duration <= 0:
            return "00:00"
        total_sec = int(round(self.duration))
        hrs, rem = divmod(total_sec, 3600)
        mins, secs = divmod(rem, 60)
        if hrs > 0:
            return f"{hrs:02d}:{mins:02d}:{secs:02d}"
        return f"{mins:02d}:{secs:02d}"

    @property
    def carousel_images(self) -> List[MediaAsset]:
        """Extract carousel images sorted by slide index."""
        images = [a for a in self.assets if a.asset_type in ("image", "thumbnail")]
        return sorted(images, key=lambda a: (a.slide_index if a.slide_index is not None else 9999))


SUPPORTED_VIDEO_FORMATS: Set[str] = {"mp4", "webm", "mkv", "mov", "avi"}
SUPPORTED_AUDIO_FORMATS: Set[str] = {"mp3", "m4a", "wav", "flac", "opus", "aac", "ogg"}
ALL_SUPPORTED_FORMATS: Set[str] = SUPPORTED_VIDEO_FORMATS | SUPPORTED_AUDIO_FORMATS


class ConversionOptions(LinkConvBaseModel):
    """Configuration options for transcoding/conversion."""
    target_format: str = "mp4"
    target_quality: Optional[str] = "best"
    extract_audio_only: bool = False
    embed_thumbnail: bool = True
    output_dir: Optional[str] = None
    filename_template: Optional[str] = "%(title)s.%(ext)s"
    custom_filename: Optional[str] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    audio_bitrate: Optional[str] = None
    video_bitrate: Optional[str] = None
    include_subtitles: bool = False

    @field_validator("target_format", mode="before")
    @classmethod
    def normalize_target_format(cls, v: Any) -> str:
        if isinstance(v, str):
            clean = v.lower().lstrip(".").strip()
            if clean not in ALL_SUPPORTED_FORMATS:
                raise ValueError(
                    f"Unsupported target format: '{v}'. Supported: {sorted(ALL_SUPPORTED_FORMATS)}"
                )
            return clean
        return v

    @model_validator(mode="after")
    def adjust_audio_options(self) -> ConversionOptions:
        if self.extract_audio_only and self.target_format in SUPPORTED_VIDEO_FORMATS:
            self.target_format = "mp3"
        return self


class ConversionRequest(LinkConvBaseModel):
    """User conversion request payload."""
    url: str
    options: ConversionOptions = Field(default_factory=ConversionOptions)
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    cookies: Optional[str] = None
    proxy: Optional[str] = None
    headers: Optional[Dict[str, str]] = None

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        clean = v.strip()
        if not clean:
            raise ValueError("Media URL cannot be empty")
        return clean


class JobState(str, Enum):
    """Status lifecycle of an asynchronous job."""
    PENDING = "pending"
    EXTRACTING = "extracting"
    DOWNLOADING = "downloading"
    CONVERTING = "converting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobStatus(LinkConvBaseModel):
    """Job status and progress tracking model."""
    job_id: str
    state: JobState = JobState.PENDING
    progress: float = 0.0
    speed: Optional[str] = None
    eta: Optional[int] = None
    current_step: Optional[str] = None
    error_message: Optional[str] = None
    error_code: Optional[str] = None
    output_path: Optional[str] = None
    output_size_bytes: Optional[int] = None
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
    metadata: Optional[MediaMetadata] = None

    def update_progress(
        self,
        progress: float,
        step: Optional[str] = None,
        speed: Optional[str] = None,
        eta: Optional[int] = None,
    ) -> None:
        """Update job progress state."""
        self.progress = max(0.0, min(100.0, float(progress)))
        if step is not None:
            self.current_step = step
        if speed is not None:
            self.speed = speed
        if eta is not None:
            self.eta = eta
        self.updated_at = time.time()

    def set_completed(self, output_path: str, output_size_bytes: Optional[int] = None) -> None:
        """Mark job as successfully finished."""
        self.state = JobState.COMPLETED
        self.progress = 100.0
        self.output_path = output_path
        self.output_size_bytes = output_size_bytes
        self.current_step = "Finished successfully"
        self.updated_at = time.time()

    def set_failed(self, error_message: str, error_code: Optional[str] = None) -> None:
        """Mark job as failed with diagnostics."""
        self.state = JobState.FAILED
        self.error_message = error_message
        self.error_code = error_code
        self.current_step = f"Failed: {error_message}"
        self.updated_at = time.time()

    @property
    def is_finished(self) -> bool:
        """Check if job reached terminal state."""
        return self.state in (JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED)
