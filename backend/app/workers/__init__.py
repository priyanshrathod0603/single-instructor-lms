"""Background workers package for Single-Instructor LMS."""

from app.workers.outbox_worker import OutboxWorker

__all__ = ["OutboxWorker"]
