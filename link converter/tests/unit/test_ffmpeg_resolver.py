"""Unit tests for FFmpegResolverService.

File: tests/unit/test_ffmpeg_resolver.py
"""
import io
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import zipfile

src_path = str(Path(__file__).resolve().parent.parent.parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from linkconv.core.exceptions import FFmpegNotFoundError
from linkconv.services.ffmpeg_resolver import FFmpegResolverService


class TestFFmpegResolverService(unittest.TestCase):
    """Unit test suite for FFmpeg discovery, verification, and provisioning."""

    def setUp(self) -> None:
        self.resolver = FFmpegResolverService()

    def test_default_init(self) -> None:
        """TC-UT-FFM-01: Default initialization sets empty cache and no custom path."""
        self.assertIsNone(self.resolver.custom_path)
        self.assertIsNone(self.resolver._cached_ffmpeg_path)
        self.assertTrue(callable(self.resolver.is_available))

    def test_set_custom_path_and_cache_invalidation(self) -> None:
        """TC-UT-FFM-02: set_custom_path invalidates cached paths."""
        self.resolver._cached_ffmpeg_path = "some/old/path"
        self.resolver._cached_version = "6.0"
        self.resolver.set_custom_path("C:\\custom\\ffmpeg.exe")
        self.assertEqual(self.resolver.custom_path, "C:\\custom\\ffmpeg.exe")
        self.assertIsNone(self.resolver._cached_ffmpeg_path)
        self.assertIsNone(self.resolver._cached_version)

    @patch("shutil.which")
    def test_tier1_path_discovery(self, mock_which) -> None:
        """TC-UT-FFM-03: Tier 1 resolves globally installed ffmpeg on PATH."""
        mock_which.return_value = r"C:\SystemTools\ffmpeg.exe"
        with patch("os.path.isfile", return_value=True):
            resolved = self.resolver.find_ffmpeg()
            self.assertEqual(resolved, os.path.abspath(r"C:\SystemTools\ffmpeg.exe"))
            self.assertTrue(self.resolver.is_available())

    @patch("shutil.which", return_value=None)
    def test_tier2_local_appdata_discovery(self, mock_which) -> None:
        """TC-UT-FFM-04: Tier 2 resolves from linkconv local appdata bin directory."""
        with patch.object(self.resolver, "get_local_appdata_ffmpeg") as mock_get_local:
            mock_path = MagicMock(spec=Path)
            mock_path.is_file.return_value = True
            mock_path.resolve.return_value = Path(r"C:\AppData\linkconv\bin\ffmpeg.exe")
            mock_get_local.return_value = mock_path

            with patch("os.access", return_value=True):
                resolved = self.resolver.find_ffmpeg()
                self.assertEqual(resolved, str(Path(r"C:\AppData\linkconv\bin\ffmpeg.exe")))

    @patch("shutil.which", return_value=None)
    def test_tier3_imageio_ffmpeg_discovery(self, mock_which) -> None:
        """TC-UT-FFM-05: Tier 3 resolves via imageio-ffmpeg wheel module if present."""
        with patch.object(self.resolver, "get_local_appdata_ffmpeg") as mock_get_local:
            mock_local = MagicMock(spec=Path)
            mock_local.is_file.return_value = False
            mock_get_local.return_value = mock_local

            mock_imageio = MagicMock()
            mock_imageio.get_ffmpeg_exe.return_value = r"C:\Python\site-packages\imageio_ffmpeg\bin\ffmpeg.exe"

            with patch.dict("sys.modules", {"imageio_ffmpeg": mock_imageio}):
                with patch("os.path.isfile", return_value=True):
                    resolved = self.resolver.find_ffmpeg()
                    self.assertEqual(resolved, os.path.abspath(r"C:\Python\site-packages\imageio_ffmpeg\bin\ffmpeg.exe"))

    @patch("shutil.which", return_value=None)
    def test_ensure_ffmpeg_raises_when_all_tiers_fail(self, mock_which) -> None:
        """TC-UT-FFM-06: ensure_ffmpeg raises FFmpegNotFoundError when not found."""
        with patch.object(self.resolver, "get_local_appdata_ffmpeg") as mock_get_local:
            mock_local = MagicMock(spec=Path)
            mock_local.is_file.return_value = False
            mock_get_local.return_value = mock_local

            with patch.dict("sys.modules", {"imageio_ffmpeg": None}):
                with self.assertRaises(FFmpegNotFoundError) as ctx:
                    self.resolver.ensure_ffmpeg(auto_download=False)
                self.assertTrue(len(ctx.exception.searched_locations) > 0)
                self.assertIn("PATH", ctx.exception.user_hint)

    @patch("subprocess.run")
    def test_get_version_standard_string(self, mock_run) -> None:
        """TC-UT-FFM-07: get_version extracts semantic version from ffmpeg -version output."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["ffmpeg", "-version"],
            returncode=0,
            stdout="ffmpeg version 6.1.1-full_build-www.gyan.dev Copyright (c) 2000-2023 the FFmpeg developers",
            stderr="",
        )
        ver = self.resolver.get_version(binary_path=r"C:\Tools\ffmpeg.exe")
        self.assertEqual(ver, "6.1.1-full_build-www.gyan.dev")

    @patch("subprocess.run")
    def test_get_version_git_revision(self, mock_run) -> None:
        """TC-UT-FFM-08: get_version extracts git dev revision."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["ffmpeg", "-version"],
            returncode=0,
            stdout="ffmpeg version n6.1-dev-20240101 Copyright (c) 2000-2024",
            stderr="",
        )
        ver = self.resolver.get_version(binary_path=r"C:\Tools\ffmpeg.exe")
        self.assertEqual(ver, "n6.1-dev-20240101")

    @patch("shutil.which", return_value=None)
    def test_find_ffprobe_alongside_ffmpeg(self, mock_which) -> None:
        """TC-UT-FFM-09: find_ffprobe detects ffprobe located in same folder as ffmpeg."""
        with patch.object(self.resolver, "find_ffmpeg", return_value=r"C:\Tools\bin\ffmpeg.exe"):
            with patch("os.path.isfile", side_effect=lambda p: "ffprobe" in str(p)):
                with patch("os.access", return_value=True):
                    probe = self.resolver.find_ffprobe()
                    self.assertIsNotNone(probe)
                    self.assertIn("ffprobe", probe)

    def test_provision_ffmpeg_extracts_binaries(self) -> None:
        """TC-UT-FFM-10: Tier 4 provisions zip archive extracting ffmpeg and ffprobe."""
        temp_dir = tempfile.mkdtemp(prefix="linkconv_test_prov_")
        try:
            # Create synthetic zip archive containing ffmpeg.exe and ffprobe.exe
            zip_buf = io.BytesIO()
            with zipfile.ZipFile(zip_buf, "w") as zf:
                zf.writestr("bin/ffmpeg.exe", b"SYNTHETIC_FFMPEG_BIN")
                zf.writestr("bin/ffprobe.exe", b"SYNTHETIC_FFPROBE_BIN")
            zip_bytes = zip_buf.getvalue()

            mock_resp = MagicMock()
            mock_resp.headers = {"content-length": str(len(zip_bytes))}
            mock_resp.read.side_effect = [zip_bytes, b""]
            mock_resp.__enter__.return_value = mock_resp

            progress_calls = []

            with patch("urllib.request.urlopen", return_value=mock_resp):
                with patch.object(self.resolver, "get_local_appdata_dir", return_value=Path(temp_dir)):
                    with patch.object(self.resolver, "get_local_appdata_ffmpeg", return_value=Path(temp_dir) / "ffmpeg.exe"):
                        res = self.resolver.provision_ffmpeg(
                            download_url="https://example.com/ffmpeg.zip",
                            progress_hook=lambda pct: progress_calls.append(pct),
                        )
                        self.assertTrue(os.path.samefile(res, Path(temp_dir) / "ffmpeg.exe"))
                        self.assertTrue((Path(temp_dir) / "ffmpeg.exe").exists())
                        self.assertTrue((Path(temp_dir) / "ffprobe.exe").exists())
                        self.assertEqual((Path(temp_dir) / "ffmpeg.exe").read_bytes(), b"SYNTHETIC_FFMPEG_BIN")
                        self.assertTrue(len(progress_calls) > 0)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_helper_getters(self) -> None:
        """TC-UT-FFM-11: get_ffmpeg_path and get_ffprobe_path expose underlying find methods."""
        with patch.object(self.resolver, "find_ffmpeg", return_value="/bin/ffmpeg"):
            with patch.object(self.resolver, "find_ffprobe", return_value="/bin/ffprobe"):
                self.assertEqual(self.resolver.get_ffmpeg_path(), "/bin/ffmpeg")
                self.assertEqual(self.resolver.get_ffprobe_path(), "/bin/ffprobe")


if __name__ == "__main__":
    unittest.main()
