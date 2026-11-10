"""Unit tests for URL Router, Sanitizer, and Shortlink Expander.

File: tests/unit/test_router.py
"""
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock, patch

src_path = str(Path(__file__).resolve().parent.parent.parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

import httpx

from linkconv.core.exceptions import InvalidUrlError, UnsupportedPlatformError
from linkconv.core.models import Platform
from linkconv.core.router import RouteResult, UrlRouterService


class TestUrlRouterService(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.router = UrlRouterService(http_timeout=2.0, max_redirects=10)

    # ---------------------------------------------------------
    # 1. YouTube Tests
    # ---------------------------------------------------------
    def test_yt_watch(self):
        platform, media_id = self.router.resolve_platform("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        self.assertEqual(platform, Platform.YOUTUBE)
        self.assertEqual(media_id, "dQw4w9WgXcQ")

    def test_yt_shortlink(self):
        platform, media_id = self.router.resolve_platform("https://youtu.be/dQw4w9WgXcQ")
        self.assertEqual(platform, Platform.YOUTUBE)
        self.assertEqual(media_id, "dQw4w9WgXcQ")

    def test_yt_shorts(self):
        platform, media_id = self.router.resolve_platform("https://www.youtube.com/shorts/3jz_26-l58g")
        self.assertEqual(platform, Platform.YOUTUBE)
        self.assertEqual(media_id, "3jz_26-l58g")

    def test_yt_music(self):
        platform, media_id = self.router.resolve_platform("https://music.youtube.com/watch?v=dQw4w9WgXcQ")
        self.assertEqual(platform, Platform.YOUTUBE)
        self.assertEqual(media_id, "dQw4w9WgXcQ")

    def test_yt_embed(self):
        platform, media_id = self.router.resolve_platform("https://www.youtube.com/embed/dQw4w9WgXcQ")
        self.assertEqual(platform, Platform.YOUTUBE)
        self.assertEqual(media_id, "dQw4w9WgXcQ")

    def test_yt_live(self):
        platform, media_id = self.router.resolve_platform("https://www.youtube.com/live/jfKfPfyJRdk")
        self.assertEqual(platform, Platform.YOUTUBE)
        self.assertEqual(media_id, "jfKfPfyJRdk")

    def test_yt_timestamp(self):
        sanitized = self.router.sanitize("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=120s")
        self.assertIn("t=120s", sanitized)
        platform, media_id = self.router.resolve_platform(sanitized)
        self.assertEqual(platform, Platform.YOUTUBE)
        self.assertEqual(media_id, "dQw4w9WgXcQ")

    def test_yt_playlist_item(self):
        sanitized = self.router.sanitize("https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PL12345&index=2")
        self.assertIn("list=PL12345", sanitized)
        self.assertIn("index=2", sanitized)
        platform, media_id = self.router.resolve_platform(sanitized)
        self.assertEqual(platform, Platform.YOUTUBE)
        self.assertEqual(media_id, "dQw4w9WgXcQ")

    def test_yt_pure_playlist(self):
        platform, media_id = self.router.resolve_platform("https://www.youtube.com/playlist?list=PL1234567890")
        self.assertEqual(platform, Platform.YOUTUBE)
        self.assertEqual(media_id, "PL1234567890")

    def test_yt_handle(self):
        platform, media_id = self.router.resolve_platform("https://www.youtube.com/@rickastley")
        self.assertEqual(platform, Platform.YOUTUBE)
        self.assertEqual(media_id, "rickastley")

    def test_yt_channel_id(self):
        platform, media_id = self.router.resolve_platform("https://www.youtube.com/channel/UCuAXFkgsw1L7xaCfnd5JJOw")
        self.assertEqual(platform, Platform.YOUTUBE)
        self.assertEqual(media_id, "UCuAXFkgsw1L7xaCfnd5JJOw")

    def test_yt_tracking_strip(self):
        sanitized = self.router.sanitize("https://youtu.be/dQw4w9WgXcQ?si=tracking123&feature=share")
        self.assertNotIn("si=", sanitized)
        self.assertNotIn("feature=", sanitized)
        self.assertEqual(sanitized, "https://youtu.be/dQw4w9WgXcQ")

    # ---------------------------------------------------------
    # 2. Instagram Tests
    # ---------------------------------------------------------
    def test_ig_post(self):
        platform, media_id = self.router.resolve_platform("https://www.instagram.com/p/C_8xK19N2fQ/")
        self.assertEqual(platform, Platform.INSTAGRAM)
        self.assertEqual(media_id, "C_8xK19N2fQ")

    def test_ig_reel(self):
        platform, media_id = self.router.resolve_platform("https://www.instagram.com/reel/DA12345xyz/")
        self.assertEqual(platform, Platform.INSTAGRAM)
        self.assertEqual(media_id, "DA12345xyz")

    def test_ig_reels_plural(self):
        platform, media_id = self.router.resolve_platform("https://www.instagram.com/reels/DA12345xyz/")
        self.assertEqual(platform, Platform.INSTAGRAM)
        self.assertEqual(media_id, "DA12345xyz")

    def test_ig_tv(self):
        platform, media_id = self.router.resolve_platform("https://www.instagram.com/tv/B_xyz123/")
        self.assertEqual(platform, Platform.INSTAGRAM)
        self.assertEqual(media_id, "B_xyz123")

    def test_ig_story(self):
        platform, media_id = self.router.resolve_platform("https://www.instagram.com/stories/taylorswift/3123456789012345678/")
        self.assertEqual(platform, Platform.INSTAGRAM)
        self.assertEqual(media_id, "taylorswift/3123456789012345678")

    def test_ig_share(self):
        platform, media_id = self.router.resolve_platform("https://www.instagram.com/share/p/C_8xK19N2fQ/")
        self.assertEqual(platform, Platform.INSTAGRAM)
        self.assertEqual(media_id, "C_8xK19N2fQ")

    def test_ig_shortlink(self):
        platform, media_id = self.router.resolve_platform("https://ig.me/C_8xK19N2fQ")
        self.assertEqual(platform, Platform.INSTAGRAM)
        self.assertEqual(media_id, "C_8xK19N2fQ")

    def test_ig_tracking_strip(self):
        sanitized = self.router.sanitize("https://www.instagram.com/reel/C_8xK19N2fQ/?igsh=token123&utm_medium=social")
        self.assertNotIn("igsh=", sanitized)
        self.assertNotIn("utm_medium=", sanitized)
        self.assertEqual(sanitized, "https://www.instagram.com/reel/C_8xK19N2fQ/")

    # ---------------------------------------------------------
    # 3. TikTok Tests
    # ---------------------------------------------------------
    def test_tt_video(self):
        platform, media_id = self.router.resolve_platform("https://www.tiktok.com/@khaby.lame/video/7123456789012345678")
        self.assertEqual(platform, Platform.TIKTOK)
        self.assertEqual(media_id, "7123456789012345678")

    def test_tt_photo(self):
        platform, media_id = self.router.resolve_platform("https://www.tiktok.com/@user/photo/7123456789012345678")
        self.assertEqual(platform, Platform.TIKTOK)
        self.assertEqual(media_id, "7123456789012345678")

    def test_tt_web(self):
        platform, media_id = self.router.resolve_platform("https://www.tiktok.com/v/7123456789012345678.html")
        self.assertEqual(platform, Platform.TIKTOK)
        self.assertEqual(media_id, "7123456789012345678")

    def test_tt_vm_shortlink(self):
        platform, media_id = self.router.resolve_platform("https://vm.tiktok.com/ZM8xy123/")
        self.assertEqual(platform, Platform.TIKTOK)
        self.assertEqual(media_id, "ZM8xy123")

    def test_tt_vt_shortlink(self):
        platform, media_id = self.router.resolve_platform("https://vt.tiktok.com/ZS8ab456/")
        self.assertEqual(platform, Platform.TIKTOK)
        self.assertEqual(media_id, "ZS8ab456")

    def test_tt_tracking_strip(self):
        sanitized = self.router.sanitize("https://www.tiktok.com/@u/video/123?share_id=1&is_copy_url=1&sender_device=pc")
        self.assertNotIn("share_id=", sanitized)
        self.assertNotIn("is_copy_url=", sanitized)
        self.assertNotIn("sender_device=", sanitized)
        self.assertEqual(sanitized, "https://www.tiktok.com/@u/video/123")

    # ---------------------------------------------------------
    # 4. Twitter / X Tests
    # ---------------------------------------------------------
    def test_tw_status(self):
        platform, media_id = self.router.resolve_platform("https://twitter.com/jack/status/20")
        self.assertEqual(platform, Platform.TWITTER)
        self.assertEqual(media_id, "20")

    def test_x_status(self):
        platform, media_id = self.router.resolve_platform("https://x.com/elonmusk/status/1712345678901234567")
        self.assertEqual(platform, Platform.TWITTER)
        self.assertEqual(media_id, "1712345678901234567")

    def test_tw_mobile(self):
        platform, media_id = self.router.resolve_platform("https://mobile.twitter.com/user/status/12345")
        self.assertEqual(platform, Platform.TWITTER)
        self.assertEqual(media_id, "12345")

    def test_tw_shortlink(self):
        platform, media_id = self.router.resolve_platform("https://t.co/abcXYZ123")
        self.assertEqual(platform, Platform.TWITTER)
        self.assertEqual(media_id, "abcXYZ123")

    def test_tw_tracking_strip(self):
        sanitized = self.router.sanitize("https://x.com/user/status/12345?ref_src=twsrc%5Etfw&s=20&t=7h8j")
        self.assertNotIn("ref_src=", sanitized)
        self.assertNotIn("s=", sanitized)
        self.assertNotIn("t=", sanitized)
        self.assertEqual(sanitized, "https://x.com/user/status/12345")

    # ---------------------------------------------------------
    # 5. Facebook Tests
    # ---------------------------------------------------------
    def test_fb_watch(self):
        platform, media_id = self.router.resolve_platform("https://www.facebook.com/watch/?v=10158273645")
        self.assertEqual(platform, Platform.FACEBOOK)
        self.assertEqual(media_id, "10158273645")

    def test_fb_video(self):
        platform, media_id = self.router.resolve_platform("https://www.facebook.com/natgeo/videos/9876543210/")
        self.assertEqual(platform, Platform.FACEBOOK)
        self.assertEqual(media_id, "9876543210")

    def test_fb_reel(self):
        platform, media_id = self.router.resolve_platform("https://www.facebook.com/reel/123456789012345")
        self.assertEqual(platform, Platform.FACEBOOK)
        self.assertEqual(media_id, "123456789012345")

    def test_fb_shortlink(self):
        platform, media_id = self.router.resolve_platform("https://fb.watch/abc123xyz/")
        self.assertEqual(platform, Platform.FACEBOOK)
        self.assertEqual(media_id, "abc123xyz")

    def test_fb_tracking_strip(self):
        sanitized = self.router.sanitize("https://www.facebook.com/watch/?v=12345&fbclid=IwAR12345&mibextid=abc")
        self.assertNotIn("fbclid=", sanitized)
        self.assertNotIn("mibextid=", sanitized)
        self.assertIn("v=12345", sanitized)

    # ---------------------------------------------------------
    # 6. Reddit Tests
    # ---------------------------------------------------------
    def test_reddit_post(self):
        platform, media_id = self.router.resolve_platform("https://www.reddit.com/r/funny/comments/18xyzab/funny_cat_video/")
        self.assertEqual(platform, Platform.REDDIT)
        self.assertEqual(media_id, "18xyzab")

    def test_reddit_shortlink(self):
        platform, media_id = self.router.resolve_platform("https://redd.it/18xyzab")
        self.assertEqual(platform, Platform.REDDIT)
        self.assertEqual(media_id, "18xyzab")

    def test_reddit_v_redd_it(self):
        platform, media_id = self.router.resolve_platform("https://v.redd.it/abcdef123456")
        self.assertEqual(platform, Platform.REDDIT)
        self.assertEqual(media_id, "abcdef123456")

    # ---------------------------------------------------------
    # 7. Pinterest Tests
    # ---------------------------------------------------------
    def test_pin_standard(self):
        platform, media_id = self.router.resolve_platform("https://www.pinterest.com/pin/893683119041234567/")
        self.assertEqual(platform, Platform.PINTEREST)
        self.assertEqual(media_id, "893683119041234567")

    def test_pin_regional(self):
        platform, media_id = self.router.resolve_platform("https://in.pinterest.com/pin/893683119041234567/")
        self.assertEqual(platform, Platform.PINTEREST)
        self.assertEqual(media_id, "893683119041234567")

    def test_pin_shortlink(self):
        platform, media_id = self.router.resolve_platform("https://pin.it/7dF3g9H")
        self.assertEqual(platform, Platform.PINTEREST)
        self.assertEqual(media_id, "7dF3g9H")

    # ---------------------------------------------------------
    # 8. Vimeo Tests
    # ---------------------------------------------------------
    def test_vimeo_standard(self):
        platform, media_id = self.router.resolve_platform("https://vimeo.com/76979871")
        self.assertEqual(platform, Platform.VIMEO)
        self.assertEqual(media_id, "76979871")

    def test_vimeo_unlisted_path(self):
        platform, media_id = self.router.resolve_platform("https://vimeo.com/76979871/abcdef1234")
        self.assertEqual(platform, Platform.VIMEO)
        self.assertEqual(media_id, "76979871:abcdef1234")

    def test_vimeo_unlisted_query(self):
        platform, media_id = self.router.resolve_platform("https://vimeo.com/76979871?h=abcdef1234")
        self.assertEqual(platform, Platform.VIMEO)
        self.assertEqual(media_id, "76979871:abcdef1234")

    # ---------------------------------------------------------
    # 9. SoundCloud Tests
    # ---------------------------------------------------------
    def test_sc_track(self):
        platform, media_id = self.router.resolve_platform("https://soundcloud.com/artist-name/track-title")
        self.assertEqual(platform, Platform.SOUNDCLOUD)
        self.assertEqual(media_id, "artist-name/track-title")

    def test_sc_set(self):
        platform, media_id = self.router.resolve_platform("https://soundcloud.com/artist-name/sets/album-title")
        self.assertEqual(platform, Platform.SOUNDCLOUD)
        self.assertEqual(media_id, "artist-name/sets/album-title")

    def test_sc_shortlink(self):
        platform, media_id = self.router.resolve_platform("https://on.soundcloud.com/12345")
        self.assertEqual(platform, Platform.SOUNDCLOUD)
        self.assertEqual(media_id, "12345")

    # ---------------------------------------------------------
    # 10. Generic HTML5 Tests
    # ---------------------------------------------------------
    def test_generic_direct_mp4(self):
        platform, media_id = self.router.resolve_platform("https://example.com/videos/sample.mp4?token=abc")
        self.assertEqual(platform, Platform.GENERIC)
        self.assertEqual(media_id, "sample.mp4")

    def test_generic_hls_m3u8(self):
        platform, media_id = self.router.resolve_platform("https://stream.example.com/live/playlist.m3u8")
        self.assertEqual(platform, Platform.GENERIC)
        self.assertEqual(media_id, "playlist.m3u8")

    # ---------------------------------------------------------
    # 11. Edge cases & Sanitization
    # ---------------------------------------------------------
    def test_whitespace_normalization(self):
        platform, media_id = self.router.resolve_platform("  \n  https://youtu.be/dQw4w9WgXcQ  \t ")
        self.assertEqual(platform, Platform.YOUTUBE)
        self.assertEqual(media_id, "dQw4w9WgXcQ")

    def test_unsupported_scheme(self):
        with self.assertRaises(InvalidUrlError):
            self.router.sanitize("file:///etc/passwd")

        with self.assertRaises(InvalidUrlError):
            self.router.sanitize("javascript:alert(1)")

    def test_empty_or_malformed_url(self):
        with self.assertRaises(InvalidUrlError):
            self.router.sanitize("")
        with self.assertRaises(InvalidUrlError):
            self.router.sanitize("   ")
        with self.assertRaises(InvalidUrlError):
            self.router.sanitize(None)  # type: ignore

    # ---------------------------------------------------------
    # 12. Async Shortlink Expansion & Security Tests
    # ---------------------------------------------------------
    async def test_expand_non_shortlink_returns_immediately(self):
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        expanded = await self.router.expand(url)
        self.assertEqual(expanded, url)

    async def test_expand_successful_redirect(self):
        short_url = "https://bit.ly/3sample"
        target_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

        mock_resp1 = httpx.Response(301, headers={"Location": target_url})
        mock_resp2 = httpx.Response(200)
        with patch.object(httpx.AsyncClient, "head", new_callable=AsyncMock) as mock_head:
            mock_head.side_effect = [mock_resp1, mock_resp2]
            expanded = await self.router.expand(short_url)
            self.assertEqual(expanded, target_url)

    async def test_expand_redirect_loop(self):
        url1 = "https://bit.ly/loop1"
        url2 = "https://bit.ly/loop2"

        mock_resp1 = httpx.Response(301, headers={"Location": url2})
        mock_resp2 = httpx.Response(301, headers={"Location": url1})

        with patch.object(httpx.AsyncClient, "head", new_callable=AsyncMock) as mock_head:
            mock_head.side_effect = [mock_resp1, mock_resp2]
            with self.assertRaises(InvalidUrlError) as ctx:
                await self.router.expand(url1)
            self.assertIn("Redirect loop detected", str(ctx.exception))

    async def test_expand_max_redirects_exceeded(self):
        def make_resp(hop):
            return httpx.Response(301, headers={"Location": f"https://bit.ly/hop{hop}"})

        resps = [make_resp(i) for i in range(1, 15)]
        with patch.object(httpx.AsyncClient, "head", new_callable=AsyncMock) as mock_head:
            mock_head.side_effect = resps
            with self.assertRaises(InvalidUrlError) as ctx:
                await self.router.expand("https://bit.ly/hop0")
            self.assertIn("Maximum redirect hops", str(ctx.exception))

    async def test_expand_ssrf_protection(self):
        with patch.object(self.router, "_is_ip_safe", return_value=False):
            with self.assertRaises(InvalidUrlError) as ctx:
                await self.router.expand("https://bit.ly/evil_internal")
            self.assertIn("Access to private/local network address", str(ctx.exception))

    # ---------------------------------------------------------
    # 13. Canonical URLs & Route Pipeline
    # ---------------------------------------------------------
    def test_canonical_urls(self):
        self.assertEqual(
            self.router.get_canonical_url(Platform.YOUTUBE, "dQw4w9WgXcQ"),
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        )
        self.assertEqual(
            self.router.get_canonical_url(Platform.YOUTUBE, "PL12345"),
            "https://www.youtube.com/playlist?list=PL12345"
        )
        self.assertEqual(
            self.router.get_canonical_url(Platform.INSTAGRAM, "C_8xK19N2fQ"),
            "https://www.instagram.com/p/C_8xK19N2fQ/"
        )
        self.assertEqual(
            self.router.get_canonical_url(Platform.TIKTOK, "7123456789"),
            "https://www.tiktok.com/@i/video/7123456789"
        )
        self.assertEqual(
            self.router.get_canonical_url(Platform.TWITTER, "123456789"),
            "https://x.com/i/status/123456789"
        )
        self.assertEqual(
            self.router.get_canonical_url(Platform.VIMEO, "76979871:abcdef"),
            "https://vimeo.com/76979871/abcdef"
        )

    async def test_route_unified_pipeline(self):
        input_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&si=tracking&t=60s"
        res = await self.router.route(input_url)
        self.assertIsInstance(res, RouteResult)
        self.assertEqual(res.platform, Platform.YOUTUBE)
        self.assertEqual(res.media_id, "dQw4w9WgXcQ")
        self.assertEqual(res.canonical_url, "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        self.assertNotIn("si=", res.sanitized_url)
        self.assertIn("t=60s", res.sanitized_url)
        self.assertEqual(res.functional_params.get("t"), "60s")

    def test_reddit_uppercase_and_subreddits(self):
        platform, media_id = self.router.resolve_platform("https://www.reddit.com/r/funny/comments/123AbC/funny_cat_video/")
        self.assertEqual(platform, Platform.REDDIT)
        self.assertEqual(media_id, "123AbC")

        platform, media_id = self.router.resolve_platform("https://redd.it/123AbC")
        self.assertEqual(platform, Platform.REDDIT)
        self.assertEqual(media_id, "123AbC")

        platform, media_id = self.router.resolve_platform("https://www.reddit.com/gallery/123AbC")
        self.assertEqual(platform, Platform.REDDIT)
        self.assertEqual(media_id, "123AbC")

    def test_canonical_channels_and_stories(self):
        canonical_yt_handle = self.router.get_canonical_url(Platform.YOUTUBE, "rickastley", "https://www.youtube.com/@rickastley")
        self.assertEqual(canonical_yt_handle, "https://www.youtube.com/@rickastley")

        canonical_yt_chan = self.router.get_canonical_url(Platform.YOUTUBE, "UCuAXFkgsw1L7xaCfnd5JJOw")
        self.assertEqual(canonical_yt_chan, "https://www.youtube.com/channel/UCuAXFkgsw1L7xaCfnd5JJOw")

        canonical_ig_story = self.router.get_canonical_url(Platform.INSTAGRAM, "taylorswift/3123456789012345678")
        self.assertEqual(canonical_ig_story, "https://www.instagram.com/stories/taylorswift/3123456789012345678/")

    def test_platform_fallthrough_rejection(self):
        with self.assertRaises(InvalidUrlError):
            self.router.resolve_platform("https://www.youtube.com/watch?")

        with self.assertRaises(InvalidUrlError):
            self.router.resolve_platform("https://www.instagram.com/reel//")

        with self.assertRaises(InvalidUrlError):
            self.router.resolve_platform("https://www.reddit.com/r/videos/comments/")

    def test_plain_text_rejected(self):
        with self.assertRaises(InvalidUrlError):
            self.router.resolve_platform("not a valid media url at all")

    async def test_direct_ssrf_protection_in_route(self):
        strict_router = UrlRouterService(allow_private_ips=False, allow_local=False)
        with self.assertRaises(InvalidUrlError) as ctx:
            await strict_router.route("http://192.168.1.1:8000/private_stream.mp4")
        self.assertIn("Access to private/local network address", str(ctx.exception))

    def test_is_canonical(self):
        self.assertTrue(self.router.is_canonical("https://www.youtube.com/watch?v=dQw4w9WgXcQ"))
        self.assertTrue(self.router.is_canonical("https://www.instagram.com/reel/C-j527BStv_/"))
        self.assertTrue(self.router.is_canonical("https://example.com/stream.mp4"))
        self.assertFalse(self.router.is_canonical("https://youtu.be/dQw4w9WgXcQ"))
        self.assertFalse(self.router.is_canonical("https://bit.ly/3sample"))


if __name__ == "__main__":
    unittest.main()

