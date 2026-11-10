"""
tests/fixtures/sample_media.py
Synthetic media byte generators and realistic mock platform metadata payloads.
Operates 100% offline with zero external dependencies (pure Python standard library).
"""

import io
import json
import struct
import zipfile
from typing import Dict, Any, List


def create_minimal_jpeg_bytes(width: int = 1, height: int = 1) -> bytes:
    """
    Returns valid minimal binary JPEG image bytes.
    Contains valid SOI, APP0 (JFIF), DQT, SOF0, DHT, SOS, and EOI markers.
    """
    # Minimal 1x1 JPEG byte stream
    return bytes([
        0xFF, 0xD8,  # SOI (Start of Image)
        0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01, 0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00,  # JFIF APP0
        0xFF, 0xDB, 0x00, 0x43, 0x00,  # DQT (Luminance)
        0x08, 0x06, 0x06, 0x07, 0x06, 0x05, 0x08, 0x07, 0x07, 0x07, 0x09, 0x09, 0x08, 0x0A, 0x0C, 0x14,
        0x0D, 0x0C, 0x0B, 0x0B, 0x0C, 0x19, 0x12, 0x13, 0x0F, 0x14, 0x1D, 0x1A, 0x1F, 0x1E, 0x1D, 0x1A,
        0x1C, 0x1C, 0x20, 0x24, 0x2E, 0x27, 0x20, 0x22, 0x2C, 0x23, 0x1C, 0x1C, 0x28, 0x37, 0x29, 0x2C,
        0x30, 0x31, 0x34, 0x34, 0x34, 0x1F, 0x27, 0x39, 0x3D, 0x38, 0x32, 0x3C, 0x2E, 0x33, 0x34, 0x32,
        0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01, 0x00, 0x01, 0x01, 0x01, 0x11, 0x00,  # SOF0 (1x1 grayscale)
        0xFF, 0xC4, 0x00, 0x1F, 0x00, 0x00, 0x01, 0x05, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00,  # DHT (DC)
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0A, 0x0B,
        0xFF, 0xDA, 0x00, 0x08, 0x01, 0x01, 0x00, 0x00, 0x3F, 0x00,  # SOS
        0x7F, 0x00,  # Scan data
        0xFF, 0xD9   # EOI (End of Image)
    ])


def create_placeholder_jpeg_bytes() -> bytes:
    """
    Returns synthetic 120x90 YouTube placeholder JPEG (< 1000 bytes)
    used to test thumbnail cascade fallback.
    """
    raw = create_minimal_jpeg_bytes()
    # Add dummy comment box (COM marker 0xFF 0xFE) to make it ~350 bytes
    comment = b"YouTube Placeholder 120x90 - Not Available"
    com_box = struct.pack(">HH", 0xFFFE, len(comment) + 2) + comment
    # Insert comment before EOI
    return raw[:-2] + com_box + raw[-2:]


def create_minimal_mp3_bytes(title: str = "Test Track", artist: str = "Test Artist") -> bytes:
    """
    Returns valid minimal MP3 byte stream with ID3v2.3 header and valid MPEG-1 Layer 3 audio frames.
    """
    # 1. ID3v2.3 Header
    # Construct TIT2 and TPE1 frames
    def make_id3_frame(frame_id: str, text: str) -> bytes:
        encoded = b"\x00" + text.encode("utf-8")  # 0 = ISO-8859-1 / UTF-8 compatible
        header = frame_id.encode("ascii") + struct.pack(">I", len(encoded)) + b"\x00\x00"
        return header + encoded

    frames = make_id3_frame("TIT2", title) + make_id3_frame("TPE1", artist)
    
    # Syncsafe size calculation for ID3 tag size (7 bits per byte)
    tag_size = len(frames)
    b0 = (tag_size >> 21) & 0x7F
    b1 = (tag_size >> 14) & 0x7F
    b2 = (tag_size >> 7) & 0x7F
    b3 = tag_size & 0x7F
    id3_header = b"ID3\x03\x00\x00" + bytes([b0, b1, b2, b3]) + frames

    # 2. MPEG-1 Layer 3 Audio Frame (128 kbps, 44100 Hz, Stereo)
    # Header: 0xFF, 0xFB, 0x90, 0x64
    # Frame size for 128kbps / 44.1kHz = 144 * 128000 / 44100 = 417 bytes
    frame_header = bytes([0xFF, 0xFB, 0x90, 0x64])
    frame_payload = bytes([0x55] * (417 - len(frame_header)))
    audio_frame = frame_header + frame_payload

    # Emit ID3 tag + 3 consecutive audio frames
    return id3_header + (audio_frame * 3)


def create_minimal_mp4_bytes() -> bytes:
    """
    Returns valid minimal ISO Base Media File Format (MP4) byte stream.
    Contains standard atoms: ftyp (isom/mp42), moov (mvhd, trak), and mdat.
    """
    # ftyp box
    ftyp_payload = b"isom" + struct.pack(">I", 0x00000200) + b"isom" + b"iso2" + b"mp41"
    ftyp_box = struct.pack(">I", 8 + len(ftyp_payload)) + b"ftyp" + ftyp_payload

    # mvhd box inside moov
    mvhd_payload = (
        b"\x00\x00\x00\x00"  # version 0, flags 0
        + struct.pack(">IIII", 0, 0, 1000, 1000)  # creation, mod, timescale=1000, duration=1000 (1.0s)
        + struct.pack(">I", 0x00010000)  # rate 1.0
        + struct.pack(">H", 0x0100)  # volume 1.0
        + b"\x00" * 10  # reserved
        + b"\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"  # matrix (part 1)
        + b"\x00\x00\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00"  # matrix (part 2)
        + b"\x00\x00\x00\x00\x00\x00\x00\x00\x40\x00\x00\x00"  # matrix (part 3)
        + b"\x00" * 24  # pre_defined
        + struct.pack(">I", 2)  # next_track_id = 2
    )
    mvhd_box = struct.pack(">I", 8 + len(mvhd_payload)) + b"mvhd" + mvhd_payload

    # moov box containing mvhd
    moov_payload = mvhd_box
    moov_box = struct.pack(">I", 8 + len(moov_payload)) + b"moov" + moov_payload

    # mdat box
    mdat_payload = b"\x00\x00\x00\x01\x67\x42\x00\x1E" + (b"\xAA" * 128)  # simulated NAL units
    mdat_box = struct.pack(">I", 8 + len(mdat_payload)) + b"mdat" + mdat_payload

    return ftyp_box + moov_box + mdat_box


def create_mock_carousel_zip_bytes(slide_count: int = 3) -> bytes:
    """
    Returns valid ZIP archive containing multiple simulated Instagram carousel slides.
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        manifest = {
            "platform": "instagram",
            "type": "carousel",
            "slide_count": slide_count,
            "slides": []
        }
        for i in range(1, slide_count + 1):
            slide_name = f"slide_{i}.jpg"
            img_data = create_minimal_jpeg_bytes()
            zf.writestr(slide_name, img_data)
            manifest["slides"].append({
                "index": i,
                "filename": slide_name,
                "dimensions": "1080x1080"
            })
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))

    return buffer.getvalue()


# Standardized Mock Payloads for Offline Deterministic Testing
MOCK_METADATA_DATABASE: Dict[str, Dict[str, Any]] = {
    "youtube_video": {
        "id": "dQw4w9WgXcQ",
        "platform": "youtube",
        "original_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "canonical_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "title": "Rick Astley - Never Gonna Give You Up (Official Music Video)",
        "description": "The official video for Never Gonna Give You Up by Rick Astley.",
        "uploader": "Rick Astley",
        "uploader_url": "https://www.youtube.com/user/RickAstleyVEVO",
        "duration": 212.0,
        "thumbnail_url": "/media/thumb.jpg",
        "view_count": 1500000000,
        "like_count": 16000000,
        "tags": ["Rick Astley", "Never Gonna Give You Up", "Pop"],
        "is_live": False,
        "is_playlist": False,
        "formats": [
            {
                "format_id": "137",
                "ext": "mp4",
                "resolution": "1920x1080",
                "width": 1920,
                "height": 1080,
                "fps": 30.0,
                "vcodec": "avc1.640028",
                "acodec": "none",
                "vbr": 4500.0,
                "is_dash": True,
                "needs_muxing": True,
                "url": "/media/sample.mp4"
            },
            {
                "format_id": "136",
                "ext": "mp4",
                "resolution": "1280x720",
                "width": 1280,
                "height": 720,
                "fps": 30.0,
                "vcodec": "avc1.4d401f",
                "acodec": "none",
                "vbr": 2300.0,
                "is_dash": True,
                "needs_muxing": True,
                "url": "/media/sample.mp4"
            },
            {
                "format_id": "140",
                "ext": "m4a",
                "resolution": None,
                "width": None,
                "height": None,
                "fps": None,
                "vcodec": "none",
                "acodec": "mp4a.40.2",
                "abr": 128.0,
                "is_dash": True,
                "needs_muxing": False,
                "url": "/media/sample.mp3"
            },
            {
                "format_id": "251",
                "ext": "webm",
                "resolution": None,
                "width": None,
                "height": None,
                "fps": None,
                "vcodec": "none",
                "acodec": "opus",
                "abr": 160.0,
                "is_dash": True,
                "needs_muxing": False,
                "url": "/media/sample.mp3"
            }
        ],
        "assets": [
            {"asset_type": "thumbnail", "url": "/media/thumb.jpg", "label": "maxresdefault", "dimensions": "1920x1080"},
            {"asset_type": "thumbnail", "url": "/media/thumb_small.jpg", "label": "default", "dimensions": "120x90"}
        ]
    },

    "youtube_shorts": {
        "id": "abc123short",
        "platform": "youtube",
        "original_url": "https://www.youtube.com/shorts/abc123short",
        "canonical_url": "https://www.youtube.com/shorts/abc123short",
        "title": "Incredible Tech Lifehack #shorts",
        "description": "Quick tech tip for everyday users #shorts",
        "uploader": "TechBytes",
        "uploader_url": "https://www.youtube.com/@techbytes",
        "duration": 45.0,
        "thumbnail_url": "/media/thumb.jpg",
        "view_count": 250000,
        "like_count": 12000,
        "tags": ["shorts", "tech", "lifehack"],
        "is_live": False,
        "is_playlist": False,
        "formats": [
            {
                "format_id": "shorts_1080",
                "ext": "mp4",
                "resolution": "1080x1920",
                "width": 1080,
                "height": 1920,
                "fps": 60.0,
                "vcodec": "avc1.64002a",
                "acodec": "mp4a.40.2",
                "is_dash": False,
                "needs_muxing": False,
                "url": "/media/sample.mp4"
            }
        ],
        "assets": [
            {"asset_type": "thumbnail", "url": "/media/thumb.jpg", "label": "poster", "dimensions": "1080x1920"}
        ]
    },

    "youtube_playlist": {
        "id": "PL1234567890",
        "platform": "youtube",
        "original_url": "https://www.youtube.com/playlist?list=PL1234567890",
        "canonical_url": "https://www.youtube.com/playlist?list=PL1234567890",
        "title": "Coding Synthwave Mixtape 2026",
        "description": "Best retro synthwave tracks for programming flow.",
        "uploader": "SynthwaveCollective",
        "duration": 600.0,
        "thumbnail_url": "/media/thumb.jpg",
        "is_live": False,
        "is_playlist": True,
        "playlist_count": 3,
        "playlist_items": [
            {"id": "track_1", "title": "Neon Grid", "duration": 180.0, "url": "https://www.youtube.com/watch?v=track_1"},
            {"id": "track_2", "title": "Cyber Sunset", "duration": 210.0, "url": "https://www.youtube.com/watch?v=track_2"},
            {"id": "track_3", "title": "Digital Horizon", "duration": 210.0, "url": "https://www.youtube.com/watch?v=track_3"}
        ],
        "formats": [],
        "assets": []
    },

    "instagram_reel": {
        "id": "C-j527BStv_",
        "platform": "instagram",
        "original_url": "https://www.instagram.com/reel/C-j527BStv_/",
        "canonical_url": "https://www.instagram.com/reel/C-j527BStv_/",
        "title": "Sunset Timelapse at the Peak 🌄",
        "description": "Captured this stunning golden hour over the mountains #travel #reels",
        "uploader": "mountain_wanderer",
        "uploader_url": "https://www.instagram.com/mountain_wanderer/",
        "duration": 15.0,
        "thumbnail_url": "/media/thumb.jpg",
        "view_count": 89000,
        "like_count": 7400,
        "tags": ["travel", "reels", "nature"],
        "is_live": False,
        "is_playlist": False,
        "formats": [
            {
                "format_id": "reel_hd",
                "ext": "mp4",
                "resolution": "1080x1920",
                "width": 1080,
                "height": 1920,
                "fps": 30.0,
                "vcodec": "avc1.4d4020",
                "acodec": "mp4a.40.2",
                "abr": 128.0,
                "is_dash": False,
                "needs_muxing": False,
                "url": "/media/sample.mp4"
            }
        ],
        "assets": [
            {"asset_type": "thumbnail", "url": "/media/thumb.jpg", "label": "cover", "dimensions": "1080x1920"}
        ]
    },

    "instagram_carousel": {
        "id": "C_carousel987",
        "platform": "instagram",
        "original_url": "https://www.instagram.com/p/C_carousel987/",
        "canonical_url": "https://www.instagram.com/p/C_carousel987/",
        "title": "Architectural Design Gallery — 3 Views",
        "description": "Exploring minimalist modern interior architectures.",
        "uploader": "arch_minimal",
        "uploader_url": "https://www.instagram.com/arch_minimal/",
        "duration": 0.0,
        "thumbnail_url": "/media/thumb.jpg",
        "is_live": False,
        "is_playlist": False,
        "formats": [],
        "assets": [
            {"asset_type": "image", "url": "/media/thumb.jpg", "label": "slide_1", "dimensions": "1080x1080"},
            {"asset_type": "image", "url": "/media/thumb.jpg", "label": "slide_2", "dimensions": "1080x1080"},
            {"asset_type": "image", "url": "/media/thumb.jpg", "label": "slide_3", "dimensions": "1080x1080"}
        ]
    },

    "tiktok_video": {
        "id": "7123456789012345678",
        "platform": "tiktok",
        "original_url": "https://www.tiktok.com/@creator/video/7123456789012345678",
        "canonical_url": "https://www.tiktok.com/@creator/video/7123456789012345678",
        "title": "Coffee art tutorial step by step #barista #coffee",
        "description": "Learn the tulip pour in 30 seconds!",
        "uploader": "creator",
        "uploader_url": "https://www.tiktok.com/@creator",
        "duration": 28.5,
        "thumbnail_url": "/media/thumb.jpg",
        "view_count": 530000,
        "like_count": 48000,
        "tags": ["barista", "coffee", "latteart"],
        "is_live": False,
        "is_playlist": False,
        "formats": [
            {
                "format_id": "download_addr",
                "ext": "mp4",
                "resolution": "1080x1920",
                "width": 1080,
                "height": 1920,
                "fps": 30.0,
                "vcodec": "h264",
                "acodec": "aac",
                "is_dash": False,
                "needs_muxing": False,
                "url": "/media/sample.mp4"
            }
        ],
        "assets": [
            {"asset_type": "thumbnail", "url": "/media/thumb.jpg", "label": "cover", "dimensions": "1080x1920"}
        ]
    },

    "reddit_post": {
        "id": "92pms9",
        "platform": "reddit",
        "original_url": "https://www.reddit.com/r/aww/comments/92pms9/golden_retriever_meets_kitten/",
        "canonical_url": "https://www.reddit.com/r/aww/comments/92pms9/golden_retriever_meets_kitten/",
        "title": "Golden retriever meets kitten for the first time",
        "description": "Heartwarming interaction between puppy and kitten.",
        "uploader": "puppylover2026",
        "uploader_url": "https://www.reddit.com/user/puppylover2026",
        "duration": 34.0,
        "thumbnail_url": "/media/thumb.jpg",
        "view_count": 120000,
        "like_count": 32000,
        "tags": ["aww", "cute", "animals"],
        "is_live": False,
        "is_playlist": False,
        "formats": [
            {
                "format_id": "DASH_720",
                "ext": "mp4",
                "resolution": "1280x720",
                "width": 1280,
                "height": 720,
                "fps": 30.0,
                "vcodec": "avc1.4d401f",
                "acodec": "none",
                "is_dash": True,
                "needs_muxing": True,
                "url": "/media/sample.mp4"
            },
            {
                "format_id": "DASH_audio",
                "ext": "mp4",
                "resolution": None,
                "width": None,
                "height": None,
                "fps": None,
                "vcodec": "none",
                "acodec": "mp4a.40.2",
                "abr": 128.0,
                "is_dash": True,
                "needs_muxing": False,
                "url": "/media/sample.mp3"
            }
        ],
        "assets": [
            {"asset_type": "thumbnail", "url": "/media/thumb.jpg", "label": "poster", "dimensions": "1280x720"}
        ]
    },

    "twitter_video": {
        "id": "1234567890123456789",
        "platform": "twitter",
        "original_url": "https://x.com/tech_insider/status/1234567890123456789",
        "canonical_url": "https://x.com/tech_insider/status/1234567890123456789",
        "title": "SpaceX Starship Launch Replay in 4K",
        "description": "Stunning booster catch from today's Starship flight test.",
        "uploader": "tech_insider",
        "duration": 60.0,
        "thumbnail_url": "/media/thumb.jpg",
        "formats": [
            {
                "format_id": "http-1080p",
                "ext": "mp4",
                "resolution": "1920x1080",
                "width": 1920,
                "height": 1080,
                "vcodec": "h264",
                "acodec": "aac",
                "is_dash": False,
                "needs_muxing": False,
                "url": "/media/sample.mp4"
            }
        ],
        "assets": [{"asset_type": "thumbnail", "url": "/media/thumb.jpg"}]
    },

    "vimeo_video": {
        "id": "987654321",
        "platform": "vimeo",
        "original_url": "https://vimeo.com/987654321",
        "canonical_url": "https://vimeo.com/987654321",
        "title": "Cinematic Drone Reel 2026",
        "description": "Aerial cinematography across Iceland and Norway.",
        "uploader": "AeroFilms",
        "duration": 180.0,
        "thumbnail_url": "/media/thumb.jpg",
        "formats": [
            {
                "format_id": "1080p",
                "ext": "mp4",
                "resolution": "1920x1080",
                "width": 1920,
                "height": 1080,
                "vcodec": "h264",
                "acodec": "aac",
                "is_dash": False,
                "needs_muxing": False,
                "url": "/media/sample.mp4"
            }
        ],
        "assets": [{"asset_type": "thumbnail", "url": "/media/thumb.jpg"}]
    },

    "soundcloud_track": {
        "id": "chill-vibes-2026",
        "platform": "soundcloud",
        "original_url": "https://soundcloud.com/chillbeats/chill-vibes-2026",
        "canonical_url": "https://soundcloud.com/chillbeats/chill-vibes-2026",
        "title": "Midnight Coffee [Lofi Hip Hop]",
        "description": "Relaxing lo-fi beats to study and relax to.",
        "uploader": "chillbeats",
        "duration": 165.0,
        "thumbnail_url": "/media/thumb.jpg",
        "formats": [
            {
                "format_id": "http_mp3",
                "ext": "mp3",
                "resolution": None,
                "vcodec": "none",
                "acodec": "mp3",
                "abr": 320.0,
                "is_dash": False,
                "needs_muxing": False,
                "url": "/media/sample.mp3"
            }
        ],
        "assets": [{"asset_type": "thumbnail", "url": "/media/thumb.jpg"}]
    },

    "generic_video": {
        "id": "direct_sample",
        "platform": "generic",
        "original_url": "https://example.com/videos/sample.mp4",
        "canonical_url": "https://example.com/videos/sample.mp4",
        "title": "Direct HTML5 Video Sample",
        "description": "Direct HTTP MP4 media source",
        "uploader": "example.com",
        "duration": 60.0,
        "thumbnail_url": "/media/thumb.jpg",
        "formats": [
            {
                "format_id": "direct",
                "ext": "mp4",
                "resolution": "1280x720",
                "width": 1280,
                "height": 720,
                "vcodec": "h264",
                "acodec": "aac",
                "is_dash": False,
                "needs_muxing": False,
                "url": "/media/sample.mp4"
            }
        ],
        "assets": []
    }
}
