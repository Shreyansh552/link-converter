"""High-performance media transcoding, remuxing, audio extraction, and packaging service.

File: src/linkconv/services/transcoding.py
"""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
import urllib.request

from pydantic import model_validator

from linkconv.core.exceptions import (
    FFmpegNotFoundError,
    InvalidOptionsError,
    TranscodingError,
)
from linkconv.core.models import (
    ConversionOptions as BaseConversionOptions,
    MediaFormat,
    MediaMetadata,
    Platform,
    SUPPORTED_AUDIO_FORMATS,
    SUPPORTED_VIDEO_FORMATS,
)
from linkconv.services.ffmpeg_resolver import FFmpegResolverService

VALID_VIDEO_QUALITIES = {"best", "4k", "2160p", "1440p", "2k", "1080p", "720p", "480p", "360p", "240p", "144p"}
VALID_AUDIO_QUALITIES = {"best", "320k", "256k", "192k", "128k", "96k", "64k"}


class ConversionOptions(BaseConversionOptions):
    """Extended ConversionOptions enforcing strict target quality and bitrate validation."""

    @model_validator(mode="after")
    def validate_quality_rules(self) -> ConversionOptions:
        q = (self.target_quality or "").lower().strip()
        if not q or q == "best":
            return self

        is_audio = self.extract_audio_only or (self.target_format in SUPPORTED_AUDIO_FORMATS)
        if is_audio:
            if q not in VALID_AUDIO_QUALITIES:
                raise ValueError(
                    f"Invalid audio quality/bitrate: '{self.target_quality}'. Allowed: {sorted(VALID_AUDIO_QUALITIES)}"
                )
        else:
            if q not in VALID_VIDEO_QUALITIES:
                raise ValueError(
                    f"Invalid video resolution/quality: '{self.target_quality}'. Allowed: {sorted(VALID_VIDEO_QUALITIES)}"
                )
        return self


def sanitize_filename(name: str, max_length: int = 120) -> str:
    """Sanitizes strings for safe cross-platform Windows/POSIX filenames."""
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name)
    cleaned = re.sub(r'[\s_]+', ' ', cleaned).strip(' .')
    reserved = {
        "CON", "PRN", "AUX", "NUL", "COM1", "COM2", "COM3", "COM4",
        "COM5", "COM6", "COM7", "COM8", "COM9", "LPT1", "LPT2",
        "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
    }
    if cleaned.upper() in reserved:
        cleaned = f"media_{cleaned}"
    if not cleaned:
        cleaned = "media_item"
    return cleaned[:max_length].strip(' .')


def is_direct_copy_eligible(
    vcodec: Optional[str],
    acodec: Optional[str],
    target_format: str,
) -> bool:
    """Evaluates whether source stream codecs can be direct-copied without transcoding."""
    fmt = target_format.lower().lstrip(".")
    vc = (vcodec or "").lower()
    ac = (acodec or "").lower()

    if fmt == "mkv":
        return True  # MKV container supports virtually all codecs natively

    if fmt == "mp4":
        is_video_compat = "avc1" in vc or "h264" in vc or "hevc" in vc or "hvc1" in vc
        is_audio_compat = not ac or ac == "none" or "mp4a" in ac or "aac" in ac or "mp3" in ac
        return bool(is_video_compat and is_audio_compat)

    if fmt == "webm":
        is_video_compat = "vp9" in vc or "vp8" in vc or "av01" in vc
        is_audio_compat = not ac or ac == "none" or "opus" in ac or "vorbis" in ac
        return bool(is_video_compat and is_audio_compat)

    if fmt == "opus":
        return "opus" in ac

    if fmt == "m4a":
        return "mp4a" in ac or "aac" in ac

    return False


class TranscodingService:
    """Executes media remuxing, transcoding, audio extraction, and asset packaging via FFmpeg."""

    def __init__(
        self,
        resolver: Optional[FFmpegResolverService] = None,
        ffmpeg_path: Optional[str] = None,
        working_dir: Optional[str] = None,
    ):
        self.resolver = resolver or FFmpegResolverService()
        self.ffmpeg_path = ffmpeg_path
        self.working_dir = Path(working_dir) if working_dir else None
        self.logger = logging.getLogger("linkconv.services.transcoding")

    def _get_ffmpeg_bin(self) -> str:
        if self.ffmpeg_path:
            return self.ffmpeg_path
        return self.resolver.ensure_ffmpeg(auto_download=False)

    async def convert(
        self,
        metadata: MediaMetadata,
        options: ConversionOptions,
        progress_callback: Optional[Callable[..., None]] = None,
    ) -> str:
        """Executes download and FFmpeg muxing/transcoding; returns output file path."""
        ffmpeg_bin = self._get_ffmpeg_bin()

        # Destination resolution
        out_dir = Path(options.output_dir or self.working_dir or os.getcwd())
        out_dir.mkdir(parents=True, exist_ok=True)

        ext = options.target_format.lower().lstrip(".")
        clean_title = sanitize_filename(metadata.title)
        if options.custom_filename:
            out_filename = options.custom_filename
        else:
            template = options.filename_template or "%(title)s.%(ext)s"
            uploader_str = sanitize_filename(metadata.uploader or "unknown")
            out_filename = template % {
                "title": clean_title,
                "id": metadata.id,
                "uploader": uploader_str,
                "ext": ext,
            }
        final_output_path = out_dir / out_filename

        # Scratch directory for intermediate files
        scratch_dir = Path(tempfile.mkdtemp(prefix=f"linkconv_{metadata.id}_"))
        try:
            is_audio_only = options.extract_audio_only or ext in SUPPORTED_AUDIO_FORMATS
            if is_audio_only:
                return await self._execute_audio_extraction(
                    ffmpeg_bin, metadata, options, scratch_dir, final_output_path, progress_callback
                )
            else:
                return await self._execute_video_conversion(
                    ffmpeg_bin, metadata, options, scratch_dir, final_output_path, progress_callback
                )
        finally:
            shutil.rmtree(scratch_dir, ignore_errors=True)

    async def _execute_video_conversion(
        self,
        ffmpeg_bin: str,
        metadata: MediaMetadata,
        options: ConversionOptions,
        scratch_dir: Path,
        output_path: Path,
        progress_callback: Optional[Callable[..., None]],
    ) -> str:
        ext = options.target_format.lower().lstrip(".")
        target_q = (options.target_quality or "best").lower()

        # 1. Resolve video & audio formats
        max_h = None
        if target_q.endswith("p"):
            try:
                max_h = int(target_q[:-1])
            except ValueError:
                pass
        elif target_q == "4k":
            max_h = 2160
        elif target_q in ("2k", "1440p"):
            max_h = 1440

        v_format = None
        if max_h:
            candidates = metadata.filter_formats(video_only=True, max_height=max_h)
            if candidates:
                v_format = candidates[0]
        if not v_format:
            v_format = metadata.best_video_format()

        if not v_format:
            raise TranscodingError(f"No suitable video stream found for {metadata.title}")

        a_format = None
        if v_format.is_dash or v_format.needs_muxing:
            a_format = metadata.best_audio_format()

        # 2. Prepare inputs (local files or downloaded streams)
        v_input = await self._materialize_stream(v_format, scratch_dir, "video_stream")
        a_input = None
        if a_format:
            a_input = await self._materialize_stream(a_format, scratch_dir, "audio_stream")

        # 3. Check direct copy vs transcode
        vcodec = v_format.vcodec
        acodec = a_format.acodec if a_format else v_format.acodec
        direct_copy = is_direct_copy_eligible(vcodec, acodec, ext)

        cmd = [ffmpeg_bin, "-y", "-nostats", "-progress", "pipe:1"]
        cmd.extend(["-i", str(v_input)])
        if a_input:
            cmd.extend(["-i", str(a_input)])

        if direct_copy:
            cmd.extend(["-c:v", "copy"])
            if a_input or (v_format.acodec and v_format.acodec.lower() != "none"):
                cmd.extend(["-c:a", "copy"])
        else:
            if ext == "mp4":
                cmd.extend([
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
                ])
            elif ext == "webm":
                cmd.extend([
                    "-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "30",
                    "-c:a", "libopus", "-b:a", "128k",
                ])
            else:
                cmd.extend(["-c:v", "copy", "-c:a", "copy"])

        if ext == "mp4":
            cmd.extend(["-movflags", "+faststart"])

        # Tag metadata
        cmd.extend(["-metadata", f"title={metadata.title}"])
        if metadata.uploader:
            cmd.extend(["-metadata", f"artist={metadata.uploader}"])
        album_name = metadata.platform.display_name if hasattr(metadata.platform, "display_name") else str(metadata.platform)
        cmd.extend(["-metadata", f"album={album_name} Conversion"])

        cmd.append(str(output_path))
        await self._run_ffmpeg_command(cmd, metadata.duration, progress_callback)
        return str(output_path)

    async def _execute_audio_extraction(
        self,
        ffmpeg_bin: str,
        metadata: MediaMetadata,
        options: ConversionOptions,
        scratch_dir: Path,
        output_path: Path,
        progress_callback: Optional[Callable[..., None]],
    ) -> str:
        ext = options.target_format.lower().lstrip(".")
        bitrate = options.target_quality if (options.target_quality and options.target_quality != "best") else "320k"
        if not bitrate.endswith("k"):
            bitrate = f"{bitrate}k"

        a_format = metadata.best_audio_format()
        if not a_format:
            a_format = metadata.best_video_format()
        if not a_format:
            raise TranscodingError(f"No audio stream available for {metadata.title}")

        a_input = await self._materialize_stream(a_format, scratch_dir, "audio_stream")

        thumb_input = None
        if options.embed_thumbnail and metadata.thumbnail_url:
            thumb_input = await self._materialize_asset(metadata.thumbnail_url, scratch_dir, "cover.jpg")

        cmd = [ffmpeg_bin, "-y", "-nostats", "-progress", "pipe:1"]
        cmd.extend(["-i", str(a_input)])
        if thumb_input and ext in ("mp3", "m4a"):
            cmd.extend(["-i", str(thumb_input)])

        cmd.append("-vn")

        if ext == "mp3":
            cmd.extend(["-c:a", "libmp3lame", "-b:a", bitrate])
            if thumb_input:
                cmd.extend([
                    "-map", "0:a", "-map", "1:0",
                    "-c:v", "mjpeg", "-id3v2_version", "3",
                    "-metadata:s:v", "title=Album cover",
                    "-metadata:s:v", "comment=Cover (front)",
                ])
        elif ext == "m4a":
            if is_direct_copy_eligible(None, a_format.acodec, "m4a"):
                cmd.extend(["-c:a", "copy"])
            else:
                cmd.extend(["-c:a", "aac", "-b:a", bitrate])
            if thumb_input:
                cmd.extend(["-map", "0:a", "-map", "1:0", "-c:v", "copy", "-disposition:v", "attached_pic"])
        elif ext == "wav":
            cmd.extend(["-c:a", "pcm_s16le", "-ar", "44100"])
        elif ext == "flac":
            cmd.extend(["-c:a", "flac", "-compression_level", "5"])
        elif ext == "opus":
            if is_direct_copy_eligible(None, a_format.acodec, "opus"):
                cmd.extend(["-c:a", "copy"])
            else:
                cmd.extend(["-c:a", "libopus", "-b:a", bitrate])
        else:
            cmd.extend(["-c:a", "copy"])

        # Tagging
        cmd.extend(["-metadata", f"title={metadata.title}"])
        if metadata.uploader:
            cmd.extend(["-metadata", f"artist={metadata.uploader}"])
        album_name = metadata.platform.display_name if hasattr(metadata.platform, "display_name") else str(metadata.platform)
        cmd.extend(["-metadata", f"album={album_name} Conversion"])

        cmd.append(str(output_path))
        await self._run_ffmpeg_command(cmd, metadata.duration, progress_callback)
        return str(output_path)

    async def _materialize_stream(self, fmt: MediaFormat, scratch_dir: Path, prefix: str) -> Path:
        """Ensures a stream URL is accessible locally by downloading to scratch directory if HTTP."""
        if not fmt.url:
            raise TranscodingError(f"Format {fmt.format_id} missing stream URL")

        if os.path.isfile(fmt.url) or not (fmt.url.startswith("http://") or fmt.url.startswith("https://")):
            return Path(fmt.url)

        target_file = scratch_dir / f"{prefix}_{fmt.format_id}.{fmt.ext}"
        if target_file.exists():
            return target_file

        url = fmt.url
        headers = fmt.http_headers or {"User-Agent": "linkconv/1.0"}
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp, open(target_file, "wb") as out:
            shutil.copyfileobj(resp, out)
        return target_file

    async def _materialize_asset(self, url: str, scratch_dir: Path, filename: str) -> Optional[Path]:
        """Downloads an asset (thumbnail) to scratch directory."""
        if os.path.isfile(url) or not (url.startswith("http://") or url.startswith("https://")):
            return Path(url)
        target = scratch_dir / filename
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "linkconv/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp, open(target, "wb") as out:
                shutil.copyfileobj(resp, out)
            return target
        except Exception as e:
            self.logger.warning("Failed to download asset %s: %s", url, e)
            return None

    def _call_progress(
        self,
        callback: Optional[Callable[..., None]],
        progress: float,
        speed: Optional[str] = None,
        elapsed: Optional[float] = None,
        stage: str = "converting",
    ) -> None:
        if not callback:
            return
        payload = {
            "progress": round(progress, 2),
            "speed": speed,
            "elapsed": round(elapsed or 0.0, 2),
            "stage": stage,
        }
        try:
            callback(payload)
        except TypeError:
            try:
                callback(progress, speed=speed, eta=None)
            except Exception:
                pass

    async def _run_ffmpeg_command(
        self,
        cmd: List[str],
        duration: Optional[float],
        progress_callback: Optional[Callable[..., None]],
    ) -> None:
        """Executes FFmpeg subprocess with asynchronous progress line parsing."""
        self.logger.debug("Running FFmpeg: %s", " ".join(cmd))
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        total_dur = duration or 0.0
        current_speed: Optional[str] = None

        async def read_progress():
            nonlocal current_speed
            if not proc.stdout:
                return
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                decoded = line.decode("utf-8", errors="replace").strip()
                if "=" in decoded:
                    k, v = decoded.split("=", 1)
                    k, v = k.strip(), v.strip()
                    if k == "speed":
                        current_speed = v
                    elif k == "out_time_us" and total_dur > 0:
                        try:
                            sec = int(v) / 1_000_000.0
                            pct = min(100.0, max(0.0, (sec / total_dur) * 100.0))
                            self._call_progress(
                                progress_callback,
                                progress=pct,
                                speed=current_speed,
                                elapsed=sec,
                                stage="converting",
                            )
                        except ValueError:
                            pass
                    elif k == "progress" and v == "end":
                        self._call_progress(
                            progress_callback,
                            progress=100.0,
                            speed=current_speed,
                            elapsed=total_dur,
                            stage="completed",
                        )

        await asyncio.gather(read_progress(), proc.wait())

        if proc.returncode != 0:
            stderr_bytes = await proc.stderr.read() if proc.stderr else b""
            stderr_text = stderr_bytes.decode("utf-8", errors="replace")
            raise TranscodingError(
                message=f"FFmpeg transcoding failed with returncode {proc.returncode}",
                command=cmd,
                returncode=proc.returncode,
                stderr=stderr_text,
            )
