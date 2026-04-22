import logging
import smtplib
import threading
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

from .. import settings_store
from ..database import connect


logger = logging.getLogger(__name__)


def list_recipients(enabled_only: bool = True) -> list[str]:
    sql = "SELECT email FROM recipient"
    if enabled_only:
        sql += " WHERE enabled = 1"
    sql += " ORDER BY id ASC"
    with connect() as conn:
        rows = conn.execute(sql).fetchall()
    return [r["email"] for r in rows]


def _build_message(
    sender: str,
    recipients: list[str],
    subject: str,
    text_body: str,
    html_body: str | None = None,
) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = formataddr(("SignalHub", sender))
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg["Message-ID"] = make_msgid(domain="signalhub.local")
    msg.set_content(text_body or "(empty)")
    if html_body:
        msg.add_alternative(html_body, subtype="html")
    return msg


def _send_via_smtp(msg: EmailMessage, recipients: list[str], cfg: dict) -> None:
    host = cfg.get("smtp_host") or ""
    port = int(cfg.get("smtp_port") or 25)
    username = cfg.get("smtp_username") or ""
    password = cfg.get("smtp_password") or ""
    use_tls = bool(cfg.get("smtp_use_tls"))

    with smtplib.SMTP(host, port, timeout=15) as smtp:
        smtp.ehlo()
        if use_tls:
            try:
                smtp.starttls()
                smtp.ehlo()
            except smtplib.SMTPException as exc:
                logger.warning("STARTTLS failed, continuing in plain: %s", exc)
        if username and password:
            try:
                smtp.login(username, password)
            except smtplib.SMTPException as exc:
                logger.warning("SMTP auth failed, attempting anonymous send: %s", exc)
        smtp.send_message(msg, from_addr=cfg["smtp_sender"], to_addrs=recipients)


def _build_bodies(outcome: dict) -> tuple[str, str, str]:
    keyword = outcome.get("keyword", "")
    run_type = outcome.get("run_type", "")
    tags = outcome.get("tags") or []
    result = outcome.get("result") or ""
    arxiv_count = outcome.get("arxiv", 0)
    hf_count = outcome.get("huggingface", 0)
    geeknews_count = outcome.get("geeknews", 0)
    aitimes_count = outcome.get("aitimes", 0)

    subject = (
        f"{keyword} · {run_type} · "
        f"arxiv={arxiv_count} hf={hf_count} geeknews={geeknews_count} aitimes={aitimes_count}"
    )
    text = (
        f"[SignalHub] keyword={keyword} run_type={run_type}\n"
        f"sources: arxiv={arxiv_count}, hf={hf_count}, "
        f"geeknews={geeknews_count}, aitimes={aitimes_count}\n"
        f"tags: {', '.join(tags) if tags else '-'}\n\n"
        f"{result}\n"
    )
    html_result = (
        result.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n", "<br/>")
    )
    html = (
        "<div style=\"font-family:ui-monospace,Consolas,monospace;"
        "font-size:13px;line-height:1.5;max-width:760px;margin:0 auto;"
        "color:#1a1a1a\">"
        f"<h2 style=\"margin:0 0 8px 0;color:#1f2937\">SignalHub — {keyword}</h2>"
        f"<p style=\"color:#6b7280;margin:0 0 12px 0\">run_type: {run_type} · "
        f"arxiv: {arxiv_count} · hf: {hf_count} · "
        f"geeknews: {geeknews_count} · aitimes: {aitimes_count}</p>"
        "<p style=\"margin:0 0 12px 0\"><strong>tags:</strong> "
        f"{', '.join(tags) if tags else '-'}</p>"
        "<hr style=\"border:0;border-top:1px solid #e5e7eb;margin:12px 0\"/>"
        f"<div style=\"white-space:pre-wrap\">{html_result}</div>"
        "</div>"
    )
    return subject, text, html


def send_analysis_email(outcome: dict) -> bool:
    """Send an email notification about a completed analysis.

    Returns True if sent, False if skipped (no host/recipients) or failed.
    """
    cfg = settings_store.get_all()
    host = (cfg.get("smtp_host") or "").strip()
    sender = (cfg.get("smtp_sender") or "").strip()
    if not host or not sender:
        logger.debug("smtp not configured — skipping email")
        return False

    recipients = list_recipients(enabled_only=True)
    if not recipients:
        logger.debug("no recipients configured — skipping email")
        return False

    prefix = (cfg.get("smtp_subject_prefix") or "").strip()
    subject_core, text, html = _build_bodies(outcome)
    subject = f"{prefix} {subject_core}".strip() if prefix else subject_core

    try:
        msg = _build_message(sender, recipients, subject, text, html)
        _send_via_smtp(msg, recipients, cfg)
        logger.info(
            "email sent: keyword=%s recipients=%d", outcome.get("keyword"), len(recipients)
        )
        return True
    except Exception:
        logger.exception("email send failed")
        return False


def send_async(outcome: dict) -> None:
    """Fire-and-forget wrapper for send_analysis_email."""
    t = threading.Thread(target=send_analysis_email, args=(outcome,), daemon=True)
    t.start()


def send_test(to_email: str | None = None) -> dict:
    cfg = settings_store.get_all()
    host = (cfg.get("smtp_host") or "").strip()
    sender = (cfg.get("smtp_sender") or "").strip()
    if not host or not sender:
        return {"ok": False, "error": "smtp_host and smtp_sender must be configured"}

    recipients = [to_email] if to_email else list_recipients(enabled_only=True)
    if not recipients:
        return {"ok": False, "error": "no recipients"}

    subject = (
        (cfg.get("smtp_subject_prefix") or "").strip() + " test message"
    ).strip() or "SignalHub test"
    try:
        msg = _build_message(
            sender,
            recipients,
            subject,
            "This is a SignalHub SMTP test message.",
            "<p>This is a <b>SignalHub</b> SMTP test message.</p>",
        )
        _send_via_smtp(msg, recipients, cfg)
        return {"ok": True, "recipients": recipients}
    except Exception as exc:
        logger.exception("smtp test failed")
        return {"ok": False, "error": str(exc)}
