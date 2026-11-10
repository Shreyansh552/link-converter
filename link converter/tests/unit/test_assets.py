"""Unit tests for MediaAssetService.

File: tests/unit/test_assets.py
"""
import asyncio
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import zipfile

src_path = str(Path(__file__).resolve().parent.parent.parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

import httpx

from linkconv.core.exceptions import ContentNotFoundError, DownloadError
from linkconv.core.models import MediaAsset, MediaMetadata, Platform
from linkconv.services.assets import MediaAssetService


class TestMediaAssetService(unittest.TestCase):
    """Unit test suite for MediaAssetService."""

    def setUp(self) -> None:
        self.service = MediaAssetService()
        self.test_dir = tempfile.mkdtemp(prefix="linkconv_test_assets_")

    def tearDown(self) -> None:
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_cascade_ordering_contract(self) -> None:
        """TC-UT-AST-01: Verifies YouTube thumbnail cascade priority ordering."""
        order = [tier[0] for tier in self.service.YOUTUBE_CASCADE]
        self.assertEqual(order[0], "maxresdefault.jpg")
        self.assertEqual(order[1], "sddefault.jpg")
        self.assertEqual(order[2], "hqdefault.jpg")
        self.assertEqual(order[3], "mqdefault.jpg")
        self.assertEqual(order[4], "default.jpg")

    def test_placeholder_threshold_detection(self) -> None:
        """TC-UT-AST-02: Detects fake YouTube gray placeholders < 2000 bytes."""
        # 1050 bytes placeholder
        self.assertTrue(self.service.is_placeholder_thumbnail(content_length=1050))
        self.assertTrue(self.service.is_placeholder_thumbnail(content_bytes=b"X" * 1500))

        # 45000 bytes real thumbnail
        self.assertFalse(self.service.is_placeholder_thumbnail(content_length=45000))
        self.assertFalse(self.service.is_placeholder_thumbnail(content_bytes=b"X" * 25000))

    def test_youtube_cascade_resolution_success(self) -> None:
        """TC-UT-AST-03: Resolves highest quality maxresdefault when available (>2000 bytes)."""
        mock_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"content-length": "85000"}
        mock_client.head.return_value = mock_resp

        asset = asyncio.run(self.service.resolve_youtube_thumbnail("dQw4w9WgXcQ", client=mock_client))
        self.assertEqual(asset.label, "maxresdefault")
        self.assertIn("maxresdefault.jpg", asset.url)
        self.assertEqual(asset.dimensions, "1920x1080")

    def test_youtube_cascade_skips_placeholder(self) -> None:
        """TC-UT-AST-04: Skips maxresdefault when placeholder detected (<2000B) and falls back to sddefault."""
        mock_client = AsyncMock()

        # maxresdefault returns 200 but content-length is 1097 (placeholder)
        resp_maxres = MagicMock()
        resp_maxres.status_code = 200
        resp_maxres.headers = {"content-length": "1097"}

        # sddefault returns valid 200 with 42000 bytes
        resp_sd = MagicMock()
        resp_sd.status_code = 200
        resp_sd.headers = {"content-length": "42000"}

        mock_client.head.side_effect = [resp_maxres, resp_sd]

        asset = asyncio.run(self.service.resolve_youtube_thumbnail("dQw4w9WgXcQ", client=mock_client))
        self.assertEqual(asset.label, "sddefault")
        self.assertIn("sddefault.jpg", asset.url)
        self.assertEqual(asset.dimensions, "640x480")

    def test_youtube_cascade_handles_404_and_403(self) -> None:
        """TC-UT-AST-05: Cascades past 404/403 responses down to available tier."""
        mock_client = AsyncMock()

        resp_404 = MagicMock()
        resp_404.status_code = 404

        resp_403 = MagicMock()
        resp_403.status_code = 403

        resp_hq = MagicMock()
        resp_hq.status_code = 200
        resp_hq.headers = {"content-length": "28000"}

        mock_client.head.side_effect = [resp_404, resp_403, resp_hq]

        asset = asyncio.run(self.service.resolve_youtube_thumbnail("dQw4w9WgXcQ", client=mock_client))
        self.assertEqual(asset.label, "hqdefault")
        self.assertIn("hqdefault.jpg", asset.url)

    def test_youtube_cascade_full_fallback(self) -> None:
        """TC-UT-AST-06: Falls back to default.jpg when all head checks fail."""
        mock_client = AsyncMock()
        resp_404 = MagicMock()
        resp_404.status_code = 404
        mock_client.head.return_value = resp_404

        asset = asyncio.run(self.service.resolve_youtube_thumbnail("unknown_id", client=mock_client))
        self.assertEqual(asset.label, "default")
        self.assertIn("default.jpg", asset.url)
        self.assertEqual(asset.dimensions, "120x90")

    def test_sanitize_filename_windows_illegal_chars(self) -> None:
        """TC-UT-AST-07: Sanitizes all Windows reserved characters < > : \" / \\ | ? * to _."""
        dirty = '<Illegal>: "Video" / Path \\ Pipe | Query? Asterisk*.jpg'
        clean = self.service.sanitize_filename(dirty)
        for char in '<>:"/\\|?*':
            self.assertNotIn(char, clean)
        self.assertTrue(clean.endswith(".jpg"))

    def test_sanitize_filename_reserved_device_names(self) -> None:
        """TC-UT-AST-08: Prefixes Windows reserved device names (CON, PRN, AUX, NUL)."""
        self.assertEqual(self.service.sanitize_filename("CON.jpg"), "_CON.jpg")
        self.assertEqual(self.service.sanitize_filename("PRN.png"), "_PRN.png")
        self.assertEqual(self.service.sanitize_filename("aux.webp"), "_aux.webp")
        self.assertEqual(self.service.sanitize_filename("NUL"), "_NUL")

    def test_sanitize_filename_length_boundary(self) -> None:
        """TC-UT-AST-09: Truncates long filenames to max_length while preserving extension."""
        long_stem = "A" * 300 + ".png"
        clean = self.service.sanitize_filename(long_stem, max_length=100)
        self.assertLessEqual(len(clean), 100)
        self.assertTrue(clean.endswith(".png"))

    def test_sanitize_filename_trailing_dots_spaces(self) -> None:
        """TC-UT-AST-10: Strips trailing dots and spaces that break Windows filesystem APIs."""
        dirty = "filename with trailing dots and spaces...   "
        clean = self.service.sanitize_filename(dirty)
        self.assertFalse(clean.endswith("."))
        self.assertFalse(clean.endswith(" "))

    def test_download_image_with_mime_extension_inference(self) -> None:
        """TC-UT-AST-11: Infers .png extension from Content-Type image/png when URL lacks extension."""
        mock_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"FAKE_PNG_BINARY_DATA"
        mock_resp.headers = {"content-type": "image/png; charset=utf-8"}
        mock_client.get.return_value = mock_resp

        with patch.object(self.service, "_get_client", return_value=mock_client):
            out_file = asyncio.run(
                self.service.download_image(
                    url="https://example.com/avatar_no_ext",
                    destination_dir=self.test_dir,
                    filename="avatar",
                )
            )
            self.assertTrue(out_file.exists())
            self.assertTrue(str(out_file).endswith(".png"))
            self.assertEqual(out_file.read_bytes(), b"FAKE_PNG_BINARY_DATA")

    def test_download_image_not_found_raises_exception(self) -> None:
        """TC-UT-AST-12: HTTP 404 raises ContentNotFoundError."""
        mock_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_client.get.return_value = mock_resp

        with patch.object(self.service, "_get_client", return_value=mock_client):
            with self.assertRaises(ContentNotFoundError):
                asyncio.run(
                    self.service.download_image(
                        url="https://example.com/missing.jpg",
                        destination_dir=self.test_dir,
                    )
                )

    def test_download_image_empty_raises_exception(self) -> None:
        """TC-UT-AST-13: 0 bytes response body raises DownloadError."""
        mock_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b""
        mock_client.get.return_value = mock_resp

        with patch.object(self.service, "_get_client", return_value=mock_client):
            with self.assertRaises(DownloadError):
                asyncio.run(
                    self.service.download_image(
                        url="https://example.com/empty.jpg",
                        destination_dir=self.test_dir,
                    )
                )

    def test_create_carousel_zip_bytes_manifest_structure(self) -> None:
        """TC-UT-AST-14: Bundles slides into ZIP with manifest.json and numbered slide files."""
        meta = MediaMetadata(
            id="C_123xyz",
            platform=Platform.INSTAGRAM,
            original_url="https://instagram.com/p/C_123xyz",
            canonical_url="https://instagram.com/p/C_123xyz",
            title="Carousel Post",
            assets=[
                MediaAsset(asset_type="image", url="https://example.com/slide1.jpg", slide_index=0, dimensions="1080x1080"),
                MediaAsset(asset_type="image", url="https://example.com/slide2.jpg", slide_index=1, dimensions="1080x1080"),
                MediaAsset(asset_type="video", url="https://example.com/slide3.mp4", slide_index=2, dimensions="1080x1350"),
            ],
        )

        mock_client = AsyncMock()

        def fake_get(url):
            m = MagicMock()
            m.status_code = 200
            m.content = f"DATA_FOR_{url}".encode("utf-8")
            return m

        mock_client.get.side_effect = fake_get

        with patch.object(self.service, "_get_client", return_value=mock_client):
            zip_bytes = asyncio.run(self.service.create_carousel_zip_bytes(meta))

        self.assertTrue(len(zip_bytes) > 0)
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            namelist = zf.namelist()
            self.assertIn("manifest.json", namelist)
            self.assertIn("slide_1.jpg", namelist)
            self.assertIn("slide_2.jpg", namelist)
            self.assertIn("slide_3.mp4", namelist)

            manifest_data = json.loads(zf.read("manifest.json").decode("utf-8"))
            self.assertEqual(manifest_data["type"], "carousel")
            self.assertEqual(manifest_data["slide_count"], 3)
            self.assertEqual(len(manifest_data["slides"]), 3)

    def test_bundle_carousel_zip_writes_file_to_disk(self) -> None:
        """TC-UT-AST-15: Writes carousel ZIP directly to disk and returns Path."""
        meta = MediaMetadata(
            id="C_disk_test",
            platform=Platform.INSTAGRAM,
            original_url="https://instagram.com/p/C_disk_test",
            canonical_url="https://instagram.com/p/C_disk_test",
            title="Disk Carousel",
            assets=[
                MediaAsset(asset_type="image", url="https://example.com/s1.jpg", slide_index=0),
            ],
        )

        mock_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"JPEG_BYTES"
        mock_client.get.return_value = mock_resp

        with patch.object(self.service, "_get_client", return_value=mock_client):
            zip_file = asyncio.run(self.service.bundle_carousel_zip(meta, output_dir=self.test_dir))
            self.assertTrue(zip_file.exists())
            self.assertTrue(str(zip_file).endswith(".zip"))
            self.assertGreater(zip_file.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
