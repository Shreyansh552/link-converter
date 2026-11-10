"""Multi-platform extractors for TikTok, Twitter/X, Facebook, Reddit, Pinterest, Vimeo, SoundCloud, and Generic HTML5.

File: src/linkconv/extractors/multi.py
"""
from __future__ import annotations

import asyncio
import re
from typing import Any, Dict, Optional, Set
import urllib.parse

import yt_dlp

from linkconv.core.models import MediaFormat, MediaMetadata, Platform
from linkconv.extractors.base import BaseExtractor, ExtractionOptions

# Regex patterns for platforms
TIKTOK_REGEX = re.compile(
    r"^(https?://)?((www|m|vm|vt)\.)?tiktok\.com/",
    re.IGNORECASE,
)
TWITTER_REGEX = re.compile(
    r"^(https?://)?((www|mobile)\.)?(twitter|x)\.com/|^(https?://)?t\.co/",
    re.IGNORECASE,
)
FACEBOOK_REGEX = re.compile(
    r"^(https?://)?((www|m|web|fb)\.)?(facebook\.com|fb\.watch)/",
    re.IGNORECASE,
)
REDDIT_REGEX = re.compile(
    r"^(https?://)?((www|old)\.)?(reddit\.com/(?:r/[\w]+/comments/|gallery/)|redd\.it/|v\.redd\.it/)",
    re.IGNORECASE,
)
PINTEREST_REGEX = re.compile(
    r"^(https?://)?([a-z0-9-]+\.)?(pinterest\.(?:com|[a-z]{2}(?:\.[a-z]{2})?)|pin\.it)/",
    re.IGNORECASE,
)
VIMEO_REGEX = re.compile(
    r"^(https?://)?((www|player)\.)?vimeo\.com/",
    re.IGNORECASE,
)
SOUNDCLOUD_REGEX = re.compile(
    r"^(https?://)?((www|m)\.)?(soundcloud\.com/|on\.soundcloud\.com/)",
    re.IGNORECASE,
)


class TikTokExtractor(BaseExtractor):
    """Extractor for TikTok videos and photos."""
    platform: Platform = Platform.TIKTOK
    supported_domains: Set[str] = {"tiktok.com", "vm.tiktok.com", "vt.tiktok.com"}

    def supports_url(self, url: str) -> bool:
        return bool(TIKTOK_REGEX.search(url))

    async def extract(self, url: str, options: Optional[ExtractionOptions] = None) -> MediaMetadata:
        opts = self._build_ydl_opts(options)

        def _sync_extract() -> Dict[str, Any]:
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=False)

        try:
            raw_info = await asyncio.to_thread(_sync_extract)
            return self._normalize_metadata(raw_info, url)
        except Exception as e:
            self.logger.error("TikTok extraction failed for %s: %s", url, e)
            raise self._map_error(e, url)


class TwitterExtractor(BaseExtractor):
    """Extractor for Twitter / X posts and videos."""
    platform: Platform = Platform.TWITTER
    supported_domains: Set[str] = {"twitter.com", "x.com", "t.co"}

    def supports_url(self, url: str) -> bool:
        return bool(TWITTER_REGEX.search(url))

    async def extract(self, url: str, options: Optional[ExtractionOptions] = None) -> MediaMetadata:
        opts = self._build_ydl_opts(options)

        def _sync_extract() -> Dict[str, Any]:
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=False)

        try:
            raw_info = await asyncio.to_thread(_sync_extract)
            return self._normalize_metadata(raw_info, url)
        except Exception as e:
            self.logger.error("Twitter/X extraction failed for %s: %s", url, e)
            raise self._map_error(e, url)


class FacebookExtractor(BaseExtractor):
    """Extractor for Facebook videos, Reels, and watch links."""
    platform: Platform = Platform.FACEBOOK
    supported_domains: Set[str] = {"facebook.com", "fb.watch"}

    def supports_url(self, url: str) -> bool:
        return bool(FACEBOOK_REGEX.search(url))

    async def extract(self, url: str, options: Optional[ExtractionOptions] = None) -> MediaMetadata:
        opts = self._build_ydl_opts(options)

        def _sync_extract() -> Dict[str, Any]:
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=False)

        try:
            raw_info = await asyncio.to_thread(_sync_extract)
            return self._normalize_metadata(raw_info, url)
        except Exception as e:
            self.logger.error("Facebook extraction failed for %s: %s", url, e)
            raise self._map_error(e, url)


class RedditExtractor(BaseExtractor):
    """Extractor for Reddit videos and posts with DASH muxing detection."""
    platform: Platform = Platform.REDDIT
    supported_domains: Set[str] = {"reddit.com", "redd.it", "v.redd.it"}

    def supports_url(self, url: str) -> bool:
        return bool(REDDIT_REGEX.search(url))

    async def extract(self, url: str, options: Optional[ExtractionOptions] = None) -> MediaMetadata:
        opts = self._build_ydl_opts(options)

        def _sync_extract() -> Dict[str, Any]:
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=False)

        try:
            raw_info = await asyncio.to_thread(_sync_extract)
            metadata = self._normalize_metadata(raw_info, url)

            # Reddit DASH detection: video-only formats require audio muxing
            for fmt in metadata.formats:
                if fmt.vcodec and fmt.vcodec.lower() != "none" and (not fmt.acodec or fmt.acodec.lower() == "none"):
                    fmt.needs_muxing = True
                    fmt.is_dash = True

            return metadata
        except Exception as e:
            self.logger.error("Reddit extraction failed for %s: %s", url, e)
            raise self._map_error(e, url)


class PinterestExtractor(BaseExtractor):
    """Extractor for Pinterest video and image pins."""
    platform: Platform = Platform.PINTEREST
    supported_domains: Set[str] = {"pinterest.com", "pin.it"}

    def supports_url(self, url: str) -> bool:
        return bool(PINTEREST_REGEX.search(url))

    async def extract(self, url: str, options: Optional[ExtractionOptions] = None) -> MediaMetadata:
        opts = self._build_ydl_opts(options)

        def _sync_extract() -> Dict[str, Any]:
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=False)

        try:
            raw_info = await asyncio.to_thread(_sync_extract)
            return self._normalize_metadata(raw_info, url)
        except Exception as e:
            self.logger.error("Pinterest extraction failed for %s: %s", url, e)
            raise self._map_error(e, url)


class VimeoExtractor(BaseExtractor):
    """Extractor for Vimeo videos with Referer spoofing and privacy hash handling."""
    platform: Platform = Platform.VIMEO
    supported_domains: Set[str] = {"vimeo.com", "player.vimeo.com"}

    def supports_url(self, url: str) -> bool:
        return bool(VIMEO_REGEX.search(url))

    def _build_ydl_opts(self, options: Optional[ExtractionOptions] = None) -> Dict[str, Any]:
        ydl_opts = super()._build_ydl_opts(options)
        headers = ydl_opts.get("http_headers") or {}
        if "Referer" not in headers:
            headers["Referer"] = "https://vimeo.com/"
        ydl_opts["http_headers"] = headers
        return ydl_opts

    async def extract(self, url: str, options: Optional[ExtractionOptions] = None) -> MediaMetadata:
        opts = self._build_ydl_opts(options)

        def _sync_extract() -> Dict[str, Any]:
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=False)

        try:
            raw_info = await asyncio.to_thread(_sync_extract)
            return self._normalize_metadata(raw_info, url)
        except Exception as e:
            self.logger.error("Vimeo extraction failed for %s: %s", url, e)
            raise self._map_error(e, url)


class SoundCloudExtractor(BaseExtractor):
    """Extractor for SoundCloud audio tracks and playlists."""
    platform: Platform = Platform.SOUNDCLOUD
    supported_domains: Set[str] = {"soundcloud.com", "on.soundcloud.com"}

    def supports_url(self, url: str) -> bool:
        return bool(SOUNDCLOUD_REGEX.search(url))

    async def extract(self, url: str, options: Optional[ExtractionOptions] = None) -> MediaMetadata:
        opts = self._build_ydl_opts(options)

        def _sync_extract() -> Dict[str, Any]:
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=False)

        try:
            raw_info = await asyncio.to_thread(_sync_extract)
            metadata = self._normalize_metadata(raw_info, url)
            # Ensure SoundCloud audio formats are audio-only
            for fmt in metadata.formats:
                fmt.vcodec = "none"
                if not fmt.acodec or fmt.acodec == "none":
                    fmt.acodec = fmt.ext
            return metadata
        except Exception as e:
            self.logger.error("SoundCloud extraction failed for %s: %s", url, e)
            raise self._map_error(e, url)


class GenericExtractor(BaseExtractor):
    """Catch-all extractor for direct media files and generic HTML5 pages."""
    platform: Platform = Platform.GENERIC
    supported_domains: Set[str] = set()

    def supports_url(self, url: str) -> bool:
        return True

    async def extract(self, url: str, options: Optional[ExtractionOptions] = None) -> MediaMetadata:
        direct_exts = {".mp4", ".m4a", ".webm", ".mkv", ".mov", ".avi", ".mp3", ".wav", ".flac", ".opus", ".ogg"}
        path_lower = urllib.parse.urlsplit(url).path.lower()
        matched_ext = next((ext for ext in direct_exts if path_lower.endswith(ext)), None)

        if matched_ext:
            clean_ext = matched_ext.lstrip(".")
            filename = urllib.parse.urlsplit(url).path.split("/")[-1]
            return MediaMetadata(
                id=filename,
                platform=Platform.GENERIC,
                original_url=url,
                canonical_url=url,
                title=filename,
                formats=[MediaFormat(
                    format_id="direct",
                    ext=clean_ext,
                    url=url,
                    needs_muxing=False,
                )],
            )

        # Fallback to yt-dlp generic extractor
        opts = self._build_ydl_opts(options)

        def _sync_extract() -> Dict[str, Any]:
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=False)

        try:
            raw_info = await asyncio.to_thread(_sync_extract)
            return self._normalize_metadata(raw_info, url)
        except Exception as e:
            self.logger.error("Generic extraction failed for %s: %s", url, e)
            raise self._map_error(e, url)


# Multi-platform aliases for test suite and contract compliance
class MultiExtractor(GenericExtractor):
    """Multi-platform catch-all extractor alias."""
    pass


MultiPlatformExtractor = MultiExtractor

__all__ = [
    "TIKTOK_REGEX",
    "TWITTER_REGEX",
    "FACEBOOK_REGEX",
    "REDDIT_REGEX",
    "PINTEREST_REGEX",
    "VIMEO_REGEX",
    "SOUNDCLOUD_REGEX",
    "TikTokExtractor",
    "TwitterExtractor",
    "FacebookExtractor",
    "RedditExtractor",
    "PinterestExtractor",
    "VimeoExtractor",
    "SoundCloudExtractor",
    "GenericExtractor",
    "MultiExtractor",
    "MultiPlatformExtractor",
]

