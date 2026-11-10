"""Embed Formatter Service for generating Markdown, responsive iframes, oEmbed, and BBCode.

File: src/linkconv/services/embeds.py
"""
from __future__ import annotations

import html
import re
from typing import Any, Dict, Optional
import xml.etree.ElementTree as ET

from linkconv.core.models import MediaMetadata, Platform


class EmbedFormatterService:
    """Generates standard embed codes and metadata formats across platforms."""

    PROVIDER_URLS = {
        Platform.YOUTUBE: "https://www.youtube.com/",
        Platform.INSTAGRAM: "https://www.instagram.com/",
        Platform.TIKTOK: "https://www.tiktok.com/",
        Platform.TWITTER: "https://twitter.com/",
        Platform.FACEBOOK: "https://www.facebook.com/",
        Platform.REDDIT: "https://www.reddit.com/",
        Platform.PINTEREST: "https://www.pinterest.com/",
        Platform.VIMEO: "https://vimeo.com/",
        Platform.SOUNDCLOUD: "https://soundcloud.com/",
        Platform.GENERIC: "https://example.com/",
    }

    def _resolve_embed_url(self, metadata: MediaMetadata) -> str:
        """Determines platform privacy-enhanced embed URL."""
        plat = metadata.platform
        media_id = metadata.id

        if plat == Platform.YOUTUBE:
            return f"https://www.youtube-nocookie.com/embed/{media_id}?rel=0"
        elif plat == Platform.VIMEO:
            return f"https://player.vimeo.com/video/{media_id}?dnt=1"
        elif plat == Platform.INSTAGRAM:
            return f"https://www.instagram.com/p/{media_id}/embed/"
        elif plat == Platform.TIKTOK:
            return f"https://www.tiktok.com/embed/v2/{media_id}"
        return metadata.canonical_url or metadata.original_url

    def to_markdown(self, metadata: MediaMetadata) -> str:
        """Generates clickable Markdown preview link with thumbnail and title."""
        title = metadata.title or "Watch Media"
        clean_title = title.replace("[", "\\[").replace("]", "\\]")
        thumb_url = metadata.thumbnail_url or ""
        target_url = metadata.canonical_url or metadata.original_url

        return f"[![{clean_title}]({thumb_url})]({target_url})"

    def to_html_iframe(
        self,
        metadata: MediaMetadata,
        responsive: bool = True,
        width: int = 560,
        height: int = 315,
    ) -> str:
        """Generates responsive, privacy-friendly iframe HTML embed code."""
        embed_url = self._resolve_embed_url(metadata)
        escaped_title = html.escape(metadata.title or "Embedded media", quote=True)
        escaped_url = html.escape(embed_url, quote=True)

        # Detect vertical video (e.g. YouTube Shorts, Instagram Reels, TikTok)
        is_vertical = False
        if metadata.platform in (Platform.TIKTOK,):
            is_vertical = True
        elif metadata.formats:
            best_fmt = metadata.best_video_format()
            if best_fmt and best_fmt.width and best_fmt.height:
                if best_fmt.height > best_fmt.width:
                    is_vertical = True

        padding_bottom = "177.78%" if is_vertical else "56.25%"

        if responsive:
            return (
                f'<div class="linkconv-embed-container" style="position: relative; '
                f'padding-bottom: {padding_bottom}; height: 0; overflow: hidden; max-width: 100%; border-radius: 8px;">'
                f'<iframe style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; border: 0;" '
                f'src="{escaped_url}" title="{escaped_title}" '
                f'allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" '
                f'allowfullscreen loading="lazy"></iframe></div>'
            )

        return (
            f'<iframe width="{width}" height="{height}" src="{escaped_url}" title="{escaped_title}" '
            f'frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" '
            f'allowfullscreen loading="lazy"></iframe>'
        )

    def to_oembed_json(
        self,
        metadata: MediaMetadata,
        maxwidth: Optional[int] = None,
        maxheight: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Generates standardized oEmbed 1.0 JSON payload."""
        embed_html = self.to_html_iframe(metadata, responsive=False)
        provider_name = (
            metadata.platform.display_name
            if hasattr(metadata.platform, "display_name")
            else str(metadata.platform).capitalize()
        )
        provider_url = self.PROVIDER_URLS.get(metadata.platform, "https://example.com/")

        # Determine dimensions
        w = maxwidth or 1920
        h = maxheight or 1080
        if metadata.formats:
            best_fmt = metadata.best_video_format()
            if best_fmt and best_fmt.width and best_fmt.height:
                w = min(best_fmt.width, maxwidth) if maxwidth else best_fmt.width
                h = min(best_fmt.height, maxheight) if maxheight else best_fmt.height

        return {
            "version": "1.0",
            "type": "video",
            "provider_name": provider_name,
            "provider_url": provider_url,
            "title": metadata.title,
            "author_name": metadata.uploader,
            "author_url": metadata.uploader_url,
            "html": embed_html,
            "width": w,
            "height": h,
            "thumbnail_url": metadata.thumbnail_url,
            "thumbnail_width": w,
            "thumbnail_height": h,
        }

    def to_oembed_xml(self, metadata: MediaMetadata) -> str:
        """Generates standardized oEmbed 1.0 XML string."""
        data = self.to_oembed_json(metadata)
        root = ET.Element("oembed")

        ET.SubElement(root, "version").text = data.get("version", "1.0")
        ET.SubElement(root, "type").text = data.get("type", "video")
        ET.SubElement(root, "provider_name").text = data.get("provider_name", "")
        ET.SubElement(root, "provider_url").text = data.get("provider_url", "")
        ET.SubElement(root, "title").text = data.get("title", "")

        if data.get("author_name"):
            ET.SubElement(root, "author_name").text = str(data["author_name"])
        if data.get("author_url"):
            ET.SubElement(root, "author_url").text = str(data["author_url"])

        ET.SubElement(root, "url").text = metadata.canonical_url or metadata.original_url
        ET.SubElement(root, "width").text = str(data.get("width", 1920))
        ET.SubElement(root, "height").text = str(data.get("height", 1080))
        ET.SubElement(root, "html").text = data.get("html", "")

        if data.get("thumbnail_url"):
            ET.SubElement(root, "thumbnail_url").text = str(data["thumbnail_url"])

        xml_declaration = '<?xml version="1.0" encoding="utf-8" standalone="yes"?>\n'
        xml_body = ET.tostring(root, encoding="utf-8").decode("utf-8")
        return xml_declaration + xml_body

    def to_bbcode(self, metadata: MediaMetadata, mode: str = "linked_image") -> str:
        """Generates forum BBCode syntax."""
        target_url = metadata.canonical_url or metadata.original_url
        if mode == "video":
            return f"[video]{target_url}[/video]"

        thumb_url = metadata.thumbnail_url or ""
        return f"[url={target_url}][img]{thumb_url}[/img][/url]"
