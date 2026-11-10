"""Unit tests for JobQueueService.

File: tests/unit/test_job_queue.py
"""
import asyncio
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

src_path = str(Path(__file__).resolve().parent.parent.parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from linkconv.core.models import (
    ConversionOptions,
    ConversionRequest,
    JobState,
    JobStatus,
    MediaMetadata,
    Platform,
)
from linkconv.services.job_queue import JobQueueService, JobRecord


class TestJobQueueLifecycle(unittest.TestCase):
    """Test suite for basic job lifecycle states and progress updates."""

    def setUp(self) -> None:
        self.test_dir = tempfile.mkdtemp(prefix="linkconv_test_jq_")
        self.queue = JobQueueService(temp_dir=self.test_dir)

    def tearDown(self) -> None:
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_job_creation_initial_state(self) -> None:
        """TC-UT-JQ-01: Job creation produces valid UUID, PENDING state, and 0.0 progress."""
        job_id = self.queue.create_job({"url": "https://example.com/video"})
        self.assertIsInstance(job_id, str)
        self.assertGreaterEqual(len(job_id), 8)

        job = self.queue.get_job(job_id)
        self.assertIsNotNone(job)
        self.assertEqual(job.status.lower(), "pending")
        self.assertEqual(job.progress, 0.0)
        self.assertFalse(job.is_finished)

    def test_job_creation_from_conversion_request(self) -> None:
        """TC-UT-JQ-02: create_job accepts ConversionRequest instance and options."""
        req = ConversionRequest(
            url="https://youtube.com/watch?v=123",
            options=ConversionOptions(target_format="mp3", target_quality="320k"),
        )
        job_id = self.queue.create_job(req)
        job = self.queue.get_job(job_id)
        self.assertEqual(job.options.target_format, "mp3")
        self.assertEqual(job.options.target_quality, "320k")

    def test_job_status_transition_to_processing(self) -> None:
        """TC-UT-JQ-03: update_progress transitions PENDING job to PROCESSING."""
        job_id = self.queue.create_job({"url": "https://example.com/video"})
        self.queue.update_progress(job_id, progress=25.0, stage="downloading")
        job = self.queue.get_job(job_id)
        self.assertEqual(job.status.lower(), "processing")
        self.assertEqual(job.progress, 25.0)
        self.assertEqual(job.stage, "downloading")

    def test_update_progress_clamping(self) -> None:
        """TC-UT-JQ-04: Progress updates clamped within [0.0, 100.0]."""
        job_id = self.queue.create_job({"url": "https://example.com/video"})
        self.queue.update_progress(job_id, progress=-15.0)
        job = self.queue.get_job(job_id)
        self.assertEqual(job.progress, 0.0)

        self.queue.update_progress(job_id, progress=125.0)
        self.assertEqual(job.progress, 100.0)

    def test_update_progress_speed_and_eta(self) -> None:
        """TC-UT-JQ-05: Preserves transfer speed and eta values."""
        job_id = self.queue.create_job({"url": "https://example.com/video"})
        self.queue.update_progress(job_id, progress=60.0, speed="15.4 MB/s", eta=5)
        job = self.queue.get_job(job_id)
        self.assertEqual(job.speed, "15.4 MB/s")
        self.assertEqual(job.eta, 5)

    def test_job_completion_state(self) -> None:
        """TC-UT-JQ-06: complete_job marks COMPLETED, sets 100%, and records output details."""
        job_id = self.queue.create_job({"url": "https://example.com/video"})
        fake_output = Path(self.test_dir) / "output.mp4"
        fake_output.write_bytes(b"DATA" * 100)

        self.queue.complete_job(job_id, output_path=str(fake_output))
        job = self.queue.get_job(job_id)
        self.assertEqual(job.status.lower(), "completed")
        self.assertEqual(job.progress, 100.0)
        self.assertEqual(job.output_path, str(fake_output))
        self.assertEqual(job.output_size_bytes, 400)
        self.assertTrue(job.is_finished)

    def test_job_failure_state(self) -> None:
        """TC-UT-JQ-07: fail_job marks FAILED and records error diagnostics."""
        job_id = self.queue.create_job({"url": "https://example.com/video"})
        self.queue.fail_job(job_id, error="Network timeout during download", error_code="LC_ERR_DOWNLOAD_FAILED")
        job = self.queue.get_job(job_id)
        self.assertEqual(job.status.lower(), "failed")
        self.assertIn("timeout", job.error.lower())
        self.assertEqual(job.error_code, "LC_ERR_DOWNLOAD_FAILED")
        self.assertTrue(job.is_finished)


class TestJobQueueConcurrency(unittest.TestCase):
    """Test suite for concurrency limits and FIFO queue ordering."""

    def setUp(self) -> None:
        self.test_dir = tempfile.mkdtemp(prefix="linkconv_test_jq_conc_")
        self.queue = JobQueueService(max_concurrency=2, temp_dir=self.test_dir)

    def tearDown(self) -> None:
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_semaphore_concurrency_ceiling(self) -> None:
        """TC-UT-JQ-08: Ensures active jobs never exceed max_concurrency ceiling."""
        async def run_scenario():
            active_count = 0
            peak_active = 0
            lock = asyncio.Lock()

            async def mock_worker(jid):
                nonlocal active_count, peak_active
                async with self.queue._semaphore:
                    async with lock:
                        active_count += 1
                        if active_count > peak_active:
                            peak_active = active_count
                    await asyncio.sleep(0.05)
                    async with lock:
                        active_count -= 1

            tasks = [asyncio.create_task(mock_worker(f"j_{i}")) for i in range(6)]
            await asyncio.gather(*tasks)
            self.assertLessEqual(peak_active, 2)

        asyncio.run(run_scenario())

    def test_high_volume_enqueuing(self) -> None:
        """TC-UT-JQ-09: Rapidly enqueues 50 jobs with unique UUIDs without collision."""
        jids = set()
        for i in range(50):
            jid = self.queue.create_job({"url": f"https://example.com/video_{i}"})
            self.assertNotIn(jid, jids)
            jids.add(jid)
        self.assertEqual(len(jids), 50)
        self.assertEqual(len(self.queue.list_jobs(limit=100)), 50)


class TestJobQueueSSEStreaming(unittest.TestCase):
    """Test suite for Server-Sent Events (SSE) streaming engine."""

    def setUp(self) -> None:
        self.test_dir = tempfile.mkdtemp(prefix="linkconv_test_jq_sse_")
        self.queue = JobQueueService(temp_dir=self.test_dir)

    def tearDown(self) -> None:
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_sse_initial_state_emission(self) -> None:
        """TC-UT-JQ-10: First SSE emitted frame contains initial job snapshot."""
        job_id = self.queue.create_job({"url": "https://example.com/video"})

        async def check_first_event():
            gen = self.queue.subscribe_events(job_id)
            first_event = await anext(gen)
            self.assertTrue(first_event.startswith("event: progress\n"))
            self.assertIn('"status": "pending"', first_event)
            self.assertIn(f'"job_id": "{job_id}"', first_event)
            await gen.aclose()

        asyncio.run(check_first_event())

    def test_sse_streaming_progress_events(self) -> None:
        """TC-UT-JQ-11: Subscribers receive live updates and stream terminates on terminal state."""
        job_id = self.queue.create_job({"url": "https://example.com/video"})

        async def stream_consumer():
            received = []
            gen = self.queue.subscribe_events(job_id, ping_interval=0.5)

            # Consume initial
            ev0 = await anext(gen)
            received.append(ev0)

            # Trigger progress
            self.queue.update_progress(job_id, 45.0, stage="transcoding")
            ev1 = await anext(gen)
            received.append(ev1)

            # Trigger complete
            self.queue.complete_job(job_id, output_path="C:\\out.mp4")
            ev2 = await anext(gen)
            received.append(ev2)

            # Generator should finish
            try:
                await anext(gen)
            except StopAsyncIteration:
                pass

            return received

        results = asyncio.run(stream_consumer())
        self.assertEqual(len(results), 3)
        self.assertIn('"progress": 45.0', results[1])
        self.assertIn('"status": "completed"', results[2])

    def test_sse_multiple_subscribers_fan_out(self) -> None:
        """TC-UT-JQ-12: Multiple subscribers receive fan-out event broadcasts."""
        job_id = self.queue.create_job({"url": "https://example.com/video"})

        async def run_fan_out():
            gen1 = self.queue.subscribe_events(job_id)
            gen2 = self.queue.subscribe_events(job_id)

            await anext(gen1)
            await anext(gen2)

            self.queue.update_progress(job_id, 70.0, stage="encoding")

            ev1 = await anext(gen1)
            ev2 = await anext(gen2)

            self.assertIn('"progress": 70.0', ev1)
            self.assertIn('"progress": 70.0', ev2)

            await gen1.aclose()
            await gen2.aclose()

        asyncio.run(run_fan_out())


class TestJobQueueCancellationAndCleanup(unittest.TestCase):
    """Test suite for cancellation and garbage collection."""

    def setUp(self) -> None:
        self.test_dir = tempfile.mkdtemp(prefix="linkconv_test_jq_cancel_")
        self.queue = JobQueueService(temp_dir=self.test_dir)

    def tearDown(self) -> None:
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_cancel_pending_job(self) -> None:
        """TC-UT-JQ-13: cancel_job cancels pending job and updates status."""
        job_id = self.queue.create_job({"url": "https://example.com/video"})
        res = self.queue.cancel_job(job_id)
        self.assertTrue(res)
        job = self.queue.get_job(job_id)
        self.assertEqual(job.status.lower(), "cancelled")
        self.assertTrue(job.is_finished)

    def test_cancel_already_finished_job_returns_false(self) -> None:
        """TC-UT-JQ-14: cancel_job returns False when job is already finished."""
        job_id = self.queue.create_job({"url": "https://example.com/video"})
        self.queue.complete_job(job_id, output_path="C:\\out.mp4")
        res = self.queue.cancel_job(job_id)
        self.assertFalse(res)

    def test_cancellation_purges_temp_scratch_files(self) -> None:
        """TC-UT-JQ-15: Cancellation purges temporary scratch directory."""
        job_id = self.queue.create_job({"url": "https://example.com/video"})
        job = self.queue.get_job(job_id)
        temp_file = job.temp_dir / "temp_stream.part"
        temp_file.write_bytes(b"TEMPORARY_PART_STREAM")
        self.assertTrue(temp_file.exists())

        self.queue.cancel_job(job_id)
        self.assertFalse(temp_file.exists())

    def test_cleanup_purges_expired_completed_jobs(self) -> None:
        """TC-UT-JQ-16: cleanup_expired_jobs purges jobs older than TTL and preserves fresh ones."""
        job_id_old = self.queue.create_job({"url": "https://example.com/old"})
        self.queue.complete_job(job_id_old, output_path="out.mp4")
        old_job = self.queue.get_job(job_id_old)
        old_job.updated_at = time.time() - 4000  # Older than 3600s TTL

        job_id_fresh = self.queue.create_job({"url": "https://example.com/fresh"})
        self.queue.complete_job(job_id_fresh, output_path="out.mp4")

        purged = self.queue.cleanup_expired_jobs(max_age_seconds=3600)
        self.assertEqual(purged, 1)
        self.assertIsNone(self.queue.get_job(job_id_old))
        self.assertIsNotNone(self.queue.get_job(job_id_fresh))

    def test_shutdown_cancels_all_active_jobs(self) -> None:
        """TC-UT-JQ-17: shutdown cancels all active/pending jobs."""
        j1 = self.queue.create_job({"url": "https://example.com/1"})
        j2 = self.queue.create_job({"url": "https://example.com/2"})
        self.queue.shutdown()
        self.assertEqual(self.queue.get_job(j1).status.lower(), "cancelled")
        self.assertEqual(self.queue.get_job(j2).status.lower(), "cancelled")

    def test_subscribe_unknown_job_yields_error_event(self) -> None:
        """TC-UT-JQ-18: Subscribing to non-existent job yields error event."""
        async def check_unknown():
            gen = self.queue.subscribe_events("invalid_id_999")
            ev = await anext(gen)
            self.assertTrue(ev.startswith("event: error\n"))
            self.assertIn("not found", ev)

        asyncio.run(check_unknown())


if __name__ == "__main__":
    unittest.main()
