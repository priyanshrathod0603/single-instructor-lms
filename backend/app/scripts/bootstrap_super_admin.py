"""One-Time Super Admin Bootstrap CLI Tool.

Architecture Specifications:
- LMS Blueprint v2.0, Pages 2-3, 8
- Single-Instructor Governance & RBAC

Operating Model:
This script allows the platform owner to promote their verified initial account
to the canonical SUPER_ADMIN role through a secure, controlled, one-time bootstrap.

Security Invariants:
1. Strict One-Time Execution: Fails immediately if ANY active or existing Super Admin exists.
2. Verified Account Required: The target account must exist and have completed mandatory email verification.
3. No Secret/Password Handling: The user registers via the normal interface with Argon2id hashing;
   this script never touches, handles, or overwrites passwords.
4. Transactional Atomicity: Role assignment and immutable audit log persist in a single ACID transaction.
5. Anti-Tamper: Fails closed on any inconsistency or ambiguity.
"""

import argparse
import asyncio
import os
import sys
from typing import Optional

# Ensure backend root is on sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import create_db_engine, create_session_factory
from app.models.user import (
    ROLE_SUPER_ADMIN,
    User,
    UserRole,
)
from app.repositories.user_repo import UserRepository
from app.services.audit_service import AuditService


async def bootstrap_super_admin(
    session: Session,
    email: str,
) -> tuple[bool, str]:
    """Promote the specified verified account to initial SUPER_ADMIN role.

    Args:
        session: Active SQLAlchemy Session.
        email: Registered and verified email address of the owner.

    Returns:
        tuple[bool, str]: (Success status, descriptive outcome message).
    """
    normalized_email = email.strip().lower()
    if not normalized_email or "@" not in normalized_email:
        return False, f"Invalid email address '{email}'."

    user_repo = UserRepository()
    audit_service = AuditService()

    # 1. Check if ANY user already has SUPER_ADMIN role
    super_admin_count_query = select(func.count(UserRole.user_id)).where(
        UserRole.role_id == ROLE_SUPER_ADMIN
    )
    existing_super_admins = session.execute(super_admin_count_query).scalar() or 0

    if existing_super_admins > 0:
        return False, (
            f"A Super Admin already exists in the database ({existing_super_admins} found). "
            "To protect platform governance, the bootstrap command can only be executed once when "
            "zero Super Admins exist."
        )

    # 2. Check target user exists
    user = session.execute(
        select(User).where(func.lower(User.email) == normalized_email)
    ).scalar_one_or_none()

    if user is None:
        return False, (
            f"Account '{normalized_email}' does not exist. "
            "Please register the account and verify email first."
        )

    # 3. Check account active status
    if not user.is_active:
        return False, f"Account '{normalized_email}' is suspended or inactive."

    # 4. Enforce mandatory email verification
    if not user.is_verified:
        return False, (
            f"Account '{normalized_email}' is not email-verified. "
            "The initial Super Admin account must be email-verified before privileged promotion."
        )

    # 5. Check if already has SUPER_ADMIN
    has_role = session.execute(
        select(UserRole).where(
            UserRole.user_id == user.id,
            UserRole.role_id == ROLE_SUPER_ADMIN,
        )
    ).scalar_one_or_none()

    if has_role is not None:
        return True, f"Account '{normalized_email}' already has SUPER_ADMIN role."

    # 6. Execute atomic promotion
    try:
        # Assign SUPER_ADMIN role
        await user_repo.assign_role(
            session,
            user_id=user.id,
            role_id=ROLE_SUPER_ADMIN,
            assigned_by=user.id,
        )

        # Record immutable audit log
        await audit_service.record_event(
            session,
            action="SUPER_ADMIN_BOOTSTRAPPED",
            resource_type="user",
            resource_id=user.id,
            actor_id=user.id,
            actor_type="SUPER_ADMIN",
            metadata={
                "bootstrap_type": "INITIAL_ONE_TIME_BOOTSTRAP",
                "promoted_email": user.email,
            },
        )

        session.commit()
        return True, f"Account '{user.email}' successfully bootstrapped as SUPER_ADMIN."
    except Exception as exc:
        session.rollback()
        return False, f"Database transaction error during bootstrap promotion: {exc}"


async def cli_bootstrap_super_admin(email: str) -> None:
    """CLI runner executing bootstrap against configured application database."""
    settings = get_settings()
    engine = create_db_engine(settings)
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        success, message = await bootstrap_super_admin(session, email)
        if success:
            print("==================================================================")
            print("  SUPER ADMIN INITIAL BOOTSTRAP SUCCESSFUL")
            print("==================================================================")
            print(f"  Target Account:    {email.strip().lower()}")
            print(f"  Role Assigned:     {ROLE_SUPER_ADMIN}")
            print("  Status:            Active & Verified")
            print("------------------------------------------------------------------")
            print("  Next Steps:")
            print("  1. Navigate to:    http://localhost:3000/login")
            print("  2. Sign in with:   Your registered email and password")
            print("  3. Access:         Super Admin Governance Dashboard (/admin)")
            print("==================================================================")
            sys.exit(0)
        else:
            print(f"[-] BOOTSTRAP REJECTED: {message}", file=sys.stderr)
            sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="One-time bootstrap utility to establish the initial SUPER_ADMIN account."
    )
    parser.add_argument(
        "--email",
        type=str,
        required=False,
        help="Email address of the verified owner account to promote to SUPER_ADMIN.",
    )

    args = parser.parse_args()
    target_email = args.email

    if not target_email:
        try:
            target_email = input("Enter the verified owner email address to promote: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nAborted.")
            sys.exit(1)

    if not target_email:
        print("[-] Email address is required.", file=sys.stderr)
        sys.exit(1)

    asyncio.run(cli_bootstrap_super_admin(target_email))


if __name__ == "__main__":
    main()
