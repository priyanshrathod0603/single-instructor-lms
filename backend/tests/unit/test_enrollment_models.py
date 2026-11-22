"""Unit tests for Student Course Enrollment database model.

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Module 6, Table 28)
- docs/backend/12-ENROLLMENT-PAYMENT-ARCHITECTURE.md (Sections 1-5)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK601)
- docs/backend/23-ARCHITECTURAL-DECISIONS.md (ADR-004)
"""

from datetime import datetime, timedelta, timezone
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.core.security import hash_password
from app.models.base import Base, utc_now
from app.models.course import COURSE_STATUS_PUBLISHED, Course
from app.models.enrollment import (
    ENROLLMENT_STATUS_ACTIVE,
    ENROLLMENT_STATUS_EXPIRED,
    ENROLLMENT_STATUS_REVOKED,
    ENROLLMENT_STATUSES,
    Enrollment,
)
from app.models.payment import ORDER_STATUS_PAID, Order
from app.models.user import User


@pytest.fixture
def db_session():
    """In-memory SQLite session with full schema initialized."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = session_factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture
def test_student(db_session: Session) -> User:
    """Fixture creating an active student user."""
    user = User(
        email="student@lms.local",
        full_name="Enrolled Student",
        password_hash=hash_password("StudentPassword123!"),
        is_verified=True,
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def test_course(db_session: Session) -> Course:
    """Fixture creating a published course."""
    course = Course(
        title="Modern Cloud Architecture",
        slug="modern-cloud-architecture",
        headline="Enterprise systems design",
        price_inr=999900,
        status=COURSE_STATUS_PUBLISHED,
    )
    db_session.add(course)
    db_session.flush()
    return course


def test_enrollment_model_creation(db_session: Session, test_student: User, test_course: Course):
    """Enrollment row initializes with default ACTIVE status, UUID PK, and timestamps."""
    enrollment = Enrollment(
        student_id=test_student.id,
        course_id=test_course.id,
    )
    db_session.add(enrollment)
    db_session.commit()

    assert isinstance(enrollment.id, uuid.UUID)
    assert enrollment.student_id == test_student.id
    assert enrollment.course_id == test_course.id
    assert enrollment.status == ENROLLMENT_STATUS_ACTIVE
    assert enrollment.order_id is None
    assert enrollment.expires_at is None
    assert enrollment.revoked_at is None
    assert enrollment.revoked_reason is None
    assert enrollment.granted_at is not None
    assert "Enrollment" in repr(enrollment)
    assert enrollment.is_access_valid is True


def test_enrollment_unique_constraint(db_session: Session, test_student: User, test_course: Course):
    """Enforces UNIQUE(student_id, course_id) preventing duplicate enrollment records."""
    e1 = Enrollment(student_id=test_student.id, course_id=test_course.id)
    db_session.add(e1)
    db_session.commit()

    e2 = Enrollment(student_id=test_student.id, course_id=test_course.id)
    db_session.add(e2)
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_enrollment_is_access_valid_logic(test_student: User, test_course: Course):
    """Verifies access validity evaluation under various lifecycle states."""
    now = datetime.now(timezone.utc)

    # 1. Active with lifetime access (no expires_at)
    e_lifetime = Enrollment(
        student_id=test_student.id,
        course_id=test_course.id,
        status=ENROLLMENT_STATUS_ACTIVE,
        expires_at=None,
    )
    assert e_lifetime.is_access_valid is True

    # 2. Active with future expiration
    e_future = Enrollment(
        student_id=test_student.id,
        course_id=test_course.id,
        status=ENROLLMENT_STATUS_ACTIVE,
        expires_at=now + timedelta(days=30),
    )
    assert e_future.is_access_valid is True

    # 3. Active with past expiration
    e_expired_time = Enrollment(
        student_id=test_student.id,
        course_id=test_course.id,
        status=ENROLLMENT_STATUS_ACTIVE,
        expires_at=now - timedelta(seconds=1),
    )
    assert e_expired_time.is_access_valid is False

    # 4. Status is REVOKED
    e_revoked = Enrollment(
        student_id=test_student.id,
        course_id=test_course.id,
        status=ENROLLMENT_STATUS_REVOKED,
        revoked_at=now,
        revoked_reason="PAYMENT_REFUNDED",
    )
    assert e_revoked.is_access_valid is False

    # 5. Status is EXPIRED
    e_expired = Enrollment(
        student_id=test_student.id,
        course_id=test_course.id,
        status=ENROLLMENT_STATUS_EXPIRED,
    )
    assert e_expired.is_access_valid is False


def test_enrollment_relationships(db_session: Session, test_student: User, test_course: Course):
    """Enrollment relationships link accurately to User, Course, and optional Order."""
    order = Order(
        order_no="ORD-202611-ABC12345",
        student_id=test_student.id,
        course_id=test_course.id,
        amount_inr=999900,
        currency="INR",
        status=ORDER_STATUS_PAID,
    )
    db_session.add(order)
    db_session.flush()

    enrollment = Enrollment(
        student_id=test_student.id,
        course_id=test_course.id,
        order_id=order.id,
    )
    db_session.add(enrollment)
    db_session.commit()

    db_session.refresh(enrollment)
    assert enrollment.student.id == test_student.id
    assert enrollment.student.email == "student@lms.local"
    assert enrollment.course.id == test_course.id
    assert enrollment.course.title == "Modern Cloud Architecture"
    assert enrollment.order is not None
    assert enrollment.order.order_no == "ORD-202611-ABC12345"
