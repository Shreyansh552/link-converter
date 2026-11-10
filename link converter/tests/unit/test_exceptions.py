"""Unit tests for linkconv error taxonomy and exceptions.

File: tests/unit/test_exceptions.py
"""
from pathlib import Path
import sys
import unittest

src_path = str(Path(__file__).resolve().parent.parent.parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

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


class TestLinkConvErrorBase(unittest.TestCase):
    def test_base_error_defaults(self):
        err = LinkConvError("Generic fault occurred")
        self.assertEqual(err.message, "Generic fault occurred")
        self.assertEqual(err.error_code, ErrorCode.UNKNOWN)
        self.assertIn("unexpected error occurred", err.user_hint)
        self.assertEqual(err.details, {})

    def test_base_error_to_dict(self):
        err = LinkConvError(
            message="Test error",
            error_code=ErrorCode.UNKNOWN,
            user_hint="Try again later",
            details={"debug_key": "debug_val"},
        )
        d = err.to_dict()
        self.assertTrue(d["error"])
        self.assertEqual(d["error_type"], "LinkConvError")
        self.assertEqual(d["error_code"], "LC_ERR_UNKNOWN")
        self.assertEqual(d["message"], "Test error")
        self.assertEqual(d["user_hint"], "Try again later")
        self.assertEqual(d["details"], {"debug_key": "debug_val"})

    def test_str_representation(self):
        err = LinkConvError("Something failed", error_code=ErrorCode.UNKNOWN, user_hint="Check logs")
        self.assertIn("[LC_ERR_UNKNOWN] Something failed", str(err))
        self.assertIn("(Hint: Check logs)", str(err))


class TestDerivedExceptions(unittest.TestCase):
    def test_invalid_url_error(self):
        err = InvalidUrlError("htt://broken", reason="Missing 'p' in protocol")
        self.assertEqual(err.error_code, ErrorCode.INVALID_URL)
        self.assertEqual(err.url, "htt://broken")
        self.assertEqual(err.reason, "Missing 'p' in protocol")
        self.assertIn("begins with http:// or https://", err.user_hint)
        d = err.to_dict()
        self.assertEqual(d["details"]["url"], "htt://broken")
        self.assertEqual(d["details"]["reason"], "Missing 'p' in protocol")

    def test_unsupported_platform_error(self):
        err = UnsupportedPlatformError("https://myspace.com/music/123", hostname="myspace.com")
        self.assertEqual(err.error_code, ErrorCode.UNSUPPORTED_PLATFORM)
        self.assertEqual(err.hostname, "myspace.com")
        self.assertIn("Supported platforms:", err.user_hint)

    def test_extraction_error(self):
        err = ExtractionError(
            url="https://youtube.com/watch?v=missing",
            message="Extractor yt-dlp failed",
            extractor="youtube",
            raw_error="HTTP Error 404: Not Found",
        )
        self.assertEqual(err.error_code, ErrorCode.EXTRACTION_FAILED)
        self.assertEqual(err.extractor, "youtube")
        self.assertEqual(err.details["raw_error"], "HTTP Error 404: Not Found")

    def test_authentication_required_error(self):
        err = AuthenticationRequiredError(
            url="https://instagram.com/reel/secret",
            platform="instagram",
        )
        self.assertEqual(err.error_code, ErrorCode.AUTH_REQUIRED)
        self.assertEqual(err.platform, "instagram")
        self.assertIn("--cookies", err.user_hint)

    def test_geo_restricted_error(self):
        err = GeoRestrictedError(
            url="https://vimeo.com/123",
            countries=["US", "CA"],
        )
        self.assertEqual(err.error_code, ErrorCode.GEO_RESTRICTED)
        self.assertEqual(err.countries, ["US", "CA"])
        self.assertIn("proxy", err.user_hint)

    def test_rate_limit_error(self):
        err = RateLimitError(platform="twitter", retry_after=60)
        self.assertEqual(err.error_code, ErrorCode.RATE_LIMITED)
        self.assertEqual(err.platform, "twitter")
        self.assertEqual(err.retry_after, 60)
        self.assertIn("60 seconds", err.message)

    def test_content_not_found_error(self):
        err = ContentNotFoundError(url="https://youtube.com/watch?v=deleted")
        self.assertEqual(err.error_code, ErrorCode.CONTENT_NOT_FOUND)
        self.assertEqual(err.url, "https://youtube.com/watch?v=deleted")
        self.assertIn("could not be found", err.user_hint)

    def test_transcoding_error(self):
        err = TranscodingError(
            message="FFmpeg exited with error 1",
            command=["ffmpeg", "-i", "in.mp4", "out.mp3"],
            returncode=1,
            stderr="Invalid audio stream",
        )
        self.assertEqual(err.error_code, ErrorCode.TRANSCODING_FAILED)
        self.assertEqual(err.returncode, 1)
        self.assertEqual(err.stderr, "Invalid audio stream")

    def test_ffmpeg_not_found_error(self):
        err = FFmpegNotFoundError(searched_locations=["C:\\Program Files\\ffmpeg", "PATH"])
        self.assertEqual(err.error_code, ErrorCode.FFMPEG_NOT_FOUND)
        self.assertIn("linkconv setup-ffmpeg", err.user_hint)
        self.assertEqual(len(err.searched_locations), 2)

    def test_download_error(self):
        err = DownloadError(url="https://cdn.example.com/video.mp4", message="Connection reset by peer")
        self.assertEqual(err.error_code, ErrorCode.DOWNLOAD_FAILED)
        self.assertEqual(err.url, "https://cdn.example.com/video.mp4")
        self.assertIn("Network transfer failed", err.user_hint)

    def test_invalid_options_error(self):
        err = InvalidOptionsError(
            message="Unsupported bitrate",
            option_name="audio_bitrate",
            invalid_value="9999k",
        )
        self.assertEqual(err.error_code, ErrorCode.INVALID_OPTIONS)
        self.assertEqual(err.option_name, "audio_bitrate")
        self.assertEqual(err.invalid_value, "9999k")

    def test_authentication_error_alias(self):
        self.assertIs(AuthenticationError, AuthenticationRequiredError)
        self.assertTrue(issubclass(AuthenticationError, LinkConvError))
        err = AuthenticationError("Auth needed", platform="instagram")
        self.assertEqual(err.error_code, ErrorCode.AUTH_REQUIRED)

    def test_platform_not_supported_error_alias(self):
        self.assertIs(PlatformNotSupportedError, UnsupportedPlatformError)
        self.assertTrue(issubclass(PlatformNotSupportedError, LinkConvError))
        err = PlatformNotSupportedError("Unsupported", hostname="example.com")
        self.assertEqual(err.error_code, ErrorCode.UNSUPPORTED_PLATFORM)



if __name__ == "__main__":
    unittest.main()
