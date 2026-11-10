"""Unified Media Extraction Engine combining URL routing, extractor registry,
anti-bot hardening, proxy routing, and fallback pipelines.

File: src/linkconv/extractors/engine.py
"""
from __future__ import annotations

import logging
import random
from typing import List, Optional

from linkconv.core.exceptions import ExtractionError, LinkConvError
from linkconv.core.models import MediaMetadata
from linkconv.core.router import UrlRouterService
from linkconv.extractors.base import BaseExtractor, ExtractionOptions
from linkconv.extractors.instagram import InstagramExtractor
from linkconv.extractors.multi import (
    FacebookExtractor,
    GenericExtractor,
    PinterestExtractor,
    RedditExtractor,
    SoundCloudExtractor,
    TikTokExtractor,
    TwitterExtractor,
    VimeoExtractor,
)
from linkconv.extractors.youtube import YouTubeExtractor

USER_AGENTS: List[str] = [
    # Chrome on Windows 10/11
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    # Edge on Windows 10/11
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
    # Chrome on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    # Safari on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
]


class MediaExtractionEngine:
    """Central facade for all media extraction.

    Manages URL sanitization, shortlink expansion, extractor selection,
    and anti-bot hardening.
    """

    def __init__(
        self,
        router: Optional[UrlRouterService] = None,
        default_options: Optional[ExtractionOptions] = None,
    ):
        self.router = router or UrlRouterService()
        self.default_options = default_options or ExtractionOptions()
        self.logger = logging.getLogger("linkconv.engine")

        # Extractor registry ordered by specificity (Generic is last)
        self.extractors: List[BaseExtractor] = [
            YouTubeExtractor(self.default_options),
            InstagramExtractor(self.default_options),
            TikTokExtractor(self.default_options),
            TwitterExtractor(self.default_options),
            FacebookExtractor(self.default_options),
            RedditExtractor(self.default_options),
            PinterestExtractor(self.default_options),
            VimeoExtractor(self.default_options),
            SoundCloudExtractor(self.default_options),
            GenericExtractor(self.default_options),
        ]

    def register_extractor(self, extractor: BaseExtractor, priority: int = 0) -> None:
        """Allows injecting custom or plugin extractors ahead of Generic."""
        self.extractors.insert(priority, extractor)

    async def extract_info(
        self,
        url: str,
        cookies: Optional[str] = None,
        proxy: Optional[str] = None,
    ) -> MediaMetadata:
        """Interface Contract #3 compliance method."""
        opts = ExtractionOptions(
            cookie_file=cookies if (cookies and not cookies.startswith(("chrome", "firefox", "edge", "brave"))) else None,
            cookie_browser=cookies if (cookies and cookies.startswith(("chrome", "firefox", "edge", "brave"))) else None,
            proxy=proxy,
        )
        return await self.extract(url, options=opts)

    async def extract(
        self,
        raw_url: str,
        options: Optional[ExtractionOptions] = None,
    ) -> MediaMetadata:
        """Full extraction pipeline:

        1. Sanitize tracking parameters
        2. Expand shortlinks
        3. Match extractor
        4. Apply anti-bot options (rotating UA, proxy, cookies)
        5. Execute extraction with fallback
        """
        # Copy or use options
        base_opts = options or self.default_options
        opts = ExtractionOptions(
            proxy=base_opts.proxy,
            cookie_file=base_opts.cookie_file,
            cookie_browser=base_opts.cookie_browser,
            user_agent=base_opts.user_agent or random.choice(USER_AGENTS),
            timeout_seconds=base_opts.timeout_seconds,
            max_retries=base_opts.max_retries,
            js_runtimes=base_opts.js_runtimes,
            custom_headers=base_opts.custom_headers,
            extract_flat=base_opts.extract_flat,
            allow_fallbacks=base_opts.allow_fallbacks,
        )

        # Step 1: Sanitize tracking parameters
        clean_url = self.router.sanitize(raw_url)
        self.logger.debug("Sanitized URL: %s -> %s", raw_url, clean_url)

        # Step 2: Expand shortlink
        canonical_url = await self.router.expand(clean_url)
        self.logger.debug("Expanded URL: %s -> %s", clean_url, canonical_url)

        # Step 3: Route to matching extractor
        matched_extractor: Optional[BaseExtractor] = None
        for extractor in self.extractors:
            if extractor.supports_url(canonical_url):
                matched_extractor = extractor
                break

        if not matched_extractor:
            matched_extractor = self.extractors[-1]  # GenericExtractor

        self.logger.info("Routing '%s' to %s", canonical_url, matched_extractor.__class__.__name__)

        # Step 4: Execute extraction
        try:
            return await matched_extractor.extract(canonical_url, options=opts)
        except LinkConvError:
            raise
        except Exception as e:
            self.logger.error("Extraction failed via %s: %s", matched_extractor.__class__.__name__, e)
            # Step 5: Fallback to Generic if specialized extractor failed and wasn't Generic
            if not isinstance(matched_extractor, GenericExtractor) and opts.allow_fallbacks:
                self.logger.warning("Attempting fallback to GenericExtractor for %s", canonical_url)
                try:
                    generic = next(e for e in self.extractors if isinstance(e, GenericExtractor))
                    return await generic.extract(canonical_url, options=opts)
                except Exception as fallback_err:
                    self.logger.error("Fallback extraction failed: %s", fallback_err)

            raise ExtractionError(
                url=canonical_url,
                message=f"Extraction failed for '{canonical_url}': {e}",
                code="EXTRACTION_FAILED",
                platform=matched_extractor.platform.value,
            )


# Alias for Interface Contract #3 compliance (PROJECT.md)
MediaExtractionService = MediaExtractionEngine

__all__ = [
    "MediaExtractionEngine",
    "MediaExtractionService",
    "USER_AGENTS",
]

