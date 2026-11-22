"""Super Admin Control Dashboard & Analytics domain service (SA-01).

Architecture Specifications:
- docs/MASTER_LMS_PRODUCT_REQUIREMENTS_AND_DEVELOPMENT_ROADMAP.md (Section 6, SA-01)
- docs/backend/06-API-ARCHITECTURE.md
- docs/backend/17-AUDIT-LOG-ARCHITECTURE.md

Strict Invariants:
1. Zero Fabricated Data: Every metric is computed strictly from verified database records.
2. Financial Precision: All financial totals computed in integer minor currency units (paise).
3. Super Admin Privacy: Sensitive credential hashes or raw tokens are never exposed.
4. Database Efficiency: Index-aligned queries avoiding N+1 loops and table scans.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import logging
from typing import Any, Dict, List, Optional

import sqlalchemy as sa
from sqlalchemy import case, desc, func
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.base import utc_now
from app.models.course import (
    COURSE_STATUS_ARCHIVED,
    COURSE_STATUS_DRAFT,
    COURSE_STATUS_PUBLISHED,
    Course,
)
from app.models.enrollment import ENROLLMENT_STATUS_ACTIVE, Enrollment
from app.models.payment import (
    ORDER_STATUS_PAID,
    REFUND_STATUS_PROCESSED,
    TRANSACTION_STATUS_SUCCESS,
    Order,
    PaymentTransaction,
    Refund,
)
from app.models.user import (
    ROLE_ADMIN,
    ROLE_STAFF,
    ROLE_STUDENT,
    ROLE_SUPER_ADMIN,
    User,
    UserRole,
)
from app.schemas.audit import AuditLogResponse
from app.schemas.control import (
    ControlOverviewResponse,
    CourseMetrics,
    DailyTrendPoint,
    EnrollmentMetrics,
    FinancialMetrics,
    SecurityMetrics,
    UserMetrics,
)

logger = logging.getLogger(__name__)

# Security-sensitive audit actions classified as security events
SECURITY_ACTIONS = frozenset({
    "AUTH_SESSION_REVOKED",
    "LOGIN_FAILED",
    "UNAUTHORIZED_ACCESS",
    "ACCOUNT_SUSPENDED",
    "SECURITY_ALERT",
    "TOKEN_VERIFICATION_FAILED",
    "INVALID_CREDENTIALS",
})


class ControlService:
    """Aggregates and formats authoritative platform overview metrics for Super Admin."""

    @staticmethod
    def _paise_to_inr(amount_paise: Any) -> float:
        """Safely converts minor currency units (paise) to INR float with two-decimal precision.

        Uses Decimal arithmetic to prevent Decimal/float division TypeError and precision loss.
        """
        if amount_paise is None:
            return 0.0
        dec_amount = Decimal(str(amount_paise))
        return float(round(dec_amount / Decimal("100"), 2))

    def get_overview(self, session: Session) -> ControlOverviewResponse:
        """Computes platform metrics, financial aggregates, trends, and recent activity.

        Args:
            session: Active SQLAlchemy database session.

        Returns:
            ControlOverviewResponse containing typed verified metrics.
        """
        now = utc_now()

        # ---------------------------------------------------------------------
        # 1. User Metrics (Roles & Account Status)
        # ---------------------------------------------------------------------
        role_counts_query = (
            session.query(UserRole.role_id, func.count(UserRole.user_id))
            .group_by(UserRole.role_id)
            .all()
        )
        role_counts_map: Dict[str, int] = {role: count for role, count in role_counts_query}

        total_students = role_counts_map.get(ROLE_STUDENT, 0)
        total_admins = role_counts_map.get(ROLE_ADMIN, 0)
        total_staff = role_counts_map.get(ROLE_STAFF, 0)
        total_super_admins = role_counts_map.get(ROLE_SUPER_ADMIN, 0)

        active_users_count = (
            session.query(func.count(User.id))
            .filter(User.is_active.is_(True))
            .scalar()
            or 0
        )

        user_metrics = UserMetrics(
            total_students=total_students,
            total_admins=total_admins,
            total_staff=total_staff,
            total_super_admins=total_super_admins,
            active_users=active_users_count,
        )

        # ---------------------------------------------------------------------
        # 2. Course Metrics (Lifecycle Status)
        # ---------------------------------------------------------------------
        course_counts_query = (
            session.query(Course.status, func.count(Course.id))
            .group_by(Course.status)
            .all()
        )
        course_counts_map: Dict[str, int] = {st: count for st, count in course_counts_query}

        published_courses = course_counts_map.get(COURSE_STATUS_PUBLISHED, 0)
        draft_courses = course_counts_map.get(COURSE_STATUS_DRAFT, 0)
        archived_courses = course_counts_map.get(COURSE_STATUS_ARCHIVED, 0)
        total_courses = sum(course_counts_map.values())

        course_metrics = CourseMetrics(
            total_courses=total_courses,
            published_courses=published_courses,
            draft_courses=draft_courses,
            archived_courses=archived_courses,
        )

        # ---------------------------------------------------------------------
        # 3. Enrollment Metrics
        # ---------------------------------------------------------------------
        enrollment_stats = (
            session.query(
                func.count(Enrollment.id).label("total"),
                func.count(
                    case((Enrollment.status == ENROLLMENT_STATUS_ACTIVE, 1), else_=None)
                ).label("active"),
            ).one_or_none()
        )

        total_enrollments = enrollment_stats.total if enrollment_stats else 0
        active_enrollments = enrollment_stats.active if enrollment_stats else 0

        enrollment_metrics = EnrollmentMetrics(
            total_enrollments=total_enrollments,
            active_enrollments=active_enrollments,
        )

        # ---------------------------------------------------------------------
        # 4. Financial Metrics (Verified Paid Orders & Processed Refunds)
        # ---------------------------------------------------------------------
        # Sum only PAID orders; client unverified orders are excluded
        paid_orders_stats = (
            session.query(
                func.count(Order.id).label("paid_count"),
                func.coalesce(func.sum(Order.amount_inr), 0).label("gross_revenue"),
            )
            .filter(Order.status == ORDER_STATUS_PAID)
            .one_or_none()
        )

        successful_transactions = (
            int(paid_orders_stats.paid_count)
            if (paid_orders_stats and paid_orders_stats.paid_count is not None)
            else 0
        )
        gross_rev_raw = paid_orders_stats.gross_revenue if paid_orders_stats else 0
        verified_revenue_paise = int(gross_rev_raw) if gross_rev_raw is not None else 0

        # Sum processed refunds
        refund_stats = (
            session.query(
                func.coalesce(func.sum(Refund.amount_inr), 0).label("refund_sum")
            )
            .filter(Refund.status == REFUND_STATUS_PROCESSED)
            .one_or_none()
        )
        refund_sum_raw = refund_stats.refund_sum if refund_stats else 0
        refunded_amount_paise = int(refund_sum_raw) if refund_sum_raw is not None else 0

        net_revenue_paise = max(0, verified_revenue_paise - refunded_amount_paise)

        financial_metrics = FinancialMetrics(
            verified_revenue_paise=verified_revenue_paise,
            verified_revenue_inr=self._paise_to_inr(verified_revenue_paise),
            successful_transactions=successful_transactions,
            refunded_amount_paise=refunded_amount_paise,
            refunded_amount_inr=self._paise_to_inr(refunded_amount_paise),
            net_revenue_paise=net_revenue_paise,
            net_revenue_inr=self._paise_to_inr(net_revenue_paise),
            currency="INR",
        )

        # ---------------------------------------------------------------------
        # 5. Security & Audit Metrics
        # ---------------------------------------------------------------------
        total_audit_events = session.query(func.count(AuditLog.id)).scalar() or 0

        security_events_count = (
            session.query(func.count(AuditLog.id))
            .filter(AuditLog.action.in_(SECURITY_ACTIONS))
            .scalar()
            or 0
        )

        active_staff_count = (
            session.query(func.count(User.id))
            .join(UserRole, UserRole.user_id == User.id)
            .filter(UserRole.role_id == ROLE_STAFF, User.is_active.is_(True))
            .scalar()
            or 0
        )

        security_metrics = SecurityMetrics(
            total_audit_events=total_audit_events,
            security_events_count=security_events_count,
            active_staff_count=active_staff_count,
            security_model="Tier 1 Hardened (Single-Active-Session & Signed Tokens)",
        )

        # ---------------------------------------------------------------------
        # 6. Analytics Time-Series (14-Day Rolling Windows)
        # ---------------------------------------------------------------------
        cutoff_date = now - timedelta(days=13)
        # Generate complete date bucket map initialized to 0
        rolling_days = [
            (cutoff_date + timedelta(days=i)).strftime("%Y-%m-%d")
            for i in range(14)
        ]
        reg_map = {d: 0 for d in rolling_days}
        enr_map = {d: 0 for d in rolling_days}

        # Query recent registrations
        recent_users = (
            session.query(User.created_at)
            .filter(User.created_at >= cutoff_date)
            .all()
        )
        for u in recent_users:
            if u.created_at:
                day_str = u.created_at.strftime("%Y-%m-%d")
                if day_str in reg_map:
                    reg_map[day_str] += 1

        # Query recent enrollments
        recent_enrollments = (
            session.query(Enrollment.granted_at)
            .filter(Enrollment.granted_at >= cutoff_date)
            .all()
        )
        for e in recent_enrollments:
            if e.granted_at:
                day_str = e.granted_at.strftime("%Y-%m-%d")
                if day_str in enr_map:
                    enr_map[day_str] += 1

        registration_trends = [
            DailyTrendPoint(date=d, count=reg_map[d]) for d in rolling_days
        ]
        enrollment_trends = [
            DailyTrendPoint(date=d, count=enr_map[d]) for d in rolling_days
        ]

        # ---------------------------------------------------------------------
        # 7. Recent Platform Activity (Latest 8 Audit Events)
        # ---------------------------------------------------------------------
        recent_audit_rows = (
            session.query(AuditLog)
            .order_by(desc(AuditLog.created_at))
            .limit(8)
            .all()
        )
        recent_activity = [
            AuditLogResponse.model_validate(log) for log in recent_audit_rows
        ]

        return ControlOverviewResponse(
            user_metrics=user_metrics,
            course_metrics=course_metrics,
            enrollment_metrics=enrollment_metrics,
            financial_metrics=financial_metrics,
            security_metrics=security_metrics,
            registration_trends=registration_trends,
            enrollment_trends=enrollment_trends,
            recent_activity=recent_activity,
            generated_at=now,
        )
