# core/services/email_queue.py
"""Очередь исходящей почты + переиспользование SMTP-соединения в одном воркере."""
from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass
from email.message import Message
from typing import Any, Optional

from ..config import settings

logger = logging.getLogger(__name__)


@dataclass
class EmailJob:
    to_address: str
    subject: str
    body_text: str
    reply_to: Optional[str] = None


class EmailDeliveryManager:
    """
    Один фоновой поток: очередь писем, для SMTP — одно долгоживущее соединение.
    При обрыве — переподключение и повторная отправка текущего письма.
    Resend обрабатывается в том же потоке без постоянного сокета (HTTPS).
    """

    def __init__(self) -> None:
        self._q: queue.Queue[Optional[EmailJob]] = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._start_lock = threading.Lock()
        self._smtp: Optional[Any] = None
        self._smtp_lock = threading.Lock()
        self._smtp_last_used: float = 0.0

    def start(self) -> None:
        """Идемпотентный запуск воркера (из lifespan FastAPI)."""
        with self._start_lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._worker_loop, name='email-delivery', daemon=True
            )
            self._thread.start()
            logger.info('Email delivery worker started')

    def stop(self, timeout: float = 5.0) -> None:
        """Остановка воркера и закрытие SMTP."""
        self._stop.set()
        self._q.put_nowait(None)
        if self._thread is not None:
            self._thread.join(timeout=timeout)
        self._smtp_disconnect()
        logger.info('Email delivery worker stopped')

    def enqueue(
        self,
        to_address: str,
        subject: str,
        body_text: str,
        reply_to: Optional[str] = None,
    ) -> None:
        """Поставить письмо в очередь (не блокирует HTTP)."""
        self.start()
        self._q.put_nowait(
            EmailJob(
                to_address=to_address,
                subject=subject,
                body_text=body_text,
                reply_to=reply_to,
            )
        )

    def _worker_loop(self) -> None:
        while not self._stop.is_set():
            try:
                job = self._q.get(timeout=0.5)
            except queue.Empty:
                continue
            if job is None:
                break
            try:
                self._deliver(job)
            except Exception:
                logger.exception('Unexpected error delivering email to %s', job.to_address)
            finally:
                self._q.task_done()

    def _deliver(self, job: EmailJob) -> None:
        if settings.RESEND_API_KEY:
            from .email_service import _send_via_resend

            _send_via_resend(job.to_address, job.subject, job.body_text)
            return

        if not settings.SMTP_HOST:
            logger.warning('SMTP_HOST not set; email to %s skipped', job.to_address)
            return

        from .email_service import _build_mime_message

        msg = _build_mime_message(
            job.to_address, job.subject, job.body_text, reply_to=job.reply_to
        )
        self._smtp_send_with_pool(msg)

    def _idle_exceeded(self) -> bool:
        if settings.SMTP_IDLE_MAX_SEC <= 0:
            return False
        if self._smtp_last_used <= 0:
            return False
        return (time.monotonic() - self._smtp_last_used) > settings.SMTP_IDLE_MAX_SEC

    def _smtp_send_with_pool(self, msg: Message) -> None:
        from .email_service import connect_smtp_server, safe_quit_smtp

        with self._smtp_lock:
            try:
                if self._smtp is None or self._idle_exceeded():
                    safe_quit_smtp(self._smtp)
                    self._smtp = None
                    self._smtp = connect_smtp_server()
                self._smtp.send_message(msg)
                self._smtp_last_used = time.monotonic()
            except Exception as e:
                logger.warning(
                    'SMTP send failed (%s), reconnecting and retrying once', e
                )
                safe_quit_smtp(self._smtp)
                self._smtp = None
                try:
                    self._smtp = connect_smtp_server()
                    self._smtp.send_message(msg)
                    self._smtp_last_used = time.monotonic()
                except Exception:
                    logger.exception('SMTP retry failed after reconnect')
                    safe_quit_smtp(self._smtp)
                    self._smtp = None

    def _smtp_disconnect(self) -> None:
        from .email_service import safe_quit_smtp

        with self._smtp_lock:
            safe_quit_smtp(self._smtp)
            self._smtp = None


_manager: Optional[EmailDeliveryManager] = None
_manager_lock = threading.Lock()


def get_email_manager() -> EmailDeliveryManager:
    global _manager
    with _manager_lock:
        if _manager is None:
            _manager = EmailDeliveryManager()
        return _manager
