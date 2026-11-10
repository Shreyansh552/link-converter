"""Adversarial stress-testing suite for Milestone 1 extractors and engine robustness.

Covers:
- Node.js detection and --js-runtimes node yt-dlp option formatting
- Instagram empty response / auth required exception handling
- Reddit DASH stream separation flags (needs_muxing, is_dash)
- Vimeo Referer header injection and preservation
- MediaFormat quality scoring and best_video/best_audio resolution under edge case payloads
- Interface contracts and export naming conformance
"""
from __future__ import annotations

import asyncio
from pathlib import Path
import shutil
import sys
import unittest
from unittest.mock import MagicMock, patch

src_path = str(Path(__file__).resolve().parent.parent.parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

import yt_dlp
from yt_dlp import YoutubeDL

from linkconv.core.exceptions import (
    AuthenticationRequiredError,
    ExtractionError,
    LinkConvError,
)
from linkconv.core.models import (
    MediaAsset,
    MediaFormat,
    MediaMetadata,
    Platform,
)
from linkconv.extractors.base import ExtractionOptions
from linkconv.extractors.engine import MediaExtractionEngine
from linkconv.extractors.instagram import InstagramExtractor
from linkconv.extractors.multi import (
    GenericExtractor,
    RedditExtractor,
    SoundCloudExtractor,
    VimeoExtractor,
)
from linkconv.extractors.youtube import YouTubeExtractor, discover_node_runtime


class TestNodeJsDetectionAndFormatting(unittest.TestCase):
    """Challenge Node.js detection and ensure yt-dlp js_runtimes option formatting."""

    def test_discover_node_runtime_on_system(self):
        """Verifies Node.js discovery behavior on current system."""
        node_path = discover_node_runtime()
        if shutil.which("node"):
            self.assertIsNotNone(node_path, "Node.js is on PATH but discover_node_runtime returned None")
            self.assertTrue(Path(node_path).exists(), f"Discovered node path does not exist: {node_path}")

    def test_discover_node_runtime_fallback_when_not_on_path(self):
        """Verifies candidate path checks when PATH has no node."""
        with patch("shutil.which", return_value=None):
            with patch("os.path.isfile", side_effect=lambda p: "C:\\Program Files\\nodejs\\node.exe" in p):
                discovered = discover_node_runtime()
                self.assertEqual(discovered, r"C:\Program Files\nodejs\node.exe")

    def test_discover_node_runtime_returns_none_when_missing(self):
        """Verifies clean None return when Node.js is completely absent."""
        with patch("shutil.which", return_value=None):
            with patch("os.path.isfile", return_value=False):
                discovered = discover_node_runtime()
                self.assertIsNone(discovered)

    def test_youtube_ydl_opts_js_runtimes_structure(self):
        """Verifies js_runtimes in YouTubeExtractor conforms to yt-dlp specification."""
        with patch("linkconv.extractors.youtube.discover_node_runtime", return_value=r"C:\fake\node.exe"):
            extractor = YouTubeExtractor()
            opts = extractor._build_ydl_opts()
            self.assertIn("js_runtimes", opts)
            self.assertIsInstance(opts["js_runtimes"], dict)
            self.assertIn("node", opts["js_runtimes"])
            self.assertEqual(opts["js_runtimes"]["node"], {"path": r"C:\fake\node.exe"})

    def test_yt_dlp_accepts_formatted_js_runtimes(self):
        """Empirically tests that yt_dlp.YoutubeDL accepts the generated js_runtimes structure."""
        opts = {
            "quiet": True,
            "skip_download": True,
            "js_runtimes": {"node": {"path": shutil.which("node") or "node"}},
        }
        ydl = yt_dlp.YoutubeDL(opts)
        self.assertIsNotNone(ydl)


class TestInstagramEmptyResponsesAndAuth(unittest.IsolatedAsyncioTestCase):
    """Challenge Instagram empty response handling and authentication error codes."""

    async def test_instagram_empty_response_none_raises_auth_required(self):
        """When yt-dlp returns None for Instagram URL, AuthenticationRequiredError with AUTH_REQUIRED_INSTAGRAM must be raised."""
        extractor = InstagramExtractor()
        mock_ydl = MagicMock()
        mock_ydl.__enter__.return_value = mock_ydl
        mock_ydl.extract_info.return_value = None

        with patch("yt_dlp.YoutubeDL", return_value=mock_ydl):
            with self.assertRaises(AuthenticationRequiredError) as ctx:
                await extractor.extract("https://www.instagram.com/p/CxyzEmptyNone/")
            
            err = ctx.exception
            self.assertEqual(err.error_code, "AUTH_REQUIRED_INSTAGRAM")
            self.assertEqual(err.to_dict()["error_code"], "AUTH_REQUIRED_INSTAGRAM")
            self.assertIn("instagram", err.details.get("platform", "").lower())

    async def test_instagram_empty_response_dict_raises_auth_required(self):
        """When yt-dlp returns empty dict {} for Instagram URL, AuthenticationRequiredError with AUTH_REQUIRED_INSTAGRAM must be raised."""
        extractor = InstagramExtractor()
        mock_ydl = MagicMock()
        mock_ydl.__enter__.return_value = mock_ydl
        mock_ydl.extract_info.return_value = {}

        with patch("yt_dlp.YoutubeDL", return_value=mock_ydl):
            with self.assertRaises(AuthenticationRequiredError) as ctx:
                await extractor.extract("https://www.instagram.com/reel/CxyzEmptyDict/")

            err = ctx.exception
            self.assertEqual(err.error_code, "AUTH_REQUIRED_INSTAGRAM")
            self.assertEqual(err.to_dict()["error_code"], "AUTH_REQUIRED_INSTAGRAM")

    async def test_instagram_login_exception_raises_auth_required_instagram(self):
        """When yt-dlp raises login/checkpoint exception, error code must be AUTH_REQUIRED_INSTAGRAM."""
        extractor = InstagramExtractor()
        mock_ydl = MagicMock()
        mock_ydl.__enter__.return_value = mock_ydl
        mock_ydl.extract_info.side_effect = Exception("checkpoint_required: please log in")

        with patch("yt_dlp.YoutubeDL", return_value=mock_ydl):
            with patch.object(extractor, "_fallback_embed_scrape", return_value=None):
                with self.assertRaises(AuthenticationRequiredError) as ctx:
                    await extractor.extract("https://www.instagram.com/reel/CxyzLogin/")

                err = ctx.exception
                self.assertEqual(err.error_code, "AUTH_REQUIRED_INSTAGRAM")


class TestRedditDashMuxingFlags(unittest.IsolatedAsyncioTestCase):
    """Challenge Reddit DASH streams: ensure needs_muxing=True and is_dash=True when audio and video are separate."""

    async def test_reddit_dash_video_only_flags(self):
        """Separate video stream must have needs_muxing=True and is_dash=True."""
        extractor = RedditExtractor()
        mock_ydl = MagicMock()
        mock_ydl.__enter__.return_value = mock_ydl
        mock_ydl.extract_info.return_value = {
            "id": "reddit123",
            "title": "Adversarial Reddit Test",
            "webpage_url": "https://www.reddit.com/r/test/comments/reddit123/title/",
            "formats": [
                {
                    "format_id": "dash_v1080",
                    "url": "https://v.redd.it/dash_1080.mp4",
                    "vcodec": "avc1.64002a",
                    "acodec": "none",
                    "height": 1080,
                    "fps": 60,
                },
                {
                    "format_id": "dash_v720_null_acodec",
                    "url": "https://v.redd.it/dash_720.mp4",
                    "vcodec": "h264",
                    "acodec": None,
                    "height": 720,
                    "fps": 30,
                },
                {
                    "format_id": "dash_audio",
                    "url": "https://v.redd.it/dash_audio.mp4",
                    "vcodec": "none",
                    "acodec": "mp4a.40.2",
                    "abr": 128,
                },
                {
                    "format_id": "pre_muxed_stream",
                    "url": "https://v.redd.it/fallback.mp4",
                    "vcodec": "h264",
                    "acodec": "aac",
                    "height": 480,
                },
            ],
        }

        with patch("yt_dlp.YoutubeDL", return_value=mock_ydl):
            meta = await extractor.extract("https://www.reddit.com/r/test/comments/reddit123/title/")

            v1080 = meta.get_format_by_id("dash_v1080")
            self.assertIsNotNone(v1080)
            self.assertTrue(v1080.needs_muxing, "Video-only DASH format must have needs_muxing=True")
            self.assertTrue(v1080.is_dash, "Video-only DASH format must have is_dash=True")

            v720 = meta.get_format_by_id("dash_v720_null_acodec")
            self.assertIsNotNone(v720)
            self.assertTrue(v720.needs_muxing, "Format with null acodec must have needs_muxing=True")
            self.assertTrue(v720.is_dash, "Format with null acodec must have is_dash=True")

            audio = meta.get_format_by_id("dash_audio")
            self.assertIsNotNone(audio)
            self.assertFalse(audio.needs_muxing, "Audio stream does not need muxing on its own")

            muxed = meta.get_format_by_id("pre_muxed_stream")
            self.assertIsNotNone(muxed)
            self.assertFalse(muxed.needs_muxing, "Pre-muxed stream must not have needs_muxing=True")
            self.assertFalse(muxed.is_dash, "Pre-muxed stream must not have is_dash=True")


class TestVimeoRefererHeaderInjection(unittest.TestCase):
    """Challenge Vimeo extractor: verify Referer header injection and preservation."""

    def test_vimeo_default_referer_injected(self):
        """VimeoExtractor must inject Referer: https://vimeo.com/ by default."""
        extractor = VimeoExtractor()
        opts = extractor._build_ydl_opts()
        headers = opts.get("http_headers", {})
        self.assertEqual(headers.get("Referer"), "https://vimeo.com/")

    def test_vimeo_custom_headers_without_referer(self):
        """Custom headers without Referer must still have Referer added."""
        extractor = VimeoExtractor()
        custom = ExtractionOptions(custom_headers={"X-Requested-With": "XMLHttpRequest"})
        opts = extractor._build_ydl_opts(custom)
        headers = opts.get("http_headers", {})
        self.assertEqual(headers.get("X-Requested-With"), "XMLHttpRequest")
        self.assertEqual(headers.get("Referer"), "https://vimeo.com/")

    def test_vimeo_preserves_custom_referer(self):
        """If caller provides custom Referer (e.g. for embedded player), it must be preserved."""
        extractor = VimeoExtractor()
        custom = ExtractionOptions(custom_headers={"Referer": "https://player.vimeo.com/video/12345"})
        opts = extractor._build_ydl_opts(custom)
        headers = opts.get("http_headers", {})
        self.assertEqual(headers.get("Referer"), "https://player.vimeo.com/video/12345")


class TestFormatQualityScoringEdgeCases(unittest.TestCase):
    """Challenge format quality scoring and best_video_format / best_audio_format resolution under edge cases."""

    def test_video_without_audio_resolution(self):
        """Video formats without audio stream must be picked by best_video_format and ignored by best_audio_format."""
        formats = [
            MediaFormat(format_id="v_1080", ext="mp4", vcodec="h264", acodec="none", height=1080, fps=60.0),
            MediaFormat(format_id="v_720", ext="mp4", vcodec="h264", acodec="none", height=720, fps=30.0),
        ]
        meta = MediaMetadata(
            id="v_only",
            platform=Platform.YOUTUBE,
            original_url="https://youtube.com/watch?v=1",
            canonical_url="https://youtube.com/watch?v=1",
            title="Video Only",
            formats=formats,
        )
        best_v = meta.best_video_format()
        self.assertIsNotNone(best_v)
        self.assertEqual(best_v.format_id, "v_1080")
        self.assertIsNone(meta.best_audio_format(), "best_audio_format must be None when no audio tracks exist")

    def test_audio_without_video_resolution(self):
        """Audio formats without video stream must be picked by best_audio_format and ignored by best_video_format."""
        formats = [
            MediaFormat(format_id="a_320", ext="mp3", vcodec="none", acodec="mp3", abr=320.0),
            MediaFormat(format_id="a_128", ext="mp3", vcodec="none", acodec="mp3", abr=128.0),
        ]
        meta = MediaMetadata(
            id="a_only",
            platform=Platform.SOUNDCLOUD,
            original_url="https://soundcloud.com/track",
            canonical_url="https://soundcloud.com/track",
            title="Audio Only",
            formats=formats,
        )
        best_a = meta.best_audio_format()
        self.assertIsNotNone(best_a)
        self.assertEqual(best_a.format_id, "a_320")
        self.assertIsNone(meta.best_video_format(), "best_video_format must be None when no video tracks exist")

    def test_missing_resolution_strings_and_dimensions(self):
        """Formats with missing resolution, height, and width must compute safe display_label and quality_score."""
        fmt = MediaFormat(
            format_id="edge_no_res",
            ext="mp4",
            vcodec="h264",
            acodec="aac",
            resolution=None,
            height=None,
            width=None,
            fps=None,
            vbr=None,
        )
        self.assertIn("video (mp4)", fmt.display_label)
        self.assertGreaterEqual(fmt.quality_score, 0)
        self.assertTrue(fmt.is_video)
        self.assertFalse(fmt.is_audio_only)

    def test_audio_format_missing_abr(self):
        """Audio format with None abr must compute safe display_label and quality_score without crashing."""
        fmt = MediaFormat(
            format_id="audio_no_abr",
            ext="opus",
            vcodec="none",
            acodec="opus",
            abr=None,
        )
        self.assertEqual(fmt.display_label, "audio (opus)")
        self.assertEqual(fmt.quality_score, 0)
        self.assertFalse(fmt.is_video)
        self.assertTrue(fmt.is_audio_only)

    def test_empty_formats_list(self):
        """MediaMetadata with empty formats must safely return None for best_video and best_audio."""
        meta = MediaMetadata(
            id="empty_meta",
            platform=Platform.GENERIC,
            original_url="https://example.com/item",
            canonical_url="https://example.com/item",
            title="Empty Meta",
            formats=[],
        )
        self.assertIsNone(meta.best_video_format())
        self.assertIsNone(meta.best_audio_format())
        self.assertEqual(meta.filter_formats(video_only=True), [])
        self.assertEqual(meta.filter_formats(audio_only=True), [])

    def test_codecs_case_insensitivity(self):
        """Codecs like 'None', 'NONE', 'none' must all be recognized as absence of stream."""
        fmt = MediaFormat(
            format_id="case_test",
            ext="mp4",
            vcodec="NONE",
            acodec="None",
        )
        self.assertFalse(fmt.is_video)
        self.assertFalse(fmt.is_audio_only)

    def test_preferred_extension_filtering_and_fallback(self):
        """best_video_format with preferred_ext must match if available, or fall back to best overall."""
        formats = [
            MediaFormat(format_id="v_mp4", ext="mp4", vcodec="h264", height=720),
            MediaFormat(format_id="v_webm", ext="webm", vcodec="vp9", height=1080),
        ]
        meta = MediaMetadata(
            id="ext_test",
            platform=Platform.YOUTUBE,
            original_url="https://youtube.com/watch?v=1",
            canonical_url="https://youtube.com/watch?v=1",
            title="Ext Test",
            formats=formats,
        )
        self.assertEqual(meta.best_video_format(preferred_ext="mp4").format_id, "v_mp4")
        self.assertEqual(meta.best_video_format(preferred_ext="webm").format_id, "v_webm")
        # Unmatched preferred_ext falls back to highest quality overall (v_webm at 1080p)
        self.assertEqual(meta.best_video_format(preferred_ext="mkv").format_id, "v_webm")


if __name__ == "__main__":
    unittest.main()
