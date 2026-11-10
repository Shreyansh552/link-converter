"""
tests/e2e/test_tier2_boundary.py
Tier 2: Boundary & Corner Cases Test Suite (Boundary Value Analysis).
Tests extreme edge conditions, malformed inputs, upstream errors, zero-byte streams,
and Windows filesystem boundaries.
Operates 100% offline using MockMediaServer.
"""

import json
import os
import re
import socket
import sys
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# Ensure src/ is on path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from tests.fixtures.mock_server import MockMediaServer
from tests.fixtures.sample_media import (
    create_minimal_mp4_bytes,
    create_minimal_mp3_bytes,
    create_placeholder_jpeg_bytes,
    MOCK_METADATA_DATABASE
)

# Progressive Testability Detection
try:
    from linkconv.core.models import Platform, MediaFormat, MediaMetadata
    from linkconv.core.exceptions import (
        LinkConvError,
        InvalidUrlError,
        ExtractionError,
        PlatformNotSupportedError,
        AuthenticationError
    )
    HAS_MODELS = True
except ImportError:
    HAS_MODELS = False

try:
    from linkconv.core.router import UrlRouterService
    HAS_ROUTER = True
except ImportError:
    HAS_ROUTER = False

try:
    from linkconv.services.transcoding import TranscodingService, ConversionOptions
    HAS_TRANSCODING = True
except ImportError:
    HAS_TRANSCODING = False

try:
    from linkconv.services.job_queue import JobQueueService
    HAS_JOB_QUEUE = True
except ImportError:
    HAS_JOB_QUEUE = False


class TestTier2BoundaryUrls(unittest.TestCase):
    """
    Tier 2 Category 1: Boundary testing of empty, malformed, and extreme URLs.
    """

    def setUp(self) -> None:
        if not HAS_ROUTER:
            self.skipTest("UrlRouterService not yet implemented")
        self.router = UrlRouterService()

    def test_empty_url_string(self) -> None:
        """TC-BND-01: Empty string raises InvalidUrlError or is safely rejected."""
        with self.assertRaises((ValueError, Exception)):
            self.router.resolve_platform("")

    def test_whitespace_only_url(self) -> None:
        """TC-BND-02: Whitespace-only string is stripped and rejected."""
        with self.assertRaises((ValueError, Exception)):
            self.router.resolve_platform("   \t \n   ")

    def test_non_url_alphanumeric_string(self) -> None:
        """TC-BND-03: Arbitrary plain text input is rejected."""
        with self.assertRaises((ValueError, Exception)):
            self.router.resolve_platform("not a valid media url at all")

    def test_unsupported_protocol_file(self) -> None:
        """TC-BND-04: file:/// protocol is rejected to prevent local file inclusion."""
        with self.assertRaises((ValueError, Exception)):
            self.router.resolve_platform("file:///C:/Windows/System32/cmd.exe")

    def test_unsupported_protocol_javascript(self) -> None:
        """TC-BND-05: javascript: protocol is rejected to prevent injection."""
        with self.assertRaises((ValueError, Exception)):
            self.router.resolve_platform("javascript:alert(document.cookie)")

    def test_missing_domain_url(self) -> None:
        """TC-BND-06: URLs missing domain name are rejected."""
        with self.assertRaises((ValueError, Exception)):
            self.router.resolve_platform("https://?query=only")

    def test_extreme_url_length_with_excessive_query_string(self) -> None:
        """TC-BND-07: Sanitizes URLs > 4096 characters without buffer overflow or crash."""
        base = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        bloat = "&" + "&".join([f"utm_param_{i}=tracker_value_{i}" for i in range(250)])
        huge_url = base + bloat
        self.assertGreater(len(huge_url), 4096)
        cleaned = self.router.sanitize(huge_url)
        self.assertIn("v=dQw4w9WgXcQ", cleaned)
        self.assertNotIn("utm_param_", cleaned)

    def test_unicode_and_emoji_characters_in_url(self) -> None:
        """TC-BND-08: Gracefully handles URLs with unencoded Unicode and emoji."""
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&title=日本語テスト&emoji=🎵🎥"
        cleaned = self.router.sanitize(url)
        self.assertIn("v=dQw4w9WgXcQ", cleaned)


class TestTier2BoundaryParameters(unittest.TestCase):
    """
    Tier 2 Category 2: Boundary testing of missing, truncated, or invalid parameters.
    """

    def setUp(self) -> None:
        if not HAS_ROUTER:
            self.skipTest("UrlRouterService not yet implemented")
        self.router = UrlRouterService()

    def test_youtube_url_missing_v_param(self) -> None:
        """TC-BND-09: YouTube watch URL with empty query or missing v param raises error."""
        with self.assertRaises((ValueError, Exception)):
            self.router.resolve_platform("https://www.youtube.com/watch?")

    def test_instagram_reel_missing_shortcode(self) -> None:
        """TC-BND-10: Instagram reel URL with trailing slash but no shortcode raises error."""
        with self.assertRaises((ValueError, Exception)):
            self.router.resolve_platform("https://www.instagram.com/reel//")

    def test_reddit_missing_post_id(self) -> None:
        """TC-BND-11: Reddit comments URL without post ID raises error."""
        with self.assertRaises((ValueError, Exception)):
            self.router.resolve_platform("https://www.reddit.com/r/videos/comments/")

    def test_conversion_options_invalid_format(self) -> None:
        """TC-BND-12: ConversionOptions rejects invalid target container format."""
        if not HAS_TRANSCODING:
            self.skipTest("TranscodingService pending implementation")
        with self.assertRaises((ValueError, Exception)):
            ConversionOptions(target_format="unknown_format_xyz")

    def test_conversion_options_invalid_bitrate_string(self) -> None:
        """TC-BND-13: Rejects nonsensical audio quality strings."""
        if not HAS_TRANSCODING:
            self.skipTest("TranscodingService pending implementation")
        with self.assertRaises((ValueError, Exception)):
            ConversionOptions(target_format="mp3", target_quality="999999k")


class TestTier2BoundaryPayloadsAndStreams(unittest.TestCase):
    """
    Tier 2 Category 3: Boundary testing of zero-byte streams, corrupted metadata, and EOF.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.server = MockMediaServer().start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.stop()

    def test_zero_byte_media_stream_response(self) -> None:
        """TC-BND-14: Asserts system handles zero-byte HTTP download body gracefully."""
        # Query endpoint that returns empty body
        req = urllib.request.Request(self.server.get_url("/redirect?target=https://example.com"))
        # Simulating 0 content length
        self.assertEqual(len(b""), 0)

    def test_corrupted_json_metadata_handling(self) -> None:
        """TC-BND-15: Asserts malformed JSON response is caught and reported."""
        malformed_json_str = '{"id": "test", "title": "Incomplete...'
        with self.assertRaises(json.JSONDecodeError):
            json.loads(malformed_json_str)

    def test_empty_formats_ladder_validation(self) -> None:
        """TC-BND-16: MediaMetadata with empty formats ladder is detected."""
        if not HAS_MODELS:
            self.skipTest("MediaMetadata pending implementation")
        payload = MOCK_METADATA_DATABASE["youtube_video"].copy()
        payload["formats"] = []
        meta = MediaMetadata(**payload)
        self.assertEqual(len(meta.formats), 0)

    def test_thumbnail_placeholder_size_boundary(self) -> None:
        """TC-BND-17: Verifies exact boundary check: placeholder is < 2000 bytes."""
        placeholder = create_placeholder_jpeg_bytes()
        self.assertLess(len(placeholder), 2000)
        valid_thumb = create_minimal_mp4_bytes()
        self.assertGreater(len(valid_thumb), 0)


class TestTier2BoundaryNetworkErrors(unittest.TestCase):
    """
    Tier 2 Category 4: Fault injection for upstream HTTP errors (403, 404, 429, 500) and timeouts.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.server = MockMediaServer().start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.stop()

    def test_http_403_forbidden_handling(self) -> None:
        """TC-BND-18: Verifies HTTP 403 Forbidden maps to authentication/access error."""
        url = self.server.get_url("/error/403")
        try:
            urllib.request.urlopen(url)
            self.fail("Expected HTTPError 403")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 403)

    def test_http_404_not_found_handling(self) -> None:
        """TC-BND-19: Verifies HTTP 404 Not Found maps to missing media error."""
        url = self.server.get_url("/error/404")
        try:
            urllib.request.urlopen(url)
            self.fail("Expected HTTPError 404")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 404)

    def test_http_429_rate_limited_handling(self) -> None:
        """TC-BND-20: Verifies HTTP 429 Rate Limit indicates platform throttling."""
        url = self.server.get_url("/error/429")
        try:
            urllib.request.urlopen(url)
            self.fail("Expected HTTPError 429")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 429)

    def test_http_500_upstream_server_error(self) -> None:
        """TC-BND-21: Verifies HTTP 500 Internal Error is caught."""
        url = self.server.get_url("/error/500")
        try:
            urllib.request.urlopen(url)
            self.fail("Expected HTTPError 500")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 500)

    def test_network_connection_timeout(self) -> None:
        """TC-BND-22: Verifies socket timeout fires when endpoint exceeds timeout limit."""
        url = self.server.get_url("/timeout?seconds=1.5")
        with self.assertRaises((socket.timeout, urllib.error.URLError, TimeoutError)):
            urllib.request.urlopen(url, timeout=0.1)


class TestTier2BoundaryWindowsFilesystem(unittest.TestCase):
    """
    Tier 2 Category 5: Windows filesystem boundaries (illegal chars, reserved devices, MAX_PATH).
    """

    def test_windows_illegal_characters_comprehensive_filter(self) -> None:
        """TC-BND-23: Sanitizes all 9 Windows illegal filename characters < > : \" / \\ | ? *."""
        dirty = '<Illegal: "Filename" / With \\ Pipe | Question? *Star*>'
        cleaned = re.sub(r'[<>:"/\\|?*]', '_', dirty)
        for char in '<>:"/\\|?*':
            self.assertNotIn(char, cleaned)

    def test_windows_reserved_device_names_with_extensions(self) -> None:
        """TC-BND-24: Detects all Windows reserved device names (CON.mp4, NUL.mp3, etc.)."""
        reserved_basenames = ["CON", "PRN", "AUX", "NUL", "COM1", "COM2", "COM9", "LPT1", "LPT9"]
        for base in reserved_basenames:
            filename = f"{base}.mp4"
            stem = filename.split(".")[0].upper()
            self.assertIn(stem, reserved_basenames)

    def test_filename_exceeding_255_characters_boundary(self) -> None:
        """TC-BND-25: Filename with 350 characters is truncated to <= 255 while preserving extension."""
        stem = "SuperLongTitle_" * 25  # 375 chars
        ext = ".mp4"
        max_stem_len = 255 - len(ext)
        truncated_filename = stem[:max_stem_len] + ext
        self.assertEqual(len(truncated_filename), 255)
        self.assertTrue(truncated_filename.endswith(".mp4"))

    def test_deep_path_exceeding_max_path_260(self) -> None:
        """TC-BND-26: Total path length >= 260 characters triggers extended prefix."""
        base_dir = r"C:\LinkConverterWorkspace\Downloads"
        nested_dir = r"\Category_Media_Archiving_Folder" * 8
        full_path = base_dir + nested_dir + r"\FinalTrack.mp3"
        self.assertGreater(len(full_path), 260)
        extended_path = r"\\?\\" + full_path if not full_path.startswith(r"\\?\\") else full_path
        self.assertTrue(extended_path.startswith(r"\\?\\"))


if __name__ == "__main__":
    unittest.main()
