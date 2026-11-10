"""Unit tests for EmbedFormatterService.

File: tests/unit/test_embeds.py
"""
import html
from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET

src_path = str(Path(__file__).resolve().parent.parent.parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from linkconv.core.models import MediaFormat, MediaMetadata, Platform
from linkconv.services.embeds import EmbedFormatterService


class TestEmbedFormatterService(unittest.TestCase):
    """Unit test suite for EmbedFormatterService."""

    def setUp(self) -> None:
        self.formatter = EmbedFormatterService()
        self.sample_meta = MediaMetadata(
            id="dQw4w9WgXcQ",
            platform=Platform.YOUTUBE,
            original_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            canonical_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            title="Rick Astley - Never Gonna Give You Up",
            uploader="RickAstleyVEVO",
            uploader_url="https://www.youtube.com/@RickAstleyVEVO",
            thumbnail_url="https://i.ytimg.com/vi/dQw4w9WgXcQ/maxresdefault.jpg",
            duration=212.0,
            formats=[
                MediaFormat(
                    format_id="1080p",
                    ext="mp4",
                    width=1920,
                    height=1080,
                    vcodec="avc1",
                    acodec="aac",
                )
            ],
        )

    def test_to_markdown_youtube_syntax(self) -> None:
        """TC-UT-EMB-01: Generates clickable Markdown preview [![Title](thumb)](url)."""
        md = self.formatter.to_markdown(self.sample_meta)
        self.assertTrue(md.startswith("[!["))
        self.assertIn("Never Gonna Give You Up", md)
        self.assertIn(self.sample_meta.thumbnail_url, md)
        self.assertTrue(md.endswith(f"]({self.sample_meta.canonical_url})"))

    def test_to_markdown_bracket_escaping(self) -> None:
        """TC-UT-EMB-02: Escapes square brackets in title to prevent Markdown link truncation."""
        meta = self.sample_meta.model_copy(update={"title": "Song [Official Video] (4K 60fps) [Remastered]"})
        md = self.formatter.to_markdown(meta)
        self.assertIn("\\[Official Video\\]", md)
        self.assertIn("\\[Remastered\\]", md)

    def test_to_markdown_missing_thumbnail(self) -> None:
        """TC-UT-EMB-03: Gracefully formats Markdown when thumbnail_url is missing."""
        meta = self.sample_meta.model_copy(update={"thumbnail_url": None})
        md = self.formatter.to_markdown(meta)
        self.assertTrue(md.startswith("[!["))
        self.assertIn("Never Gonna Give You Up", md)

    def test_to_html_iframe_responsive_youtube(self) -> None:
        """TC-UT-EMB-04: Generates responsive container with youtube-nocookie.com privacy host."""
        iframe_html = self.formatter.to_html_iframe(self.sample_meta, responsive=True)
        self.assertIn("youtube-nocookie.com/embed/dQw4w9WgXcQ?rel=0", iframe_html)
        self.assertIn("padding-bottom: 56.25%", iframe_html)
        self.assertIn("allowfullscreen", iframe_html)
        self.assertIn("linkconv-embed-container", iframe_html)

    def test_to_html_iframe_responsive_vertical_shorts(self) -> None:
        """TC-UT-EMB-05: Emits 9:16 vertical padding (177.78%) for vertical formats / TikTok."""
        vertical_meta = self.sample_meta.model_copy(
            update={
                "platform": Platform.TIKTOK,
                "formats": [
                    MediaFormat(
                        format_id="vertical_1080",
                        ext="mp4",
                        width=1080,
                        height=1920,
                        vcodec="h264",
                        acodec="aac",
                    )
                ],
            }
        )
        iframe_html = self.formatter.to_html_iframe(vertical_meta, responsive=True)
        self.assertIn("padding-bottom: 177.78%", iframe_html)

    def test_to_html_iframe_fixed_dimensions(self) -> None:
        """TC-UT-EMB-06: When responsive=False, renders fixed width and height attributes."""
        iframe_html = self.formatter.to_html_iframe(self.sample_meta, responsive=False, width=640, height=360)
        self.assertIn('width="640"', iframe_html)
        self.assertIn('height="360"', iframe_html)
        self.assertNotIn("linkconv-embed-container", iframe_html)

    def test_to_html_iframe_xss_sanitization(self) -> None:
        """TC-UT-EMB-07: HTML entities escaped to prevent script injection in titles or URLs."""
        xss_meta = self.sample_meta.model_copy(
            update={"title": '<script>alert("XSS")</script>&"\'<img onerror=hack>'}
        )
        iframe_html = self.formatter.to_html_iframe(xss_meta)
        self.assertNotIn("<script>", iframe_html)
        self.assertNotIn("<img", iframe_html)
        self.assertIn("&lt;script&gt;", iframe_html)

    def test_to_html_iframe_vimeo_dnt(self) -> None:
        """TC-UT-EMB-08: Vimeo embeds use dnt=1 Do Not Track flag."""
        vimeo_meta = MediaMetadata(
            id="76979871",
            platform=Platform.VIMEO,
            original_url="https://vimeo.com/76979871",
            canonical_url="https://vimeo.com/76979871",
            title="Vimeo Short Film",
        )
        iframe_html = self.formatter.to_html_iframe(vimeo_meta)
        self.assertIn("player.vimeo.com/video/76979871?dnt=1", iframe_html)

    def test_to_html_iframe_instagram_embed(self) -> None:
        """TC-UT-EMB-09: Instagram reels/posts use /embed/ iframe path."""
        ig_meta = MediaMetadata(
            id="C-j527BStv_",
            platform=Platform.INSTAGRAM,
            original_url="https://www.instagram.com/reel/C-j527BStv_/",
            canonical_url="https://www.instagram.com/reel/C-j527BStv_/",
            title="Instagram Reel",
        )
        iframe_html = self.formatter.to_html_iframe(ig_meta)
        self.assertIn("instagram.com/p/C-j527BStv_/embed/", iframe_html)

    def test_to_oembed_json_schema_compliance(self) -> None:
        """TC-UT-EMB-10: Validates oEmbed 1.0 JSON format schema compliance."""
        data = self.formatter.to_oembed_json(self.sample_meta)
        self.assertEqual(data["version"], "1.0")
        self.assertEqual(data["type"], "video")
        self.assertEqual(data["provider_name"], "YouTube")
        self.assertEqual(data["provider_url"], "https://www.youtube.com/")
        self.assertEqual(data["title"], self.sample_meta.title)
        self.assertEqual(data["author_name"], self.sample_meta.uploader)
        self.assertEqual(data["author_url"], self.sample_meta.uploader_url)
        self.assertIn("<iframe", data["html"])
        self.assertEqual(data["width"], 1920)
        self.assertEqual(data["height"], 1080)
        self.assertEqual(data["thumbnail_url"], self.sample_meta.thumbnail_url)

    def test_to_oembed_json_custom_dimensions(self) -> None:
        """TC-UT-EMB-11: Custom maxwidth and maxheight constrain output dimensions."""
        data = self.formatter.to_oembed_json(self.sample_meta, maxwidth=800, maxheight=450)
        self.assertLessEqual(data["width"], 800)
        self.assertLessEqual(data["height"], 450)

    def test_to_oembed_xml_well_formed(self) -> None:
        """TC-UT-EMB-12: Emits well-formed XML string with valid XML declaration and oembed root."""
        xml_str = self.formatter.to_oembed_xml(self.sample_meta)
        self.assertTrue(xml_str.startswith('<?xml version="1.0"'))
        root = ET.fromstring(xml_str)
        self.assertEqual(root.tag, "oembed")
        self.assertEqual(root.find("version").text, "1.0")
        self.assertEqual(root.find("provider_name").text, "YouTube")
        self.assertEqual(root.find("title").text, self.sample_meta.title)

    def test_to_bbcode_linked_image(self) -> None:
        """TC-UT-EMB-13: Default BBCode produces [url=...][img]...[/img][/url]."""
        bbcode = self.formatter.to_bbcode(self.sample_meta, mode="linked_image")
        self.assertTrue(bbcode.startswith(f"[url={self.sample_meta.canonical_url}][img]"))
        self.assertIn(self.sample_meta.thumbnail_url, bbcode)
        self.assertTrue(bbcode.endswith("[/img][/url]"))

    def test_to_bbcode_video_mode(self) -> None:
        """TC-UT-EMB-14: Video mode BBCode produces [video]...[/video]."""
        bbcode = self.formatter.to_bbcode(self.sample_meta, mode="video")
        self.assertEqual(bbcode, f"[video]{self.sample_meta.canonical_url}[/video]")


if __name__ == "__main__":
    unittest.main()
