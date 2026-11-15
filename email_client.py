# email_client.py
import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

log = logging.getLogger(__name__)

def send_email(
    subject: str,
    html_body: str,
    *,
    sender: str | None = None,
    recipient: str | None = None,
    password: str | None = None,
    host: str = "smtp.gmail.com",
    port: int = 465,
    timeout: int = 30,
) -> None:
    sender = sender or os.getenv("EMAIL_MITTENTE")
    recipient = recipient or os.getenv("EMAIL_DESTINATARIO")
    password = password or os.getenv("GMAIL_APP_PASSWORD")
    if not (sender and recipient and password):
        raise RuntimeError("EMAIL_MITTENTE / EMAIL_DESTINATARIO / GMAIL_APP_PASSWORD non configurati.")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP_SSL(host, port, timeout=timeout) as server:
        server.login(sender, password)
        server.send_message(msg)
    log.info("✅ Email inviata con successo!")