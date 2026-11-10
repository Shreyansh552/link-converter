"""Universal Media Link Converter (linkconv).

A high-performance media link extraction, transcoding, and embedding framework.
"""

__version__ = "0.1.0"

from linkconv.core.models import (
    ConversionOptions,
    ConversionRequest,
    JobState,
    JobStatus,
    MediaAsset,
    MediaFormat,
    MediaMetadata,
    Platform,
)
from linkconv.core.exceptions import (
    AuthenticationError,
    AuthenticationRequiredError,
    ContentNotFoundError,
    DownloadError,
    ErrorCode,
    ExtractionError,
    FFmpegNotFoundError,
    GeoRestrictedError,
    InvalidOptionsError,
    InvalidUrlError,
    LinkConvError,
    PlatformNotSupportedError,
    RateLimitError,
    TranscodingError,
    UnsupportedPlatformError,
)
from linkconv.core.router import RouteResult, UrlRouterService
from linkconv.extractors.engine import MediaExtractionEngine, MediaExtractionService

__all__ = [
    "__version__",
    "Platform",
    "MediaFormat",
    "MediaAsset",
    "MediaMetadata",
    "ConversionOptions",
    "ConversionRequest",
    "JobState",
    "JobStatus",
    "LinkConvError",
    "ErrorCode",
    "InvalidUrlError",
    "UnsupportedPlatformError",
    "PlatformNotSupportedError",
    "ExtractionError",
    "AuthenticationRequiredError",
    "AuthenticationError",
    "GeoRestrictedError",
    "RateLimitError",
    "ContentNotFoundError",
    "TranscodingError",
    "FFmpegNotFoundError",
    "DownloadError",
    "InvalidOptionsError",
    "RouteResult",
    "UrlRouterService",
    "MediaExtractionEngine",
    "MediaExtractionService",
]
