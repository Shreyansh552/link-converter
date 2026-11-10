"""Unit tests for linkconv core domain models.

File: tests/unit/test_models.py
"""
from pathlib import Path
import sys
import tempfile
import unittest

src_path = str(Path(__file__).resolve().parent.parent.parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from pydantic import ValidationError

from linkconv.core.models import (
    ALL_SUPPORTED_FORMATS,
    ConversionOptions,
    ConversionRequest,
    JobState,
    JobStatus,
    MediaAsset,
    MediaFormat,
    MediaMetadata,
    Platform,
    SUPPORTED_AUDIO_FORMATS,
    SUPPORTED_VIDEO_FORMATS,
)


class TestPlatformEnum(unittest.TestCase):
    def test_enum_members_count_and_values(self):
        expected_platforms = {
            "youtube", "instagram", "tiktok", "twitter", "facebook",
            "reddit", "pinterest", "vimeo", "soundcloud", "generic"
        }
        actual = {p.value for p in Platform}
        self.assertEqual(expected_platforms, actual)

    def test_from_str_exact_and_case_insensitive(self):
        self.assertEqual(Platform.from_str("youtube"), Platform.YOUTUBE)
        self.assertEqual(Platform.from_str("YouTube"), Platform.YOUTUBE)
        self.assertEqual(Platform.from_str("INSTAGRAM"), Platform.INSTAGRAM)

    def test_from_str_aliases(self):
        self.assertEqual(Platform.from_str("yt"), Platform.YOUTUBE)
        self.assertEqual(Platform.from_str("youtu.be"), Platform.YOUTUBE)
        self.assertEqual(Platform.from_str("ig"), Platform.INSTAGRAM)
        self.assertEqual(Platform.from_str("insta"), Platform.INSTAGRAM)
        self.assertEqual(Platform.from_str("tt"), Platform.TIKTOK)
        self.assertEqual(Platform.from_str("x"), Platform.TWITTER)
        self.assertEqual(Platform.from_str("tw"), Platform.TWITTER)
        self.assertEqual(Platform.from_str("fb"), Platform.FACEBOOK)
        self.assertEqual(Platform.from_str("pin"), Platform.PINTEREST)
        self.assertEqual(Platform.from_str("sc"), Platform.SOUNDCLOUD)
        self.assertEqual(Platform.from_str("direct"), Platform.GENERIC)
        self.assertEqual(Platform.from_str("html5"), Platform.GENERIC)

    def test_from_str_invalid(self):
        with self.assertRaises(ValueError) as ctx:
            Platform.from_str("unsupported_platform_xyz")
        self.assertIn("Unknown platform", str(ctx.exception))

        with self.assertRaises(ValueError):
            Platform.from_str(123)  # type: ignore

    def test_display_name_and_badge_color(self):
        self.assertEqual(Platform.YOUTUBE.display_name, "YouTube")
        self.assertEqual(Platform.TWITTER.display_name, "Twitter / X")
        self.assertEqual(Platform.GENERIC.display_name, "Generic / Direct")
        self.assertTrue(Platform.YOUTUBE.badge_color.startswith("#"))
        self.assertEqual(Platform.YOUTUBE.badge_color, "#FF0000")


class TestMediaFormat(unittest.TestCase):
    def test_format_instantiation_defaults(self):
        fmt = MediaFormat(format_id="22", ext="mp4")
        self.assertEqual(fmt.format_id, "22")
        self.assertEqual(fmt.ext, "mp4")
        self.assertFalse(fmt.is_dash)
        self.assertFalse(fmt.needs_muxing)

    def test_is_video_and_is_audio_only(self):
        video_fmt = MediaFormat(format_id="137", ext="mp4", vcodec="avc1", acodec="none")
        self.assertTrue(video_fmt.is_video)
        self.assertFalse(video_fmt.is_audio_only)

        audio_fmt = MediaFormat(format_id="140", ext="m4a", vcodec="none", acodec="mp4a")
        self.assertFalse(audio_fmt.is_video)
        self.assertTrue(audio_fmt.is_audio_only)

        muxed_fmt = MediaFormat(format_id="18", ext="mp4", vcodec="avc1", acodec="mp4a")
        self.assertTrue(muxed_fmt.is_video)
        self.assertFalse(muxed_fmt.is_audio_only)

    def test_filesize_mb(self):
        fmt = MediaFormat(format_id="1", ext="mp4", filesize_approx=10485760)  # 10 MB
        self.assertEqual(fmt.filesize_mb, 10.0)

        fmt_none = MediaFormat(format_id="2", ext="mp4")
        self.assertIsNone(fmt_none.filesize_mb)

    def test_display_label(self):
        vfmt = MediaFormat(format_id="1", ext="mp4", height=1080, vcodec="avc1")
        self.assertIn("1080p (mp4)", vfmt.display_label)

        afmt = MediaFormat(format_id="2", ext="mp3", abr=320.0, vcodec="none", acodec="mp3")
        self.assertIn("320kbps (mp3)", afmt.display_label)

    def test_quality_score(self):
        fmt1080 = MediaFormat(format_id="1", ext="mp4", height=1080, fps=60.0, vcodec="avc1")
        fmt720 = MediaFormat(format_id="2", ext="mp4", height=720, fps=30.0, vcodec="avc1")
        self.assertGreater(fmt1080.quality_score, fmt720.quality_score)


class TestMediaMetadata(unittest.TestCase):
    def setUp(self):
        self.sample_metadata = MediaMetadata(
            id="test12345",
            platform=Platform.YOUTUBE,
            original_url="https://youtu.be/test12345",
            canonical_url="https://www.youtube.com/watch?v=test12345",
            title="Sample Test Video",
            duration=215.0,  # 3m 35s
            formats=[
                MediaFormat(format_id="18", ext="mp4", height=360, vcodec="avc1", acodec="mp4a", vbr=500.0),
                MediaFormat(format_id="137", ext="mp4", height=1080, vcodec="avc1", acodec="none", vbr=4000.0),
                MediaFormat(format_id="140", ext="m4a", abr=128.0, vcodec="none", acodec="mp4a"),
                MediaFormat(format_id="251", ext="opus", abr=160.0, vcodec="none", acodec="opus"),
            ],
            assets=[
                MediaAsset(asset_type="thumbnail", url="https://img.test/thumb.jpg", label="default"),
                MediaAsset(asset_type="image", url="https://img.test/slide2.jpg", slide_index=1),
                MediaAsset(asset_type="image", url="https://img.test/slide1.jpg", slide_index=0),
            ],
        )

    def test_duration_formatted(self):
        self.assertEqual(self.sample_metadata.duration_formatted, "03:35")

        meta_long = MediaMetadata(
            id="long", platform=Platform.GENERIC, original_url="http://a", canonical_url="http://a",
            title="Long", duration=3665.0,  # 1h 1m 5s
        )
        self.assertEqual(meta_long.duration_formatted, "01:01:05")

        meta_zero = MediaMetadata(
            id="zero", platform=Platform.GENERIC, original_url="http://a", canonical_url="http://a",
            title="Zero", duration=0.0,
        )
        self.assertEqual(meta_zero.duration_formatted, "00:00")

    def test_best_video_format(self):
        best_v = self.sample_metadata.best_video_format()
        self.assertIsNotNone(best_v)
        self.assertEqual(best_v.format_id, "137")
        self.assertEqual(best_v.height, 1080)

    def test_best_audio_format(self):
        best_a = self.sample_metadata.best_audio_format()
        self.assertIsNotNone(best_a)
        self.assertEqual(best_a.format_id, "251")
        self.assertEqual(best_a.abr, 160.0)

    def test_best_audio_format_with_preferred_ext(self):
        best_m4a = self.sample_metadata.best_audio_format(preferred_ext="m4a")
        self.assertIsNotNone(best_m4a)
        self.assertEqual(best_m4a.format_id, "140")

    def test_get_format_by_id(self):
        fmt = self.sample_metadata.get_format_by_id("137")
        self.assertIsNotNone(fmt)
        self.assertEqual(fmt.height, 1080)

        fmt_missing = self.sample_metadata.get_format_by_id("non_existent")
        self.assertIsNone(fmt_missing)

    def test_filter_formats(self):
        videos = self.sample_metadata.filter_formats(video_only=True)
        self.assertEqual(len(videos), 2)
        self.assertTrue(all(f.is_video for f in videos))

        audios = self.sample_metadata.filter_formats(audio_only=True)
        self.assertEqual(len(audios), 2)
        self.assertTrue(all(f.is_audio_only for f in audios))

        under_720 = self.sample_metadata.filter_formats(video_only=True, max_height=720)
        self.assertEqual(len(under_720), 1)
        self.assertEqual(under_720[0].format_id, "18")

    def test_carousel_images_sorting(self):
        slides = self.sample_metadata.carousel_images
        self.assertEqual(len(slides), 3)
        self.assertEqual(slides[0].slide_index, 0)
        self.assertEqual(slides[1].slide_index, 1)


class TestConversionOptions(unittest.TestCase):
    def test_default_options(self):
        opts = ConversionOptions()
        self.assertEqual(opts.target_format, "mp4")
        self.assertEqual(opts.target_quality, "best")
        self.assertFalse(opts.extract_audio_only)
        self.assertTrue(opts.embed_thumbnail)

    def test_format_normalization(self):
        opts = ConversionOptions(target_format=".MP3")
        self.assertEqual(opts.target_format, "mp3")

    def test_unsupported_format_raises_validation_error(self):
        with self.assertRaises(ValidationError):
            ConversionOptions(target_format="invalid_container_xyz")

    def test_extract_audio_only_auto_adjusts_video_format(self):
        opts = ConversionOptions(target_format="mp4", extract_audio_only=True)
        self.assertEqual(opts.target_format, "mp3")


class TestConversionRequest(unittest.TestCase):
    def test_request_instantiation_generates_uuid(self):
        req = ConversionRequest(url="https://youtube.com/watch?v=123")
        self.assertTrue(len(req.request_id) > 10)
        self.assertEqual(req.options.target_format, "mp4")

    def test_empty_url_raises_validation_error(self):
        with self.assertRaises(ValidationError):
            ConversionRequest(url="   ")


class TestJobStatus(unittest.TestCase):
    def test_job_lifecycle(self):
        job = JobStatus(job_id="job_001")
        self.assertEqual(job.state, JobState.PENDING)
        self.assertEqual(job.progress, 0.0)
        self.assertFalse(job.is_finished)

        job.update_progress(45.5, step="Downloading video", speed="4.2 MB/s", eta=12)
        self.assertEqual(job.progress, 45.5)
        self.assertEqual(job.current_step, "Downloading video")
        self.assertEqual(job.speed, "4.2 MB/s")
        self.assertEqual(job.eta, 12)

        # Progress clamped
        job.update_progress(150.0)
        self.assertEqual(job.progress, 100.0)

        job.set_completed(output_path="/tmp/output.mp4", output_size_bytes=1048576)
        self.assertEqual(job.state, JobState.COMPLETED)
        self.assertTrue(job.is_finished)
        self.assertEqual(job.output_path, "/tmp/output.mp4")

    def test_job_failure(self):
        job = JobStatus(job_id="job_002")
        job.set_failed("Transcoding failed", error_code="LC_ERR_TRANSCODING_FAILED")
        self.assertEqual(job.state, JobState.FAILED)
        self.assertTrue(job.is_finished)
        self.assertEqual(job.error_code, "LC_ERR_TRANSCODING_FAILED")


class TestSerializationRoundTrip(unittest.TestCase):
    def test_dict_and_json_roundtrip(self):
        original = MediaMetadata(
            id="vid1",
            platform=Platform.TIKTOK,
            original_url="https://www.tiktok.com/@user/video/123",
            canonical_url="https://www.tiktok.com/@user/video/123",
            title="Funny TikTok",
            duration=15.0,
            formats=[
                MediaFormat(format_id="1", ext="mp4", resolution="720x1280", vcodec="h264", acodec="aac")
            ],
        )

        # To dict / from dict
        d = original.to_dict()
        self.assertIsInstance(d, dict)
        restored_from_dict = MediaMetadata.from_dict(d)
        self.assertEqual(original.id, restored_from_dict.id)
        self.assertEqual(original.platform, restored_from_dict.platform)

        # To json / from json
        j = original.to_json()
        self.assertIsInstance(j, str)
        restored_from_json = MediaMetadata.from_json(j)
        self.assertEqual(original.title, restored_from_json.title)

    def test_file_save_and_load(self):
        original = MediaMetadata(
            id="save_load_test",
            platform=Platform.VIMEO,
            original_url="https://vimeo.com/123456",
            canonical_url="https://vimeo.com/123456",
            title="Vimeo Film",
            duration=600.0,
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "subfolder" / "meta.json"
            original.save_to_file(file_path)
            self.assertTrue(file_path.exists())

            loaded = MediaMetadata.load_from_file(file_path)
            self.assertEqual(original.id, loaded.id)
            self.assertEqual(original.platform, loaded.platform)


if __name__ == "__main__":
    unittest.main()
