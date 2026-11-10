"""Media extraction subsystem for linkconv.

Contains platform extractors and unified extraction engine.
"""

from linkconv.extractors.base import BaseExtractor, ExtractionOptions
from linkconv.extractors.youtube import YouTubeExtractor
from linkconv.extractors.instagram import InstagramExtractor
from linkconv.extractors.multi import (
    FacebookExtractor,
    GenericExtractor,
    MultiExtractor,
    MultiPlatformExtractor,
    PinterestExtractor,
    RedditExtractor,
    SoundCloudExtractor,
    TikTokExtractor,
    TwitterExtractor,
    VimeoExtractor,
)
from linkconv.extractors.engine import MediaExtractionEngine, MediaExtractionService

__all__ = [
    "BaseExtractor",
    "ExtractionOptions",
    "YouTubeExtractor",
    "InstagramExtractor",
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
    "MediaExtractionEngine",
    "MediaExtractionService",
]
