"""Synthetic yt-dlp info dictionaries representing authentic responses from all platforms.

File: tests/fixtures/synthetic_ytdl.py
"""
from typing import Any, Dict

SAMPLE_YOUTUBE_VIDEO: Dict[str, Any] = {
    "id": "dQw4w9WgXcQ",
    "title": "Rick Astley - Never Gonna Give You Up (Official Music Video)",
    "description": "The official video for Never Gonna Give You Up...",
    "uploader": "Rick Astley",
    "uploader_url": "https://www.youtube.com/@RickAstleyYT",
    "duration": 213.0,
    "view_count": 1500000000,
    "like_count": 17000000,
    "thumbnail": "https://i.ytimg.com/vi/dQw4w9WgXcQ/maxresdefault.jpg",
    "webpage_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "thumbnails": [
        {"url": "https://i.ytimg.com/vi/dQw4w9WgXcQ/default.jpg", "width": 120, "height": 90},
        {"url": "https://i.ytimg.com/vi/dQw4w9WgXcQ/maxresdefault.jpg", "width": 1920, "height": 1080},
    ],
    "formats": [
        # DASH Video-only 1080p (AVC)
        {
            "format_id": "137",
            "ext": "mp4",
            "resolution": "1920x1080",
            "width": 1920,
            "height": 1080,
            "fps": 30.0,
            "vcodec": "avc1.640028",
            "acodec": "none",
            "vbr": 2500.0,
            "abr": None,
            "filesize": 65000000,
            "url": "https://rr1---sn-mock.googlevideo.com/videoplayback?itag=137",
            "protocol": "https",
        },
        # DASH Audio-only Opus
        {
            "format_id": "251",
            "ext": "webm",
            "resolution": "audio only",
            "width": None,
            "height": None,
            "fps": None,
            "vcodec": "none",
            "acodec": "opus",
            "vbr": None,
            "abr": 160.0,
            "filesize": 4200000,
            "url": "https://rr1---sn-mock.googlevideo.com/videoplayback?itag=251",
            "protocol": "https",
        },
        # Progressive 720p (Video + Audio)
        {
            "format_id": "22",
            "ext": "mp4",
            "resolution": "1280x720",
            "width": 1280,
            "height": 720,
            "fps": 30.0,
            "vcodec": "avc1.64001F",
            "acodec": "mp4a.40.2",
            "vbr": 1200.0,
            "abr": 128.0,
            "filesize": 32000000,
            "url": "https://rr1---sn-mock.googlevideo.com/videoplayback?itag=22",
            "protocol": "https",
        },
    ],
    "subtitles": {
        "en": [{"ext": "vtt", "url": "https://www.youtube.com/api/timedtext?lang=en"}]
    },
    "chapters": [
        {"start_time": 0.0, "end_time": 45.0, "title": "Intro"},
        {"start_time": 45.0, "end_time": 213.0, "title": "Main Song"},
    ],
    "tags": ["Rick Astley", "Pop", "80s"],
}

SAMPLE_INSTAGRAM_CAROUSEL: Dict[str, Any] = {
    "_type": "playlist",
    "id": "C_abcdef123",
    "title": "Weekend photo dump",
    "uploader": "test_creator",
    "webpage_url": "https://www.instagram.com/p/C_abcdef123/",
    "entries": [
        {
            "id": "C_slide1",
            "url": "https://instagram.mock/slide1.jpg",
            "thumbnail": "https://instagram.mock/slide1.jpg",
            "width": 1080,
            "height": 1080,
        },
        {
            "id": "C_slide2",
            "thumbnail": "https://instagram.mock/slide2_thumb.jpg",
            "formats": [
                {
                    "format_id": "mp4_hd",
                    "ext": "mp4",
                    "width": 1080,
                    "height": 1920,
                    "vcodec": "h264",
                    "acodec": "aac",
                    "url": "https://instagram.mock/slide2.mp4",
                }
            ],
        },
        {
            "id": "C_slide3",
            "url": "https://instagram.mock/slide3.jpg",
            "thumbnail": "https://instagram.mock/slide3.jpg",
            "width": 1080,
            "height": 1350,
        },
    ],
}

SAMPLE_REDDIT_VIDEO: Dict[str, Any] = {
    "id": "abc123reddit",
    "title": "Cute cat jumping off couch",
    "uploader": "cat_lover",
    "webpage_url": "https://www.reddit.com/r/aww/comments/abc123reddit/",
    "formats": [
        {
            "format_id": "dash-1080",
            "ext": "mp4",
            "resolution": "1920x1080",
            "width": 1920,
            "height": 1080,
            "vcodec": "h264",
            "acodec": "none",
            "protocol": "http_dash_segments",
            "url": "https://v.redd.it/abc123reddit/DASH_1080.mp4",
        },
        {
            "format_id": "dash-audio",
            "ext": "mp4",
            "resolution": "audio only",
            "vcodec": "none",
            "acodec": "aac",
            "protocol": "http_dash_segments",
            "url": "https://v.redd.it/abc123reddit/DASH_audio.mp4",
        },
    ],
}

SAMPLE_TIKTOK_VIDEO: Dict[str, Any] = {
    "id": "7123456789012345678",
    "title": "Viral dance trend",
    "uploader": "dance_star",
    "duration": 15.0,
    "thumbnail": "https://tiktok.mock/thumb.jpg",
    "webpage_url": "https://www.tiktok.com/@dance_star/video/7123456789012345678",
    "formats": [
        {
            "format_id": "play_addr",
            "ext": "mp4",
            "resolution": "1080x1920",
            "width": 1080,
            "height": 1920,
            "vcodec": "h264",
            "acodec": "aac",
            "url": "https://tiktok.mock/video.mp4",
        }
    ],
}

SAMPLE_TWITTER_VIDEO: Dict[str, Any] = {
    "id": "1712345678901234567",
    "title": "Exciting game clip",
    "uploader": "game_hub",
    "duration": 30.0,
    "thumbnail": "https://twitter.mock/thumb.jpg",
    "webpage_url": "https://x.com/game_hub/status/1712345678901234567",
    "formats": [
        {
            "format_id": "http-2176",
            "ext": "mp4",
            "resolution": "1280x720",
            "width": 1280,
            "height": 720,
            "vcodec": "h264",
            "acodec": "aac",
            "vbr": 2176.0,
            "url": "https://twitter.mock/vid_720.mp4",
        }
    ],
}

SAMPLE_VIMEO_VIDEO: Dict[str, Any] = {
    "id": "76979871",
    "title": "Cinematic Short",
    "uploader": "indie_director",
    "duration": 480.0,
    "thumbnail": "https://vimeo.mock/thumb.jpg",
    "webpage_url": "https://vimeo.com/76979871",
    "formats": [
        {
            "format_id": "http-1080p",
            "ext": "mp4",
            "resolution": "1920x1080",
            "width": 1920,
            "height": 1080,
            "vcodec": "h264",
            "acodec": "aac",
            "url": "https://vimeo.mock/1080p.mp4",
        }
    ],
}

SAMPLE_SOUNDCLOUD_TRACK: Dict[str, Any] = {
    "id": "track_12345",
    "title": "Summer Vibes",
    "uploader": "cool_dj",
    "duration": 185.0,
    "thumbnail": "https://soundcloud.mock/art_500x500.jpg",
    "webpage_url": "https://soundcloud.com/cool_dj/summer-vibes",
    "formats": [
        {
            "format_id": "http_mp3_128",
            "ext": "mp3",
            "abr": 128.0,
            "vcodec": "none",
            "acodec": "mp3",
            "url": "https://soundcloud.mock/stream.mp3",
        }
    ],
}
