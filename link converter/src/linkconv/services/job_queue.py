"""Asynchronous Job Queue Service for conversion task management and SSE streaming.

File: src/linkconv/services/job_queue.py
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import json
import logging
import os
from pathlib import Path
import platform
import shutil
import time
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional, Set, Union
import uuid

from linkconv.core.exceptions import (
    ErrorCode,
    LinkConvError,
)
from linkconv.core.models import (
    ConversionOptions,
    ConversionRequest,
    JobState,
    JobStatus,
    MediaMetadata,
)

logger = logging.getLogger("linkconv.services.job_queue")


class JobRecord:
    """In-memory operational record for an asynchronous job."""

    def __init__(
        self,
        job_id: str,
        url: str,
        options: Optional[ConversionOptions] = None,
        state: JobState = JobState.PENDING,
        temp_dir: Optional[Path] = None,
    ):
        self.job_id: str = job_id
        self.url: str = url
        self.options: ConversionOptions = options or ConversionOptions()
        self.state: JobState = state
        self.progress: float = 0.0
        self.stage: str = "queued"
        self.speed: Optional[str] = None
        self.eta: Optional[int] = None
        self.output_path: Optional[str] = None
        self.output_size_bytes: Optional[int] = None
        self.error_message: Optional[str] = None
        self.error_code: Optional[str] = None
        self.metadata: Optional[MediaMetadata] = None
        self.temp_dir: Optional[Path] = temp_dir
        self.created_at: float = time.time()
        self.updated_at: float = time.time()
        self.completed_at: Optional[float] = None

        # Async orchestration primitives
        self.task: Optional[asyncio.Task] = None
        self.cancel_event: asyncio.Event = asyncio.Event()
        self.subscribers: Set[asyncio.Queue] = set()

    @property
    def status(self) -> str:
        """Canonical status string matching external contracts."""
        if self.state in (JobState.EXTRACTING, JobState.DOWNLOADING, JobState.CONVERTING):
            return "processing"
        val = getattr(self.state, "value", str(self.state)).lower()
        if val in ("processing", "converting", "downloading", "extracting"):
            return "processing"
        if self.state == JobState.PENDING or val in ("pending", "queued"):
            return "pending"
        if self.state == JobState.COMPLETED or val == "completed":
            return "completed"
        if self.state == JobState.FAILED or val == "failed":
            return "failed"
        if self.state == JobState.CANCELLED or val == "cancelled":
            return "cancelled"
        return val

    @property
    def error(self) -> Optional[str]:
        """Backward-compatible alias for error_message."""
        return self.error_message

    @property
    def is_finished(self) -> bool:
        """True if job has reached a terminal state."""
        return self.state in (JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED)

    def to_dict(self) -> Dict[str, Any]:
        """Convert job state to JSON-serializable dictionary."""
        return {
            "job_id": self.job_id,
            "url": self.url,
            "status": self.status,
            "state": self.state.value if hasattr(self.state, "value") else str(self.state),
            "progress": round(self.progress, 1),
            "stage": self.stage,
            "speed": self.speed,
            "eta": self.eta,
            "output_path": self.output_path,
            "output_size_bytes": self.output_size_bytes,
            "error": self.error_message,
            "error_message": self.error_message,
            "error_code": self.error_code,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
            "metadata": self.metadata.to_dict() if self.metadata else None,
        }

    def to_job_status(self) -> JobStatus:
        """Convert to domain JobStatus model."""
        return JobStatus(
            job_id=self.job_id,
            state=self.state,
            progress=self.progress,
            speed=self.speed,
            eta=self.eta,
            current_step=self.stage,
            error_message=self.error_message,
            error_code=self.error_code,
            output_path=self.output_path,
            output_size_bytes=self.output_size_bytes,
            created_at=self.created_at,
            updated_at=self.updated_at,
            metadata=self.metadata,
        )


class JobQueueService:
    """In-memory asynchronous job manager with SSE progress streaming and concurrency limits."""

    def __init__(
        self,
        max_concurrency: int = 3,
        extraction_service: Optional[Any] = None,
        transcoding_service: Optional[Any] = None,
        temp_dir: Optional[str] = None,
        job_ttl_seconds: float = 3600.0,
    ) -> None:
        self.max_concurrency = max_concurrency
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self.extraction_service = extraction_service
        self.transcoding_service = transcoding_service
        self._job_ttl_seconds = job_ttl_seconds
        self._jobs: Dict[str, JobRecord] = {}

        if temp_dir:
            self._base_temp_dir = Path(temp_dir)
        elif platform.system() == "Windows":
            base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
            self._base_temp_dir = Path(base) / "linkconv" / "temp" / "jobs"
        else:
            self._base_temp_dir = Path.home() / ".local" / "share" / "linkconv" / "temp" / "jobs"

        self._base_temp_dir.mkdir(parents=True, exist_ok=True)

    def _broadcast(self, job: JobRecord, event_data: Dict[str, Any]) -> None:
        """Pushes an event payload to all active client subscriber queues for a job."""
        dead_queues = []
        for q in list(job.subscribers):
            try:
                q.put_nowait(event_data)
            except asyncio.QueueFull:
                dead_queues.append(q)
            except Exception:
                dead_queues.append(q)
        for dq in dead_queues:
            job.subscribers.discard(dq)

    def create_job(
        self,
        request: Union[Dict[str, Any], ConversionRequest, str],
        options: Optional[ConversionOptions] = None,
        job_id: Optional[str] = None,
    ) -> str:
        """Creates a job record in PENDING state with unique ID."""
        url = ""
        opts = options

        if isinstance(request, str):
            url = request.strip()
        elif isinstance(request, ConversionRequest):
            url = request.url
            opts = opts or request.options
        elif isinstance(request, dict):
            url = request.get("url", "")
            if not opts:
                fmt = request.get("format", request.get("target_format", "mp4"))
                q = request.get("quality", request.get("target_quality", "best"))
                opts = ConversionOptions(target_format=fmt, target_quality=q)

        jid = job_id or uuid.uuid4().hex[:12]
        job_temp = self._base_temp_dir / f"job_{jid}"
        job_temp.mkdir(parents=True, exist_ok=True)

        record = JobRecord(
            job_id=jid,
            url=url,
            options=opts or ConversionOptions(),
            state=JobState.PENDING,
            temp_dir=job_temp,
        )
        self._jobs[jid] = record
        return jid

    def get_job(self, job_id: str) -> Optional[JobRecord]:
        """Returns the JobRecord for given job_id or None if not found."""
        return self._jobs.get(job_id)

    def list_jobs(self, status: Optional[str] = None, limit: int = 50) -> List[JobRecord]:
        """Lists registered jobs with optional status filter and limit."""
        results = list(self._jobs.values())
        if status:
            target_status = status.lower().strip()
            results = [j for j in results if j.status.lower() == target_status]
        results.sort(key=lambda j: j.created_at, reverse=True)
        return results[:limit]

    def update_progress(
        self,
        job_id: str,
        progress: float,
        stage: Optional[str] = None,
        speed: Optional[str] = None,
        eta: Optional[int] = None,
    ) -> None:
        """Updates job progress and broadcasts event to all active SSE subscribers."""
        job = self._jobs.get(job_id)
        if not job:
            raise KeyError(f"Job '{job_id}' not found")

        # Automatically transition pending jobs into active conversion state
        if job.state == JobState.PENDING:
            job.state = JobState.CONVERTING

        job.progress = max(0.0, min(100.0, float(progress)))
        if stage is not None:
            job.stage = stage
        if speed is not None:
            job.speed = speed
        if eta is not None:
            job.eta = eta
        job.updated_at = time.time()

        event = {
            "event": "progress",
            "job_id": job_id,
            "status": job.status,
            "progress": job.progress,
            "stage": job.stage,
            "speed": job.speed,
            "eta": job.eta,
        }
        self._broadcast(job, event)

    def complete_job(
        self,
        job_id: str,
        output_path: str,
        output_size_bytes: Optional[int] = None,
        metadata: Optional[MediaMetadata] = None,
    ) -> None:
        """Marks job COMPLETED, records output file info, and broadcasts terminal event."""
        job = self._jobs.get(job_id)
        if not job:
            raise KeyError(f"Job '{job_id}' not found")

        job.state = JobState.COMPLETED
        job.progress = 100.0
        job.stage = "completed"
        job.output_path = output_path
        if metadata:
            job.metadata = metadata

        if output_size_bytes is not None:
            job.output_size_bytes = output_size_bytes
        elif output_path and os.path.isfile(output_path):
            try:
                job.output_size_bytes = os.path.getsize(output_path)
            except OSError:
                pass

        job.completed_at = time.time()
        job.updated_at = time.time()

        # Clean intermediate scratch files from job temp_dir (keeping output if inside)
        if job.temp_dir and job.temp_dir.exists():
            for item in job.temp_dir.glob("*"):
                if str(item.resolve()) != str(Path(output_path).resolve()):
                    try:
                        if item.is_file():
                            item.unlink()
                        elif item.is_dir():
                            shutil.rmtree(item, ignore_errors=True)
                    except OSError:
                        pass

        event = {
            "event": "completed",
            "job_id": job_id,
            "status": "completed",
            "progress": 100.0,
            "output_path": job.output_path,
            "output_size_bytes": job.output_size_bytes,
        }
        self._broadcast(job, event)

    def fail_job(
        self,
        job_id: str,
        error: str,
        error_code: Optional[str] = None,
    ) -> None:
        """Marks job FAILED, logs diagnostic error, and broadcasts terminal event."""
        job = self._jobs.get(job_id)
        if not job:
            raise KeyError(f"Job '{job_id}' not found")

        job.state = JobState.FAILED
        job.error_message = error
        job.error_code = error_code or "LC_ERR_UNKNOWN"
        job.stage = f"failed: {error}"
        job.completed_at = time.time()
        job.updated_at = time.time()

        # Purge scratch files
        if job.temp_dir and job.temp_dir.exists():
            shutil.rmtree(job.temp_dir, ignore_errors=True)

        event = {
            "event": "failed",
            "job_id": job_id,
            "status": "failed",
            "error": error,
            "error_code": job.error_code,
        }
        self._broadcast(job, event)

    def cancel_job(self, job_id: str) -> bool:
        """Cancels active job, halts background task, purges scratch files, returns True."""
        job = self._jobs.get(job_id)
        if not job or job.is_finished:
            return False

        job.state = JobState.CANCELLED
        job.stage = "cancelled"
        job.cancel_event.set()
        job.completed_at = time.time()
        job.updated_at = time.time()

        if job.task and not job.task.done():
            job.task.cancel()

        # Purge scratch directory
        if job.temp_dir and job.temp_dir.exists():
            shutil.rmtree(job.temp_dir, ignore_errors=True)

        event = {
            "event": "cancelled",
            "job_id": job_id,
            "status": "cancelled",
        }
        self._broadcast(job, event)
        return True

    async def submit_job(
        self,
        url: str,
        options: Optional[ConversionOptions] = None,
        cookies: Optional[str] = None,
        proxy: Optional[str] = None,
    ) -> str:
        """Submits a conversion job to the background execution runner."""
        job_id = self.create_job(request={"url": url}, options=options)
        job = self._jobs[job_id]

        job.task = asyncio.create_task(
            self._job_worker(job_id=job_id, cookies=cookies, proxy=proxy)
        )
        return job_id

    async def _job_worker(
        self,
        job_id: str,
        cookies: Optional[str] = None,
        proxy: Optional[str] = None,
    ) -> None:
        """Background worker executing extraction and transcoding under concurrency semaphore."""
        job = self._jobs.get(job_id)
        if not job:
            return

        async with self._semaphore:
            if job.cancel_event.is_set():
                return

            try:
                # Extraction Stage
                self.update_progress(job_id, progress=5.0, stage="extracting")
                if not self.extraction_service:
                    from linkconv.extractors.engine import MediaExtractionService
                    self.extraction_service = MediaExtractionService()

                metadata = await self.extraction_service.extract_info(
                    url=job.url, cookies=cookies, proxy=proxy
                )
                job.metadata = metadata

                if job.cancel_event.is_set():
                    return

                # Transcoding Stage
                self.update_progress(job_id, progress=15.0, stage="transcoding")
                if not self.transcoding_service:
                    from linkconv.services.transcoding import TranscodingService
                    self.transcoding_service = TranscodingService()

                def on_transcode_progress(data: Union[Dict[str, Any], float], **kwargs):
                    if job.cancel_event.is_set():
                        return
                    if isinstance(data, dict):
                        pct = data.get("progress", 0.0)
                        speed = data.get("speed")
                        eta = data.get("eta")
                    else:
                        pct = float(data)
                        speed = kwargs.get("speed")
                        eta = kwargs.get("eta")
                    overall = 15.0 + (pct * 0.80)
                    self.update_progress(
                        job_id,
                        progress=overall,
                        stage="transcoding",
                        speed=speed,
                        eta=eta,
                    )

                job_opts = job.options
                if not job_opts.output_dir:
                    job_opts = job_opts.model_copy(update={"output_dir": str(job.temp_dir)})

                output_file = await self.transcoding_service.convert(
                    metadata=metadata,
                    options=job_opts,
                    progress_callback=on_transcode_progress,
                )

                self.complete_job(job_id, output_path=output_file, metadata=metadata)

            except asyncio.CancelledError:
                self.cancel_job(job_id)
                raise
            except Exception as exc:
                err_code = getattr(exc, "error_code", "LC_ERR_UNKNOWN")
                code_val = err_code.value if hasattr(err_code, "value") else str(err_code)
                self.fail_job(job_id, error=str(exc), error_code=code_val)

    async def subscribe_events(
        self,
        job_id: str,
        ping_interval: float = 15.0,
    ) -> AsyncGenerator[str, None]:
        """Asynchronous generator streaming real-time SSE progress events."""
        job = self._jobs.get(job_id)
        if not job:
            payload = json.dumps({"error": f"Job '{job_id}' not found", "error_code": "LC_ERR_JOB_NOT_FOUND"})
            yield f"event: error\ndata: {payload}\n\n"
            return

        client_queue: asyncio.Queue = asyncio.Queue(maxsize=200)
        if not job.is_finished:
            job.subscribers.add(client_queue)

        try:
            # Immediate initial state snapshot
            initial_data = json.dumps(job.to_dict())
            yield f"event: progress\ndata: {initial_data}\n\n"

            if job.is_finished:
                return
            while True:
                try:
                    event_data = await asyncio.wait_for(client_queue.get(), timeout=ping_interval)
                    evt_type = event_data.get("event", "progress")
                    yield f"event: {evt_type}\ndata: {json.dumps(event_data)}\n\n"

                    if event_data.get("status") in ("completed", "failed", "cancelled"):
                        break
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        except (GeneratorExit, asyncio.CancelledError):
            pass
        finally:
            job.subscribers.discard(client_queue)

    def cleanup_expired_jobs(self, max_age_seconds: Optional[float] = None) -> int:
        """Purges completed, failed, or cancelled jobs older than TTL and removes scratch files."""
        ttl = max_age_seconds if max_age_seconds is not None else self._job_ttl_seconds
        cutoff = time.time() - ttl
        purged = 0

        for jid in list(self._jobs.keys()):
            job = self._jobs[jid]
            if job.is_finished and job.updated_at < cutoff:
                if job.temp_dir and job.temp_dir.exists():
                    shutil.rmtree(job.temp_dir, ignore_errors=True)
                del self._jobs[jid]
                purged += 1

        return purged

    def shutdown(self) -> None:
        """Cancels all active jobs and purges resources."""
        for jid in list(self._jobs.keys()):
            job = self._jobs[jid]
            if not job.is_finished:
                self.cancel_job(jid)
