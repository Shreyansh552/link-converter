"""Application services registry for the linkconv framework.

Exports all Milestone 2 domain services:
- FFmpegResolverService: Windows auto-discovery and binary provisioning
- TranscodingService: Video muxing, audio extraction, and format conversion
- ConversionOptions: Enhanced conversion options model with bitrate validation
- MediaAssetService: Thumbnail cascade, carousel bundling, and avatar fetching
- EmbedFormatterService: oEmbed, Markdown, HTML iframe, and BBCode generation
- JobQueueService: In-memory async job runner with SSE event streaming
- JobRecord: Job execution and state tracking model
"""
from __future__ import annotations

from linkconv.services.ffmpeg_resolver import FFmpegResolverService
from linkconv.services.transcoding import TranscodingService, ConversionOptions
from linkconv.services.assets import MediaAssetService
from linkconv.services.embeds import EmbedFormatterService
from linkconv.services.job_queue import JobQueueService, JobRecord
from linkconv.extractors.engine import MediaExtractionService

__all__ = [
    "FFmpegResolverService",
    "TranscodingService",
    "ConversionOptions",
    "MediaAssetService",
    "EmbedFormatterService",
    "JobQueueService",
    "JobRecord",
    "MediaExtractionService",
]
