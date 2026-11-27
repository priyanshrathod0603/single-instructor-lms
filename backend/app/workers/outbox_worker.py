"""Transactional Outbox background polling worker.

Architecture Specifications:
- docs/backend/04-DATABASE-ARCHITECTURE.md (Table 34)
- docs/backend/16-NOTIFICATION-ARCHITECTURE.md (Section 2, 3)
- docs/backend/22-BACKEND-DEVELOPMENT-ROADMAP.md (TASK008)
- docs/backend/23-ARCHITECTURAL-DECISIONS.md (ADR-012)

Strict Invariants:
1. Concurrency isolation: Row-level locking (FOR UPDATE SKIP LOCKED) prevents dual processing.
2. Resilience: Delivery failures are caught without crashing the worker process.
3. Exponential backoff: Backoff schedule (30 * 2^retry_count seconds) prevents provider throttling.
4. Dead-letter queue: After max_retries attempts, event transitions to FAILED.
5. Crash recovery: Abandoned events in PROCESSING state are reclaimed via stale threshold.
6. Clean resource disposal: Database sessions are guaranteed to be closed in all execution paths.
"""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime
import logging
from pathlib import Path
import sys
from typing import Any, Optional, Union

# Ensure backend root directory is in sys.path when executed directly as a script
_backend_dir = str(Path(__file__).resolve().parent.parent.parent)
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

import app.core.database as db_module
from app.core.config import get_settings
from app.core.logging import redact_sensitive_text
from app.models.notification import (
    OUTBOX_CHANNEL_EMAIL,
    OUTBOX_CHANNEL_IN_APP,
    OUTBOX_CHANNEL_WEBHOOK,
    NotificationOutbox,
)
from app.repositories.notification_repo import NotificationOutboxRepository

logger = logging.getLogger(__name__)

# Type alias for outbox dispatch handlers
OutboxDispatcher = Callable[[NotificationOutbox], Awaitable[None]]


def _format_email_text(event: NotificationOutbox) -> str:
    """Format structured, human-readable email body instead of raw JSON dump (P1 Outbox)."""
    payload = event.payload or {}
    if isinstance(payload, dict) and payload.get("is_encrypted") and "_encrypted" in payload:
        try:
            from app.core.security import decrypt_payload
            payload = decrypt_payload(payload["_encrypted"])
        except Exception as e:
            logger.error("Failed to decrypt outbox payload: %s", e)

    if "body" in payload and isinstance(payload["body"], str):
        return payload["body"]
    if "message" in payload and isinstance(payload["message"], str):
        return payload["message"]

    if event.event_type in ("PASSWORD_RESET", "AUTH_RESET_PASSWORD"):
        reset_link = payload.get("reset_url") or payload.get("link")
        if not reset_link:
            token = payload.get("reset_token") or payload.get("token") or ""
            settings = get_settings()
            frontend_url = settings.FRONTEND_URL.rstrip("/")
            reset_link = f"{frontend_url}/reset-password?token={token}"
        return (
            f"Hello,\n\n"
            f"A password reset was requested for your account.\n"
            f"Open the following link to choose a new password:\n{reset_link}\n\n"
            f"This link will expire shortly. If you did not make this request, please ignore this email."
        )
    elif event.event_type in ("EMAIL_VERIFICATION", "AUTH_VERIFY_EMAIL"):
        verify_link = payload.get("verification_url") or payload.get("link")
        if not verify_link:
            token = payload.get("verification_token") or payload.get("token") or ""
            settings = get_settings()
            frontend_url = settings.FRONTEND_URL.rstrip("/")
            verify_link = f"{frontend_url}/verify-email?token={token}"
        return (
            f"Welcome to the Single-Instructor LMS!\n\n"
            f"Please verify your email address by opening the link below:\n{verify_link}\n\n"
            f"Thank you for joining!"
        )
    elif event.event_type == "ENROLLMENT_RECEIPT":
        order_no = payload.get("order_no", "N/A")
        amount_inr = payload.get("amount_inr", 0)
        formatted_amount = f"₹{amount_inr / 100:.2f}" if isinstance(amount_inr, (int, float)) else str(amount_inr)
        return (
            f"Payment Received & Enrollment Confirmed!\n\n"
            f"Order Number: {order_no}\n"
            f"Amount Paid: {formatted_amount}\n"
            f"Payment ID: {payload.get('razorpay_payment_id', 'N/A')}\n\n"
            f"You have been successfully enrolled and your course access is active."
        )
    elif event.event_type == "STAFF_INVITATION":
        settings = get_settings()
        frontend_url = settings.FRONTEND_URL.rstrip("/")
        invite_link = (
            payload.get("invitation_url")
            or payload.get("link")
            or (f"{frontend_url}/onboarding/claim?token={payload.get('invitation_token') or payload.get('token') or ''}")
        )
        return (
            f"Hello {payload.get('full_name') or 'there'},\n\n"
            f"You have been invited as a staff member ({payload.get('role', 'Staff')}) on the Single-Instructor LMS platform.\n\n"
            f"Please complete your onboarding at:\n{invite_link}\n\n"
            f"This invitation link will expire in 48 hours."
        )

    lines = [f"Notification: {event.subject}"]
    for k, v in payload.items():
        if k not in ("token", "hash"):
            lines.append(f"{k.replace('_', ' ').title()}: {v}")
    return "\n".join(lines)


def _format_email_html(event: NotificationOutbox) -> Optional[str]:
    """Format responsive, accessible HTML email body matching platform brand styling."""
    payload = event.payload or {}
    if isinstance(payload, dict) and payload.get("is_encrypted") and "_encrypted" in payload:
        try:
            from app.core.security import decrypt_payload
            payload = decrypt_payload(payload["_encrypted"])
        except Exception as e:
            logger.error("Failed to decrypt outbox payload: %s", e)

    settings = get_settings()
    frontend_url = settings.FRONTEND_URL.rstrip("/")

    if event.event_type in ("EMAIL_VERIFICATION", "AUTH_VERIFY_EMAIL"):
        verify_link = payload.get("verification_url") or payload.get("link")
        if not verify_link:
            token = payload.get("verification_token") or payload.get("token") or ""
            verify_link = f"{frontend_url}/verify-email?token={token}"

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Verify Your Email Address</title>
</head>
<body style="margin: 0; padding: 0; background-color: #FFF8F5; font-family: -apple-system, BlinkMacSystemFont, 'Plus Jakarta Sans', 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1E293B;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color: #FFF8F5; padding: 40px 16px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" style="max-width: 560px; background-color: #FFFFFF; border-radius: 16px; border: 1px solid #FCE8E1; box-shadow: 0 4px 12px rgba(0, 107, 96, 0.05); overflow: hidden;" cellspacing="0" cellpadding="0">
          <tr>
            <td style="background-color: #006B60; padding: 28px 32px; text-align: center;">
              <h1 style="margin: 0; color: #FFFFFF; font-size: 24px; font-weight: 700; letter-spacing: -0.02em;">Single-Instructor LMS</h1>
            </td>
          </tr>
          <tr>
            <td style="padding: 36px 32px;">
              <h2 style="margin: 0 0 16px 0; color: #006B60; font-size: 20px; font-weight: 600;">Verify Your Email Address</h2>
              <p style="margin: 0 0 24px 0; font-size: 15px; line-height: 1.6; color: #475569;">
                Welcome to the platform! Please verify your email address to activate your account and start your courses.
              </p>
              <table role="presentation" cellspacing="0" cellpadding="0" style="margin: 0 0 28px 0;">
                <tr>
                  <td align="center" style="border-radius: 10px; background-color: #006B60;">
                    <a href="{verify_link}" target="_blank" rel="noopener noreferrer" style="display: inline-block; padding: 14px 28px; font-size: 15px; font-weight: 600; color: #FFFFFF; text-decoration: none; border-radius: 10px; background-color: #006B60;">
                      Verify Email Address
                    </a>
                  </td>
                </tr>
              </table>
              <p style="margin: 0 0 8px 0; font-size: 13px; line-height: 1.5; color: #64748B;">
                Or copy and paste this link into your browser:
              </p>
              <p style="margin: 0 0 24px 0; font-size: 13px; line-height: 1.5; color: #006B60; word-break: break-all;">
                <a href="{verify_link}" style="color: #006B60; text-decoration: underline;">{verify_link}</a>
              </p>
              <hr style="border: none; border-top: 1px solid #F1F5F9; margin: 24px 0;" />
              <p style="margin: 0; font-size: 12px; line-height: 1.5; color: #94A3B8;">
                If you did not create an account, you can safely ignore this email. This link will expire shortly.
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

    elif event.event_type in ("PASSWORD_RESET", "AUTH_RESET_PASSWORD"):
        reset_link = payload.get("reset_url") or payload.get("link")
        if not reset_link:
            token = payload.get("reset_token") or payload.get("token") or ""
            reset_link = f"{frontend_url}/reset-password?token={token}"

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Reset Your Password</title>
</head>
<body style="margin: 0; padding: 0; background-color: #FFF8F5; font-family: -apple-system, BlinkMacSystemFont, 'Plus Jakarta Sans', 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1E293B;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color: #FFF8F5; padding: 40px 16px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" style="max-width: 560px; background-color: #FFFFFF; border-radius: 16px; border: 1px solid #FCE8E1; box-shadow: 0 4px 12px rgba(0, 107, 96, 0.05); overflow: hidden;" cellspacing="0" cellpadding="0">
          <tr>
            <td style="background-color: #006B60; padding: 28px 32px; text-align: center;">
              <h1 style="margin: 0; color: #FFFFFF; font-size: 24px; font-weight: 700; letter-spacing: -0.02em;">Single-Instructor LMS</h1>
            </td>
          </tr>
          <tr>
            <td style="padding: 36px 32px;">
              <h2 style="margin: 0 0 16px 0; color: #006B60; font-size: 20px; font-weight: 600;">Reset Your Password</h2>
              <p style="margin: 0 0 24px 0; font-size: 15px; line-height: 1.6; color: #475569;">
                A password reset was requested for your account. Click the button below to choose a new password.
              </p>
              <table role="presentation" cellspacing="0" cellpadding="0" style="margin: 0 0 28px 0;">
                <tr>
                  <td align="center" style="border-radius: 10px; background-color: #006B60;">
                    <a href="{reset_link}" target="_blank" rel="noopener noreferrer" style="display: inline-block; padding: 14px 28px; font-size: 15px; font-weight: 600; color: #FFFFFF; text-decoration: none; border-radius: 10px; background-color: #006B60;">
                      Reset Password
                    </a>
                  </td>
                </tr>
              </table>
              <p style="margin: 0 0 8px 0; font-size: 13px; line-height: 1.5; color: #64748B;">
                Or copy and paste this link into your browser:
              </p>
              <p style="margin: 0 0 24px 0; font-size: 13px; line-height: 1.5; color: #006B60; word-break: break-all;">
                <a href="{reset_link}" style="color: #006B60; text-decoration: underline;">{reset_link}</a>
              </p>
              <hr style="border: none; border-top: 1px solid #F1F5F9; margin: 24px 0;" />
              <p style="margin: 0; font-size: 12px; line-height: 1.5; color: #94A3B8;">
                If you did not request a password reset, you can safely ignore this email. Your password will remain unchanged.
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

    elif event.event_type == "STAFF_INVITATION":
        invite_link = (
            payload.get("invitation_url")
            or payload.get("link")
            or (f"{frontend_url}/onboarding/claim?token={payload.get('invitation_token') or payload.get('token') or ''}")
        )
        role_name = payload.get("role", "Staff")
        full_name = payload.get("full_name", "there")

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Staff Team Invitation</title>
</head>
<body style="margin: 0; padding: 0; background-color: #FFF8F5; font-family: -apple-system, BlinkMacSystemFont, 'Plus Jakarta Sans', 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1E293B;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color: #FFF8F5; padding: 40px 16px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" style="max-width: 560px; background-color: #FFFFFF; border-radius: 16px; border: 1px solid #FCE8E1; box-shadow: 0 4px 12px rgba(0, 107, 96, 0.05); overflow: hidden;" cellspacing="0" cellpadding="0">
          <tr>
            <td style="background-color: #006B60; padding: 28px 32px; text-align: center;">
              <h1 style="margin: 0; color: #FFFFFF; font-size: 24px; font-weight: 700; letter-spacing: -0.02em;">Single-Instructor LMS</h1>
            </td>
          </tr>
          <tr>
            <td style="padding: 36px 32px;">
              <h2 style="margin: 0 0 16px 0; color: #006B60; font-size: 20px; font-weight: 600;">Staff Invitation</h2>
              <p style="margin: 0 0 16px 0; font-size: 15px; line-height: 1.6; color: #475569;">
                Hello {full_name},
              </p>
              <p style="margin: 0 0 24px 0; font-size: 15px; line-height: 1.6; color: #475569;">
                You have been invited to join the Single-Instructor LMS team as a <strong>{role_name}</strong>. Click the button below to accept your invitation and activate your account.
              </p>
              <table role="presentation" cellspacing="0" cellpadding="0" style="margin: 0 0 28px 0;">
                <tr>
                  <td align="center" style="border-radius: 10px; background-color: #006B60;">
                    <a href="{invite_link}" target="_blank" rel="noopener noreferrer" style="display: inline-block; padding: 14px 28px; font-size: 15px; font-weight: 600; color: #FFFFFF; text-decoration: none; border-radius: 10px; background-color: #006B60;">
                      Accept Invitation
                    </a>
                  </td>
                </tr>
              </table>
              <p style="margin: 0 0 8px 0; font-size: 13px; line-height: 1.5; color: #64748B;">
                Or copy and paste this link into your browser:
              </p>
              <p style="margin: 0 0 24px 0; font-size: 13px; line-height: 1.5; color: #006B60; word-break: break-all;">
                <a href="{invite_link}" style="color: #006B60; text-decoration: underline;">{invite_link}</a>
              </p>
              <hr style="border: none; border-top: 1px solid #F1F5F9; margin: 24px 0;" />
              <p style="margin: 0; font-size: 12px; line-height: 1.5; color: #94A3B8;">
                This invitation link will expire in 48 hours. If you were not expecting this invitation, you can safely ignore this email.
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

    elif event.event_type == "ENROLLMENT_RECEIPT":
        order_no = payload.get("order_no", "N/A")
        amount_inr = payload.get("amount_inr", 0)
        formatted_amount = f"₹{amount_inr / 100:.2f}" if isinstance(amount_inr, (int, float)) else str(amount_inr)
        payment_id = payload.get("razorpay_payment_id", "N/A")
        dashboard_link = f"{frontend_url}/app"

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Enrollment Confirmed</title>
</head>
<body style="margin: 0; padding: 0; background-color: #FFF8F5; font-family: -apple-system, BlinkMacSystemFont, 'Plus Jakarta Sans', 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1E293B;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color: #FFF8F5; padding: 40px 16px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" style="max-width: 560px; background-color: #FFFFFF; border-radius: 16px; border: 1px solid #FCE8E1; box-shadow: 0 4px 12px rgba(0, 107, 96, 0.05); overflow: hidden;" cellspacing="0" cellpadding="0">
          <tr>
            <td style="background-color: #006B60; padding: 28px 32px; text-align: center;">
              <h1 style="margin: 0; color: #FFFFFF; font-size: 24px; font-weight: 700; letter-spacing: -0.02em;">Single-Instructor LMS</h1>
            </td>
          </tr>
          <tr>
            <td style="padding: 36px 32px;">
              <h2 style="margin: 0 0 16px 0; color: #006B60; font-size: 20px; font-weight: 600;">Payment Received & Enrollment Confirmed!</h2>
              <p style="margin: 0 0 24px 0; font-size: 15px; line-height: 1.6; color: #475569;">
                Thank you for your purchase. Your payment has been confirmed and your course access is now active.
              </p>
              <table role="presentation" width="100%" style="background-color: #F8FAFC; border-radius: 8px; border: 1px solid #E2E8F0; margin: 0 0 24px 0; padding: 16px;" cellspacing="0" cellpadding="6">
                <tr>
                  <td style="font-size: 14px; color: #64748B;">Order Number:</td>
                  <td style="font-size: 14px; font-weight: 600; color: #1E293B; text-align: right;">{order_no}</td>
                </tr>
                <tr>
                  <td style="font-size: 14px; color: #64748B;">Amount Paid:</td>
                  <td style="font-size: 14px; font-weight: 600; color: #006B60; text-align: right;">{formatted_amount}</td>
                </tr>
                <tr>
                  <td style="font-size: 14px; color: #64748B;">Payment ID:</td>
                  <td style="font-size: 14px; color: #1E293B; text-align: right;">{payment_id}</td>
                </tr>
              </table>
              <table role="presentation" cellspacing="0" cellpadding="0" style="margin: 0 0 28px 0;">
                <tr>
                  <td align="center" style="border-radius: 10px; background-color: #006B60;">
                    <a href="{dashboard_link}" target="_blank" rel="noopener noreferrer" style="display: inline-block; padding: 14px 28px; font-size: 15px; font-weight: 600; color: #FFFFFF; text-decoration: none; border-radius: 10px; background-color: #006B60;">
                      Go to Your Dashboard
                    </a>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

    return None


def _send_smtp_email(
    settings: Any,
    from_addr: str,
    recipient: str,
    subject: str,
    body_text: str,
    body_html: Optional[str] = None,
) -> None:
    """Synchronous SMTP delivery helper using Python standard library smtplib with certifi SSL."""
    import smtplib
    import ssl
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.utils import formatdate, make_msgid

    try:
        import certifi
        cafile = certifi.where()
    except ImportError:
        cafile = None

    if body_html:
        msg = MIMEMultipart("alternative")
        part_text = MIMEText(body_text, "plain", "utf-8")
        part_html = MIMEText(body_html, "html", "utf-8")
        msg.attach(part_text)
        msg.attach(part_html)
    else:
        msg = MIMEText(body_text, "plain", "utf-8")

    msg["From"] = from_addr
    msg["To"] = recipient
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid()

    timeout = getattr(settings, "SMTP_TIMEOUT_SECONDS", 10)
    host = settings.SMTP_HOST
    port = settings.SMTP_PORT
    username = settings.SMTP_USERNAME
    password = settings.SMTP_PASSWORD.get_secret_value() if settings.SMTP_PASSWORD else ""

    try:
        with smtplib.SMTP(host=host, port=port, timeout=timeout) as server:
            server.ehlo()
            if getattr(settings, "SMTP_USE_TLS", True):
                ssl_context = (
                    ssl.create_default_context(cafile=cafile)
                    if cafile
                    else ssl.create_default_context()
                )
                server.starttls(context=ssl_context)
                server.ehlo()
            server.login(username, password)
            server.send_message(msg, from_addr=settings.EMAIL_FROM, to_addrs=[recipient])
    except smtplib.SMTPAuthenticationError as auth_err:
        raise RuntimeError(f"SMTP authentication failed for user '{username}': credentials rejected.") from auth_err
    except (smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected) as conn_err:
        raise RuntimeError(f"SMTP connection error: {conn_err}") from conn_err
    except smtplib.SMTPException as smtp_err:
        raise RuntimeError(f"SMTP delivery error: {smtp_err}") from smtp_err
    except (TimeoutError, OSError) as net_err:
        raise RuntimeError(f"SMTP network error: {net_err}") from net_err
    except Exception as exc:
        raise RuntimeError(f"Unexpected error during SMTP email delivery: {exc}") from exc


async def default_outbox_dispatcher(event: NotificationOutbox) -> None:
    """Dispatch outbox event using configured email/notification provider (BUG-005).

    In production: strictly enforces configured provider and valid API keys; never marks
    events SENT without actual provider acceptance.
    In development/testing: allows console logging only when non-production.
    """
    if event.channel != OUTBOX_CHANNEL_EMAIL:
        return

    settings = get_settings()

    # Reject console dispatcher or missing credentials in production
    if settings.is_production:
        if settings.EMAIL_PROVIDER in ("resend", "sendgrid"):
            if not settings.EMAIL_API_KEY:
                raise RuntimeError(
                    f"Production email delivery blocked: EMAIL_PROVIDER '{settings.EMAIL_PROVIDER}' "
                    "is unconfigured or missing EMAIL_API_KEY."
                )
            api_val = settings.EMAIL_API_KEY.get_secret_value().lower()
            if "mock" in api_val or "test" in api_val or "placeholder" in api_val:
                raise RuntimeError("Production email delivery blocked: placeholder or mock EMAIL_API_KEY.")
        elif settings.EMAIL_PROVIDER == "smtp":
            if (
                not settings.SMTP_HOST
                or not settings.SMTP_PORT
                or not settings.SMTP_USERNAME
                or not settings.SMTP_PASSWORD
            ):
                raise RuntimeError(
                    "Production email delivery blocked: EMAIL_PROVIDER 'smtp' "
                    "is unconfigured or missing SMTP_HOST, SMTP_PORT, SMTP_USERNAME, or SMTP_PASSWORD."
                )
            pwd_val = settings.SMTP_PASSWORD.get_secret_value().lower()
            user_val = settings.SMTP_USERNAME.lower()
            if "mock" in pwd_val or "test" in pwd_val or "placeholder" in pwd_val:
                raise RuntimeError("Production email delivery blocked: placeholder or mock SMTP_PASSWORD.")
            if "mock" in user_val or "placeholder" in user_val:
                raise RuntimeError("Production email delivery blocked: placeholder or mock SMTP_USERNAME.")
        else:
            raise RuntimeError(
                f"Production email delivery blocked: EMAIL_PROVIDER '{settings.EMAIL_PROVIDER}' "
                "is prohibited in production."
            )

    if settings.EMAIL_PROVIDER == "console":
        logger.info(
            "Outbox event dispatch [CONSOLE] [%s]: id=%s channel=%s recipient=%s subject=%s",
            event.event_type,
            event.id,
            event.channel,
            event.recipient,
            event.subject,
        )
        return

    # Real external email provider integration
    if settings.EMAIL_PROVIDER in ("resend", "sendgrid"):
        api_key = settings.EMAIL_API_KEY.get_secret_value() if settings.EMAIL_API_KEY else ""
        if not api_key:
            raise RuntimeError(f"Email provider '{settings.EMAIL_PROVIDER}' missing API key.")

        import json
        import urllib.error
        import urllib.request

        email_text = _format_email_text(event)

        if settings.EMAIL_PROVIDER == "resend":
            endpoint = "https://api.resend.com/emails"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            body = json.dumps({
                "from": f"{settings.EMAIL_FROM_NAME} <{settings.EMAIL_FROM}>",
                "to": [event.recipient],
                "subject": event.subject,
                "text": email_text,
            }).encode("utf-8")
        else:  # sendgrid
            endpoint = "https://api.sendgrid.com/v3/mail/send"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            body = json.dumps({
                "personalizations": [{"to": [{"email": event.recipient}]}],
                "from": {"email": settings.EMAIL_FROM, "name": settings.EMAIL_FROM_NAME},
                "subject": event.subject,
                "content": [{"type": "text/plain", "value": email_text}],
            }).encode("utf-8")

        req = urllib.request.Request(endpoint, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                code = resp.getcode()
                raw_resp = resp.read()
                if settings.EMAIL_PROVIDER == "resend":
                    if code not in (200, 201):
                        raise RuntimeError(f"Resend rejected email dispatch with HTTP {code}")
                    parsed = json.loads(raw_resp.decode("utf-8")) if raw_resp else {}
                    if not parsed.get("id"):
                        raise RuntimeError("Resend provider response missing accepted email ID.")
                else:  # sendgrid
                    if code not in (200, 202):
                        raise RuntimeError(f"SendGrid rejected email dispatch with HTTP {code}")
        except urllib.error.HTTPError as err:
            err_body = err.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Email provider HTTP {err.code}: {err_body}") from err
        except Exception as exc:
            raise RuntimeError(f"Email delivery network error: {exc}") from exc

    elif settings.EMAIL_PROVIDER == "smtp":
        if not settings.SMTP_HOST or not settings.SMTP_PORT:
            raise RuntimeError("Email provider 'smtp' missing SMTP_HOST or SMTP_PORT.")
        if not settings.SMTP_USERNAME or not settings.SMTP_PASSWORD:
            raise RuntimeError("Email provider 'smtp' missing SMTP_USERNAME or SMTP_PASSWORD.")

        email_text = _format_email_text(event)
        email_html = _format_email_html(event)
        from_addr = (
            f"{settings.EMAIL_FROM_NAME} <{settings.EMAIL_FROM}>"
            if settings.EMAIL_FROM_NAME
            else settings.EMAIL_FROM
        )

        await asyncio.to_thread(
            _send_smtp_email,
            settings=settings,
            from_addr=from_addr,
            recipient=event.recipient,
            subject=event.subject or "",
            body_text=email_text,
            body_html=email_html,
        )
    else:
        raise RuntimeError(f"Unsupported EMAIL_PROVIDER '{settings.EMAIL_PROVIDER}'.")


class OutboxWorker:
    """Asynchronous background worker polling and dispatching transactional outbox events."""

    def __init__(
        self,
        repository: Optional[NotificationOutboxRepository] = None,
        session_factory: Optional[Any] = None,
        batch_size: int = 50,
        poll_interval: float = 5.0,
        base_backoff_seconds: int = 30,
        max_retries: int = 5,
        stale_threshold_seconds: int = 300,
        dispatcher: Optional[OutboxDispatcher] = None,
    ) -> None:
        """Initialize OutboxWorker with configurable polling parameters.

        Args:
            repository: Optional NotificationOutboxRepository instance.
            session_factory: Callable providing AsyncSession or Session.
            batch_size: Max events to claim in one batch.
            poll_interval: Sleep seconds between polling batches when queue is idle.
            base_backoff_seconds: Base multiplier for exponential backoff (default 30s).
            max_retries: Failure threshold before transitioning event to FAILED (default 5).
            stale_threshold_seconds: Threshold in seconds to recover crashed worker events (default 300s).
            dispatcher: Custom async dispatch handler for external delivery.
        """
        self.repository = repository or NotificationOutboxRepository()
        self.session_factory = session_factory
        self.batch_size = max(1, batch_size)
        self.poll_interval = max(0.1, poll_interval)
        self.base_backoff_seconds = max(1, base_backoff_seconds)
        self.max_retries = max(1, max_retries)
        self.stale_threshold_seconds = max(10, stale_threshold_seconds)
        self.dispatcher = dispatcher or default_outbox_dispatcher

        self._running: bool = False
        self._task: Optional[asyncio.Task] = None

    def _get_session(self) -> Union[AsyncSession, Session]:
        """Obtain a database session from configured or default session factory."""
        if self.session_factory is not None:
            return self.session_factory()
        # Prefer synchronous SessionLocal (does not require greenlet in Python 3.14)
        if db_module.SessionLocal is not None:
            return db_module.SessionLocal()
        if db_module.AsyncSessionLocal is not None:
            return db_module.AsyncSessionLocal()
        raise RuntimeError("Database session factory is not configured for OutboxWorker.")

    async def run_once(self) -> int:
        """Execute a single polling, claiming, dispatching, and settlement cycle.

        Returns:
            Number of events claimed and processed during this cycle.
        """
        session = self._get_session()
        is_async = isinstance(session, AsyncSession)

        try:
            # 1. Recover stale events left by crashed or interrupted workers
            if is_async:
                async with session.begin():
                    recovered = await self.repository.recover_stale_processing_events(
                        session,
                        stale_threshold_seconds=self.stale_threshold_seconds,
                    )
            else:
                with session.begin():
                    recovered = await self.repository.recover_stale_processing_events(
                        session,
                        stale_threshold_seconds=self.stale_threshold_seconds,
                    )
            if recovered > 0:
                logger.warning("OutboxWorker recovered %d stale processing event(s).", recovered)

            # 2. Claim pending eligible events (with row-level lock)
            if is_async:
                async with session.begin():
                    events = await self.repository.claim_pending_events(
                        session,
                        batch_size=self.batch_size,
                        lock=True,
                    )
            else:
                with session.begin():
                    events = await self.repository.claim_pending_events(
                        session,
                        batch_size=self.batch_size,
                        lock=True,
                    )

            if not events:
                return 0

            logger.info("OutboxWorker claimed %d pending outbox event(s).", len(events))

            # 3. Process each event independently with isolated settlement
            for event in events:
                await self._process_single_event(session, event)

            return len(events)

        finally:
            if is_async:
                await session.close()
            else:
                session.close()

    async def _process_single_event(
        self,
        session: Union[AsyncSession, Session],
        event: NotificationOutbox,
    ) -> None:
        """Dispatch a single event and record its success or failure independently."""
        is_async = isinstance(session, AsyncSession)
        try:
            # Dispatch external notification/email
            await self.dispatcher(event)

            # Record success (SENT)
            if is_async:
                async with session.begin():
                    await self.repository.mark_as_sent(session, event.id)
            else:
                with session.begin():
                    await self.repository.mark_as_sent(session, event.id)

            logger.debug("Outbox event %s successfully dispatched and marked SENT.", event.id)

        except Exception as exc:
            # Scrub error description to prevent sensitive leakage
            clean_error = redact_sensitive_text(str(exc))
            logger.exception(
                "Error dispatching outbox event %s (attempt %d): %s",
                event.id,
                event.retry_count + 1,
                clean_error,
            )

            # Record failure and schedule next exponential retry
            try:
                if is_async:
                    async with session.begin():
                        await self.repository.record_failure(
                            session,
                            event_id=event.id,
                            error_message=clean_error,
                            base_backoff_seconds=self.base_backoff_seconds,
                            max_retries=self.max_retries,
                        )
                else:
                    with session.begin():
                        await self.repository.record_failure(
                            session,
                            event_id=event.id,
                            error_message=clean_error,
                            base_backoff_seconds=self.base_backoff_seconds,
                            max_retries=self.max_retries,
                        )
            except Exception as record_exc:
                logger.error(
                    "Failed to record outbox failure for event %s: %s",
                    event.id,
                    record_exc,
                )

    async def _run_loop(self) -> None:
        """Continuous background execution loop."""
        logger.info("OutboxWorker background polling loop started.")
        while self._running:
            try:
                processed_count = await self.run_once()
                if processed_count == 0 and self._running:
                    await asyncio.sleep(self.poll_interval)
            except asyncio.CancelledError:
                logger.info("OutboxWorker loop received cancellation signal.")
                break
            except Exception as exc:
                logger.exception("Unexpected error in OutboxWorker polling loop: %s", exc)
                if self._running:
                    await asyncio.sleep(self.poll_interval)
        logger.info("OutboxWorker background polling loop stopped.")

    async def start(self) -> None:
        """Start the background outbox polling worker task."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        """Stop the background outbox polling worker gracefully."""
        if not self._running:
            return
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None


def main() -> None:
    """CLI entrypoint for executing OutboxWorker as a standalone worker or single-cycle job."""
    import argparse
    import signal
    import sys

    parser = argparse.ArgumentParser(description="Transactional Outbox background polling worker.")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single outbox polling/dispatch cycle and exit.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="Max events to claim in one batch (default: from settings).",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=None,
        help="Polling interval in seconds between cycles (default: from settings).",
    )
    args = parser.parse_args()

    # Configure root logging for CLI runner if not already configured
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    settings = get_settings()
    batch_size = args.batch_size or settings.OUTBOX_BATCH_SIZE
    poll_interval = args.poll_interval or settings.OUTBOX_POLL_INTERVAL_SECONDS

    worker = OutboxWorker(
        batch_size=batch_size,
        poll_interval=poll_interval,
        base_backoff_seconds=settings.OUTBOX_BASE_BACKOFF_SECONDS,
        max_retries=settings.OUTBOX_MAX_RETRIES,
        stale_threshold_seconds=settings.OUTBOX_STALE_THRESHOLD_SECONDS,
    )

    async def _async_main() -> None:
        if args.once:
            logger.info("Running OutboxWorker single cycle (batch_size=%d)...", batch_size)
            processed = await worker.run_once()
            logger.info("OutboxWorker single cycle completed. %d event(s) processed.", processed)
            return

        logger.info(
            "Starting OutboxWorker continuous polling (poll_interval=%.1fs, batch_size=%d)...",
            poll_interval,
            batch_size,
        )
        loop = asyncio.get_running_loop()
        stop_event = asyncio.Event()

        def _handle_signal() -> None:
            logger.info("Shutdown signal received; stopping OutboxWorker...")
            stop_event.set()

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, _handle_signal)
            except (NotImplementedError, RuntimeError):
                pass

        await worker.start()
        try:
            await stop_event.wait()
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            await worker.stop()
            logger.info("OutboxWorker stopped successfully.")

    try:
        asyncio.run(_async_main())
    except KeyboardInterrupt:
        logger.info("OutboxWorker interrupted by user.")
        sys.exit(0)


if __name__ == "__main__":
    main()

