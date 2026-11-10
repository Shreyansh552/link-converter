"""Instagram Extractor for Reels, Posts, Carousels, and Stories with Cookie & Auth Error handling.

File: src/linkconv/extractors/instagram.py
"""
from __future__ import annotations

import asyncio
import re
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup
import httpx
import yt_dlp

from linkconv.core.exceptions import AuthenticationRequiredError
from linkconv.core.models import MediaAsset, MediaFormat, MediaMetadata, Platform
from linkconv.extractors.base import BaseExtractor, ExtractionOptions

INSTAGRAM_REGEX = re.compile(
    r"^(https?://)?(www\.)?(instagram\.com/(?:p|reel|reels|tv|stories|share/p)/|ig\.me/)(?P<id>[a-zA-Z0-9_-]+)(/(?P<story_id>\d+))?",
    re.IGNORECASE,
)


class InstagramExtractor(BaseExtractor):
    """Extractor for Instagram Posts, Reels, IGTV, Stories, and Carousels."""
    platform: Platform = Platform.INSTAGRAM
    supported_domains = {"instagram.com", "instagr.am", "ig.me"}

    def supports_url(self, url: str) -> bool:
        return bool(INSTAGRAM_REGEX.search(url))

    def load_cookies(self, cookies: str) -> Dict[str, str]:
        """Parses a cookie header formatted string into a key-value dictionary.

        Args:
            cookies: Semicolon-delimited cookie string (e.g., 'sessionid=xyz; ds_user_id=123').

        Returns:
            Dictionary mapping cookie keys to cookie values.
        """
        cookie_dict: Dict[str, str] = {}
        for item in cookies.split(";"):
            item = item.strip()
            if not item:
                continue
            if "=" in item:
                key, val = item.split("=", 1)
                cookie_dict[key.strip()] = val.strip()
        return cookie_dict

    def _build_ydl_opts(self, options: Optional[ExtractionOptions] = None) -> Dict[str, Any]:
        ydl_opts = super()._build_ydl_opts(options)
        headers = ydl_opts.get("http_headers") or {}
        headers.update({
            "Referer": "https://www.instagram.com/",
            "Sec-Fetch-Mode": "navigate",
        })
        ydl_opts["http_headers"] = headers
        return ydl_opts

    async def extract(self, url: str, options: Optional[ExtractionOptions] = None) -> MediaMetadata:
        opts = self._build_ydl_opts(options)

        def _sync_extract() -> Dict[str, Any]:
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=False)

        try:
            raw_info = await asyncio.to_thread(_sync_extract)
            if not raw_info:
                raise AuthenticationRequiredError(
                    url=url,
                    platform="instagram",
                    message="Instagram returned empty response. Authentication is likely required.",
                    code="AUTH_REQUIRED_INSTAGRAM",
                    user_hint="Provide cookies via --cookies or --cookies-from-browser chrome",
                )

            # Check for carousel (multi-slide sidecar)
            entries = raw_info.get("entries")
            if entries:
                return self._normalize_carousel(raw_info, entries, url)

            return self._normalize_metadata(raw_info, url)

        except AuthenticationRequiredError:
            raise
        except Exception as e:
            msg = str(e).lower()
            if any(k in msg for k in ["login", "log in", "checkpoint", "redirect", "private", "requires authentication"]):
                # Try fallback embed scraper before giving up
                opt_obj = options or self.options
                if opt_obj.allow_fallbacks:
                    fallback_meta = await self._fallback_embed_scrape(url)
                    if fallback_meta:
                        return fallback_meta

                raise AuthenticationRequiredError(
                    url=url,
                    platform="instagram",
                    message=f"Instagram requires authentication: {e}",
                    code="AUTH_REQUIRED_INSTAGRAM",
                    user_hint="Provide cookies via --cookies or --cookies-from-browser chrome",
                )
            raise self._map_error(e, url)

    def _normalize_carousel(
        self,
        raw_info: Dict[str, Any],
        entries: List[Dict[str, Any]],
        url: str,
    ) -> MediaMetadata:
        """Indexes all carousel slides as discrete assets and formats."""
        assets: List[MediaAsset] = []
        formats: List[MediaFormat] = []

        for idx, entry in enumerate(entries):
            slide_num = idx + 1
            entry_formats = entry.get("formats") or []
            if entry_formats:
                best_fmt = max(
                    [f for f in entry_formats if f.get("url")],
                    key=lambda x: (x.get("height") or 0, x.get("tbr") or 0),
                    default=None,
                )
                if best_fmt:
                    fmt_obj = self._normalize_format(best_fmt)
                    fmt_obj.format_id = f"slide_{slide_num}_{fmt_obj.format_id}"
                    formats.append(fmt_obj)
                    assets.append(MediaAsset(
                        asset_type="video",
                        url=fmt_obj.url or "",
                        label=f"slide_{slide_num}",
                        dimensions=fmt_obj.resolution,
                        slide_index=idx,
                    ))

            img_url = entry.get("thumbnail") or entry.get("url")
            if img_url and not any(a.label == f"slide_{slide_num}" and a.asset_type == "video" for a in assets):
                w = entry.get("width")
                h = entry.get("height")
                dim = f"{w}x{h}" if (w and h) else None
                assets.append(MediaAsset(
                    asset_type="image",
                    url=img_url,
                    label=f"slide_{slide_num}",
                    dimensions=dim,
                    slide_index=idx,
                ))

        primary_thumb = assets[0].url if assets else None

        return MediaMetadata(
            id=str(raw_info.get("id", "carousel")),
            platform=Platform.INSTAGRAM,
            original_url=url,
            canonical_url=raw_info.get("webpage_url") or url,
            title=raw_info.get("title") or f"Instagram Carousel ({len(entries)} slides)",
            description=raw_info.get("description"),
            uploader=raw_info.get("uploader"),
            thumbnail_url=primary_thumb,
            formats=formats,
            assets=assets,
            is_playlist=True,
            playlist_count=len(entries),
            playlist_items=[{"id": str(e.get("id")), "title": f"Slide {i+1}"} for i, e in enumerate(entries)],
        )

    async def _fallback_embed_scrape(self, url: str) -> Optional[MediaMetadata]:
        """Scrapes Instagram public embed page as fallback for public posts."""
        match = INSTAGRAM_REGEX.search(url)
        if not match:
            return None
        shortcode = match.group("id")
        embed_url = f"https://www.instagram.com/p/{shortcode}/embed/captioned/"

        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                headers = {
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/131.0.0.0 Safari/537.36"
                    ),
                    "Accept-Language": "en-US,en;q=0.9",
                }
                res = await client.get(embed_url, headers=headers)
                if res.status_code != 200:
                    return None
                soup = BeautifulSoup(res.text, "html.parser")

                video_elem = soup.find("video")
                video_url = video_elem.get("src") if video_elem else None

                img_elem = soup.find("img", class_="EmbeddedMediaImage") or soup.find("img")
                img_url = img_elem.get("src") if img_elem else None

                caption_elem = soup.find("div", class_="Caption")
                caption = caption_elem.get_text(strip=True) if caption_elem else None

                if not video_url and not img_url:
                    return None

                formats: List[MediaFormat] = []
                assets: List[MediaAsset] = []
                if video_url:
                    formats.append(MediaFormat(
                        format_id="embed_video",
                        ext="mp4",
                        resolution="720p",
                        vcodec="h264",
                        acodec="aac",
                        url=video_url,
                        needs_muxing=False,
                    ))
                    assets.append(MediaAsset(asset_type="video", url=video_url, label="primary_video"))

                if img_url:
                    assets.append(MediaAsset(asset_type="thumbnail", url=img_url, label="cover_image"))

                return MediaMetadata(
                    id=shortcode,
                    platform=Platform.INSTAGRAM,
                    original_url=url,
                    canonical_url=f"https://www.instagram.com/p/{shortcode}/",
                    title=caption[:60] if caption else f"Instagram {shortcode}",
                    description=caption,
                    thumbnail_url=img_url,
                    formats=formats,
                    assets=assets,
                )
        except Exception:
            return None
