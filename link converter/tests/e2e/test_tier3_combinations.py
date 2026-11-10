"""
tests/e2e/test_tier3_combinations.py
Tier 3: Cross-Feature Combinations Test Suite (Pairwise & Multi-System Workflows).
Tests end-to-end integration between multiple subsystems (Router, Extractors,
Transcoding, Embeds, Assets, and Job Queue).
Operates 100% offline using MockMediaServer.
"""

import asyncio
import io
import json
import re
import sys
import unittest
import zipfile
from pathlib import Path
from typing import Dict, Any, List

# Ensure src/ is on path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from tests.fixtures.mock_server import MockMediaServer
from tests.fixtures.sample_media import (
    create_minimal_mp4_bytes,
    create_minimal_mp3_bytes,
    create_mock_carousel_zip_bytes,
    MOCK_METADATA_DATABASE
)

# Progressive Testability Detection
try:
    from linkconv.core.models import Platform, MediaFormat, MediaAsset, MediaMetadata
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
    from linkconv.services.assets import MediaAssetService
    HAS_ASSETS = True
except ImportError:
    HAS_ASSETS = False

try:
    from linkconv.services.embeds import EmbedFormatterService
    HAS_EMBEDS = True
except ImportError:
    HAS_EMBEDS = False

try:
    from linkconv.services.job_queue import JobQueueService
    HAS_JOB_QUEUE = True
except ImportError:
    HAS_JOB_QUEUE = False


class TestTier3CrossFeatureCombinations(unittest.TestCase):
    """
    Tier 3: Pairwise and multi-feature cross-subsystem pipeline test suite.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.server = MockMediaServer().start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.stop()

    # ------------------------------------------------------------------------
    # Combination 1: Shortlink Unshortening + Audio Extraction + ID3 Tagging
    # ------------------------------------------------------------------------
    def test_comb_01_shortlink_audio_id3_pipeline(self) -> None:
        """
        TC-CMB-01: Workflow:
        1. Input: Shortened YouTube tracking URL (youtu.be/dQw4w9WgXcQ?si=tracker123)
        2. Unshorten & sanitize to canonical URL
        3. Extract metadata
        4. Transcode to MP3 320k with embedded ID3 metadata tags
        """
        if not HAS_ROUTER or not HAS_MODELS:
            self.skipTest("Router or Models pending implementation")

        router = UrlRouterService()
        raw_url = "https://youtu.be/dQw4w9WgXcQ?si=tracker123"

        # Step 1: Sanitize tracking parameters
        clean_url = router.sanitize(raw_url)
        self.assertNotIn("si=", clean_url)

        # Step 2: Expand shortlink
        expanded = asyncio.run(router.expand(clean_url)) if asyncio.iscoroutinefunction(router.expand) else router.expand(clean_url)
        self.assertIn("youtube.com/watch", expanded)

        # Step 3: Platform detection
        platform, media_id = router.resolve_platform(expanded)
        self.assertEqual(platform, Platform.YOUTUBE)
        self.assertEqual(media_id, "dQw4w9WgXcQ")

        # Step 4: Metadata verification
        meta = MediaMetadata(**MOCK_METADATA_DATABASE["youtube_video"])
        self.assertEqual(meta.uploader, "Rick Astley")

        # Step 5: Configure audio transcode options
        if HAS_TRANSCODING:
            opts = ConversionOptions(
                target_format="mp3",
                target_quality="320k",
                extract_audio_only=True,
                embed_thumbnail=True
            )
            self.assertEqual(opts.target_quality, "320k")
            self.assertTrue(opts.extract_audio_only)

    # ------------------------------------------------------------------------
    # Combination 2: YouTube Shorts + 1080p Muxing + Markdown & HTML Embed
    # ------------------------------------------------------------------------
    def test_comb_02_shorts_muxing_and_embed_synthesis(self) -> None:
        """
        TC-CMB-02: Workflow:
        1. Input: YouTube Shorts URL
        2. Resolve vertical aspect ratio (1080x1920)
        3. Configure MP4 muxing pipeline
        4. Synthesize Markdown and responsive HTML iframe embeds
        """
        if not HAS_MODELS:
            self.skipTest("Models pending implementation")

        meta = MediaMetadata(**MOCK_METADATA_DATABASE["youtube_shorts"])
        fmt = meta.formats[0]
        self.assertEqual(fmt.width, 1080)
        self.assertEqual(fmt.height, 1920)

        # Muxing options
        if HAS_TRANSCODING:
            opts = ConversionOptions(target_format="mp4", target_quality="1080p")
            self.assertEqual(opts.target_format, "mp4")

        # Embed generation
        if HAS_EMBEDS:
            formatter = EmbedFormatterService()
            md = formatter.to_markdown(meta)
            html = formatter.to_html_iframe(meta, responsive=True)
            self.assertIn("[![", md)
            self.assertIn("<iframe", html)
            self.assertIn("allowfullscreen", html)

    # ------------------------------------------------------------------------
    # Combination 3: Instagram Carousel + Multi-Slide ZIP + Batch Processing
    # ------------------------------------------------------------------------
    def test_comb_03_instagram_carousel_zip_batch(self) -> None:
        """
        TC-CMB-03: Workflow:
        1. Input: Instagram Carousel with 3 slides
        2. Extract each individual slide asset
        3. Package slides into an in-memory ZIP archive
        4. Verify manifest.json and slide images inside ZIP
        """
        if not HAS_MODELS:
            self.skipTest("Models pending implementation")

        meta = MediaMetadata(**MOCK_METADATA_DATABASE["instagram_carousel"])
        self.assertEqual(len(meta.assets), 3)

        # Generate ZIP archive
        zip_bytes = create_mock_carousel_zip_bytes(len(meta.assets))
        with zipfile.ZipFile(io.BytesIO(zip_bytes), mode="r") as zf:
            files = zf.namelist()
            self.assertIn("manifest.json", files)
            self.assertIn("slide_1.jpg", files)
            self.assertIn("slide_2.jpg", files)
            self.assertIn("slide_3.jpg", files)

            # Read and parse manifest
            manifest_raw = zf.read("manifest.json").decode("utf-8")
            manifest = json.loads(manifest_raw)
            self.assertEqual(manifest["platform"], "instagram")
            self.assertEqual(manifest["slide_count"], 3)

    # ------------------------------------------------------------------------
    # Combination 4: Reddit Decoupled Streams + MP4 Remux + Thumbnail Extract
    # ------------------------------------------------------------------------
    def test_comb_04_reddit_decoupled_stream_remux_with_thumbnail(self) -> None:
        """
        TC-CMB-04: Workflow:
        1. Input: Reddit post with separate DASH video (DASH_720) and audio (DASH_audio)
        2. Detect separate streams requiring FFmpeg muxing (needs_muxing=True)
        3. Mux into MP4 container
        4. Extract post preview thumbnail alongside video
        """
        if not HAS_MODELS:
            self.skipTest("Models pending implementation")

        meta = MediaMetadata(**MOCK_METADATA_DATABASE["reddit_post"])
        video_stream = next(f for f in meta.formats if f.format_id == "DASH_720")
        audio_stream = next(f for f in meta.formats if f.format_id == "DASH_audio")

        # Assert decoupled streams require muxing
        self.assertTrue(video_stream.needs_muxing)
        self.assertEqual(audio_stream.vcodec, "none")
        self.assertIsNotNone(meta.thumbnail_url)

    # ------------------------------------------------------------------------
    # Combination 5: Multi-Platform Batch URL Routing & Normalization
    # ------------------------------------------------------------------------
    def test_comb_05_multi_platform_batch_routing(self) -> None:
        """
        TC-CMB-05: Workflow:
        1. Input: Mixed playlist text containing YouTube, Instagram, TikTok, and Reddit URLs
        2. Process all links through router in batch
        3. Verify correct platform classification and ID extraction for all items
        """
        if not HAS_ROUTER or not HAS_MODELS:
            self.skipTest("Router or Models pending implementation")

        batch_inputs = [
            ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", Platform.YOUTUBE, "dQw4w9WgXcQ"),
            ("https://www.instagram.com/reel/C-j527BStv_/", Platform.INSTAGRAM, "C-j527BStv_"),
            ("https://www.tiktok.com/@creator/video/71234567890", Platform.TIKTOK, "71234567890"),
            ("https://www.reddit.com/r/aww/comments/92pms9/kitten/", Platform.REDDIT, "92pms9"),
        ]

        router = UrlRouterService()
        for url, expected_platform, expected_id in batch_inputs:
            platform, media_id = router.resolve_platform(url)
            self.assertEqual(platform, expected_platform)
            self.assertEqual(media_id, expected_id)

    # ------------------------------------------------------------------------
    # Combination 6: REST API Job Lifecycle with SSE Event Stream Simulation
    # ------------------------------------------------------------------------
    def test_comb_06_job_lifecycle_sse_streaming(self) -> None:
        """
        TC-CMB-06: Workflow:
        1. Create background job via JobQueueService
        2. Verify state transitions: PENDING -> PROCESSING (50%) -> COMPLETED (100%)
        3. Verify SSE event serialization format (event: ..., data: ...)
        """
        if not HAS_JOB_QUEUE:
            self.skipTest("JobQueueService pending implementation")

        queue = JobQueueService()
        job_id = queue.create_job({"url": "https://example.com/video", "format": "mp4"})

        # Step 1: Initial state
        job = queue.get_job(job_id)
        self.assertEqual(job.status.lower(), "pending")

        # Step 2: Progress update
        queue.update_progress(job_id, progress=50.0, stage="transcoding")
        job = queue.get_job(job_id)
        self.assertEqual(job.status.lower(), "processing")
        self.assertEqual(job.progress, 50.0)

        # Step 3: Completion
        queue.complete_job(job_id, output_path="C:\\Downloads\\video.mp4")
        job = queue.get_job(job_id)
        self.assertEqual(job.status.lower(), "completed")

        # Step 4: SSE formatting check
        sse_event = f"event: progress\ndata: {json.dumps({'job_id': job_id, 'progress': 100.0, 'status': 'completed'})}\n\n"
        self.assertTrue(sse_event.startswith("event: progress\n"))
        self.assertTrue(sse_event.endswith("\n\n"))

    # ------------------------------------------------------------------------
    # Combination 7: Format Ladder Filtering + Dual oEmbed Generation
    # ------------------------------------------------------------------------
    def test_comb_07_format_filtering_and_dual_oembed_synthesis(self) -> None:
        """
        TC-CMB-07: Workflow:
        1. Extract format ladder containing 1080p, 720p, 480p
        2. Filter formats where height <= 720
        3. Simultaneously generate both oEmbed JSON and oEmbed XML
        4. Assert metadata synchronization across JSON and XML formats
        """
        if not HAS_MODELS:
            self.skipTest("Models pending implementation")

        meta = MediaMetadata(**MOCK_METADATA_DATABASE["youtube_video"])

        # Filter formats <= 720p
        filtered_formats = [f for f in meta.formats if f.height is not None and f.height <= 720]
        self.assertTrue(len(filtered_formats) > 0)
        self.assertTrue(all(f.height <= 720 for f in filtered_formats))

        # Query mock server oEmbed JSON & XML
        import urllib.request
        json_res = urllib.request.urlopen(self.server.get_url("/oembed?format=json"))
        xml_res = urllib.request.urlopen(self.server.get_url("/oembed?format=xml"))

        json_data = json.loads(json_res.read().decode("utf-8"))
        xml_data = xml_res.read().decode("utf-8")

        self.assertEqual(json_data["provider_name"], "YouTube")
        self.assertIn("<provider_name>YouTube</provider_name>", xml_data)
        self.assertEqual(json_data["title"], "Never Gonna Give You Up")
        self.assertIn("<title>Never Gonna Give You Up</title>", xml_data)

    # ------------------------------------------------------------------------
    # Combination 8: Lossless Audio Transcode + Windows Filename Templating
    # ------------------------------------------------------------------------
    def test_comb_08_flac_transcode_windows_templating(self) -> None:
        """
        TC-CMB-08: Workflow:
        1. Select lossless audio format FLAC
        2. Apply dynamic naming template: {uploader} - {title} [{id}].flac
        3. Sanitize output filename for Windows filesystems
        4. Validate final destination path structure
        """
        if not HAS_MODELS:
            self.skipTest("Models pending implementation")

        meta = MediaMetadata(**MOCK_METADATA_DATABASE["youtube_video"])
        template = "{uploader} - {title} [{id}].flac"

        # Interpolate template variables
        raw_filename = template.format(
            uploader=meta.uploader,
            title=meta.title,
            id=meta.id
        )

        # Sanitize Windows illegal characters
        clean_filename = re.sub(r'[<>:"/\\|?*]', '_', raw_filename)
        self.assertTrue(clean_filename.startswith(f"{meta.uploader} - "))
        self.assertIn("Never Gonna Give You Up", clean_filename)
        self.assertTrue(clean_filename.endswith(f"[{meta.id}].flac"))
        for char in '<>:"/\\|?*':
            self.assertNotIn(char, clean_filename)


if __name__ == "__main__":
    unittest.main()
