"""Data access repositories package for Single-Instructor LMS."""

from app.repositories.assignment_repo import AssignmentRepository
from app.repositories.audit_repo import AuditRepository
from app.repositories.certificate_repo import CertificateRepository
from app.repositories.enrollment_repo import EnrollmentRepository
from app.repositories.notification_repo import (
    NotificationOutboxRepository,
    OutboxRepository,
)
from app.repositories.order_repo import OrderRepository
from app.repositories.progress_repo import ProgressRepository
from app.repositories.quiz_repo import QuizRepository
from app.repositories.session_repo import SessionRepository
from app.repositories.token_repo import AuthTokenRepository
from app.repositories.transcode_job_repo import MediaTranscodeJobRepository
from app.repositories.user_repo import UserRepository

__all__ = [
    "AuditRepository",
    "EnrollmentRepository",
    "MediaTranscodeJobRepository",
    "NotificationOutboxRepository",
    "OutboxRepository",
    "UserRepository",
    "SessionRepository",
    "AuthTokenRepository",
    "OrderRepository",
    "AssignmentRepository",
    "QuizRepository",
    "ProgressRepository",
    "CertificateRepository",
]
