# core/services/email_service.py
"""Отправка писем: Resend API (приоритет) или SMTP (STARTTLS / SSL)."""
import logging
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

import httpx

from ..config import settings

logger = logging.getLogger(__name__)

RESEND_API_URL = 'https://api.resend.com/emails'


def _smtp_login_user() -> str:
    return (settings.SMTP_USER or settings.EMAIL_FROM or '').strip()


def _smtp_password() -> str:
    return settings.SMTP_PASSWORD or ''


def _send_via_resend(to_address: str, subject: str, body_text: str) -> bool:
    """Отправка через Resend REST API."""
    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.post(
                RESEND_API_URL,
                headers={
                    'Authorization': f'Bearer {settings.RESEND_API_KEY}',
                    'Content-Type': 'application/json',
                },
                json={
                    'from': settings.EMAIL_FROM,
                    'to': [to_address],
                    'subject': subject,
                    'text': body_text,
                },
            )
        if r.status_code in (200, 201):
            return True
        logger.error(
            'Resend API error: %s %s', r.status_code, r.text[:500] if r.text else ''
        )
        return False
    except Exception as e:
        logger.error('Resend request failed: %s', e, exc_info=True)
        return False


def _build_mime_message(
    to_address: str, subject: str, body_text: str, reply_to: Optional[str] = None
) -> MIMEMultipart:
    msg = MIMEMultipart()
    msg['Subject'] = subject
    msg['From'] = settings.EMAIL_FROM
    msg['To'] = to_address
    if reply_to:
        msg['Reply-To'] = reply_to
    msg.attach(MIMEText(body_text, 'plain', 'utf-8'))
    return msg


def _send_via_smtp(
    to_address: str, subject: str, body_text: str, reply_to: Optional[str] = None
) -> bool:
    """SMTP: implicit SSL (465) или обычный порт + STARTTLS (2525, 587)."""
    msg = _build_mime_message(to_address, subject, body_text, reply_to=reply_to)
    login_user = _smtp_login_user()
    password = _smtp_password()
    timeout = 30
    ctx = ssl.create_default_context()

    if settings.SMTP_USE_SSL:
        with smtplib.SMTP_SSL(
            settings.SMTP_HOST, settings.SMTP_PORT, context=ctx, timeout=timeout
        ) as smtp:
            if settings.DEBUG:
                smtp.set_debuglevel(1)
            smtp.ehlo()
            if login_user:
                smtp.login(login_user, password)
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(
            settings.SMTP_HOST, settings.SMTP_PORT, timeout=timeout
        ) as smtp:
            if settings.DEBUG:
                smtp.set_debuglevel(1)
            smtp.ehlo()
            if settings.SMTP_USE_STARTTLS:
                smtp.starttls(context=ctx)
                smtp.ehlo()
            if login_user:
                smtp.login(login_user, password)
            smtp.send_message(msg)
    return True


def send_email_sync(
    to_address: str, subject: str, body_text: str, reply_to: Optional[str] = None
) -> bool:
    """
    Синхронная отправка письма.
    Сначала Resend (если задан RESEND_API_KEY), иначе SMTP (если задан SMTP_HOST).
    """
    if settings.RESEND_API_KEY:
        return _send_via_resend(to_address, subject, body_text)

    if not settings.SMTP_HOST:
        logger.warning(
            'Neither RESEND_API_KEY nor SMTP_HOST is set; email not sent'
        )
        return False

    try:
        return _send_via_smtp(to_address, subject, body_text, reply_to=reply_to)
    except Exception as e:
        logger.error('Failed to send email via SMTP: %s', e, exc_info=True)
        return False


def build_verification_email_body(code: str) -> str:
    return (
        f'Ваш код подтверждения TaskFlow: {code}\n\n'
        f'Код действителен {settings.EMAIL_CODE_EXPIRY_MINUTES} минут.\n'
        f'Если вы не запрашивали код, проигнорируйте это письмо.\n'
    )


def build_recovery_email_body(code: str) -> str:
    return (
        f'Код восстановления пароля TaskFlow: {code}\n\n'
        f'Если вы не запрашивали сброс пароля, проигнорируйте это письмо.\n'
    )
