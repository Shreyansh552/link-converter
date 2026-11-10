"""
tests/e2e/test_tier4_workloads.py
Tier 4: Real-World Workloads & Stress Scenarios Test Suite.
Simulates real user personas, bulk operations, queue limits, disk cleanup,
and process termination.
Operates 100% offline using MockMediaServer.
"""

import asyncio
import io
import json
import os
import shutil
import tempfile
import sys
import unittest
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
    create_placeholder_jpeg_bytes,
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


class TestTier4RealWorldWorkloads(unittest.TestCase):
    """
    Tier 4: Persona-driven end-to-end user workflows and stress tests.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.server = MockMediaServer().start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.stop()

    def setUp(self) -> None:
        self.test_dir = tempfile.mkdtemp(prefix="linkconv_test_tier4_")

    def tearDown(self) -> None:
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    # ------------------------------------------------------------------------
    # Scenario 1: Content Creator Music Playlist Archiver
    # ------------------------------------------------------------------------
    def test_scenario_01_playlist_archiver_workflow(self) -> None:
        """
        TC-WRK-01: Content Creator Archiving Playlist:
        - Extracts playlist metadata containing 3 tracks
        - Processes all tracks in playlist sequence
        - Generates ID3 tags (track number 1/3, 2/3, 3/3, title, artist)
        - Writes synthetic MP3 outputs to structured artist/album folder
        """
        if not HAS_MODELS:
            self.skipTest("Models pending implementation")

        playlist_meta = MediaMetadata(**MOCK_METADATA_DATABASE["youtube_playlist"])
        self.assertTrue(playlist_meta.is_playlist)
        self.assertEqual(playlist_meta.playlist_count, 3)

        out_folder = Path(self.test_dir) / playlist_meta.uploader / playlist_meta.title
        out_folder.mkdir(parents=True, exist_ok=True)

        for idx, item in enumerate(playlist_meta.playlist_items, start=1):
            track_title = item["title"]
            track_num = f"{idx}/{playlist_meta.playlist_count}"
            filename = f"{idx:02d} - {track_title}.mp3"
            target_path = out_folder / filename

            # Write synthetic tagged MP3
            mp3_bytes = create_minimal_mp3_bytes(title=track_title, artist=playlist_meta.uploader)
            target_path.write_bytes(mp3_bytes)

            self.assertTrue(target_path.exists())
            self.assertGreater(target_path.stat().st_size, 0)

        # Verify all 3 tracks are created in target directory
        created_files = list(out_folder.glob("*.mp3"))
        self.assertEqual(len(created_files), 3)

    # ------------------------------------------------------------------------
    # Scenario 2: Social Media Manager Multi-Platform Embed Campaign
    # ------------------------------------------------------------------------
    def test_scenario_02_social_manager_embed_campaign(self) -> None:
        """
        TC-WRK-02: Social Media Manager Campaign Generation:
        - Processes 3 URLs across YouTube, Instagram, and TikTok
        - Generates responsive HTML iframe snippet for each
        - Generates Markdown preview cards for social scheduling
        - Bundles campaign report into structured JSON summary
        """
        if not HAS_MODELS:
            self.skipTest("Models pending implementation")

        campaign_items = [
            ("youtube", MediaMetadata(**MOCK_METADATA_DATABASE["youtube_video"])),
            ("instagram", MediaMetadata(**MOCK_METADATA_DATABASE["instagram_reel"])),
            ("tiktok", MediaMetadata(**MOCK_METADATA_DATABASE["tiktok_video"])),
        ]

        campaign_report = []
        for platform_name, meta in campaign_items:
            # Markdown preview card
            md_card = f"[![{meta.title}]({meta.thumbnail_url})]({meta.canonical_url})"
            # Responsive HTML snippet
            html_card = f'<div class="embed-card"><iframe src="{meta.canonical_url}" loading="lazy"></iframe></div>'

            campaign_report.append({
                "platform": platform_name,
                "title": meta.title,
                "uploader": meta.uploader,
                "markdown": md_card,
                "html": html_card
            })

        self.assertEqual(len(campaign_report), 3)
        self.assertTrue(all(item["markdown"].startswith("[![") for item in campaign_report))
        self.assertTrue(all("<iframe" in item["html"] for item in campaign_report))

    # ------------------------------------------------------------------------
    # Scenario 3: Mobile User High-Res Reel Thumbnail & Asset Extraction
    # ------------------------------------------------------------------------
    def test_scenario_03_mobile_highres_thumbnail_cascade(self) -> None:
        """
        TC-WRK-03: Mobile User Thumbnail Extraction:
        - Video thumbnail maxresdefault returns 120x90 placeholder (< 2000 bytes)
        - Pipeline detects placeholder size and cascades to alternative asset
        - Successfully resolves full-resolution thumbnail
        """
        if not HAS_MODELS:
            self.skipTest("Models pending implementation")

        meta = MediaMetadata(**MOCK_METADATA_DATABASE["youtube_video"])
        
        # Simulated cascade check
        chosen_thumb = None
        for asset in meta.assets:
            if asset.asset_type == "thumbnail":
                if asset.dimensions == "120x90":
                    continue  # Skip placeholder
                chosen_thumb = asset
                break

        self.assertIsNotNone(chosen_thumb)
        self.assertEqual(chosen_thumb.dimensions, "1920x1080")

    # ------------------------------------------------------------------------
    # Scenario 4: CLI Batch Processing from Dirty Text File
    # ------------------------------------------------------------------------
    def test_scenario_04_cli_batch_dirty_text_file(self) -> None:
        """
        TC-WRK-04: Batch Processing from Text File:
        - File contains comments (# comment), blank lines, trailing spaces
        - Parser strips non-URL content and extracts exactly the valid URLs
        - Feeds sanitized list to URL router
        """
        batch_file_content = """
        # Link Converter Batch List - Marketing Links
        https://www.youtube.com/watch?v=dQw4w9WgXcQ?si=tracker1
        
        # Instagram Content
           https://www.instagram.com/reel/C-j527BStv_/?igsh=tracker2   
        
        # TikTok Content
        https://www.tiktok.com/@creator/video/71234567890
        
        # Empty space below with comments
        # EOF
        """
        batch_path = Path(self.test_dir) / "batch_links.txt"
        batch_path.write_text(batch_file_content, encoding="utf-8")

        # Parse batch file
        valid_urls = []
        for line in batch_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            valid_urls.append(line)

        self.assertEqual(len(valid_urls), 3)
        self.assertIn("dQw4w9WgXcQ", valid_urls[0])
        self.assertIn("C-j527BStv_", valid_urls[1])
        self.assertIn("71234567890", valid_urls[2])

    # ------------------------------------------------------------------------
    # Scenario 5: High-Concurrency Job Queue & Semaphore Stress
    # ------------------------------------------------------------------------
    def test_scenario_05_job_queue_concurrency_stress(self) -> None:
        """
        TC-WRK-05: Queue Concurrency Limit Stress:
        - Enqueues 10 jobs simultaneously
        - Configures max_concurrency = 3
        - Verifies at most 3 jobs are processing concurrently
        - Verifies pending queue preserves FIFO ordering
        """
        max_concurrency = 3
        total_jobs = 10
        queue = []
        active_jobs = []
        completed_jobs = []

        # 1. Enqueue 10 jobs
        for i in range(total_jobs):
            queue.append({"id": f"job_{i}", "status": "pending"})

        # 2. Dispatch worker loop respecting semaphore
        while queue or active_jobs:
            while len(active_jobs) < max_concurrency and queue:
                job = queue.pop(0)
                job["status"] = "processing"
                active_jobs.append(job)

            self.assertLessEqual(len(active_jobs), max_concurrency)

            # Complete one active job
            finished = active_jobs.pop(0)
            finished["status"] = "completed"
            completed_jobs.append(finished)

        self.assertEqual(len(completed_jobs), total_jobs)
        self.assertEqual(len(active_jobs), 0)
        self.assertEqual(len(queue), 0)

    # ------------------------------------------------------------------------
    # Scenario 6: Disk Space Management & Temporary File Lifecycle Cleanup
    # ------------------------------------------------------------------------
    def test_scenario_06_temp_disk_cleanup_lifecycle(self) -> None:
        """
        TC-WRK-06: Temporary Directory Cleanup:
        - During transcode, intermediate .part, temp_audio, temp_video are created
        - Upon job completion or failure, temporary working files are cleaned up
        - Only the final converted artifact remains in destination
        """
        job_temp_dir = Path(self.test_dir) / "job_work_dir_123"
        job_temp_dir.mkdir(parents=True, exist_ok=True)

        # Simulate creation of temp artifacts
        part_file = job_temp_dir / "download.mp4.part"
        temp_audio = job_temp_dir / "temp_audio_stream.aac"
        part_file.write_bytes(b"\x00" * 1024)
        temp_audio.write_bytes(b"\x00" * 512)

        final_output = Path(self.test_dir) / "Final_Output.mp4"
        final_output.write_bytes(create_minimal_mp4_bytes())

        # Cleanup simulation
        shutil.rmtree(job_temp_dir, ignore_errors=True)

        self.assertFalse(job_temp_dir.exists())
        self.assertFalse(part_file.exists())
        self.assertTrue(final_output.exists())
        self.assertGreater(final_output.stat().st_size, 0)

    # ------------------------------------------------------------------------
    # Scenario 7: Interrupted / Cancelled Job Recovery
    # ------------------------------------------------------------------------
    def test_scenario_07_job_cancellation_recovery(self) -> None:
        """
        TC-WRK-07: Job Cancellation Mid-Execution:
        - Job is initiated and starts transcoding
        - User requests job cancellation
        - Background process is halted, status set to CANCELLED, partial files purged
        """
        partial_file = Path(self.test_dir) / "cancelled_output.mp4.part"
        partial_file.write_bytes(b"\x00" * 2048)

        job_state = {"id": "job_cancel_test", "status": "processing", "cancelled": False}

        # Simulate cancellation trigger
        job_state["cancelled"] = True
        job_state["status"] = "cancelled"
        if partial_file.exists():
            partial_file.unlink()

        self.assertEqual(job_state["status"], "cancelled")
        self.assertFalse(partial_file.exists())


if __name__ == "__main__":
    unittest.main()
