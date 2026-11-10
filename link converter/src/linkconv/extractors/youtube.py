"""YouTube Extractor with Node.js n-sig deciphering, DASH streams, and subtitle/chapter parsing.

File: src/linkconv/extractors/youtube.py
"""
from __future__ import annotations

import asyncio
import os
import re
import shutil
from typing import Any, Dict, Optional

import yt_dlp

from linkconv.core.models import MediaMetadata, Platform
from linkconv.extractors.base import BaseExtractor, ExtractionOptions

YOUTUBE_REGEX = re.compile(
    r"^(https?://)?(www\.|m\.|music\.)?(youtube\.com/(watch\?.*v=|shorts/|embed/|playlist\?|@|c/|user/|channel/|v/|e/|live/)|youtu\.be/)(?P<id>[a-zA-Z0-9_-]{11}|[a-zA-Z0-9_-]+)",
    re.IGNORECASE,
)


def discover_node_runtime() -> Optional[str]:
    """Finds the Node.js binary on Windows/PATH for n-sig cipher deciphering."""
    node_path = shutil.which("node")
    if node_path:
        return node_path

    candidates = [
        r"C:\Program Files\nodejs\node.exe",
        r"C:\Program Files (x86)\nodejs\node.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\nodejs\node.exe"),
    ]
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    return None


class YouTubeExtractor(BaseExtractor):
    """Extractor for YouTube videos, Shorts, Music, playlists, and channels."""
    platform: Platform = Platform.YOUTUBE
    supported_domains = {"youtube.com", "youtu.be", "music.youtube.com", "m.youtube.com"}

    def __init__(self, options: Optional[ExtractionOptions] = None):
        super().__init__(options)
        self.node_path = discover_node_runtime()
        if self.node_path:
            self.logger.info("Discovered Node.js at '%s' for YouTube n-sig deciphering.", self.node_path)
        else:
            self.logger.warning("Node.js not found! YouTube downloads may experience throttling.")

    def supports_url(self, url: str) -> bool:
        return bool(YOUTUBE_REGEX.search(url))

    def _build_ydl_opts(self, options: Optional[ExtractionOptions] = None) -> Dict[str, Any]:
        ydl_opts = super()._build_ydl_opts(options)

        # Inject Node.js runtime for deciphering n-sig cipher
        if self.node_path:
            ydl_opts["js_runtimes"] = {
                "node": {"path": self.node_path}
            }

        # YouTube specific extractor arguments
        ydl_opts["extractor_args"] = {
            "youtube": {
                "player_client": ["web", "ios"],
                "player_skip": ["configs", "webpage"],
            }
        }
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
            self.logger.error("YouTube extraction failed for %s: %s", url, e)
            raise self._map_error(e, url)
