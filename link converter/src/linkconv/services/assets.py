"""Media Asset Service for thumbnail cascade, carousel ZIP bundles, and image downloads.

File: src/linkconv/services/assets.py
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import mimetypes
import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple, Union
import urllib.parse
import zipfile

import httpx

from linkconv.core.exceptions import (
    ContentNotFoundError,
    DownloadError,
    InvalidOptionsError,
    LinkConvError,
)
from linkconv.core.models import MediaAsset, MediaMetadata, Platform

logger = logging.getLogger("linkconv.services.assets")

WINDOWS_ILLEGAL_CHARS_REGEX = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


class MediaAssetService:
    """Service handling thumbnail cascade resolution, carousel archives, and image downloads."""

    PLACEHOLDER_THRESHOLD_BYTES = 2000

    YOUTUBE_CASCADE = [
        ("maxresdefault.jpg", "1920x1080", "maxresdefault"),
        ("sddefault.jpg", "640x480", "sddefault"),
        ("hqdefault.jpg", "480x360", "hqdefault"),
        ("mqdefault.jpg", "320x180", "mqdefault"),
        ("default.jpg", "120x90", "default"),
    ]

    def __init__(
        self,
        http_client: Optional[httpx.AsyncClient] = None,
        timeout: float = 30.0,
        max_concurrent_downloads: int = 5,
    ) -> None:
        self._client = http_client
        self._timeout = timeout
        self._semaphore = asyncio.Semaphore(max_concurrent_downloads)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is not None and not self._client.is_closed:
            return self._client
        return httpx.AsyncClient(
            timeout=httpx.Timeout(self._timeout),
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                )
            },
        )

    def sanitize_filename(self, name: str, max_length: int = 255) -> str:
        """Sanitizes filename for Windows filesystem compatibility."""
        if not name:
            return "unnamed_asset"

        # Strip illegal characters
        cleaned = WINDOWS_ILLEGAL_CHARS_REGEX.sub("_", name)
        cleaned = cleaned.strip(". ")

        if not cleaned:
            cleaned = "unnamed_asset"

        # Check reserved device names
        stem = Path(cleaned).stem.upper()
        if stem in WINDOWS_RESERVED_NAMES:
            cleaned = f"_{cleaned}"

        # Truncate length preserving extension
        if len(cleaned) > max_length:
            ext = Path(cleaned).suffix
            stem_limit = max_length - len(ext)
            cleaned = cleaned[:stem_limit].rstrip(". ") + ext

        return cleaned

    def is_placeholder_thumbnail(
        self,
        content_length: Optional[int] = None,
        content_bytes: Optional[bytes] = None,
    ) -> bool:
        """Returns True if size indicates YouTube 120x90 placeholder graphic (< 2000 bytes)."""
        if content_length is not None and content_length < self.PLACEHOLDER_THRESHOLD_BYTES:
            return True
        if content_bytes is not None and len(content_bytes) < self.PLACEHOLDER_THRESHOLD_BYTES:
            return True
        return False

    async def resolve_youtube_thumbnail(
        self,
        video_id: str,
        client: Optional[httpx.AsyncClient] = None,
    ) -> MediaAsset:
        """Resolves YouTube thumbnail cascade down to first valid non-placeholder image."""
        owns_client = False
        if client is None:
            client = await self._get_client()
            owns_client = self._client is None

        try:
            for filename, dimensions, label in self.YOUTUBE_CASCADE:
                url = f"https://img.youtube.com/vi/{video_id}/{filename}"
                try:
                    resp = await client.head(url)
                    if resp.status_code == 200:
                        cl_str = resp.headers.get("content-length")
                        cl = int(cl_str) if cl_str and cl_str.isdigit() else None
                        if cl is not None and cl < self.PLACEHOLDER_THRESHOLD_BYTES:
                            continue  # Fake placeholder detected!
                        return MediaAsset(
                            asset_type="thumbnail",
                            url=url,
                            label=label,
                            dimensions=dimensions,
                            filesize_approx=cl,
                        )
                    elif resp.status_code in (404, 403):
                        continue
                except Exception:
                    continue

            # Fallback to default
            return MediaAsset(
                asset_type="thumbnail",
                url=f"https://img.youtube.com/vi/{video_id}/default.jpg",
                label="default",
                dimensions="120x90",
            )
        finally:
            if owns_client and client is not None:
                await client.aclose()

    async def download_image(
        self,
        url: str,
        destination_dir: Union[str, Path],
        filename: Optional[str] = None,
        sanitize: bool = True,
    ) -> Path:
        """Downloads image to destination directory with sanitized filename and inferred extension."""
        dest_path = Path(destination_dir)
        dest_path.mkdir(parents=True, exist_ok=True)

        client = await self._get_client()
        owns_client = self._client is None

        try:
            resp = await client.get(url)
            if resp.status_code == 404:
                raise ContentNotFoundError(url=url, message=f"Image not found at '{url}'")
            if resp.status_code != 200:
                raise DownloadError(url=url, message=f"HTTP {resp.status_code} downloading image from '{url}'")

            data = resp.content
            if not data:
                raise DownloadError(url=url, message=f"Received empty response from '{url}'")

            # Determine filename & extension
            if not filename:
                parsed = urllib.parse.urlparse(url)
                raw_name = Path(parsed.path).name or "image"
            else:
                raw_name = filename

            if not Path(raw_name).suffix:
                ct = resp.headers.get("content-type", "").split(";")[0].strip().lower()
                ext = mimetypes.guess_extension(ct) or ".jpg"
                if ext == ".jpe":
                    ext = ".jpg"
                raw_name = f"{raw_name}{ext}"

            final_name = self.sanitize_filename(raw_name) if sanitize else raw_name
            out_file = dest_path / final_name
            out_file.write_bytes(data)
            return out_file
        finally:
            if owns_client:
                await client.aclose()

    async def create_carousel_zip_bytes(self, metadata: MediaMetadata) -> bytes:
        """Downloads all slides for a carousel and bundles into an in-memory ZIP archive."""
        candidate_slides = [a for a in metadata.assets if a.slide_index is not None or a.asset_type in ("image", "video")]
        if candidate_slides:
            slides = sorted(candidate_slides, key=lambda a: (a.slide_index if a.slide_index is not None else 9999))
        else:
            slides = metadata.carousel_images

        client = await self._get_client()
        owns_client = self._client is None

        async def _download_slide(slide: MediaAsset, idx: int) -> Tuple[int, str, bytes, Optional[str]]:
            num = slide.slide_index + 1 if slide.slide_index is not None else idx + 1
            ext = ".mp4" if slide.asset_type == "video" else ".jpg"
            filename = f"slide_{num}{ext}"

            # Check if local file
            if os.path.isfile(slide.url):
                try:
                    content = Path(slide.url).read_bytes()
                    return (num, filename, content, slide.dimensions)
                except Exception as e:
                    logger.warning("Failed to read local slide %s: %s", slide.url, e)
                    return (num, filename, b"", slide.dimensions)

            async with self._semaphore:
                try:
                    resp = await client.get(slide.url)
                    if resp.status_code == 200 and resp.content:
                        return (num, filename, resp.content, slide.dimensions)
                except Exception as e:
                    logger.warning("Failed to download slide %d from %s: %s", num, slide.url, e)
            return (num, filename, b"", slide.dimensions)

        try:
            tasks = [_download_slide(slide, i) for i, slide in enumerate(slides)]
            results = await asyncio.gather(*tasks) if tasks else []

            buf = io.BytesIO()
            with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
                manifest_slides = []
                for num, filename, content, dim in sorted(results, key=lambda x: x[0]):
                    if content:
                        zf.writestr(filename, content)
                        manifest_slides.append({
                            "index": num,
                            "filename": filename,
                            "dimensions": dim or "unknown",
                        })

                platform_val = (
                    metadata.platform.value
                    if hasattr(metadata.platform, "value")
                    else str(metadata.platform)
                )
                manifest = {
                    "platform": platform_val,
                    "type": "carousel",
                    "id": metadata.id,
                    "slide_count": len(manifest_slides),
                    "slides": manifest_slides,
                }
                zf.writestr("manifest.json", json.dumps(manifest, indent=2))

            return buf.getvalue()
        finally:
            if owns_client:
                await client.aclose()

    async def bundle_carousel_zip(
        self,
        metadata: MediaMetadata,
        output_path: Optional[Union[str, Path]] = None,
        output_dir: Optional[Union[str, Path]] = None,
    ) -> Path:
        """Downloads all slides and writes a carousel .zip archive to disk."""
        zip_bytes = await self.create_carousel_zip_bytes(metadata)
        if output_path is not None:
            out_file = Path(output_path)
        else:
            base_dir = Path(output_dir or ".")
            clean_id = self.sanitize_filename(metadata.id)
            out_file = base_dir / f"{clean_id}_carousel.zip"

        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_bytes(zip_bytes)
        return out_file
