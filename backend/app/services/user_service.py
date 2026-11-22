"""UserService orchestrating User Management, Staff Onboarding, and RBAC Administration.

Architecture Specifications:
- docs/backend/06-API-ARCHITECTURE.md (Section 2.2)
- docs/backend/09-RBAC-PERMISSION-ARCHITECTURE.md
- docs/backend/10-USER-MANAGEMENT.md
- docs/backend/17-AUDIT-LOG-ARCHITECTURE.md
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK203, TASK204)
- Single_Instructor_LMS_Blueprint_v2_Detailed_Specification(1).pdf [Pages 2-3, 8]

Strict Invariants:
1. Sole Super Admin Protection: Under NO circumstance may the final active Super Admin
   be suspended, demoted, or have their role revoked.
2. Immediate Session Revocation: Suspending an account atomically revokes all active sessions.
3. Cryptographic Staff Onboarding: High-entropy 32-byte URL-safe token, SHA-256 hashed, 48h TTL.
4. Transactional Outbox & Auditing: All lifecycle mutations stage outbox events and immutable audit entries.
"""

from datetime import timedelta
import math
from typing import Any, Optional, Tuple, Union
import uuid

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.exceptions import (
    BadRequestException,
    ConflictException,
    ForbiddenException,
    NotFoundException,
    ValidationException,
)
from app.core.security import (
    generate_secure_token,
    hash_password,
    hash_token,
    validate_password_complexity,
)
from app.models.assignment import Assignment, AssignmentSubmission
from app.models.audit_log import AuditLog
from app.models.auth_token import TOKEN_TYPE_STAFF_ONBOARDING
from app.models.base import utc_now
from app.models.certificate import Certificate
from app.models.course import Course
from app.models.enrollment import Enrollment
from app.models.notification import OUTBOX_CHANNEL_EMAIL
from app.models.progress import CourseProgressSummary
from app.models.quiz import Quiz, QuizAttempt
from app.models.user import (
    ROLE_ADMIN,
    ROLE_STAFF,
    ROLE_SUPER_ADMIN,
    SYSTEM_ROLES,
    Role,
    User,
)
from app.repositories.session_repo import SessionRepository
from app.repositories.token_repo import AuthTokenRepository
from app.repositories.user_repo import UserRepository
from app.schemas.user import (
    StudentAssignmentSubmissionSummary,
    StudentCertificateSummary,
    StudentEnrollmentSummary,
    StudentLearningSummaryResponse,
    StudentQuizAttemptSummary,
    UserCreateRequest,
    UserDirectoryItemResponse,
    UserDirectoryResponse,
    UserProfileResponse,
    validate_email_syntax,
    validate_phone_syntax,
)
from app.services.audit_service import AuditService
from app.services.outbox_service import OutboxService


class UserService:
    """Service handling user directory queries, staff onboarding, profile updates, and RBAC governance."""

    def __init__(
        self,
        user_repo: Optional[UserRepository] = None,
        session_repo: Optional[SessionRepository] = None,
        token_repo: Optional[AuthTokenRepository] = None,
        audit_service: Optional[AuditService] = None,
        outbox_service: Optional[OutboxService] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        self.user_repo = user_repo or UserRepository()
        self.session_repo = session_repo or SessionRepository()
        self.token_repo = token_repo or AuthTokenRepository()
        self.audit_service = audit_service or AuditService()
        self.outbox_service = outbox_service or OutboxService()
        self.settings = settings or get_settings()

    async def list_users(
        self,
        session: Union[AsyncSession, Session],
        *,
        search: Optional[str] = None,
        role: Optional[str] = None,
        is_active: Optional[bool] = None,
        is_verified: Optional[bool] = None,
        sort_by: Optional[str] = "created_at",
        sort_order: Optional[str] = "desc",
        page: int = 1,
        per_page: int = 20,
    ) -> UserDirectoryResponse:
        """Retrieve paginated user directory list with filters and dynamic sorting."""
        users, total = await self.user_repo.list_users(
            session,
            search=search,
            role=role,
            is_active=is_active,
            is_verified=is_verified,
            sort_by=sort_by,
            sort_order=sort_order,
            page=page,
            per_page=per_page,
        )
        total_pages = math.ceil(total / per_page) if per_page > 0 else 0
        items = [
            UserDirectoryItemResponse(
                id=u.id,
                email=u.email,
                full_name=u.full_name,
                phone=u.phone,
                avatar_url=u.avatar_url,
                is_verified=u.is_verified,
                is_active=u.is_active,
                roles=u.roles,
                created_at=u.created_at,
            )
            for u in users
        ]
        return UserDirectoryResponse(
            items=items,
            total=total,
            page=page,
            per_page=per_page,
            total_pages=total_pages,
        )

    async def get_user_profile(
        self,
        session: Union[AsyncSession, Session],
        user_id: Union[uuid.UUID, str],
    ) -> UserProfileResponse:
        """Fetch complete user profile with assigned roles and aggregated permissions."""
        user = await self.user_repo.get_by_id(session, user_id)
        if user is None:
            raise NotFoundException(message="User not found.", code="USER_NOT_FOUND")

        permissions = sorted(list(user.get_aggregated_permissions()))
        return UserProfileResponse(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            phone=user.phone,
            avatar_url=user.avatar_url,
            is_verified=user.is_verified,
            is_active=user.is_active,
            roles=user.roles,
            permissions=permissions,
            created_at=user.created_at or utc_now(),
            updated_at=user.updated_at or utc_now(),
        )

    async def create_user(
        self,
        session: Union[AsyncSession, Session],
        data: UserCreateRequest,
        *,
        actor: User,
    ) -> UserProfileResponse:
        """Provision a new user account with personal details, credentials, and role.

        Guarantees:
        1. Caller Authorization: Strictly restricted to active SUPER_ADMIN users.
        2. Credential Validation: Enforces backend password complexity and RFC email syntax.
        3. Email Uniqueness: Checks against normalized email address.
        4. Password Security: Hashes password with Argon2id; never stores plaintext.
        5. Role Assignment: Assigns canonical role from SYSTEM_ROLES (SUPER_ADMIN, ADMIN, STAFF, STUDENT).
        6. Audit Logging: Permanently records USER_CREATED event with actor reference and safe snapshot.
        7. Pre-verification: Super Admin provisioned accounts are pre-verified (is_verified=True).
        """
        if not actor.has_role(ROLE_SUPER_ADMIN):
            raise ForbiddenException(
                message="Only Super Administrators are authorized to provision user accounts.",
                code="SUPER_ADMIN_REQUIRED",
            )

        # 1. Independent backend password complexity validation
        validate_password_complexity(data.password)

        # 2. Normalize and validate email syntax
        normalized_email = validate_email_syntax(data.email)

        # 3. Validate phone syntax and digit length
        cleaned_phone = validate_phone_syntax(data.phone)

        # 4. Check email uniqueness
        existing = await self.user_repo.get_by_email(session, normalized_email)
        if existing is not None:
            raise ConflictException(
                message="An account with this email address already exists.",
                code="EMAIL_ALREADY_EXISTS",
                details={"email": normalized_email},
            )

        # 5. Verify role exists in SYSTEM_ROLES
        role_id = data.role.strip().upper()
        if role_id not in SYSTEM_ROLES:
            raise ValidationException(
                message=f"Invalid system role: {role_id}",
                code="INVALID_ROLE",
            )

        # 6. Hash password using Argon2id
        password_hash = hash_password(data.password)

        # 7. Create user entity via repository
        user = await self.user_repo.create_user(
            session,
            email=normalized_email,
            full_name=data.full_name.strip(),
            phone=cleaned_phone,
            password_hash=password_hash,
            avatar_url=None,
            is_verified=True,
            role_id=role_id,
            assigned_by=actor.id,
        )

        # 8. Record audit log
        await self.audit_service.record_event(
            session,
            action="USER_CREATED",
            resource_type="user",
            resource_id=str(user.id),
            actor_id=actor.id,
            actor_type="SUPER_ADMIN",
            before_state=None,
            after_state={
                "id": str(user.id),
                "email": user.email,
                "full_name": user.full_name,
                "phone": user.phone,
                "role": role_id,
                "roles": user.roles,
                "is_active": user.is_active,
                "is_verified": user.is_verified,
            },
        )

        permissions = sorted(list(user.get_aggregated_permissions()))
        return UserProfileResponse(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            phone=user.phone,
            avatar_url=user.avatar_url,
            is_verified=user.is_verified,
            is_active=user.is_active,
            roles=user.roles,
            permissions=permissions,
            created_at=user.created_at or utc_now(),
            updated_at=user.updated_at or utc_now(),
        )

    async def get_student_learning_summary(
        self,
        session: Union[AsyncSession, Session],
        user_id: Union[uuid.UUID, str],
    ) -> StudentLearningSummaryResponse:
        """Fetch unified learning history and audit trail for a student profile."""
        profile = await self.get_user_profile(session, user_id)
        uid = profile.id

        # 1. Enrollments with Course & CourseProgressSummary
        stmt_enr = (
            select(Enrollment, Course, CourseProgressSummary)
            .join(Course, Course.id == Enrollment.course_id)
            .outerjoin(
                CourseProgressSummary,
                sa.and_(
                    CourseProgressSummary.student_id == Enrollment.student_id,
                    CourseProgressSummary.course_id == Enrollment.course_id,
                ),
            )
            .where(Enrollment.student_id == uid)
            .order_by(Enrollment.granted_at.desc())
        )
        if isinstance(session, AsyncSession):
            enr_res = (await session.execute(stmt_enr)).all()
        else:
            enr_res = session.execute(stmt_enr).all()

        enrollments = [
            StudentEnrollmentSummary(
                id=enr.id,
                course_id=crs.id,
                course_title=crs.title,
                course_slug=crs.slug,
                status=enr.status,
                granted_at=enr.granted_at,
                expires_at=enr.expires_at,
                progress_percentage=float(prog.progress_percentage) if prog else 0.0,
                completed_lessons_count=prog.completed_lessons_count if prog else 0,
                total_lessons_count=prog.total_lessons_count if prog else 0,
                last_activity_at=prog.last_activity_at if prog else None,
            )
            for enr, crs, prog in enr_res
        ]

        # 2. Quiz Attempts with Quiz
        stmt_quiz = (
            select(QuizAttempt, Quiz)
            .join(Quiz, Quiz.id == QuizAttempt.quiz_id)
            .where(QuizAttempt.student_id == uid)
            .order_by(QuizAttempt.started_at.desc())
        )
        if isinstance(session, AsyncSession):
            quiz_res = (await session.execute(stmt_quiz)).all()
        else:
            quiz_res = session.execute(stmt_quiz).all()

        quiz_attempts = [
            StudentQuizAttemptSummary(
                id=attempt.id,
                quiz_id=quiz.id,
                quiz_title=quiz.title,
                attempt_no=attempt.attempt_no,
                status=attempt.status,
                score=float(attempt.score) if attempt.score is not None else None,
                is_passed=attempt.is_passed,
                started_at=attempt.started_at,
                completed_at=attempt.completed_at,
            )
            for attempt, quiz in quiz_res
        ]

        # 3. Assignment Submissions with Assignment
        stmt_assign = (
            select(AssignmentSubmission, Assignment)
            .join(Assignment, Assignment.id == AssignmentSubmission.assignment_id)
            .where(AssignmentSubmission.student_id == uid)
            .order_by(AssignmentSubmission.submitted_at.desc())
        )
        if isinstance(session, AsyncSession):
            assign_res = (await session.execute(stmt_assign)).all()
        else:
            assign_res = session.execute(stmt_assign).all()

        assignment_submissions = [
            StudentAssignmentSubmissionSummary(
                id=sub.id,
                assignment_id=assign.id,
                assignment_title=assign.title,
                attempt_no=sub.attempt_no,
                status=sub.status,
                final_score=float(sub.final_score) if sub.final_score is not None else None,
                max_score=float(assign.max_score) if assign.max_score is not None else 100.0,
                pass_score=float(assign.pass_score) if assign.pass_score is not None else 50.0,
                file_url=sub.file_url,
                submitted_at=sub.submitted_at,
                graded_at=sub.graded_at,
                feedback=sub.feedback,
            )
            for sub, assign in assign_res
        ]

        # 4. Certificates with Course
        stmt_cert = (
            select(Certificate, Course)
            .join(Course, Course.id == Certificate.course_id)
            .where(Certificate.student_id == uid)
            .order_by(Certificate.issued_at.desc())
        )
        if isinstance(session, AsyncSession):
            cert_res = (await session.execute(stmt_cert)).all()
        else:
            cert_res = session.execute(stmt_cert).all()

        certificates = [
            StudentCertificateSummary(
                id=cert.id,
                certificate_no=cert.certificate_no,
                course_id=crs.id,
                course_title=crs.title,
                issued_at=cert.issued_at,
                verification_hash=cert.verification_hash,
                pdf_url=cert.pdf_url,
                is_revoked=cert.is_revoked,
                revoked_at=cert.revoked_at,
                revoked_reason=cert.revoked_reason,
            )
            for cert, crs in cert_res
        ]

        # 5. Audit trail records for this user (as actor or target)
        stmt_audit = (
            select(AuditLog)
            .where(
                sa.or_(
                    AuditLog.resource_id == str(uid),
                    AuditLog.actor_id == uid,
                )
            )
            .order_by(AuditLog.created_at.desc())
            .limit(50)
        )
        if isinstance(session, AsyncSession):
            audit_res = (await session.execute(stmt_audit)).scalars().all()
        else:
            audit_res = session.execute(stmt_audit).scalars().all()

        audit_logs = [
            {
                "id": str(log.id),
                "action": log.action,
                "actor_type": log.actor_type,
                "resource_type": log.resource_type,
                "resource_id": log.resource_id,
                "before_state": log.before_state,
                "after_state": log.after_state,
                "ip_address": log.ip_address,
                "created_at": log.created_at.isoformat(),
            }
            for log in audit_res
        ]

        return StudentLearningSummaryResponse(
            user=profile,
            enrollments=enrollments,
            quiz_attempts=quiz_attempts,
            assignment_submissions=assignment_submissions,
            certificates=certificates,
            audit_logs=audit_logs,
        )

    async def update_profile(
        self,
        session: Union[AsyncSession, Session],
        user_id: Union[uuid.UUID, str],
        *,
        full_name: Optional[str] = None,
        avatar_url: Optional[str] = None,
        actor_id: Optional[Union[uuid.UUID, str]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> UserProfileResponse:
        """Update full_name or avatar_url on a user account and record audit event."""
        existing = await self.user_repo.get_by_id(session, user_id)
        if existing is None:
            raise NotFoundException(message="User not found.", code="USER_NOT_FOUND")

        before_state = {
            "full_name": existing.full_name,
            "avatar_url": existing.avatar_url,
        }

        updated = await self.user_repo.update_profile(
            session,
            user_id,
            full_name=full_name,
            avatar_url=avatar_url,
        )

        after_state = {
            "full_name": updated.full_name,
            "avatar_url": updated.avatar_url,
        }

        await self.audit_service.record_event(
            session,
            action="USER_PROFILE_UPDATED",
            resource_type="user",
            resource_id=str(updated.id),
            actor_id=actor_id or user_id,
            actor_type="USER",
            before_state=before_state,
            after_state=after_state,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return await self.get_user_profile(session, updated.id)

    async def invite_staff(
        self,
        session: Union[AsyncSession, Session],
        *,
        email: str,
        full_name: str,
        role: str,
        actor_id: Union[uuid.UUID, str],
        actor_type: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> dict[str, Any]:
        """Invite a new staff member or administrator with a 48h cryptographic onboarding token.

        Enforces:
        - Role must be 'STAFF' or 'ADMIN' (cannot invite as SUPER_ADMIN).
        - Generates 32-byte secret token and stages outbox email.
        - If account already exists, adds role directly.
        - Resolves accurate actor_type (SUPER_ADMIN vs ADMIN) for audit log.
        - Never leaks raw token in return dict (delivered exclusively via outbox).
        """
        if role not in (ROLE_STAFF, ROLE_ADMIN):
            raise ValidationException(
                message=f"Can only invite roles '{ROLE_STAFF}' or '{ROLE_ADMIN}'",
                code="INVALID_INVITATION_ROLE",
            )

        # Determine actual authenticated actor type
        resolved_actor_type = actor_type
        if not resolved_actor_type:
            actor = await self.user_repo.get_by_id(session, actor_id)
            if actor and actor.has_role(ROLE_SUPER_ADMIN):
                resolved_actor_type = "SUPER_ADMIN"
            elif actor and actor.has_role(ROLE_ADMIN):
                resolved_actor_type = "ADMIN"
            elif actor and actor.has_role(ROLE_STAFF):
                resolved_actor_type = "STAFF"
            else:
                resolved_actor_type = "ADMIN"

        normalized_email = email.strip().lower()
        existing = await self.user_repo.get_by_email(session, normalized_email)

        if existing is not None:
            if existing.has_role(role):
                return {
                    "user_id": str(existing.id),
                    "email": existing.email,
                    "role": role,
                    "invited": False,
                    "message": f"User already possesses role {role}.",
                }
            await self.user_repo.assign_role(session, existing.id, role, assigned_by=actor_id)
            await self.audit_service.record_event(
                session,
                action="STAFF_ROLE_ASSIGNED",
                resource_type="user",
                resource_id=str(existing.id),
                actor_id=actor_id,
                actor_type=resolved_actor_type,
                after_state={"assigned_role": role},
                ip_address=ip_address,
                user_agent=user_agent,
            )
            return {
                "user_id": str(existing.id),
                "email": existing.email,
                "role": role,
                "invited": True,
                "message": f"Role {role} granted to existing account.",
            }

        # User does not exist: create user without password (password_hash=None)
        user = await self.user_repo.create_user(
            session,
            email=normalized_email,
            full_name=full_name,
            password_hash=None,
            is_verified=True,
            role_id=role,
            assigned_by=actor_id,
        )

        # Generate 48h cryptographic onboarding token
        raw_token = generate_secure_token(32)
        token_hash = hash_token(raw_token)
        expires_at = utc_now() + timedelta(hours=48)

        await self.token_repo.create_token(
            session,
            user_id=user.id,
            token_hash=token_hash,
            token_type=TOKEN_TYPE_STAFF_ONBOARDING,
            expires_at=expires_at,
        )

        # Stage transactional outbox invitation email
        frontend_url = self.settings.FRONTEND_URL.rstrip("/")
        invitation_url = f"{frontend_url}/onboarding/claim?token={raw_token}"
        await self.outbox_service.publish_event(
            session,
            event_type="STAFF_INVITATION",
            channel=OUTBOX_CHANNEL_EMAIL,
            recipient=user.email,
            subject="Invitation to join Single-Instructor LMS team",
            payload={
                "user_id": str(user.id),
                "email": user.email,
                "full_name": user.full_name,
                "role": role,
                "token": raw_token,
                "invitation_token": raw_token,
                "invitation_url": invitation_url,
                "expires_at": expires_at.isoformat(),
            },
        )

        # Record immutable audit log with accurate actor_type
        await self.audit_service.record_event(
            session,
            action="STAFF_INVITED",
            resource_type="user",
            resource_id=str(user.id),
            actor_id=actor_id,
            actor_type=resolved_actor_type,
            after_state={"email": user.email, "role": role},
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return {
            "user_id": str(user.id),
            "email": user.email,
            "role": role,
            "invited": True,
            "expires_at": expires_at.isoformat(),
            "message": "Staff invitation staged successfully.",
        }

    async def claim_staff_onboarding(
        self,
        session: Union[AsyncSession, Session],
        *,
        token: str,
        password: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Tuple[User, str, Any]:
        """Claim a staff onboarding invitation, validate password, and issue active session."""
        validate_password_complexity(password)

        token_hash = hash_token(token)
        auth_token = await self.token_repo.get_by_hash(
            session,
            token_hash,
            token_type=TOKEN_TYPE_STAFF_ONBOARDING,
        )

        if auth_token is None or auth_token.is_used or auth_token.expires_at <= utc_now():
            raise BadRequestException(
                message="Invalid, expired, or already used onboarding token.",
                code="INVALID_OR_EXPIRED_TOKEN",
            )

        user = await self.user_repo.get_by_id(session, auth_token.user_id)
        if user is None:
            raise NotFoundException(message="User not found.", code="USER_NOT_FOUND")

        # Set Argon2id password hash
        pwd_hash = hash_password(password)
        await self.user_repo.update_password_hash(session, user.id, pwd_hash)

        # Consume token
        await self.token_repo.consume_token(session, auth_token.id)

        # Issue active session (Single-Active-Session invariant)
        raw_session_token = generate_secure_token(32)
        session_token_hash = hash_token(raw_session_token)
        expires_at = utc_now() + timedelta(seconds=self.settings.SESSION_MAX_AGE_SECONDS)

        new_session, displaced = await self.session_repo.atomic_displace_session(
            session,
            user_id=user.id,
            new_session_token_hash=session_token_hash,
            expires_at=expires_at,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        # Record audit log
        await self.audit_service.record_event(
            session,
            action="STAFF_ONBOARDED",
            resource_type="user",
            resource_id=str(user.id),
            actor_id=user.id,
            actor_type="STAFF",
            after_state={"is_active": True, "is_verified": True},
            ip_address=ip_address,
            user_agent=user_agent,
        )

        refreshed_user = await self.user_repo.get_by_id(session, user.id)
        return refreshed_user, raw_session_token, new_session

    async def update_user_status(
        self,
        session: Union[AsyncSession, Session],
        *,
        user_id: Union[uuid.UUID, str],
        is_active: bool,
        reason: Optional[str] = None,
        actor_id: Optional[Union[uuid.UUID, str]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> UserProfileResponse:
        """Activate or suspend user account.

        Enforces Sole Super Admin Protection Invariant:
        Cannot suspend the final active Super Admin account.
        """
        user = await self.user_repo.get_by_id(session, user_id)
        if user is None:
            raise NotFoundException(message="User not found.", code="USER_NOT_FOUND")

        # Guard against suspending the last active Super Admin (BUG-006: DB-level serialization lock)
        if not is_active and user.has_role(ROLE_SUPER_ADMIN):
            stmt_lock = select(Role).where(Role.id == ROLE_SUPER_ADMIN).with_for_update()
            if isinstance(session, AsyncSession):
                await session.execute(stmt_lock)
            else:
                session.execute(stmt_lock)

            active_count = await self.user_repo.count_active_super_admins(session)
            if active_count <= 1:
                raise ConflictException(
                    message="Cannot suspend the sole active Super Admin account.",
                    code="CANNOT_SUSPEND_LAST_SUPER_ADMIN",
                )

        before_state = {"is_active": user.is_active}
        await self.user_repo.update_status(session, user.id, is_active)

        # If suspended, atomically revoke ALL active sessions with metadata
        if not is_active:
            suspension_reason = "ACCOUNT_SUSPENDED: " + (reason or "Administrative suspension")
            await self.session_repo.revoke_all_user_sessions(
                session,
                user.id,
                reason=suspension_reason,
                revoked_by=actor_id,
            )

        after_state = {"is_active": is_active, "reason": reason}

        await self.audit_service.record_event(
            session,
            action="USER_STATUS_UPDATED",
            resource_type="user",
            resource_id=str(user.id),
            actor_id=actor_id,
            actor_type="SUPER_ADMIN",
            before_state=before_state,
            after_state=after_state,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return await self.get_user_profile(session, user.id)

    async def manage_user_role(
        self,
        session: Union[AsyncSession, Session],
        *,
        user_id: Union[uuid.UUID, str],
        role_id: str,
        action: str,
        actor_id: Optional[Union[uuid.UUID, str]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> UserProfileResponse:
        """Assign or revoke a system role for a user.

        Enforces Sole Super Admin Protection Invariant:
        Cannot demote or revoke the SUPER_ADMIN role from the sole active Super Admin.
        """
        user = await self.user_repo.get_by_id(session, user_id)
        if user is None:
            raise NotFoundException(message="User not found.", code="USER_NOT_FOUND")

        clean_action = action.strip().upper()
        clean_role = role_id.strip().upper()

        if clean_role not in SYSTEM_ROLES:
            raise ValidationException(
                message=f"Unknown system role: {clean_role}",
                code="INVALID_ROLE",
            )

        if clean_action == "REVOKE":
            if clean_role == ROLE_SUPER_ADMIN:
                stmt_lock = select(Role).where(Role.id == ROLE_SUPER_ADMIN).with_for_update()
                if isinstance(session, AsyncSession):
                    await session.execute(stmt_lock)
                else:
                    session.execute(stmt_lock)

                active_count = await self.user_repo.count_active_super_admins(session)
                if active_count <= 1:
                    raise ConflictException(
                        message="Cannot demote or revoke role from the sole active Super Admin.",
                        code="CANNOT_DEMOTE_LAST_SUPER_ADMIN",
                    )
            await self.user_repo.remove_role(session, user.id, clean_role)
            # Revoke all active sessions on administrative role demotion to eliminate privilege residue
            if clean_role in (ROLE_ADMIN, ROLE_STAFF, ROLE_SUPER_ADMIN):
                await self.session_repo.revoke_all_user_sessions(
                    session,
                    user.id,
                    reason=f"PRIVILEGE_DEMOTION: {clean_role}_REVOKED",
                    revoked_by=actor_id,
                )
            audit_action = "ROLE_REVOKED"
        elif clean_action == "ASSIGN":
            await self.user_repo.assign_role(session, user.id, clean_role, assigned_by=actor_id)
            audit_action = "ROLE_ASSIGNED"
        else:
            raise ValidationException(
                message="Action must be either 'ASSIGN' or 'REVOKE'",
                code="INVALID_ACTION",
            )

        await self.audit_service.record_event(
            session,
            action=audit_action,
            resource_type="user",
            resource_id=str(user.id),
            actor_id=actor_id,
            actor_type="SUPER_ADMIN",
            after_state={"role_id": clean_role, "action": clean_action},
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return await self.get_user_profile(session, user.id)
