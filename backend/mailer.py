"""Sends the password-reset confirmation email.

If SMTP_HOST is not configured (typical in local development) the link is
printed to the server log instead, so you can click it from the terminal.
"""
import smtplib
from email.message import EmailMessage


def send_reset_email(app, to_address: str, link: str) -> None:
    host = app.config.get("SMTP_HOST")
    if not host:
        app.logger.warning("[DEV] SMTP not configured. Reset link for %s: %s", to_address, link)
        return

    msg = EmailMessage()
    msg["Subject"] = "Confirm your new Recifix password"
    msg["From"] = app.config["MAIL_FROM"]
    msg["To"] = to_address
    msg.set_content(
        "Someone asked to change the password on your Recifix account.\n\n"
        f"To confirm the new password, open this link (valid for 1 hour):\n{link}\n\n"
        "If this wasn't you, ignore this email and your password stays the same."
    )

    port = app.config["SMTP_PORT"]
    try:
        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=15)
        else:
            server = smtplib.SMTP(host, port, timeout=15)
            if app.config["SMTP_STARTTLS"]:
                server.starttls()
        with server:
            if app.config.get("SMTP_USER"):
                server.login(app.config["SMTP_USER"], app.config["SMTP_PASSWORD"])
            server.send_message(msg)
    except Exception:
        # Never reveal mail problems (or whether the account exists) to the client.
        app.logger.exception("Failed to send reset email to %s", to_address)
