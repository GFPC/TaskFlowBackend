import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import ssl
import random
import string

# ========== НАСТРОЙКИ TIMEWEB CLOUD ==========
TIMEWEB_SMTP = 'smtp.timeweb.ru'  # SMTP сервер Timeweb [citation:2][citation:5]
TIMEWEB_PORT = 2525  # SSL порт (рекомендуется)
# Альтернативные порты: 25, 2525 (без шифрования) или 587 [citation:1]

# Данные вашей корпоративной почты
EMAIL_FROM = 'no-reply@corsair-taskflow.site'  # Полный адрес почтового ящика
EMAIL_PASSWORD = '+$-/ZGJ6Oi9fWV'  # Пароль от этого ящика


# ============================================

def send_email(to_email, subject, body):
    try:
        # Создаем SSL-контекст для starttls
        context = ssl.create_default_context()

        # Используем обычный SMTP (НЕ SSL)
        server = smtplib.SMTP(TIMEWEB_SMTP, TIMEWEB_PORT, timeout=30)
        server.set_debuglevel(1)  # включим отладку, потом можно убрать

        # Приветствие
        server.ehlo()

        # Включаем TLS шифрование
        print("Включение TLS...")
        server.starttls(context=context)
        server.ehlo()  # повторное приветствие после шифрования

        # Авторизация
        print("Авторизация...")
        server.login(EMAIL_FROM, EMAIL_PASSWORD)

        # Формируем письмо
        msg = MIMEMultipart()
        msg['From'] = EMAIL_FROM
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain', 'utf-8'))

        # Отправляем
        print("Отправка письма...")
        server.send_message(msg)
        server.quit()

        print(f"✅ Письмо успешно отправлено на {to_email}")
        return True

    except Exception as e:
        print(f"❌ Ошибка при отправке: {e}")
        return False


# Пример использования
if __name__ == "__main__":
    send_email(
        to_email='fgrgi@ya.ru',
        subject='Код подтверждения',
        body='Ваш код подтверждения: 644377'
    )