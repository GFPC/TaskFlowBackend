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


def safe_quit_smtp(smtp: Optional[smtplib.SMTP]) -> None:
    """Закрыть SMTP без исключений наружу."""
    if smtp is None:
        return
    try:
        smtp.quit()
    except Exception:
        try:
            smtp.close()
        except Exception:
            pass


def connect_smtp_server() -> smtplib.SMTP:
    """
    Установить соединение с SMTP и залогиниться.
    Вызывающий обязан вызвать safe_quit_smtp при завершении (или держать пул).
    """
    login_user = _smtp_login_user()
    password = _smtp_password()
    timeout = settings.SMTP_TIMEOUT
    ctx = ssl.create_default_context()

    logger.info(
        'SMTP connect to %s:%s (timeout=%ss, ssl=%s, starttls=%s)',
        settings.SMTP_HOST,
        settings.SMTP_PORT,
        timeout,
        settings.SMTP_USE_SSL,
        settings.SMTP_USE_STARTTLS,
    )

    if settings.SMTP_USE_SSL:
        smtp = smtplib.SMTP_SSL(
            settings.SMTP_HOST, settings.SMTP_PORT, context=ctx, timeout=timeout
        )
        if settings.DEBUG:
            smtp.set_debuglevel(1)
        smtp.ehlo()
        if login_user:
            smtp.login(login_user, password)
        return smtp

    smtp = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=timeout)
    if settings.DEBUG:
        smtp.set_debuglevel(1)
    smtp.ehlo()
    if settings.SMTP_USE_STARTTLS:
        smtp.starttls(context=ctx)
        smtp.ehlo()
    if login_user:
        smtp.login(login_user, password)
    return smtp


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
    """Одноразовая отправка SMTP (connect → send → quit). Для API — очередь email_queue."""
    msg = _build_mime_message(to_address, subject, body_text, reply_to=reply_to)
    smtp = connect_smtp_server()
    try:
        smtp.send_message(msg)
        return True
    finally:
        safe_quit_smtp(smtp)


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
    except (TimeoutError, OSError) as e:
        if isinstance(e, TimeoutError) or 'timed out' in str(e).lower():
            logger.error(
                'SMTP connection timed out to %s:%s. '
                'Often: outbound port blocked by hosting firewall, wrong host/port, '
                'or provider allows only 587/465. Try SMTP_PORT=587 with STARTTLS, '
                'or SMTP_USE_SSL=true and SMTP_PORT=465, or use RESEND_API_KEY (HTTPS). '
                'Original: %s',
                settings.SMTP_HOST,
                settings.SMTP_PORT,
                e,
            )
        else:
            logger.error('SMTP network error: %s', e, exc_info=True)
        return False
    except Exception as e:
        logger.error('Failed to send email via SMTP: %s', e, exc_info=True)
        return False


def send_email_in_thread(
    to_address: str, subject: str, body_text: str, reply_to: Optional[str] = None
) -> None:
    """Ставит письмо в очередь фонового менеджера (SMTP-пул / Resend в одном воркере)."""
    from .email_queue import get_email_manager

    get_email_manager().enqueue(to_address, subject, body_text, reply_to=reply_to)


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
