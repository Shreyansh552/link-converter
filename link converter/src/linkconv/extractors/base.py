"""Abstract base class and configuration models for all platform extractors.

File: src/linkconv/extractors/base.py
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import logging
from typing import Any, Dict, List, Optional, Set

from linkconv.core.exceptions import (
    AuthenticationRequiredError,
    ContentNotFoundError,
    ExtractionError,
    GeoRestrictedError,
    InvalidUrlError,
    LinkConvError,
    RateLimitError,
)
from linkconv.core.models import MediaAsset, MediaFormat, MediaMetadata, Platform


@dataclass
class ExtractionOptions:
    """Options governing network, credentials, and anti-bot behavior."""
    proxy: Optional[str] = None
    cookie_file: Optional[str] = None
    cookie_browser: Optional[str] = None
    user_agent: Optional[str] = None
    timeout_seconds: float = 30.0
    max_retries: int = 2
    js_runtimes: Optional[Dict[str, Any]] = None
    custom_headers: Optional[Dict[str, str]] = None
    extract_flat: bool = False
    allow_fallbacks: bool = True


class BaseExtractor(ABC):
    """Abstract base extractor encapsulating common yt-dlp lifecycle,

    normalization logic, and structured error handling.
    """
    platform: Platform = Platform.GENERIC
    supported_domains: Set[str] = set()

    def __init__(self, options: Optional[ExtractionOptions] = None):
        self.options = options or ExtractionOptions()
        self.logger = logging.getLogger(f"linkconv.extractors.{self.platform.value}")

    @abstractmethod
    def supports_url(self, url: str) -> bool:
        """Determines whether this extractor can process the given URL."""
        pass

    @abstractmethod
    async def extract(self, url: str, options: Optional[ExtractionOptions] = None) -> MediaMetadata:
        """Asynchronously extracts metadata and formats from the URL."""
        pass

    def _build_ydl_opts(self, options: Optional[ExtractionOptions] = None) -> Dict[str, Any]:
        """Builds standardized yt-dlp option dictionary with proxy, cookies,

        timeouts, and user agents applied.
        """
        opts = options or self.options
        ydl_opts: Dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": not opts.extract_flat,
            "extract_flat": opts.extract_flat,
            "socket_timeout": opts.timeout_seconds,
            "retries": opts.max_retries,
        }

        # Anti-bot User-Agent
        if opts.user_agent:
            ydl_opts["user_agent"] = opts.user_agent
        else:
            ydl_opts["user_agent"] = (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            )

        # Proxy support
        if opts.proxy:
            ydl_opts["proxy"] = opts.proxy

        # Cookies
        if opts.cookie_file:
            ydl_opts["cookiefile"] = opts.cookie_file
        elif opts.cookie_browser:
            ydl_opts["cookiesfrombrowser"] = (opts.cookie_browser,)

        # Custom HTTP Headers
        if opts.custom_headers:
            ydl_opts["http_headers"] = dict(opts.custom_headers)

        # JS Runtimes (e.g. Node.js for YouTube n-sig)
        if opts.js_runtimes:
            ydl_opts["js_runtimes"] = opts.js_runtimes

        return ydl_opts

    def _normalize_format(self, raw_fmt: Dict[str, Any]) -> MediaFormat:
        """Converts a raw yt-dlp format dictionary into a standardized MediaFormat model.

        Correctly detects DASH streams and flags `needs_muxing`.
        """
        vcodec = raw_fmt.get("vcodec") or "none"
        acodec = raw_fmt.get("acodec") or "none"
        protocol = str(raw_fmt.get("protocol") or "").lower()
        format_note = str(raw_fmt.get("format_note") or "").lower()

        # Is this a DASH or fragmented stream?
        is_dash = (
            "dash" in protocol
            or "dash" in format_note
            or protocol in ("http_dash_segments", "m3u8_native")
        )

        is_video_only = (vcodec != "none") and (acodec == "none")
        needs_muxing = is_video_only

        # Resolution computation
        width = raw_fmt.get("width")
        height = raw_fmt.get("height")
        resolution = raw_fmt.get("resolution")
        if not resolution and width and height:
            resolution = f"{width}x{height}"
        elif not resolution and height:
            resolution = f"{height}p"

        # Bitrates
        abr = float(raw_fmt["abr"]) if raw_fmt.get("abr") is not None else None
        vbr = float(raw_fmt["vbr"]) if raw_fmt.get("vbr") is not None else None

        # Filesize approximation
        filesize = raw_fmt.get("filesize") or raw_fmt.get("filesize_approx")

        return MediaFormat(
            format_id=str(raw_fmt.get("format_id", "")),
            ext=raw_fmt.get("ext", "mp4"),
            resolution=resolution,
            width=width,
            height=height,
            fps=float(raw_fmt["fps"]) if raw_fmt.get("fps") is not None else None,
            vcodec=vcodec,
            acodec=acodec,
            abr=abr,
            vbr=vbr,
            filesize_approx=filesize,
            url=raw_fmt.get("url"),
            is_dash=is_dash,
            needs_muxing=needs_muxing,
            format_note=raw_fmt.get("format_note"),
            http_headers=raw_fmt.get("http_headers"),
        )

    def _normalize_metadata(self, raw_info: Dict[str, Any], url: str) -> MediaMetadata:
        """Converts a raw yt-dlp info dictionary into a strongly typed MediaMetadata model."""
        raw_formats = raw_info.get("formats") or []
        formats: List[MediaFormat] = [
            self._normalize_format(fmt) for fmt in raw_formats if fmt.get("url")
        ]

        # Assets: Thumbnails
        assets: List[MediaAsset] = []
        raw_thumbnails = raw_info.get("thumbnails") or []
        for idx, thumb in enumerate(raw_thumbnails):
            thumb_url = thumb.get("url")
            if not thumb_url:
                continue
            w = thumb.get("width")
            h = thumb.get("height")
            dim = f"{w}x{h}" if (w and h) else None
            assets.append(MediaAsset(
                asset_type="thumbnail",
                url=thumb_url,
                label=f"thumbnail_{idx}",
                dimensions=dim,
            ))

        # Assets: Subtitles & Captions
        subtitles = raw_info.get("subtitles") or {}
        for lang, sub_list in subtitles.items():
            if isinstance(sub_list, list):
                for sub_entry in sub_list:
                    if isinstance(sub_entry, dict) and sub_entry.get("url"):
                        assets.append(MediaAsset(
                            asset_type="subtitle",
                            url=sub_entry["url"],
                            label=f"{lang}_{sub_entry.get('ext', 'vtt')}",
                            language=lang,
                        ))

        # Check for playlist
        is_playlist = raw_info.get("_type") == "playlist" or bool(raw_info.get("entries"))
        playlist_items = None
        playlist_count = None
        if is_playlist:
            entries = [e for e in (raw_info.get("entries") or []) if e]
            playlist_count = len(entries)
            playlist_items = [
                {
                    "id": str(e.get("id")),
                    "title": e.get("title", ""),
                    "url": e.get("webpage_url") or e.get("url", ""),
                }
                for e in entries
            ]

        # Extract primary thumbnail URL (prefer highest resolution)
        primary_thumbnail = raw_info.get("thumbnail")
        if not primary_thumbnail and assets:
            thumb_assets = [a for a in assets if a.asset_type == "thumbnail"]
            if thumb_assets:
                primary_thumbnail = thumb_assets[-1].url

        extra_info: Dict[str, Any] = {}
        if "chapters" in raw_info and raw_info["chapters"]:
            extra_info["chapters"] = raw_info["chapters"]

        return MediaMetadata(
            id=str(raw_info.get("id", "")),
            platform=self.platform,
            original_url=url,
            canonical_url=raw_info.get("webpage_url") or url,
            title=raw_info.get("title") or "Untitled Media",
            description=raw_info.get("description"),
            uploader=raw_info.get("uploader") or raw_info.get("channel"),
            uploader_url=raw_info.get("uploader_url") or raw_info.get("channel_url"),
            duration=float(raw_info["duration"]) if raw_info.get("duration") is not None else None,
            thumbnail_url=primary_thumbnail,
            formats=formats,
            assets=assets,
            view_count=raw_info.get("view_count"),
            like_count=raw_info.get("like_count"),
            tags=raw_info.get("tags") or [],
            is_live=bool(raw_info.get("is_live", False)),
            is_playlist=is_playlist,
            playlist_count=playlist_count,
            playlist_items=playlist_items,
            extra_info=extra_info,
        )

    def _map_error(self, exc: Exception, url: str) -> LinkConvError:
        """Translates raw yt-dlp or network exceptions into the structured

        LinkConvError taxonomy with actionable error codes and hints.
        """
        msg = str(exc).lower()

        # Authentication Required
        if any(term in msg for term in [
            "sign in", "login", "log in", "private video", "private account",
            "confirm your age", "age-restricted", "checkpoint_required",
            "this video is private", "requires authentication",
        ]):
            return AuthenticationRequiredError(
                url=url,
                platform=self.platform.value,
                message=f"Authentication required to access media at '{url}'. Provide cookies or browser session.",
                code="AUTH_REQUIRED",
                user_hint="Provide a cookies file with --cookies or browser session with --cookies-from-browser",
            )

        # Content Not Found (404)
        if any(term in msg for term in ["not found", "404", "does not exist", "deleted"]):
            return ContentNotFoundError(
                url=url,
                message=f"Media not found at '{url}': {exc}",
                user_hint="The requested media could not be found. It may have been deleted or the URL contains a typo.",
            )

        # Geo-Restricted
        if any(term in msg for term in [
            "not available in your country", "georestricted",
            "blocked in your country", "geo restricted",
        ]):
            return GeoRestrictedError(
                url=url,
                message=f"Media is geographically restricted at '{url}'.",
                code="GEO_RESTRICTED",
                platform=self.platform.value,
                user_hint="Use a proxy from an allowed country via --proxy",
            )

        # Rate Limited
        if any(term in msg for term in ["429", "too many requests", "rate limit", "throttled"]):
            return RateLimitError(
                platform=self.platform.value,
                message=f"Rate limit exceeded while accessing '{url}'.",
                code="RATE_LIMITED",
                user_hint="Wait a moment before retrying or route through a proxy",
            )

        # Invalid URL
        if any(term in msg for term in ["unsupported url", "is not a valid url", "invalid url"]):
            return InvalidUrlError(
                url=url,
                reason=str(exc),
                message=f"The URL '{url}' is invalid or unsupported.",
                code="INVALID_URL",
                platform=self.platform.value,
                user_hint="Check the URL format and try again",
            )

        # General Extraction Error
        return ExtractionError(
            url=url,
            message=f"Failed to extract media from '{url}': {str(exc)}",
            code="EXTRACTION_FAILED",
            extractor=self.platform.value,
            raw_error=str(exc),
            original_exception=exc,
            user_hint="Verify the link is accessible in an incognito browser window",
        )
