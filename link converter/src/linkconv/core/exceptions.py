"""Exceptions taxonomy and error codes for linkconv media converter.

Provides a structured, hierarchical error model with machine-readable codes,
actionable user guidance, and serializable dict representations for CLI and REST APIs.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional


class ErrorCode(str, Enum):
    """Standardized error codes for linkconv operations."""
    UNKNOWN = "LC_ERR_UNKNOWN"
    INVALID_URL = "LC_ERR_INVALID_URL"
    UNSUPPORTED_PLATFORM = "LC_ERR_UNSUPPORTED_PLATFORM"
    EXTRACTION_FAILED = "LC_ERR_EXTRACTION_FAILED"
    AUTH_REQUIRED = "LC_ERR_AUTH_REQUIRED"
    GEO_RESTRICTED = "LC_ERR_GEO_RESTRICTED"
    RATE_LIMITED = "LC_ERR_RATE_LIMITED"
    CONTENT_NOT_FOUND = "LC_ERR_CONTENT_NOT_FOUND"
    CONTENT_PRIVATE = "LC_ERR_CONTENT_PRIVATE"
    LIVE_STREAM_UNSUPPORTED = "LC_ERR_LIVE_STREAM_UNSUPPORTED"
    TRANSCODING_FAILED = "LC_ERR_TRANSCODING_FAILED"
    FFMPEG_NOT_FOUND = "LC_ERR_FFMPEG_NOT_FOUND"
    DOWNLOAD_FAILED = "LC_ERR_DOWNLOAD_FAILED"
    INVALID_OPTIONS = "LC_ERR_INVALID_OPTIONS"
    NETWORK_ERROR = "LC_ERR_NETWORK_ERROR"
    JOB_NOT_FOUND = "LC_ERR_JOB_NOT_FOUND"


class LinkConvError(Exception):
    """Base domain exception for all linkconv operations."""

    def __init__(
        self,
        message: str,
        error_code: ErrorCode | str = ErrorCode.UNKNOWN,
        user_hint: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        original_exception: Optional[Exception] = None,
    ):
        super().__init__(message)
        self.message = message
        if isinstance(error_code, ErrorCode):
            self.error_code = error_code
        else:
            try:
                self.error_code = ErrorCode(error_code)
            except ValueError:
                self.error_code = error_code
        self.user_hint = user_hint or self._default_user_hint()
        self.details = details or {}
        self.original_exception = original_exception

    def _default_user_hint(self) -> str:
        return "An unexpected error occurred in linkconv. Please verify your input and configuration."

    def to_dict(self) -> Dict[str, Any]:
        """Serialize error details for API responses and structured logging."""
        code_val = self.error_code.value if isinstance(self.error_code, ErrorCode) else str(self.error_code)
        return {
            "error": True,
            "error_type": self.__class__.__name__,
            "error_code": code_val,
            "message": self.message,
            "user_hint": self.user_hint,
            "details": self.details,
        }

    def __str__(self) -> str:
        code_str = self.error_code.value if isinstance(self.error_code, ErrorCode) else str(self.error_code)
        if self.user_hint:
            return f"[{code_str}] {self.message} (Hint: {self.user_hint})"
        return f"[{code_str}] {self.message}"


class InvalidUrlError(LinkConvError):
    """Raised when an input URL is malformed, empty, or unparseable."""

    def __init__(
        self,
        url: str = "",
        reason: Optional[str] = None,
        message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        user_hint: Optional[str] = None,
        code: Optional[str] = None,
        platform: Optional[str] = None,
    ):
        if message:
            msg = message
        else:
            msg = f"Invalid URL '{url}'"
            if reason:
                msg += f": {reason}"
        det = {"url": url}
        if reason:
            det["reason"] = reason
        if platform:
            det["platform"] = platform
        if details:
            det.update(details)
        hint = user_hint or "Please check that the URL is complete, begins with http:// or https://, and is not truncated."
        super().__init__(
            message=msg,
            error_code=code or ErrorCode.INVALID_URL,
            user_hint=hint,
            details=det,
        )
        self.url = url
        self.reason = reason


class UnsupportedPlatformError(LinkConvError):
    """Raised when a URL does not match any recognized platform extractor."""

    def __init__(
        self,
        url: str = "",
        hostname: Optional[str] = None,
        supported_platforms: Optional[List[str]] = None,
        message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        user_hint: Optional[str] = None,
    ):
        if message:
            msg = message
        else:
            msg = f"Unsupported platform for URL: '{url}'"
            if hostname:
                msg += f" (host: {hostname})"
        det = {"url": url}
        if hostname:
            det["hostname"] = hostname
        if supported_platforms:
            det["supported_platforms"] = supported_platforms
        if details:
            det.update(details)
        hint = user_hint or (
            "The platform is not supported. Supported platforms: YouTube, Instagram, TikTok, "
            "Twitter/X, Facebook, Reddit, Pinterest, Vimeo, SoundCloud, or direct HTML5 media links."
        )
        super().__init__(
            message=msg,
            error_code=ErrorCode.UNSUPPORTED_PLATFORM,
            user_hint=hint,
            details=det,
        )
        self.url = url
        self.hostname = hostname


class ExtractionError(LinkConvError):
    """Raised when an extractor fails to retrieve metadata or media streams."""

    def __init__(
        self,
        url: str = "",
        message: str = "Extraction failed",
        extractor: Optional[str] = None,
        raw_error: Optional[str] = None,
        code: Optional[str] = None,
        platform: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        user_hint: Optional[str] = None,
        original_exception: Optional[Exception] = None,
    ):
        det = {"url": url}
        if extractor or platform:
            det["extractor"] = extractor or platform
        if raw_error:
            det["raw_error"] = raw_error
        if details:
            det.update(details)
        hint = user_hint or "Extraction failed. Verify that the URL is public, accessible without login, and has not been taken down."
        super().__init__(
            message=message,
            error_code=code or ErrorCode.EXTRACTION_FAILED,
            user_hint=hint,
            details=det,
            original_exception=original_exception,
        )
        self.url = url
        self.extractor = extractor or platform
        self.raw_error = raw_error


class AuthenticationRequiredError(LinkConvError):
    """Raised when content is private or requires user authentication/login cookies."""

    def __init__(
        self,
        url: Optional[str] = None,
        platform: Optional[str] = None,
        message: Optional[str] = None,
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        user_hint: Optional[str] = None,
    ):
        target_url = url or ""
        msg = message or f"Authentication required to access content at '{target_url}'"
        det = {"url": target_url}
        if platform:
            det["platform"] = platform
        if details:
            det.update(details)
        hint = user_hint or "This media requires authentication. Provide session cookies using the --cookies or --cookies-from-browser option."
        super().__init__(
            message=msg,
            error_code=code or ErrorCode.AUTH_REQUIRED,
            user_hint=hint,
            details=det,
        )
        self.url = target_url
        self.platform = platform


class GeoRestrictedError(LinkConvError):
    """Raised when media is blocked in the requester's geographical region."""

    def __init__(
        self,
        url: Optional[str] = None,
        countries: Optional[List[str]] = None,
        message: Optional[str] = None,
        code: Optional[str] = None,
        platform: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        user_hint: Optional[str] = None,
    ):
        target_url = url or ""
        msg = message or f"Content at '{target_url}' is geographically restricted in your region."
        det = {"url": target_url}
        if countries:
            det["allowed_or_blocked_countries"] = countries
        if platform:
            det["platform"] = platform
        if details:
            det.update(details)
        hint = user_hint or "This video is not available in your region due to geographic restrictions. Try configuring an HTTP or SOCKS5 proxy."
        super().__init__(
            message=msg,
            error_code=code or ErrorCode.GEO_RESTRICTED,
            user_hint=hint,
            details=det,
        )
        self.url = target_url
        self.countries = countries or []


class RateLimitError(LinkConvError):
    """Raised when platform rate limits or bot challenges are triggered."""

    def __init__(
        self,
        platform: str = "",
        retry_after: Optional[int] = None,
        message: Optional[str] = None,
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        user_hint: Optional[str] = None,
    ):
        msg = message or f"Rate limit exceeded for platform '{platform}'."
        if retry_after and "retry after" not in msg.lower():
            msg += f" Retry after {retry_after} seconds."
        det = {"platform": platform}
        if retry_after:
            det["retry_after"] = retry_after
        if details:
            det.update(details)
        hint = user_hint or "The platform has temporarily rate-limited your requests. Please wait a few minutes before trying again or configure a proxy."
        super().__init__(
            message=msg,
            error_code=code or ErrorCode.RATE_LIMITED,
            user_hint=hint,
            details=det,
        )
        self.platform = platform
        self.retry_after = retry_after


class ContentNotFoundError(LinkConvError):
    """Raised when requested media has been deleted or cannot be found (HTTP 404)."""

    def __init__(
        self,
        url: str = "",
        message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        user_hint: Optional[str] = None,
    ):
        msg = message or f"Media content not found at '{url}'."
        det = {"url": url}
        if details:
            det.update(details)
        hint = user_hint or "The requested media could not be found. It may have been deleted, set to private, or the URL contains a typo."
        super().__init__(
            message=msg,
            error_code=ErrorCode.CONTENT_NOT_FOUND,
            user_hint=hint,
            details=det,
        )
        self.url = url


class TranscodingError(LinkConvError):
    """Raised when FFmpeg muxing, format conversion, or encoding fails."""

    def __init__(
        self,
        message: str = "Transcoding failed",
        command: Optional[List[str]] = None,
        returncode: Optional[int] = None,
        stderr: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        user_hint: Optional[str] = None,
    ):
        det: Dict[str, Any] = {}
        if command:
            det["command"] = command
        if returncode is not None:
            det["returncode"] = returncode
        if stderr:
            det["stderr_tail"] = stderr[-1000:] if len(stderr) > 1000 else stderr
        if details:
            det.update(details)
        hint = user_hint or "Media transcoding failed. Check that input and output codecs are compatible and that sufficient disk space exists."
        super().__init__(
            message=message,
            error_code=ErrorCode.TRANSCODING_FAILED,
            user_hint=hint,
            details=det,
        )
        self.command = command
        self.returncode = returncode
        self.stderr = stderr


class FFmpegNotFoundError(LinkConvError):
    """Raised when FFmpeg binary is missing from PATH and local caches."""

    def __init__(
        self,
        searched_locations: Optional[List[str]] = None,
        message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        user_hint: Optional[str] = None,
    ):
        msg = message or "FFmpeg executable could not be found on your system."
        det: Dict[str, Any] = {}
        if searched_locations:
            det["searched_locations"] = searched_locations
        if details:
            det.update(details)
        hint = user_hint or "FFmpeg binary was not found on your system. Run 'linkconv setup-ffmpeg' to auto-download, or install FFmpeg and add it to your PATH."
        super().__init__(
            message=msg,
            error_code=ErrorCode.FFMPEG_NOT_FOUND,
            user_hint=hint,
            details=det,
        )
        self.searched_locations = searched_locations or []


class DownloadError(LinkConvError):
    """Raised when network stream download is interrupted or fails."""

    def __init__(
        self,
        url: str = "",
        message: str = "Download failed",
        details: Optional[Dict[str, Any]] = None,
        user_hint: Optional[str] = None,
    ):
        det = {"url": url}
        if details:
            det.update(details)
        hint = user_hint or "Network transfer failed during media stream download. Check your internet connection or proxy settings."
        super().__init__(
            message=message,
            error_code=ErrorCode.DOWNLOAD_FAILED,
            user_hint=hint,
            details=det,
        )
        self.url = url


class InvalidOptionsError(LinkConvError):
    """Raised when invalid conversion options or parameters are provided."""

    def __init__(
        self,
        message: str = "Invalid options",
        option_name: Optional[str] = None,
        invalid_value: Optional[Any] = None,
        details: Optional[Dict[str, Any]] = None,
        user_hint: Optional[str] = None,
    ):
        det: Dict[str, Any] = {}
        if option_name:
            det["option_name"] = option_name
        if invalid_value is not None:
            det["invalid_value"] = str(invalid_value)
        if details:
            det.update(details)
        hint = user_hint or "Invalid conversion options specified. Please verify supported formats and parameters."
        super().__init__(
            message=message,
            error_code=ErrorCode.INVALID_OPTIONS,
            user_hint=hint,
            details=det,
        )
        self.option_name = option_name
        self.invalid_value = invalid_value


# Canonical aliases for backward compatibility and test contracts
AuthenticationError = AuthenticationRequiredError
PlatformNotSupportedError = UnsupportedPlatformError

__all__ = [
    "ErrorCode",
    "LinkConvError",
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
]

