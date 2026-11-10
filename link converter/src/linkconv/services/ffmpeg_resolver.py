"""FFmpeg discovery, verification, and automated provisioning service.

File: src/linkconv/services/ffmpeg_resolver.py
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import tempfile
from typing import Callable, List, Optional
import urllib.request
import zipfile

from linkconv.core.exceptions import FFmpegNotFoundError


class FFmpegResolverService:
    """Discovers, validates, and provisions FFmpeg and FFprobe executables across platforms."""

    DEFAULT_WIN64_DOWNLOAD_URL = (
        "https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
    )
    VERSION_REGEX = re.compile(r"ffmpeg\s+version\s+([^\s,]+)", re.IGNORECASE)

    def __init__(self, custom_path: Optional[str] = None):
        self.custom_path: Optional[str] = custom_path
        self.logger = logging.getLogger("linkconv.services.ffmpeg_resolver")
        self._cached_ffmpeg_path: Optional[str] = None
        self._cached_ffprobe_path: Optional[str] = None
        self._cached_version: Optional[str] = None

    def set_custom_path(self, path: str) -> None:
        """Sets an explicit user-provided ffmpeg binary path override."""
        self.custom_path = path
        self._cached_ffmpeg_path = None
        self._cached_ffprobe_path = None
        self._cached_version = None

    def get_local_appdata_dir(self) -> Path:
        """Returns the local linkconv bin directory."""
        if platform.system() == "Windows":
            base = os.environ.get("LOCALAPPDATA")
            if not base:
                base = str(Path.home() / "AppData" / "Local")
            return Path(base) / "linkconv" / "bin"
        else:
            xdg_data = os.environ.get("XDG_DATA_HOME")
            if xdg_data:
                return Path(xdg_data) / "linkconv" / "bin"
            return Path.home() / ".local" / "share" / "linkconv" / "bin"

    def get_local_appdata_ffmpeg(self) -> Path:
        """Returns expected path to ffmpeg executable in local appdata."""
        exe = "ffmpeg.exe" if platform.system() == "Windows" else "ffmpeg"
        return self.get_local_appdata_dir() / exe

    def get_local_appdata_ffprobe(self) -> Path:
        """Returns expected path to ffprobe executable in local appdata."""
        exe = "ffprobe.exe" if platform.system() == "Windows" else "ffprobe"
        return self.get_local_appdata_dir() / exe

    def find_ffmpeg(self) -> Optional[str]:
        """Executes 4-tier discovery order without auto-download.
        
        Tiers:
        0. Explicit custom path override
        1. System PATH
        2. %LOCALAPPDATA%\\linkconv\\bin\\ffmpeg.exe
        3. imageio-ffmpeg static wheel
        """
        if self._cached_ffmpeg_path and os.path.isfile(self._cached_ffmpeg_path):
            return self._cached_ffmpeg_path

        # Tier 0: Custom override
        if self.custom_path:
            p = Path(self.custom_path)
            if p.is_file() and os.access(p, os.X_OK):
                self._cached_ffmpeg_path = str(p.resolve())
                return self._cached_ffmpeg_path
            elif p.is_dir():
                candidate = p / ("ffmpeg.exe" if platform.system() == "Windows" else "ffmpeg")
                if candidate.is_file() and os.access(candidate, os.X_OK):
                    self._cached_ffmpeg_path = str(candidate.resolve())
                    return self._cached_ffmpeg_path

        # Tier 1: System PATH
        path_binary = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
        if path_binary and os.path.isfile(path_binary):
            self._cached_ffmpeg_path = os.path.abspath(path_binary)
            return self._cached_ffmpeg_path

        # Tier 2: Local AppData
        local_binary = self.get_local_appdata_ffmpeg()
        if local_binary.is_file() and os.access(local_binary, os.X_OK):
            self._cached_ffmpeg_path = str(local_binary.resolve())
            return self._cached_ffmpeg_path

        # Tier 3: imageio-ffmpeg static wheel
        try:
            import imageio_ffmpeg
            img_binary = imageio_ffmpeg.get_ffmpeg_exe()
            if img_binary and os.path.isfile(img_binary):
                self._cached_ffmpeg_path = os.path.abspath(img_binary)
                return self._cached_ffmpeg_path
        except (ImportError, Exception):
            pass

        return None

    def find_ffprobe(self) -> Optional[str]:
        """Locates ffprobe executable matching discovered ffmpeg or environment."""
        if self._cached_ffprobe_path and os.path.isfile(self._cached_ffprobe_path):
            return self._cached_ffprobe_path

        # Check alongside discovered ffmpeg
        ffmpeg_bin = self.find_ffmpeg()
        if ffmpeg_bin:
            ffmpeg_dir = Path(ffmpeg_bin).parent
            candidate = ffmpeg_dir / ("ffprobe.exe" if platform.system() == "Windows" else "ffprobe")
            if candidate.is_file() and os.access(candidate, os.X_OK):
                self._cached_ffprobe_path = str(candidate.resolve())
                return self._cached_ffprobe_path

        # Check PATH
        path_bin = shutil.which("ffprobe") or shutil.which("ffprobe.exe")
        if path_bin and os.path.isfile(path_bin):
            self._cached_ffprobe_path = os.path.abspath(path_bin)
            return self._cached_ffprobe_path

        # Check Local AppData
        local_bin = self.get_local_appdata_ffprobe()
        if local_bin.is_file() and os.access(local_bin, os.X_OK):
            self._cached_ffprobe_path = str(local_bin.resolve())
            return self._cached_ffprobe_path

        return None

    def is_available(self) -> bool:
        """Returns True if FFmpeg is discovered and executable, False otherwise."""
        return self.find_ffmpeg() is not None

    def get_ffmpeg_path(self) -> Optional[str]:
        """Returns the discovered FFmpeg executable path or None."""
        return self.find_ffmpeg()

    def get_ffprobe_path(self) -> Optional[str]:
        """Returns the discovered FFprobe executable path or None."""
        return self.find_ffprobe()

    def get_version(self, binary_path: Optional[str] = None) -> Optional[str]:
        """Extracts semantic version string from ffmpeg -version."""
        if self._cached_version and not binary_path:
            return self._cached_version

        exe = binary_path or self.find_ffmpeg()
        if not exe:
            return None

        try:
            res = subprocess.run(
                [exe, "-version"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if res.returncode == 0 and res.stdout:
                match = self.VERSION_REGEX.search(res.stdout)
                if match:
                    ver = match.group(1).strip()
                    if not binary_path:
                        self._cached_version = ver
                    return ver
        except Exception as e:
            self.logger.warning("Failed to extract FFmpeg version from %s: %s", exe, e)
        return None

    def provision_ffmpeg(
        self,
        download_url: Optional[str] = None,
        progress_hook: Optional[Callable[[float], None]] = None,
    ) -> str:
        """Tier 4: Downloads and provisions static FFmpeg/FFprobe binaries on Windows."""
        url = download_url or self.DEFAULT_WIN64_DOWNLOAD_URL
        dest_dir = self.get_local_appdata_dir()
        dest_dir.mkdir(parents=True, exist_ok=True)

        self.logger.info("Auto-provisioning static FFmpeg from %s to %s", url, dest_dir)

        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp_file:
            tmp_zip_path = Path(tmp_file.name)

        try:
            # Download with progress
            req = urllib.request.Request(url, headers={"User-Agent": "linkconv/1.0"})
            with urllib.request.urlopen(req, timeout=60) as resp, open(tmp_zip_path, "wb") as out:
                total = int(resp.headers.get("content-length", 0))
                downloaded = 0
                chunk_size = 64 * 1024
                while True:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    out.write(chunk)
                    downloaded += len(chunk)
                    if progress_hook and total > 0:
                        progress_hook(min(100.0, (downloaded / total) * 100.0))

            # Extract ffmpeg.exe and ffprobe.exe
            with zipfile.ZipFile(tmp_zip_path, "r") as z:
                for member in z.namelist():
                    norm_name = member.replace("\\", "/").lower()
                    if norm_name.endswith("ffmpeg.exe") or (norm_name.endswith("/ffmpeg") and platform.system() != "Windows"):
                        target = dest_dir / ("ffmpeg.exe" if platform.system() == "Windows" else "ffmpeg")
                        with z.open(member) as src, open(target, "wb") as dst:
                            shutil.copyfileobj(src, dst)
                        if platform.system() != "Windows":
                            os.chmod(target, 0o755)
                    elif norm_name.endswith("ffprobe.exe") or (norm_name.endswith("/ffprobe") and platform.system() != "Windows"):
                        target = dest_dir / ("ffprobe.exe" if platform.system() == "Windows" else "ffprobe")
                        with z.open(member) as src, open(target, "wb") as dst:
                            shutil.copyfileobj(src, dst)
                        if platform.system() != "Windows":
                            os.chmod(target, 0o755)

            resolved = self.get_local_appdata_ffmpeg()
            if resolved.is_file():
                self._cached_ffmpeg_path = str(resolved.resolve())
                return self._cached_ffmpeg_path
            raise RuntimeError(f"Extraction completed but {resolved} was not found in zip archive.")
        finally:
            if tmp_zip_path.exists():
                try:
                    tmp_zip_path.unlink()
                except OSError:
                    pass

    def ensure_ffmpeg(self, auto_download: bool = True) -> str:
        """Resolves FFmpeg executable path or raises FFmpegNotFoundError."""
        resolved = self.find_ffmpeg()
        if resolved:
            return resolved

        if auto_download and platform.system() == "Windows":
            try:
                return self.provision_ffmpeg()
            except Exception as e:
                self.logger.error("Auto-provisioning failed: %s", e)

        searched = [
            f"Custom override: {self.custom_path}" if self.custom_path else None,
            "System PATH (ffmpeg / ffmpeg.exe)",
            str(self.get_local_appdata_ffmpeg()),
            "imageio-ffmpeg module",
        ]
        searched_locations = [s for s in searched if s]
        raise FFmpegNotFoundError(
            searched_locations=searched_locations,
            message="FFmpeg executable could not be found on your system.",
            user_hint="Run 'linkconv setup-ffmpeg' to auto-download static binaries, or install FFmpeg manually and add it to PATH.",
        )

    def resolve(self) -> str:
        """Alias for ensure_ffmpeg(auto_download=False) for compatibility."""
        return self.ensure_ffmpeg(auto_download=False)
