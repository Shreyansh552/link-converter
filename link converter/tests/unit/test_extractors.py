"""Unit tests for Platform Extractors and MediaExtractionEngine.

File: tests/unit/test_extractors.py
"""
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

src_path = str(Path(__file__).resolve().parent.parent.parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from yt_dlp import YoutubeDL

from linkconv.core.exceptions import AuthenticationRequiredError, ExtractionError
from linkconv.core.models import MediaMetadata, Platform
from linkconv.extractors.base import ExtractionOptions
from linkconv.extractors.engine import MediaExtractionEngine, MediaExtractionService
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
from linkconv.extractors.youtube import YouTubeExtractor, discover_node_runtime
from tests.fixtures.synthetic_ytdl import (
    SAMPLE_INSTAGRAM_CAROUSEL,
    SAMPLE_REDDIT_VIDEO,
    SAMPLE_SOUNDCLOUD_TRACK,
    SAMPLE_TIKTOK_VIDEO,
    SAMPLE_TWITTER_VIDEO,
    SAMPLE_VIMEO_VIDEO,
    SAMPLE_YOUTUBE_VIDEO,
)


class TestYouTubeExtractor(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.extractor = YouTubeExtractor()

    def test_node_discovery(self):
        node = discover_node_runtime()
        self.assertIsNotNone(node)
        self.assertIn("node", node.lower())

    def test_youtube_node_js_runtime_config(self):
        opts = self.extractor._build_ydl_opts()
        self.assertIn("js_runtimes", opts)
        self.assertIn("node", opts["js_runtimes"])
        self.assertIn("path", opts["js_runtimes"]["node"])
        self.assertIn("extractor_args", opts)
        self.assertIn("youtube", opts["extractor_args"])

    def test_youtube_supports_url(self):
        self.assertTrue(self.extractor.supports_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ"))
        self.assertTrue(self.extractor.supports_url("https://youtu.be/dQw4w9WgXcQ"))
        self.assertTrue(self.extractor.supports_url("https://www.youtube.com/shorts/3jz_26-l58g"))
        self.assertFalse(self.extractor.supports_url("https://www.instagram.com/reel/123"))

    def test_youtube_dash_separation(self):
        meta = self.extractor._normalize_metadata(SAMPLE_YOUTUBE_VIDEO, "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        self.assertEqual(meta.id, "dQw4w9WgXcQ")
        self.assertEqual(meta.platform, Platform.YOUTUBE)
        self.assertEqual(meta.title, "Rick Astley - Never Gonna Give You Up (Official Music Video)")

        # Format 137: DASH video-only
        fmt137 = meta.get_format_by_id("137")
        self.assertIsNotNone(fmt137)
        self.assertTrue(fmt137.is_video)
        self.assertFalse(fmt137.is_audio_only)
        self.assertTrue(fmt137.needs_muxing)

        # Format 251: DASH audio-only
        fmt251 = meta.get_format_by_id("251")
        self.assertIsNotNone(fmt251)
        self.assertFalse(fmt251.is_video)
        self.assertTrue(fmt251.is_audio_only)
        self.assertFalse(fmt251.needs_muxing)

        # Format 22: Progressive
        fmt22 = meta.get_format_by_id("22")
        self.assertIsNotNone(fmt22)
        self.assertTrue(fmt22.is_video)
        self.assertFalse(fmt22.needs_muxing)

    def test_youtube_assets_and_chapters(self):
        meta = self.extractor._normalize_metadata(SAMPLE_YOUTUBE_VIDEO, "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        self.assertTrue(any(a.asset_type == "thumbnail" for a in meta.assets))
        self.assertTrue(any(a.asset_type == "subtitle" for a in meta.assets))
        self.assertIn("chapters", meta.extra_info)
        self.assertEqual(len(meta.extra_info["chapters"]), 2)

    async def test_youtube_async_extract(self):
        with patch.object(YoutubeDL, "extract_info", return_value=SAMPLE_YOUTUBE_VIDEO):
            meta = await self.extractor.extract("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
            self.assertEqual(meta.id, "dQw4w9WgXcQ")
            self.assertEqual(len(meta.formats), 3)


class TestInstagramExtractor(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.extractor = InstagramExtractor()

    def test_instagram_supports_url(self):
        self.assertTrue(self.extractor.supports_url("https://www.instagram.com/p/C_8xK19N2fQ/"))
        self.assertTrue(self.extractor.supports_url("https://www.instagram.com/reel/DA123/"))
        self.assertTrue(self.extractor.supports_url("https://ig.me/abc"))
        self.assertFalse(self.extractor.supports_url("https://www.tiktok.com/@u/video/123"))

    def test_instagram_carousel_sidecar(self):
        meta = self.extractor._normalize_carousel(
            SAMPLE_INSTAGRAM_CAROUSEL,
            SAMPLE_INSTAGRAM_CAROUSEL["entries"],
            "https://www.instagram.com/p/C_abcdef123/"
        )
        self.assertEqual(meta.platform, Platform.INSTAGRAM)
        self.assertTrue(meta.is_playlist)
        self.assertEqual(meta.playlist_count, 3)

        labels = [a.label for a in meta.assets]
        self.assertIn("slide_1", labels)
        self.assertIn("slide_2", labels)
        self.assertIn("slide_3", labels)
        self.assertEqual(len(meta.formats), 1)
        self.assertEqual(meta.formats[0].format_id, "slide_2_mp4_hd")

    async def test_instagram_auth_error_raised(self):
        with patch.object(YoutubeDL, "extract_info", side_effect=Exception("Please log in to continue")):
            with patch.object(self.extractor, "_fallback_embed_scrape", return_value=None):
                with self.assertRaises(AuthenticationRequiredError) as ctx:
                    await self.extractor.extract("https://www.instagram.com/reel/secret/")
                self.assertIn("AUTH_REQUIRED_INSTAGRAM", str(ctx.exception.error_code))

    def test_instagram_load_cookies(self):
        cookies = self.extractor.load_cookies("sessionid=fake_cookie_123; ds_user_id=456; csrftoken=token789;")
        self.assertEqual(cookies["sessionid"], "fake_cookie_123")
        self.assertEqual(cookies["ds_user_id"], "456")
        self.assertEqual(cookies["csrftoken"], "token789")
        empty_cookies = self.extractor.load_cookies("")
        self.assertEqual(empty_cookies, {})



class TestMultiPlatformExtractors(unittest.IsolatedAsyncioTestCase):
    async def test_reddit_dash_needs_muxing_flag(self):
        extractor = RedditExtractor()
        with patch.object(YoutubeDL, "extract_info", return_value=SAMPLE_REDDIT_VIDEO):
            meta = await extractor.extract("https://www.reddit.com/r/aww/comments/abc123reddit/")
            self.assertEqual(meta.platform, Platform.REDDIT)
            fmt_v = meta.get_format_by_id("dash-1080")
            self.assertIsNotNone(fmt_v)
            self.assertTrue(fmt_v.needs_muxing)
            self.assertTrue(fmt_v.is_dash)

    async def test_vimeo_referer_injected(self):
        extractor = VimeoExtractor()
        opts = extractor._build_ydl_opts()
        self.assertIn("http_headers", opts)
        self.assertIn("Referer", opts["http_headers"])

        with patch.object(YoutubeDL, "extract_info", return_value=SAMPLE_VIMEO_VIDEO):
            meta = await extractor.extract("https://vimeo.com/76979871")
            self.assertEqual(meta.platform, Platform.VIMEO)
            self.assertEqual(meta.id, "76979871")

    async def test_soundcloud_audio_normalization(self):
        extractor = SoundCloudExtractor()
        with patch.object(YoutubeDL, "extract_info", return_value=SAMPLE_SOUNDCLOUD_TRACK):
            meta = await extractor.extract("https://soundcloud.com/cool_dj/summer-vibes")
            self.assertEqual(meta.platform, Platform.SOUNDCLOUD)
            for fmt in meta.formats:
                self.assertEqual(fmt.vcodec, "none")
                self.assertTrue(fmt.is_audio_only)

    async def test_tiktok_extraction(self):
        extractor = TikTokExtractor()
        with patch.object(YoutubeDL, "extract_info", return_value=SAMPLE_TIKTOK_VIDEO):
            meta = await extractor.extract("https://www.tiktok.com/@dance_star/video/7123456789012345678")
            self.assertEqual(meta.platform, Platform.TIKTOK)
            self.assertEqual(meta.id, "7123456789012345678")

    async def test_twitter_extraction(self):
        extractor = TwitterExtractor()
        with patch.object(YoutubeDL, "extract_info", return_value=SAMPLE_TWITTER_VIDEO):
            meta = await extractor.extract("https://x.com/game_hub/status/1712345678901234567")
            self.assertEqual(meta.platform, Platform.TWITTER)
            self.assertEqual(meta.id, "1712345678901234567")

    async def test_generic_direct_file_extraction(self):
        extractor = GenericExtractor()
        url = "https://example.com/assets/intro_video.mp4"
        meta = await extractor.extract(url)
        self.assertEqual(meta.platform, Platform.GENERIC)
        self.assertEqual(meta.id, "intro_video.mp4")
        self.assertEqual(len(meta.formats), 1)
        self.assertEqual(meta.formats[0].ext, "mp4")
        self.assertEqual(meta.formats[0].url, url)

    def test_multi_platform_extractor_alias(self):
        self.assertIs(MultiPlatformExtractor, MultiExtractor)
        extractor = MultiPlatformExtractor()
        self.assertIsInstance(extractor, GenericExtractor)


class TestMediaExtractionEngine(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = MediaExtractionEngine()

    async def test_engine_router_integration(self):
        url_with_tracking = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&si=tracking123"
        with patch.object(YoutubeDL, "extract_info", return_value=SAMPLE_YOUTUBE_VIDEO):
            meta = await self.engine.extract(url_with_tracking)
            self.assertEqual(meta.platform, Platform.YOUTUBE)
            self.assertEqual(meta.id, "dQw4w9WgXcQ")

    async def test_engine_extract_info_interface_contract(self):
        with patch.object(YoutubeDL, "extract_info", return_value=SAMPLE_YOUTUBE_VIDEO):
            meta = await self.engine.extract_info(
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                cookies="chrome",
                proxy="http://127.0.0.1:8080",
            )
            self.assertEqual(meta.platform, Platform.YOUTUBE)

    async def test_engine_fallback_resilience(self):
        yt_extractor = next(e for e in self.engine.extractors if isinstance(e, YouTubeExtractor))
        with patch.object(yt_extractor, "extract", side_effect=Exception("Unexpected scraper fault")):
            with patch.object(YoutubeDL, "extract_info", return_value=SAMPLE_YOUTUBE_VIDEO):
                meta = await self.engine.extract(
                    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                    options=ExtractionOptions(allow_fallbacks=True)
                )
                self.assertIsNotNone(meta)

    def test_media_extraction_service_alias(self):
        self.assertIs(MediaExtractionService, MediaExtractionEngine)
        service = MediaExtractionService()
        self.assertIsInstance(service, MediaExtractionEngine)



if __name__ == "__main__":
    unittest.main()
