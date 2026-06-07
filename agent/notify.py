"""Email notifications over Gmail SMTP (Plan 2 app password). Best-effort:
a send failure logs and never breaks the job flow (spec §8)."""
import smtplib
from email.mime.text import MIMEText

from agent.config import settings


def build_ready_email(match_name: str, results_url: str, expires_on: str):
    subject = f"Your analysis is ready: {match_name}"
    html = (f"<p>Your match <b>{match_name}</b> has been analysed.</p>"
            f'<p><a href="{results_url}">Open your results</a></p>'
            f"<p>Available until <b>{expires_on}</b> — download them soon.</p>")
    return subject, html


def build_failed_email(match_name: str, message: str):
    subject = f"Update on: {match_name}"
    html = (f"<p>We hit a problem with <b>{match_name}</b>.</p>"
            f"<p>{message}</p><p>You're welcome to submit it again.</p>")
    return subject, html


def build_promoted_email(match_name: str, job_url: str):
    subject = f"It's your turn: {match_name}"
    html = (f"<p>Storage has freed up — it's your turn to upload "
            f"<b>{match_name}</b>.</p>"
            f'<p><a href="{job_url}">Click here to upload your footage.</a></p>')
    return subject, html


def send_email(to: str | None, subject: str, html: str) -> None:
    if not to or not settings.smtp_user or not settings.smtp_app_password:
        print(f"  email skipped: {subject!r} -> {to}")
        return
    try:
        msg = MIMEText(html, "html")
        msg["Subject"] = subject
        msg["From"] = settings.email_from
        msg["To"] = to
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as s:
            s.login(settings.smtp_user, settings.smtp_app_password)
            s.sendmail(settings.smtp_user, [to], msg.as_string())
        print(f"  email sent: {subject!r} -> {to}")
    except Exception as e:  # noqa: BLE001 — never let email kill a job
        print(f"  email FAILED ({e}): {subject!r} -> {to}")
