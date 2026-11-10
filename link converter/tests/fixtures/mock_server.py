"""
tests/fixtures/mock_server.py
Lightweight, thread-safe, 100% offline HTTP mock server for E2E testing.
Emulates upstream platform APIs, CDN media endpoints, redirect services,
and oEmbed responses without external internet connectivity.
"""

import http.server
import json
import socket
import socketserver
import threading
import time
import urllib.parse
from typing import Optional, Dict, Any

from tests.fixtures.sample_media import (
    create_minimal_mp4_bytes,
    create_minimal_mp3_bytes,
    create_minimal_jpeg_bytes,
    create_placeholder_jpeg_bytes,
    create_mock_carousel_zip_bytes,
    MOCK_METADATA_DATABASE
)


class MockMediaHandler(http.server.BaseHTTPRequestHandler):
    """
    HTTP Request handler delivering synthetic platform media, HTML embeds,
    redirects, error codes, and binary fixtures.
    """

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress standard HTTP server stderr logging during test runs."""
        pass

    def do_HEAD(self) -> None:
        """Handle HEAD requests (e.g., redirect resolution / link expansion)."""
        self._dispatch(is_head=True)

    def do_GET(self) -> None:
        """Handle GET requests (media payloads, streams, assets, embeds)."""
        self._dispatch(is_head=False)

    def do_POST(self) -> None:
        """Handle POST requests (simulated extraction and unshortening APIs)."""
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else b""
        
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path.startswith("/api/expand"):
            # Unshortener mock endpoint
            try:
                data = json.loads(body.decode("utf-8")) if body else {}
                url = data.get("url", "")
                target = self._resolve_mock_redirect(url)
                self._send_json(200, {"original_url": url, "canonical_url": target})
            except Exception as e:
                self._send_json(400, {"error": str(e)})
            return

        if parsed.path.startswith("/api/mock_extract"):
            try:
                data = json.loads(body.decode("utf-8")) if body else {}
                platform_key = data.get("platform_key", "youtube_video")
                payload = MOCK_METADATA_DATABASE.get(platform_key, MOCK_METADATA_DATABASE["generic_video"])
                self._send_json(200, payload)
            except Exception as e:
                self._send_json(400, {"error": str(e)})
            return

        self._send_json(404, {"error": "Mock POST endpoint not found"})

    def _dispatch(self, is_head: bool = False) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        # 1. Health check
        if path in ("/health", "/ping"):
            self._send_json(200, {"status": "ok", "mock_server": True})
            return

        # 2. Shortlink redirects (HTTP 301 / 302)
        if path.startswith("/redirect"):
            target = query.get("target", ["https://www.youtube.com/watch?v=dQw4w9WgXcQ"])[0]
            self._send_redirect(302, target)
            return

        if path.startswith("/short/"):
            slug = path[len("/short/"):]
            target = f"https://www.youtube.com/watch?v={slug}"
            self._send_redirect(301, target)
            return

        if path.startswith("/vm_tiktok/"):
            slug = path[len("/vm_tiktok/"):]
            target = f"https://www.tiktok.com/@creator/video/{slug}"
            self._send_redirect(301, target)
            return

        if path.startswith("/pinit/"):
            slug = path[len("/pinit/"):]
            target = f"https://www.pinterest.com/pin/{slug}/"
            self._send_redirect(301, target)
            return

        # 3. HTTP Error Simulations
        if path.startswith("/error/"):
            try:
                code = int(path.split("/error/")[1].split("/")[0])
            except (IndexError, ValueError):
                code = 500
            self._send_json(code, {"error": f"Simulated HTTP {code} error", "code": code})
            return

        # 4. Timeout simulation
        if path.startswith("/timeout"):
            duration = float(query.get("seconds", ["2.0"])[0])
            time.sleep(duration)
            self._send_json(200, {"message": f"Delayed response after {duration}s"})
            return

        # 5. Binary Media Deliveries
        if path == "/media/sample.mp4":
            mp4_bytes = create_minimal_mp4_bytes()
            self._send_bytes(200, "video/mp4", mp4_bytes, is_head)
            return

        if path == "/media/sample.mp3":
            mp3_bytes = create_minimal_mp3_bytes()
            self._send_bytes(200, "audio/mpeg", mp3_bytes, is_head)
            return

        if path == "/media/thumb.jpg":
            jpg_bytes = create_minimal_jpeg_bytes()
            self._send_bytes(200, "image/jpeg", jpg_bytes, is_head)
            return

        if path == "/media/thumb_small.jpg":
            # 120x90 simulated placeholder (< 2000 bytes)
            placeholder_bytes = create_placeholder_jpeg_bytes()
            self._send_bytes(200, "image/jpeg", placeholder_bytes, is_head)
            return

        if path == "/media/carousel.zip":
            zip_bytes = create_mock_carousel_zip_bytes(3)
            self._send_bytes(200, "application/zip", zip_bytes, is_head)
            return

        # 6. oEmbed endpoints (JSON & XML)
        if path.startswith("/oembed"):
            fmt = query.get("format", ["json"])[0].lower()
            url_param = query.get("url", ["https://www.youtube.com/watch?v=dQw4w9WgXcQ"])[0]
            if fmt == "xml":
                xml_body = (
                    '<?xml version="1.0" encoding="utf-8" standalone="yes"?>\n'
                    '<oembed>\n'
                    '  <version>1.0</version>\n'
                    '  <type>video</type>\n'
                    '  <provider_name>YouTube</provider_name>\n'
                    '  <title>Never Gonna Give You Up</title>\n'
                    '  <author_name>Rick Astley</author_name>\n'
                    f'  <url>{url_param}</url>\n'
                    '  <width>1920</width>\n'
                    '  <height>1080</height>\n'
                    '  <html>&lt;iframe src="https://www.youtube.com/embed/dQw4w9WgXcQ"&gt;&lt;/iframe&gt;</html>\n'
                    '</oembed>'
                ).encode("utf-8")
                self._send_bytes(200, "application/xml; charset=utf-8", xml_body, is_head)
            else:
                self._send_json(200, {
                    "version": "1.0",
                    "type": "video",
                    "provider_name": "YouTube",
                    "provider_url": "https://www.youtube.com/",
                    "title": "Never Gonna Give You Up",
                    "author_name": "Rick Astley",
                    "width": 1920,
                    "height": 1080,
                    "html": '<iframe width="1920" height="1080" src="https://www.youtube.com/embed/dQw4w9WgXcQ" frameborder="0" allowfullscreen></iframe>',
                    "thumbnail_url": "/media/thumb.jpg"
                })
            return

        # 7. Platform HTML / JSON endpoints
        if path.startswith("/youtube/watch"):
            video_id = query.get("v", ["dQw4w9WgXcQ"])[0]
            html = f"""<!DOCTYPE html>
            <html>
            <head><title>Mock YouTube - {video_id}</title></head>
            <body>
                <div id="player" data-video-id="{video_id}">Mock Video</div>
            </body>
            </html>""".encode("utf-8")
            self._send_bytes(200, "text/html; charset=utf-8", html, is_head)
            return

        if path.startswith("/instagram/p/"):
            code = path.split("/instagram/p/")[1].split("/")[0]
            payload = MOCK_METADATA_DATABASE["instagram_reel"].copy()
            payload["id"] = code
            self._send_json(200, payload)
            return

        if path.startswith("/reddit/r/"):
            payload = MOCK_METADATA_DATABASE["reddit_post"]
            self._send_json(200, payload)
            return

        # 8. Direct metadata query by platform
        for key, data in MOCK_METADATA_DATABASE.items():
            if path == f"/metadata/{key}":
                self._send_json(200, data)
                return

        # Default 404
        self._send_json(404, {"error": "Mock path not found", "path": path})

    def _send_bytes(self, status: int, content_type: str, data: bytes, is_head: bool = False) -> None:
        try:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            if not is_head:
                self.wfile.write(data)
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            pass

    def _send_json(self, status: int, obj: Any) -> None:
        try:
            body = json.dumps(obj).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            pass

    def _send_redirect(self, status: int, location: str) -> None:
        self.send_response(status)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _resolve_mock_redirect(self, url: str) -> str:
        parsed = urllib.parse.urlparse(url)
        if "youtu.be" in parsed.netloc:
            video_id = parsed.path.lstrip("/")
            return f"https://www.youtube.com/watch?v={video_id}"
        if "vm.tiktok.com" in parsed.netloc:
            slug = parsed.path.lstrip("/")
            return f"https://www.tiktok.com/@creator/video/{slug}"
        if "pin.it" in parsed.netloc:
            slug = parsed.path.lstrip("/")
            return f"https://www.pinterest.com/pin/{slug}/"
        if "bit.ly" in parsed.netloc or "t.co" in parsed.netloc:
            slug = parsed.path.lstrip("/")
            return f"https://canonical.example.com/item/{slug}"
        return url


class MockMediaServer:
    """
    Manages an embedded, thread-isolated HTTP mock server running on an ephemeral port.
    Guarantees 100% offline, deterministic execution and immediate teardown.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 0) -> None:
        self.host = host
        self.requested_port = port
        self.server: Optional[socketserver.TCPServer] = None
        self.thread: Optional[threading.Thread] = None
        self.actual_port: int = 0

    def start(self) -> "MockMediaServer":
        """Starts the server in a background daemon thread."""
        class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
            allow_reuse_address = True
            daemon_threads = True

            def handle_error(self, request: Any, client_address: Any) -> None:
                exc_type, _, _ = sys.exc_info()
                if exc_type in (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
                    return
                super().handle_error(request, client_address)

        self.server = ThreadedTCPServer((self.host, self.requested_port), MockMediaHandler)
        self.actual_port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        
        # Verify socket readiness
        self._wait_until_ready()
        return self

    def _wait_until_ready(self, timeout: float = 2.0) -> None:
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                with socket.create_connection((self.host, self.actual_port), timeout=0.1):
                    return
            except (socket.error, ConnectionRefusedError):
                time.sleep(0.02)
        raise RuntimeError(f"Mock server failed to bind and become ready on {self.host}:{self.actual_port}")

    def stop(self) -> None:
        """Stops the mock server and releases all bound sockets."""
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.server = None
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)
            self.thread = None

    @property
    def base_url(self) -> str:
        """Returns the full root URL of the mock server."""
        return f"http://{self.host}:{self.actual_port}"

    def get_url(self, path: str) -> str:
        """Returns the formatted URL for a given path."""
        if not path.startswith("/"):
            path = "/" + path
        return f"{self.base_url}{path}"

    def __enter__(self) -> "MockMediaServer":
        return self.start()

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.stop()


if __name__ == "__main__":
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8099
    server = MockMediaServer(port=port)
    server.start()
    print(f"Mock Media Server running at {server.base_url}")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        server.stop()
        print("Mock Media Server stopped.")
