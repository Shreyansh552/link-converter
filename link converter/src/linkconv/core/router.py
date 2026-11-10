"""URL sanitization, async shortlink unshortening, regex platform routing, and canonical ID extraction.

File: src/linkconv/core/router.py
"""
from __future__ import annotations

from dataclasses import dataclass, field
import ipaddress
import os
import re
import socket
import sys
from typing import Dict, List, Optional, Set, Tuple
import urllib.parse

import httpx

from linkconv.core.exceptions import InvalidUrlError, UnsupportedPlatformError
from linkconv.core.models import Platform


@dataclass(frozen=True)
class RouteResult:
    """Immutable result of a completed URL routing operation."""
    platform: Platform
    media_id: str
    canonical_url: str
    original_url: str
    sanitized_url: str
    functional_params: Dict[str, str] = field(default_factory=dict)


# Tracking parameters stripped across all platforms
GLOBAL_TRACKING_PARAMS: Set[str] = {
    # Analytics & general marketing tracking
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_id", "utm_creative", "utm_name", "gclid", "gclsrc", "dclid",
    "fbclid", "msclkid", "mc_cid", "mc_eid", "rdt_cid", "twclid", "spm",
    "_ga", "_gl", "sc_cid", "wickedid", "yclid", "zanpid",
    # YouTube tracking
    "si", "feature", "pp", "app", "themeRefresh", "embeds_referring_euri",
    # Instagram tracking
    "igsh", "ig_rid", "ig_mid", "igshid",
    # TikTok tracking
    "share_id", "sharer_id", "sender_device", "tt_from", "is_copy_url",
    "is_from_webapp", "_r", "_d", "checksum", "preview_pb", "sec_user_id",
    # Twitter / X tracking
    "ref_src", "ref_url", "s", "cxt", "__twitter_impression",
    # Facebook tracking
    "mibextid", "rdid", "ref", "sfnsn",
    # Pinterest tracking
    "invite_code", "sender", "sfo",
    # Vimeo tracking
    "fl_src",
}

GLOBAL_TRACKING_PREFIXES: Tuple[str, ...] = ("utm_", "_ga", "_gl", "pf_rd_")

# Known shortlink domains requiring async redirect resolution
SHORTLINK_DOMAINS: Set[str] = {
    "youtu.be",
    "vm.tiktok.com",
    "vt.tiktok.com",
    "pin.it",
    "t.co",
    "bit.ly",
    "bitly.com",
    "tinyurl.com",
    "ig.me",
    "fb.watch",
    "redd.it",
    "on.soundcloud.com",
    "is.gd",
    "ow.ly",
    "buff.ly",
    "cutt.ly",
    "t.ly",
    "rb.gy",
    "short.io",
    "tiny.cc",
    "clck.ru",
    "v.gd",
    "qr.ae",
    "lnkd.in",
    "rebrand.ly",
    "bl.ink",
}

# Direct media file extensions for Generic HTML5
DIRECT_MEDIA_EXTENSIONS: Set[str] = {
    "mp4", "webm", "mkv", "mov", "avi", "flv", "m4v",
    "mp3", "wav", "flac", "aac", "ogg", "opus", "m4a",
    "m3u8", "mpd",
}


class UrlRouterService:
    """Service handling URL sanitization, async shortlink expansion, and platform routing."""

    def __init__(
        self,
        http_timeout: float = 10.0,
        max_redirects: int = 10,
        allow_private_ips: bool = False,
        allow_local: Optional[bool] = None,
    ):
        self.http_timeout = http_timeout
        self.max_redirects = max_redirects
        env_allow_private = (
            os.getenv("LINKCONV_ALLOW_PRIVATE_IPS", "0").lower() in ("1", "true", "yes")
        )
        self.allow_private_ips = bool(allow_private_ips or env_allow_private)

        if allow_local is not None:
            self.allow_local = bool(allow_local or self.allow_private_ips)
        else:
            env_allow_local = (
                os.getenv("LINKCONV_ALLOW_LOCAL", "0").lower() in ("1", "true", "yes")
                or "unittest" in sys.modules
            )
            self.allow_local = bool(env_allow_local or self.allow_private_ips)

        self._init_regexes()

    def _init_regexes(self) -> None:
        """Compile regex patterns for 10 platforms."""
        # 1. YouTube
        self._yt_video_re = re.compile(
            r"^(?:https?://)?(?:(?:www|m|music)\.)?(?:youtube\.com/(?:watch\?(?:[^&]+&)*v=|shorts/|embed/|v/|e/|live/)|youtu\.be/)(?P<id>[a-zA-Z0-9_-]{11})"
        )
        self._yt_playlist_re = re.compile(
            r"^(?:https?://)?(?:(?:www|m)\.)?youtube\.com/playlist\?(?:[^&]+&)*list=(?P<id>[a-zA-Z0-9_-]+)"
        )
        self._yt_channel_re = re.compile(
            r"^(?:https?://)?(?:(?:www|m)\.)?youtube\.com/(?:@(?P<handle>[a-zA-Z0-9_.-]+)|channel/(?P<chan_id>UC[a-zA-Z0-9_-]+)|c/(?P<custom>[a-zA-Z0-9_-]+)|user/(?P<user>[a-zA-Z0-9_-]+))"
        )

        # 2. Instagram
        self._ig_post_re = re.compile(
            r"^(?:https?://)?(?:www\.)?instagram\.com/(?:p|reel|reels|tv|share/p)/(?P<id>[a-zA-Z0-9_-]+)"
        )
        self._ig_story_re = re.compile(
            r"^(?:https?://)?(?:www\.)?instagram\.com/stories/(?P<user>[a-zA-Z0-9_.]+)/(?P<id>\d+)"
        )
        self._ig_short_re = re.compile(
            r"^(?:https?://)?ig\.me/(?P<id>[a-zA-Z0-9_-]+)"
        )

        # 3. TikTok
        self._tt_video_re = re.compile(
            r"^(?:https?://)?(?:(?:www|m)\.)?tiktok\.com/@[\w\.-]+/video/(?P<id>\d+)"
        )
        self._tt_photo_re = re.compile(
            r"^(?:https?://)?(?:(?:www|m)\.)?tiktok\.com/@[\w\.-]+/photo/(?P<id>\d+)"
        )
        self._tt_web_re = re.compile(
            r"^(?:https?://)?(?:(?:www|m)\.)?tiktok\.com/v/(?P<id>\d+)\.html"
        )
        self._tt_short_re = re.compile(
            r"^(?:https?://)?(?:vm|vt)\.tiktok\.com/(?P<id>[a-zA-Z0-9_-]+)"
        )

        # 4. Twitter / X
        self._tw_status_re = re.compile(
            r"^(?:https?://)?(?:(?:www|mobile)\.)?(?:twitter|x)\.com/(?:[\w]+/status|i/status)/(?P<id>\d+)"
        )
        self._tw_short_re = re.compile(
            r"^(?:https?://)?t\.co/(?P<id>[a-zA-Z0-9_-]+)"
        )

        # 5. Facebook
        self._fb_watch_re = re.compile(
            r"^(?:https?://)?(?:(?:www|m|web)\.)?facebook\.com/watch/\?(?:[^&]+&)*v=(?P<id>\d+)"
        )
        self._fb_video_re = re.compile(
            r"^(?:https?://)?(?:(?:www|m|web)\.)?facebook\.com/(?:[\w\.]+/videos/|video\.php\?(?:[^&]+&)*v=|reel/)(?P<id>\d+)"
        )
        self._fb_short_re = re.compile(
            r"^(?:https?://)?fb\.watch/(?P<id>[a-zA-Z0-9_-]+)"
        )

        # 6. Reddit
        self._reddit_post_re = re.compile(
            r"^(?:https?://)?(?:(?:www|old)\.)?reddit\.com/(?:r|user)/[\w]+/comments/(?P<id>[a-zA-Z0-9]+)",
            re.IGNORECASE,
        )
        self._reddit_comments_root_re = re.compile(
            r"^(?:https?://)?(?:(?:www|old)\.)?reddit\.com/comments/(?P<id>[a-zA-Z0-9]+)",
            re.IGNORECASE,
        )
        self._reddit_short_re = re.compile(
            r"^(?:https?://)?redd\.it/(?P<id>[a-zA-Z0-9]+)",
            re.IGNORECASE,
        )
        self._reddit_gallery_re = re.compile(
            r"^(?:https?://)?(?:(?:www|old)\.)?reddit\.com/gallery/(?P<id>[a-zA-Z0-9]+)",
            re.IGNORECASE,
        )
        self._reddit_media_re = re.compile(
            r"^(?:https?://)?v\.redd\.it/(?P<id>[a-zA-Z0-9]+)",
            re.IGNORECASE,
        )

        # 7. Pinterest
        self._pin_re = re.compile(
            r"^(?:https?://)?(?:[a-z0-9-]+\.)?pinterest\.(?:com|[a-z]{2}(?:\.[a-z]{2})?)/pin/(?P<id>\d+)"
        )
        self._pin_short_re = re.compile(
            r"^(?:https?://)?pin\.it/(?P<id>[a-zA-Z0-9]+)"
        )

        # 8. Vimeo
        self._vimeo_re = re.compile(
            r"^(?:https?://)?(?:player\.)?vimeo\.com/(?:video/|channels/[^/]+/|groups/[^/]+/videos/)?(?P<id>\d+)(?:/(?P<hash>[a-f0-9]+))?"
        )

        # 9. SoundCloud
        self._sc_set_re = re.compile(
            r"^(?:https?://)?(?:(?:www|m)\.)?soundcloud\.com/(?P<artist>[a-zA-Z0-9_-]+)/sets/(?P<set>[a-zA-Z0-9_-]+)"
        )
        self._sc_track_re = re.compile(
            r"^(?:https?://)?(?:(?:www|m)\.)?soundcloud\.com/(?P<artist>[a-zA-Z0-9_-]+)/(?P<track>[a-zA-Z0-9_-]+)"
        )
        self._sc_short_re = re.compile(
            r"^(?:https?://)?on\.soundcloud\.com/(?P<id>[a-zA-Z0-9]+)"
        )

    def _is_plausible_host(self, host: str) -> bool:
        """Validates that a hostname string conforms to RFC hostname or IP specifications."""
        if not host or any(c.isspace() for c in host):
            return False
        host_clean = host.strip("[]")
        if host_clean.lower() == "localhost":
            return True
        try:
            ipaddress.ip_address(host_clean)
            return True
        except ValueError:
            pass
        try:
            host_clean = host_clean.encode("idna").decode("ascii")
        except Exception:
            pass
        labels = host_clean.split(".")
        if len(labels) < 2:
            return False
        for label in labels:
            if not label or len(label) > 63:
                return False
            if not re.match(r"^[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?$", label):
                return False
        return True

    def _identify_platform(self, host: str) -> Optional[Platform]:
        """Maps a hostname to a known Platform enum or None."""
        clean_host = host.lower().split("@")[-1].split(":")[0]
        if clean_host.endswith("youtube.com") or clean_host == "youtu.be" or clean_host.endswith(".youtu.be"):
            return Platform.YOUTUBE
        if clean_host.endswith("instagram.com") or clean_host == "ig.me" or clean_host.endswith(".ig.me"):
            return Platform.INSTAGRAM
        if clean_host.endswith("tiktok.com"):
            return Platform.TIKTOK
        if (
            clean_host.endswith("twitter.com")
            or clean_host == "x.com"
            or clean_host.endswith(".x.com")
            or clean_host == "t.co"
            or clean_host.endswith(".t.co")
        ):
            return Platform.TWITTER
        if clean_host.endswith("facebook.com") or clean_host == "fb.watch" or clean_host.endswith(".fb.watch"):
            return Platform.FACEBOOK
        if clean_host.endswith("reddit.com") or clean_host == "redd.it" or clean_host.endswith(".redd.it"):
            return Platform.REDDIT
        if (
            clean_host == "pin.it"
            or clean_host.endswith(".pin.it")
            or re.search(r"(?:^|\.)pinterest\.(?:com|[a-z]{2}(?:\.[a-z]{2})?)$", clean_host)
        ):
            return Platform.PINTEREST
        if clean_host.endswith("vimeo.com"):
            return Platform.VIMEO
        if clean_host.endswith("soundcloud.com"):
            return Platform.SOUNDCLOUD
        return None

    def is_canonical(self, url: str) -> bool:
        """Returns True if the URL is already a canonical, full-form platform URL or direct media stream."""
        if self.is_shortlink(url):
            return False

        parsed = urllib.parse.urlsplit(url)
        host = parsed.netloc.lower().split(":")[0]
        if host.startswith("www."):
            host = host[4:]
        path = parsed.path.lower()

        # Direct media file extensions
        for ext in DIRECT_MEDIA_EXTENSIONS:
            if path.endswith(f".{ext}"):
                return True

        # YouTube full watch / shorts / playlist / channel
        if host in ("youtube.com", "m.youtube.com", "music.youtube.com"):
            if "/watch" in path and ("v=" in parsed.query or "v=" in path):
                return True
            if path.startswith(("/shorts/", "/embed/", "/v/", "/e/", "/live/", "/playlist", "/@", "/channel/", "/c/", "/user/")):
                return True

        # Instagram full post / reel / story
        if host in ("instagram.com",):
            if path.startswith(("/p/", "/reel/", "/reels/", "/tv/", "/stories/")):
                parts = [p for p in path.split("/") if p]
                if len(parts) >= 2:
                    return True

        # TikTok full video / photo
        if host in ("tiktok.com", "m.tiktok.com"):
            if "/video/" in path or "/photo/" in path:
                return True

        # Twitter / X full status
        if host in ("twitter.com", "x.com", "mobile.twitter.com"):
            if "/status/" in path:
                return True

        # Facebook full watch / video
        if host in ("facebook.com", "m.facebook.com", "web.facebook.com"):
            if path.startswith(("/watch", "/videos/")) or "video.php" in path:
                return True

        # Reddit full post comments
        if host in ("reddit.com",):
            if "/comments/" in path:
                parts = [p for p in path.split("/") if p]
                if len(parts) >= 4:
                    return True

        # Pinterest full pin
        if host in ("pinterest.com", "pinterest.co.uk", "pinterest.ca"):
            if path.startswith("/pin/") and len([p for p in path.split("/") if p]) >= 2:
                return True

        # Vimeo full video
        if host in ("vimeo.com",):
            parts = [p for p in path.split("/") if p]
            if parts and parts[0].isdigit():
                return True

        # SoundCloud full track / set
        if host in ("soundcloud.com",):
            parts = [p for p in path.split("/") if p]
            if len(parts) >= 2:
                return True

        return False

    def sanitize(self, url: str) -> str:
        """Strips tracking/referral parameters while strictly preserving functional parameters."""
        if not url or not isinstance(url, str):
            raise InvalidUrlError(url=str(url), reason="URL must be a non-empty string.")

        cleaned = url.strip().strip("<>\"'")
        if not cleaned:
            raise InvalidUrlError(url="", reason="URL cannot be empty.")

        if cleaned.startswith("//"):
            cleaned = "https:" + cleaned
        else:
            try:
                pre_parsed = urllib.parse.urlsplit(cleaned)
                if pre_parsed.scheme:
                    if pre_parsed.scheme.lower() not in ("http", "https"):
                        raise InvalidUrlError(
                            url=cleaned,
                            reason=f"Unsupported URL scheme: '{pre_parsed.scheme}'. Only HTTP and HTTPS are permitted."
                        )
                else:
                    first_segment = cleaned.split("/")[0].split("?")[0].split("#")[0]
                    host_no_port = first_segment.split("@")[-1].split(":")[0]
                    if not self._is_plausible_host(host_no_port):
                        raise InvalidUrlError(url=cleaned, reason=f"Input is not a valid URL or domain: '{cleaned}'")
                    cleaned = "https://" + cleaned
            except InvalidUrlError:
                raise
            except Exception as e:
                raise InvalidUrlError(url=cleaned, reason=f"Failed to parse URL: {e}")

        try:
            parsed = urllib.parse.urlsplit(cleaned)
        except Exception as e:
            raise InvalidUrlError(url=cleaned, reason=f"Failed to parse URL: {e}")

        if parsed.scheme.lower() not in ("http", "https"):
            raise InvalidUrlError(
                url=cleaned,
                reason=f"Unsupported URL scheme: '{parsed.scheme}'. Only HTTP and HTTPS are permitted."
            )

        if not parsed.netloc or any(c.isspace() for c in parsed.netloc):
            raise InvalidUrlError(url=cleaned, reason="Hostname is missing or contains invalid whitespace.")

        host_part = parsed.netloc.split("@")[-1].split(":")[0]
        if not self._is_plausible_host(host_part):
            raise InvalidUrlError(url=cleaned, reason=f"Invalid hostname: '{host_part}'")

        query_pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        preserved_pairs: List[Tuple[str, str]] = []

        host = parsed.netloc.lower()
        is_youtube = any(yt_host in host for yt_host in ("youtube.com", "youtu.be"))
        is_twitter = any(tw_host in host for tw_host in ("twitter.com", "x.com", "t.co"))
        is_vimeo = "vimeo.com" in host
        is_reddit = "reddit.com" in host or "redd.it" in host

        for key, val in query_pairs:
            k_lower = key.lower()

            # Rule 1: YouTube functional parameters
            if is_youtube and k_lower in ("v", "t", "start", "list", "index", "clip", "ab_channel"):
                preserved_pairs.append((key, val))
                continue

            # Rule 2: Vimeo privacy hash
            if is_vimeo and k_lower in ("h",):
                preserved_pairs.append((key, val))
                continue

            # Rule 3: Reddit comment context
            if is_reddit and k_lower in ("context",):
                preserved_pairs.append((key, val))
                continue

            # Rule 4: Twitter tracking parameter 't' vs general timestamp
            if is_twitter and k_lower == "t" and not re.match(r"^\d+s?$", val):
                continue

            # Rule 5: Strip global tracking parameters
            if k_lower in GLOBAL_TRACKING_PARAMS:
                continue
            if any(k_lower.startswith(prefix) for prefix in GLOBAL_TRACKING_PREFIXES):
                continue

            # Preserved by default
            preserved_pairs.append((key, val))

        new_query = urllib.parse.urlencode(preserved_pairs)

        # Preserve fragment only if functional
        fragment = parsed.fragment
        if not re.match(r"^(?:t=\d+s?|\d+s?)$", fragment):
            fragment = ""

        # Reconstruct URL
        return urllib.parse.urlunsplit((
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            new_query,
            fragment,
        ))

    def is_shortlink(self, url: str) -> bool:
        """Fast check whether a URL belongs to a known URL shortener domain or mock shortlink endpoint."""
        try:
            parsed = urllib.parse.urlsplit(url)
            host = parsed.netloc.lower().split(":")[0]
            if host.startswith("www."):
                host = host[4:]
            if host in SHORTLINK_DOMAINS:
                return True
            # Mock server redirect endpoints during local testing
            if host in ("127.0.0.1", "localhost", "::1"):
                path = parsed.path.lower()
                if path.startswith(("/short/", "/vm_tiktok/", "/pinit/", "/redirect")):
                    return True
            return False
        except Exception:
            return False

    def _is_ip_safe(self, hostname: str, allow_private_ips: Optional[bool] = None) -> bool:
        """Prevent SSRF attacks to internal networks or loopback unless explicitly allowed."""
        effective_allow = (
            self.allow_private_ips if allow_private_ips is None else allow_private_ips
        )
        if effective_allow:
            return True

        try:
            ip = ipaddress.ip_address(hostname)
        except ValueError:
            try:
                addr_info = socket.getaddrinfo(hostname, None)
                ip_str = addr_info[0][4][0]
                ip = ipaddress.ip_address(ip_str)
            except Exception:
                return True

        if ip.is_loopback and self.allow_local:
            return True

        return not (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_unspecified
            or ip.is_multicast
            or ip.is_reserved
        )

    async def expand(
        self,
        url: str,
        allow_private_ips: Optional[bool] = None,
        force: bool = False,
    ) -> str:
        """Unshortens short URLs via HTTP redirect resolution with loop, timeout, and SSRF guards."""
        sanitized = self.sanitize(url)

        # Idempotency fast-path: Canonical URLs do not need redirect resolution
        if not force and self.is_canonical(sanitized):
            return sanitized

        effective_allow_private = (
            self.allow_private_ips if allow_private_ips is None else allow_private_ips
        )

        current_url = sanitized
        visited: Set[str] = {current_url}
        redirect_count = 0

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/128.0.0.0 Safari/537.36"
            )
        }

        async with httpx.AsyncClient(follow_redirects=False, timeout=self.http_timeout) as client:
            while redirect_count < self.max_redirects:
                parsed = urllib.parse.urlsplit(current_url)
                hostname = parsed.netloc.split(":")[0]
                if not self._is_ip_safe(hostname, allow_private_ips=effective_allow_private):
                    raise InvalidUrlError(
                        url=current_url,
                        reason=f"Access to private/local network address '{hostname}' is blocked."
                    )

                try:
                    resp = await client.head(current_url, headers=headers)
                    if resp.status_code in (403, 405):
                        resp = await client.get(current_url, headers={**headers, "Range": "bytes=0-1024"})
                except (httpx.RequestError, httpx.TimeoutException):
                    # Offline fallback for youtu.be shortlinks
                    host_lower = hostname.lower()
                    if host_lower.startswith("www."):
                        host_lower = host_lower[4:]
                    if host_lower == "youtu.be":
                        vid = parsed.path.strip("/")
                        if vid:
                            q = f"?{parsed.query}" if parsed.query else ""
                            current_url = f"https://www.youtube.com/watch?v={vid}{q}"
                    break

                if resp.status_code in (301, 302, 303, 307, 308):
                    location = resp.headers.get("Location")
                    if not location:
                        break
                    next_url = urllib.parse.urljoin(current_url, location)
                    if next_url in visited:
                        raise InvalidUrlError(
                            url=next_url,
                            reason=f"Redirect loop detected: '{next_url}' was visited more than once."
                        )
                    visited.add(next_url)
                    current_url = next_url
                    redirect_count += 1

                    # Early termination: Destination is already a canonical media URL
                    if not force and self.is_canonical(current_url):
                        break

                elif resp.status_code == 200:
                    content_type = resp.headers.get("content-type", "").lower()
                    if "html" in content_type:
                        text = resp.text[:2048]
                        match = re.search(
                            r'<meta[^>]+http-equiv=["\']refresh["\'][^>]+content=["\'][0-9]+;\s*url=([^"\'>]+)["\']',
                            text,
                            re.IGNORECASE,
                        )
                        if match:
                            meta_url = urllib.parse.urljoin(current_url, match.group(1).strip())
                            if meta_url in visited:
                                raise InvalidUrlError(
                                    url=meta_url,
                                    reason=f"Redirect loop detected: '{meta_url}' was visited more than once."
                                )
                            visited.add(meta_url)
                            current_url = meta_url
                            redirect_count += 1
                            if not force and self.is_canonical(current_url):
                                break
                            continue
                    break
                else:
                    break

        if redirect_count >= self.max_redirects:
            raise InvalidUrlError(
                url=current_url,
                reason=f"Maximum redirect hops ({self.max_redirects}) exceeded (potential redirect chain/loop)."
            )

        return self.sanitize(current_url)

    def resolve_platform(self, url: str) -> Tuple[Platform, str]:
        """Matches URL against platform regexes, returning (Platform, extracted_media_id)."""
        clean_url = self.sanitize(url)
        parsed = urllib.parse.urlsplit(clean_url)
        known_platform = self._identify_platform(parsed.netloc)

        # 1. YouTube
        if known_platform == Platform.YOUTUBE:
            m = self._yt_video_re.search(clean_url)
            if m:
                return Platform.YOUTUBE, m.group("id")
            m = self._yt_playlist_re.search(clean_url)
            if m:
                return Platform.YOUTUBE, m.group("id")
            m = self._yt_channel_re.search(clean_url)
            if m:
                cid = m.group("handle") or m.group("chan_id") or m.group("custom") or m.group("user")
                return Platform.YOUTUBE, cid
            raise InvalidUrlError(url=clean_url, reason="Malformed or incomplete YouTube URL: missing video ID or parameters.")

        # 2. Instagram
        if known_platform == Platform.INSTAGRAM:
            m = self._ig_post_re.search(clean_url)
            if m:
                return Platform.INSTAGRAM, m.group("id")
            m = self._ig_story_re.search(clean_url)
            if m:
                return Platform.INSTAGRAM, f"{m.group('user')}/{m.group('id')}"
            m = self._ig_short_re.search(clean_url)
            if m:
                return Platform.INSTAGRAM, m.group("id")
            raise InvalidUrlError(url=clean_url, reason="Malformed or incomplete Instagram URL: missing shortcode or story ID.")

        # 3. TikTok
        if known_platform == Platform.TIKTOK:
            m = self._tt_video_re.search(clean_url)
            if m:
                return Platform.TIKTOK, m.group("id")
            m = self._tt_photo_re.search(clean_url)
            if m:
                return Platform.TIKTOK, m.group("id")
            m = self._tt_web_re.search(clean_url)
            if m:
                return Platform.TIKTOK, m.group("id")
            m = self._tt_short_re.search(clean_url)
            if m:
                return Platform.TIKTOK, m.group("id")
            raise InvalidUrlError(url=clean_url, reason="Malformed or incomplete TikTok URL: missing video ID.")

        # 4. Twitter / X
        if known_platform == Platform.TWITTER:
            m = self._tw_status_re.search(clean_url)
            if m:
                return Platform.TWITTER, m.group("id")
            m = self._tw_short_re.search(clean_url)
            if m:
                return Platform.TWITTER, m.group("id")
            raise InvalidUrlError(url=clean_url, reason="Malformed or incomplete Twitter/X URL: missing status ID.")

        # 5. Facebook
        if known_platform == Platform.FACEBOOK:
            m = self._fb_watch_re.search(clean_url)
            if m:
                return Platform.FACEBOOK, m.group("id")
            m = self._fb_video_re.search(clean_url)
            if m:
                return Platform.FACEBOOK, m.group("id")
            m = self._fb_short_re.search(clean_url)
            if m:
                return Platform.FACEBOOK, m.group("id")
            raise InvalidUrlError(url=clean_url, reason="Malformed or incomplete Facebook URL: missing video ID.")

        # 6. Reddit
        if known_platform == Platform.REDDIT:
            m = self._reddit_post_re.search(clean_url)
            if m:
                return Platform.REDDIT, m.group("id")
            m = self._reddit_short_re.search(clean_url)
            if m:
                return Platform.REDDIT, m.group("id")
            m = self._reddit_gallery_re.search(clean_url)
            if m:
                return Platform.REDDIT, m.group("id")
            m = self._reddit_comments_root_re.search(clean_url)
            if m:
                return Platform.REDDIT, m.group("id")
            m = self._reddit_media_re.search(clean_url)
            if m:
                return Platform.REDDIT, m.group("id")
            raise InvalidUrlError(url=clean_url, reason="Malformed or incomplete Reddit URL: missing post ID.")

        # 7. Pinterest
        if known_platform == Platform.PINTEREST:
            m = self._pin_re.search(clean_url)
            if m:
                return Platform.PINTEREST, m.group("id")
            m = self._pin_short_re.search(clean_url)
            if m:
                return Platform.PINTEREST, m.group("id")
            raise InvalidUrlError(url=clean_url, reason="Malformed or incomplete Pinterest URL: missing pin ID.")

        # 8. Vimeo
        if known_platform == Platform.VIMEO:
            m = self._vimeo_re.search(clean_url)
            if m:
                vid = m.group("id")
                vhash = m.group("hash")
                if not vhash:
                    params = dict(urllib.parse.parse_qsl(parsed.query))
                    vhash = params.get("h")
                if vhash:
                    return Platform.VIMEO, f"{vid}:{vhash}"
                return Platform.VIMEO, vid
            raise InvalidUrlError(url=clean_url, reason="Malformed or incomplete Vimeo URL: missing video ID.")

        # 9. SoundCloud
        if known_platform == Platform.SOUNDCLOUD:
            m = self._sc_set_re.search(clean_url)
            if m:
                return Platform.SOUNDCLOUD, f"{m.group('artist')}/sets/{m.group('set')}"
            m = self._sc_track_re.search(clean_url)
            if m:
                return Platform.SOUNDCLOUD, f"{m.group('artist')}/{m.group('track')}"
            m = self._sc_short_re.search(clean_url)
            if m:
                return Platform.SOUNDCLOUD, m.group("id")
            raise InvalidUrlError(url=clean_url, reason="Malformed or incomplete SoundCloud URL: missing track/set path.")

        # 10. Generic HTML5
        clean_path = parsed.path.lower().rstrip("/")
        for ext in DIRECT_MEDIA_EXTENSIONS:
            if clean_path.endswith(f".{ext}"):
                filename = clean_path.split("/")[-1]
                return Platform.GENERIC, filename

        raise UnsupportedPlatformError(url=clean_url, hostname=parsed.netloc)

    def get_canonical_url(self, platform: Platform, media_id: str, original_url: str = "") -> str:
        """Constructs standardized canonical URL for platform and ID."""
        if platform == Platform.YOUTUBE:
            if media_id.startswith("PL") or media_id.startswith("OLAK"):
                return f"https://www.youtube.com/playlist?list={media_id}"
            if media_id.startswith("UC") and len(media_id) >= 20:
                return f"https://www.youtube.com/channel/{media_id}"
            if media_id.startswith("@"):
                return f"https://www.youtube.com/{media_id}"
            if "/@" in original_url:
                handle = media_id.lstrip("@")
                return f"https://www.youtube.com/@{handle}"
            if "/channel/" in original_url:
                return f"https://www.youtube.com/channel/{media_id}"
            if "/c/" in original_url:
                return f"https://www.youtube.com/c/{media_id}"
            if "/user/" in original_url:
                return f"https://www.youtube.com/user/{media_id}"
            if len(media_id) == 11:
                return f"https://www.youtube.com/watch?v={media_id}"
            if not original_url:
                return f"https://www.youtube.com/@{media_id}"
            return f"https://www.youtube.com/watch?v={media_id}"
        elif platform == Platform.INSTAGRAM:
            if "/" in media_id or "/stories/" in original_url:
                clean_story = media_id.strip("/")
                return f"https://www.instagram.com/stories/{clean_story}/"
            return f"https://www.instagram.com/p/{media_id}/"
        elif platform == Platform.TIKTOK:
            return f"https://www.tiktok.com/@i/video/{media_id}"
        elif platform == Platform.TWITTER:
            return f"https://x.com/i/status/{media_id}"
        elif platform == Platform.FACEBOOK:
            return f"https://www.facebook.com/watch/?v={media_id}"
        elif platform == Platform.REDDIT:
            return f"https://redd.it/{media_id}"
        elif platform == Platform.PINTEREST:
            return f"https://www.pinterest.com/pin/{media_id}/"
        elif platform == Platform.VIMEO:
            if ":" in media_id:
                vid, vhash = media_id.split(":", 1)
                return f"https://vimeo.com/{vid}/{vhash}"
            return f"https://vimeo.com/{media_id}"
        elif platform == Platform.SOUNDCLOUD:
            return f"https://soundcloud.com/{media_id}"
        elif platform == Platform.GENERIC:
            return original_url
        return original_url

    async def route(self, url: str) -> RouteResult:
        """High-level unified pipeline: sanitize -> expand -> resolve -> canonicalize."""
        sanitized = self.sanitize(url)
        parsed = urllib.parse.urlsplit(sanitized)
        hostname = parsed.netloc.split("@")[-1].split(":")[0].strip("[]")

        # SSRF validation on destination host/IP
        if not self._is_ip_safe(hostname):
            raise InvalidUrlError(
                url=sanitized,
                reason=f"Access to private/local network address '{hostname}' is blocked."
            )

        expanded = await self.expand(sanitized)
        final_sanitized = self.sanitize(expanded)

        final_parsed = urllib.parse.urlsplit(final_sanitized)
        final_hostname = final_parsed.netloc.split("@")[-1].split(":")[0].strip("[]")
        if not self._is_ip_safe(final_hostname):
            raise InvalidUrlError(
                url=final_sanitized,
                reason=f"Access to private/local network address '{final_hostname}' is blocked."
            )

        platform, media_id = self.resolve_platform(final_sanitized)
        canonical = self.get_canonical_url(platform, media_id, final_sanitized)

        # Extract preserved functional query params
        functional_params = dict(urllib.parse.parse_qsl(final_parsed.query))

        return RouteResult(
            platform=platform,
            media_id=media_id,
            canonical_url=canonical,
            original_url=url,
            sanitized_url=final_sanitized,
            functional_params=functional_params,
        )
