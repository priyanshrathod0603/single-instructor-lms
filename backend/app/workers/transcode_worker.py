"""Asynchronous background worker polling and executing video transcoding jobs.

Architecture Specifications:
- VM-02: Video Transcoding Infrastructure (FFmpeg + HLS)
- docs/backend/04-DATABASE-ARCHITECTURE.md
- docs/backend/15-FILE-MEDIA-ARCHITECTURE.md

Strict Invariants:
1. High-Throughput Leasing: Uses PostgreSQL FOR UPDATE SKIP LOCKED during polling.
2. Graceful Shutdown: Listens to SIGTERM/SIGINT signals; allows in-flight jobs to complete or safely recover.
3. Crash Recovery: Recovers stale jobs abandoned by worker crashes or timeouts.
4. Independent Execution: Can run as a standalone process (python -m app.workers.transcode_worker) or programmatic runner.
"""

import argparse
import asyncio
import logging
import os
import signal
import socket
import sys
from typing import Any, Callable, Optional, Union

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core import database as db_module
from app.core.config import Settings, get_settings
from app.repositories.transcode_job_repo import MediaTranscodeJobRepository
from app.services.transcode_service import TranscodeService

logger = logging.getLogger(__name__)


class TranscodeWorker:
    """Worker polling the media_transcode_jobs queue and executing multi-resolution FFmpeg transcoding."""

    def __init__(
        self,
        service: Optional[TranscodeService] = None,
        job_repo: Optional[MediaTranscodeJobRepository] = None,
        session_factory: Optional[Any] = None,
        batch_size: int = 2,
        poll_interval: float = 3.0,
        stale_threshold_seconds: int = 600,
        worker_id: Optional[str] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.service = service or TranscodeService(settings=self.settings)
        self.job_repo = job_repo or MediaTranscodeJobRepository()
        self.session_factory = session_factory
        self.batch_size = max(1, batch_size)
        self.poll_interval = max(0.5, poll_interval)
        self.stale_threshold_seconds = max(60, stale_threshold_seconds)
        self.worker_id = worker_id or f"{socket.gethostname()}_{os.getpid()}"

        self._running: bool = False
        self._stop_event: asyncio.Event = asyncio.Event()

    def _get_session(self) -> Session:
        """Obtain a database session."""
        if self.session_factory is not None:
            return self.session_factory()
        if db_module.SessionLocal is not None:
            return db_module.SessionLocal()
        raise RuntimeError("Database session factory is not configured for TranscodeWorker.")

    async def run_once(self) -> int:
        """Execute a single polling, claiming, processing, and settlement cycle.

        Returns:
            Number of jobs claimed and processed during this cycle.
        """
        session = self._get_session()
        processed_count = 0

        try:
            # 1. Recover stale processing jobs left by crashed workers
            with session.begin():
                recovered = self.job_repo.recover_stale_processing_jobs(
                    session,
                    stale_threshold_seconds=self.stale_threshold_seconds,
                )
            if recovered > 0:
                logger.warning("TranscodeWorker recovered %d stale processing job(s).", recovered)

            # 2. Claim pending eligible jobs with row-level lock
            with session.begin():
                jobs = self.job_repo.claim_pending_jobs(
                    session,
                    batch_size=self.batch_size,
                    worker_id=self.worker_id,
                )

            if not jobs:
                return 0

            logger.info("TranscodeWorker %s claimed %d job(s).", self.worker_id, len(jobs))

            # 3. Process each claimed job
            for job in jobs:
                try:
                    # Execute in dedicated transaction
                    with session.begin():
                        await self.service.process_job(session, job.id)
                    processed_count += 1
                except Exception as job_err:
                    logger.exception("Error processing transcode job %s: %s", job.id, job_err)

            return processed_count

        finally:
            session.close()

    async def run_forever(self) -> None:
        """Run continuous polling loop until shutdown signal received."""
        self._running = True
        self._stop_event.clear()
        logger.info("TranscodeWorker %s starting polling loop (poll_interval=%.1fs)...", self.worker_id, self.poll_interval)

        # Setup OS signal handlers if running in main thread
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, self.stop)
            except (NotImplementedError, RuntimeError):
                # Signals not available in some environments/threads
                pass

        try:
            while self._running and not self._stop_event.is_set():
                try:
                    processed = await self.run_once()
                    if processed == 0:
                        try:
                            await asyncio.wait_for(self._stop_event.wait(), timeout=self.poll_interval)
                        except asyncio.TimeoutError:
                            pass
                except Exception as cycle_err:
                    logger.exception("Unexpected error in transcode worker cycle: %s", cycle_err)
                    await asyncio.sleep(self.poll_interval)
        finally:
            logger.info("TranscodeWorker %s stopped gracefully.", self.worker_id)
            self._running = False

    def stop(self) -> None:
        """Signal worker to stop gracefully after current jobs conclude."""
        logger.info("TranscodeWorker %s received stop signal.", self.worker_id)
        self._running = False
        self._stop_event.set()


def main() -> None:
    """CLI entrypoint for running the transcoding background worker."""
    parser = argparse.ArgumentParser(description="Single-Instructor LMS Video Transcoding Worker")
    parser.add_argument("--once", action="store_true", help="Run a single processing cycle and exit")
    parser.add_argument("--batch-size", type=int, default=2, help="Number of jobs to claim per batch")
    parser.add_argument("--poll-interval", type=float, default=3.0, help="Seconds to sleep between polls")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    worker = TranscodeWorker(
        batch_size=args.batch_size,
        poll_interval=args.poll_interval,
    )

    if args.once:
        count = asyncio.run(worker.run_once())
        logger.info("Transcode worker completed single run. Processed %d job(s).", count)
    else:
        asyncio.run(worker.run_forever())


if __name__ == "__main__":
    main()
