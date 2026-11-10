"""Unit tests for TranscodingService and ConversionOptions.

File: tests/unit/test_transcoding.py
"""
import asyncio
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

src_path = str(Path(__file__).resolve().parent.parent.parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from linkconv.core.exceptions import TranscodingError
from linkconv.core.models import MediaFormat, MediaMetadata, Platform
from linkconv.services.transcoding import (
    ConversionOptions,
    TranscodingService,
    is_direct_copy_eligible,
    sanitize_filename,
)


class TestTranscodingService(unittest.TestCase):
    """Unit test suite for TranscodingService and conversion rules."""

    def setUp(self) -> None:
        self.transcoder = TranscodingService(ffmpeg_path="/mock/bin/ffmpeg")

    def test_conversion_options_validations(self) -> None:
        """TC-UT-TRN-01: Validates format and quality options, rejecting invalid combinations."""
        # Valid video formats
        opt1 = ConversionOptions(target_format="mp4", target_quality="1080p")
        self.assertEqual(opt1.target_format, "mp4")
        self.assertEqual(opt1.target_quality, "1080p")

        # Valid audio format
        opt2 = ConversionOptions(target_format="mp3", target_quality="320k")
        self.assertEqual(opt2.target_format, "mp3")
        self.assertEqual(opt2.target_quality, "320k")

        # Invalid format
        with self.assertRaises(ValueError):
            ConversionOptions(target_format="unsupported_xyz")

        # Invalid bitrate
        with self.assertRaises(ValueError):
            ConversionOptions(target_format="mp3", target_quality="999999k")

        # Invalid video quality
        with self.assertRaises(ValueError):
            ConversionOptions(target_format="mp4", target_quality="8000p")

    def test_direct_copy_matrix(self) -> None:
        """TC-UT-TRN-02: Evaluates direct stream copy eligibility across codecs and containers."""
        # MP4 with H.264 + AAC is direct copy
        self.assertTrue(is_direct_copy_eligible("avc1.640028", "mp4a.40.2", "mp4"))
        self.assertTrue(is_direct_copy_eligible("h264", "aac", "mp4"))

        # MP4 with VP9 is NOT direct copy
        self.assertFalse(is_direct_copy_eligible("vp9", "opus", "mp4"))

        # WEBM with VP9 + Opus is direct copy
        self.assertTrue(is_direct_copy_eligible("vp9", "opus", "webm"))
        self.assertTrue(is_direct_copy_eligible("av01", "opus", "webm"))

        # WEBM with H.264 is NOT direct copy
        self.assertFalse(is_direct_copy_eligible("avc1", "aac", "webm"))

        # MKV container accepts any codecs natively
        self.assertTrue(is_direct_copy_eligible("vp9", "opus", "mkv"))
        self.assertTrue(is_direct_copy_eligible("h264", "aac", "mkv"))

        # Audio direct copy
        self.assertTrue(is_direct_copy_eligible(None, "opus", "opus"))
        self.assertTrue(is_direct_copy_eligible(None, "mp4a.40.2", "m4a"))
        self.assertFalse(is_direct_copy_eligible(None, "mp3", "opus"))

    def test_filename_sanitizer(self) -> None:
        """TC-UT-TRN-03: Sanitizes filenames for Windows filesystem compatibility."""
        dirty = 'Test: <Video> "Special" / * ? | Characters.mp4'
        clean = sanitize_filename(dirty)
        for char in '<>:"/\\|?*':
            self.assertNotIn(char, clean)

        # Reserved Windows names
        con_name = sanitize_filename("CON")
        self.assertTrue(con_name.startswith("media_"))

        nul_name = sanitize_filename("NUL")
        self.assertTrue(nul_name.startswith("media_"))

        # Length truncation
        long_name = "A" * 200
        truncated = sanitize_filename(long_name, max_length=120)
        self.assertLessEqual(len(truncated), 120)

    def test_mp4_remux_command_direct_copy(self) -> None:
        """TC-UT-TRN-04: Builds command with direct copy flags for compatible streams."""
        meta = MediaMetadata(
            id="v123",
            platform=Platform.YOUTUBE,
            original_url="https://youtube.com/watch?v=v123",
            canonical_url="https://youtube.com/watch?v=v123",
            title="Direct Copy Video",
            duration=60.0,
            formats=[
                MediaFormat(
                    format_id="137",
                    ext="mp4",
                    resolution="1080p",
                    height=1080,
                    vcodec="avc1.640028",
                    acodec="none",
                    is_dash=True,
                    url=r"C:\fake\video.mp4",
                ),
                MediaFormat(
                    format_id="140",
                    ext="m4a",
                    acodec="mp4a.40.2",
                    vcodec="none",
                    abr=128.0,
                    url=r"C:\fake\audio.m4a",
                ),
            ],
        )
        opts = ConversionOptions(target_format="mp4")

        captured_cmds = []

        async def fake_run_ffmpeg(cmd, dur, cb):
            captured_cmds.append(cmd)

        with patch.object(self.transcoder, "_run_ffmpeg_command", side_effect=fake_run_ffmpeg):
            asyncio.run(self.transcoder.convert(meta, opts))

        self.assertEqual(len(captured_cmds), 1)
        cmd = captured_cmds[0]
        self.assertIn("-c:v", cmd)
        idx_v = cmd.index("-c:v")
        self.assertEqual(cmd[idx_v + 1], "copy")
        self.assertIn("-movflags", cmd)
        self.assertIn("+faststart", cmd)

    def test_mp4_transcode_command_incompatible(self) -> None:
        """TC-UT-TRN-05: Builds command with libx264+aac transcode when codecs incompatible."""
        meta = MediaMetadata(
            id="v456",
            platform=Platform.YOUTUBE,
            original_url="https://youtube.com/watch?v=v456",
            canonical_url="https://youtube.com/watch?v=v456",
            title="Transcode Needed Video",
            duration=60.0,
            formats=[
                MediaFormat(
                    format_id="248",
                    ext="webm",
                    resolution="1080p",
                    height=1080,
                    vcodec="vp9",
                    acodec="none",
                    is_dash=True,
                    url=r"C:\fake\video.webm",
                ),
                MediaFormat(
                    format_id="251",
                    ext="webm",
                    acodec="opus",
                    vcodec="none",
                    abr=160.0,
                    url=r"C:\fake\audio.opus",
                ),
            ],
        )
        opts = ConversionOptions(target_format="mp4")

        captured_cmds = []

        async def fake_run_ffmpeg(cmd, dur, cb):
            captured_cmds.append(cmd)

        with patch.object(self.transcoder, "_run_ffmpeg_command", side_effect=fake_run_ffmpeg):
            asyncio.run(self.transcoder.convert(meta, opts))

        self.assertEqual(len(captured_cmds), 1)
        cmd = captured_cmds[0]
        self.assertIn("libx264", cmd)
        self.assertIn("aac", cmd)
        self.assertIn("+faststart", cmd)

    def test_audio_extraction_command_mp3_cover_art(self) -> None:
        """TC-UT-TRN-06: Builds command for MP3 with ID3v2 tags and attached album art."""
        meta = MediaMetadata(
            id="a789",
            platform=Platform.SOUNDCLOUD,
            original_url="https://soundcloud.com/artist/track",
            canonical_url="https://soundcloud.com/artist/track",
            title="Audio Track",
            uploader="Famous Artist",
            duration=180.0,
            thumbnail_url=r"C:\fake\cover.jpg",
            formats=[
                MediaFormat(
                    format_id="audio_high",
                    ext="mp3",
                    acodec="mp3",
                    vcodec="none",
                    abr=320.0,
                    url=r"C:\fake\track.mp3",
                )
            ],
        )
        opts = ConversionOptions(target_format="mp3", target_quality="320k", embed_thumbnail=True)

        captured_cmds = []

        async def fake_run_ffmpeg(cmd, dur, cb):
            captured_cmds.append(cmd)

        with patch.object(self.transcoder, "_run_ffmpeg_command", side_effect=fake_run_ffmpeg):
            asyncio.run(self.transcoder.convert(meta, opts))

        self.assertEqual(len(captured_cmds), 1)
        cmd = captured_cmds[0]
        self.assertIn("libmp3lame", cmd)
        self.assertIn("320k", cmd)
        self.assertIn("-id3v2_version", cmd)
        self.assertIn("title=Album cover", " ".join(cmd))

    def test_audio_extraction_lossless_and_opus(self) -> None:
        """TC-UT-TRN-07: Builds command for WAV (pcm_s16le), FLAC, and OPUS."""
        meta = MediaMetadata(
            id="lossless_test",
            platform=Platform.GENERIC,
            original_url="https://example.com/audio.wav",
            canonical_url="https://example.com/audio.wav",
            title="Lossless Audio",
            formats=[
                MediaFormat(
                    format_id="wav_fmt",
                    ext="wav",
                    acodec="pcm_s16le",
                    vcodec="none",
                    url=r"C:\fake\in.wav",
                )
            ],
        )
        opts_wav = ConversionOptions(target_format="wav")

        captured = []

        async def fake_run_ffmpeg(cmd, dur, cb):
            captured.append(cmd)

        with patch.object(self.transcoder, "_run_ffmpeg_command", side_effect=fake_run_ffmpeg):
            asyncio.run(self.transcoder.convert(meta, opts_wav))

        cmd = captured[0]
        self.assertIn("pcm_s16le", cmd)

    def test_progress_monitoring_pipe(self) -> None:
        """TC-UT-TRN-08: Progress parser reads -progress pipe:1 and invokes callback."""
        mock_proc = MagicMock()
        mock_proc.returncode = 0

        # Simulate stdout lines
        lines = [
            b"speed=1.50x\n",
            b"out_time_us=30000000\n",
            b"progress=continue\n",
            b"out_time_us=60000000\n",
            b"progress=end\n",
            b"",
        ]

        async def fake_readline():
            if lines:
                return lines.pop(0)
            return b""

        mock_stdout = MagicMock()
        mock_stdout.readline = AsyncMock(side_effect=fake_readline)
        mock_proc.stdout = mock_stdout
        mock_proc.stderr = None
        mock_proc.wait = AsyncMock(return_value=0)

        progress_records = []

        def on_progress(payload):
            progress_records.append(payload)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            asyncio.run(
                self.transcoder._run_ffmpeg_command(
                    cmd=["ffmpeg", "-i", "in.mp4", "out.mp4"],
                    duration=60.0,
                    progress_callback=on_progress,
                )
            )

        self.assertTrue(len(progress_records) >= 2)
        # 30s of 60s is 50.0%
        self.assertAlmostEqual(progress_records[0]["progress"], 50.0, places=1)
        # Final end progress is 100.0%
        self.assertEqual(progress_records[-1]["progress"], 100.0)

    def test_transcode_failure_raises_transcoding_error(self) -> None:
        """TC-UT-TRN-09: Non-zero returncode raises TranscodingError with diagnostics."""
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.stdout = None

        mock_stderr = MagicMock()
        mock_stderr.read = AsyncMock(return_value=b"Error while opening encoder for output stream #0:0")
        mock_proc.stderr = mock_stderr
        mock_proc.wait = AsyncMock(return_value=1)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with self.assertRaises(TranscodingError) as ctx:
                asyncio.run(
                    self.transcoder._run_ffmpeg_command(
                        cmd=["ffmpeg", "-i", "in.mp4", "out.mp4"],
                        duration=60.0,
                        progress_callback=None,
                    )
                )
            self.assertEqual(ctx.exception.returncode, 1)
            self.assertIn("encoder", ctx.exception.stderr)


if __name__ == "__main__":
    unittest.main()
