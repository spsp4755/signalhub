import html
import logging
import re
import smtplib
import threading
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

from .. import settings_store
from ..database import connect


logger = logging.getLogger(__name__)

_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")


def list_recipients(enabled_only: bool = True) -> list[str]:
    sql = "SELECT email FROM recipient"
    if enabled_only:
        sql += " WHERE enabled = 1"
    sql += " ORDER BY id ASC"
    with connect() as conn:
        rows = conn.execute(sql).fetchall()
    return [r["email"] for r in rows]


def list_recipient_profiles(enabled_only: bool = True) -> list[dict]:
    sql = "SELECT id, email FROM recipient"
    if enabled_only:
        sql += " WHERE enabled = 1"
    sql += " ORDER BY id ASC"
    with connect() as conn:
        rows = conn.execute(sql).fetchall()
        kw_rows = conn.execute(
            "SELECT recipient_id, keyword_id FROM recipient_keyword ORDER BY keyword_id ASC"
        ).fetchall()

    keywords_by_recipient: dict[int, list[int]] = {}
    for row in kw_rows:
        keywords_by_recipient.setdefault(row["recipient_id"], []).append(row["keyword_id"])

    return [
        {
            "id": row["id"],
            "email": row["email"],
            "keyword_ids": keywords_by_recipient.get(row["id"], []),
        }
        for row in rows
    ]


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


def _render_inline(text: str) -> str:
    parts: list[str] = []
    pos = 0
    for match in _LINK_RE.finditer(text or ""):
        parts.append(html.escape(text[pos : match.start()]))
        label = html.escape(match.group(1).strip())
        url = html.escape(match.group(2).strip(), quote=True)
        parts.append(
            f'<a href="{url}" target="_blank" rel="noopener noreferrer" '
            f'style="color:#2563eb;text-decoration:none">{label}</a>'
        )
        pos = match.end()
    parts.append(html.escape(text[pos:]))
    return "".join(parts)


def _markdownish_to_html(markdown: str) -> str:
    html_parts: list[str] = []
    in_list = False

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            html_parts.append("</ul>")
            in_list = False

    for raw_line in (markdown or "").splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            close_list()
            continue
        if stripped.startswith("### "):
            close_list()
            html_parts.append(
                '<h4 style="margin:14px 0 6px;color:#1d4ed8;font-size:15px">'
                + _render_inline(stripped[4:])
                + "</h4>"
            )
        elif stripped.startswith("## "):
            close_list()
            html_parts.append(
                '<h3 style="margin:18px 0 8px;color:#111827;font-size:17px">'
                + _render_inline(stripped[3:])
                + "</h3>"
            )
        elif stripped.startswith("- "):
            if not in_list:
                html_parts.append('<ul style="margin:6px 0 10px 20px;padding:0">')
                in_list = True
            html_parts.append(
                '<li style="margin:4px 0">' + _render_inline(stripped[2:]) + "</li>"
            )
        else:
            close_list()
            html_parts.append(
                '<p style="margin:7px 0">' + _render_inline(stripped) + "</p>"
            )

    close_list()
    return "\n".join(html_parts)


def _plain_source_lines(sources: dict, group: str) -> list[str]:
    if group == "news":
        items = (sources.get("geeknews") or []) + (sources.get("aitimes") or [])
    else:
        items = (
            (sources.get("arxiv") or [])
            + (sources.get("huggingface_papers") or [])
            + (sources.get("huggingface_models") or [])
        )
    return [
        f"- {item.get('title', '-')}: {item.get('url', '')}".rstrip()
        for item in items
        if item.get("title") or item.get("url")
    ]


def _html_source_section(title: str, items: list[dict]) -> str:
    if not items:
        return ""
    rows = []
    for item in items:
        label = html.escape(item.get("title") or item.get("url") or "-")
        url = item.get("url") or ""
        authors = item.get("authors") or []
        if url.startswith(("http://", "https://")):
            label_html = (
                f'<a href="{html.escape(url, quote=True)}" target="_blank" '
                f'rel="noopener noreferrer" style="color:#2563eb;text-decoration:none">'
                f"{label}</a>"
            )
        else:
            label_html = label
        author_html = ""
        if authors:
            author_html = (
                '<div style="color:#6b7280;font-size:12px;margin-top:2px">'
                + html.escape(", ".join(authors[:4]))
                + (" 외" if len(authors) > 4 else "")
                + "</div>"
            )
        rows.append(f"<li style=\"margin:5px 0\">{label_html}{author_html}</li>")
    return (
        f'<h4 style="margin:14px 0 6px;color:#374151;font-size:13px">{title}</h4>'
        f'<ul style="margin:0 0 8px 20px;padding:0">{"".join(rows)}</ul>'
    )


def _build_source_sections_html(sources: dict) -> str:
    news = (sources.get("geeknews") or []) + (sources.get("aitimes") or [])
    papers = (
        (sources.get("arxiv") or [])
        + (sources.get("huggingface_papers") or [])
        + (sources.get("huggingface_models") or [])
    )
    return (
        _html_source_section("뉴스 출처", news)
        + _html_source_section("논문·모델 출처", papers)
    )


def _count_summary(outcome: dict) -> str:
    news = int(outcome.get("geeknews", 0)) + int(outcome.get("aitimes", 0))
    papers = int(outcome.get("arxiv", 0)) + int(outcome.get("huggingface", 0))
    return f"news={news} papers/models={papers}"


def _build_bodies(outcome: dict) -> tuple[str, str, str]:
    keyword = outcome.get("keyword", "")
    run_type = outcome.get("run_type", "")
    tags = outcome.get("tags") or []
    result = outcome.get("result") or ""
    sources = outcome.get("sources") or {}

    subject = f"{keyword} · {run_type} · {_count_summary(outcome)}"
    text_sections = [
        f"[SignalHub] keyword={keyword} run_type={run_type}",
        f"sources: {_count_summary(outcome)}",
        f"tags: {', '.join(tags) if tags else '-'}",
        "",
        result,
        "",
        "뉴스 출처",
        *(_plain_source_lines(sources, "news") or ["-"]),
        "",
        "논문·모델 출처",
        *(_plain_source_lines(sources, "papers") or ["-"]),
    ]
    text = "\n".join(text_sections)

    html_body = (
        '<div style="font-family:Arial,Apple SD Gothic Neo,Malgun Gothic,sans-serif;'
        'font-size:14px;line-height:1.6;max-width:820px;margin:0 auto;color:#111827">'
        f'<h2 style="margin:0 0 8px;color:#111827">SignalHub - {html.escape(keyword)}</h2>'
        f'<p style="color:#6b7280;margin:0 0 12px">run_type: {html.escape(run_type)} · '
        f'{html.escape(_count_summary(outcome))}</p>'
        f'<p style="margin:0 0 12px"><strong>tags:</strong> '
        f'{html.escape(", ".join(tags) if tags else "-")}</p>'
        '<hr style="border:0;border-top:1px solid #e5e7eb;margin:14px 0"/>'
        + _markdownish_to_html(result)
        + '<hr style="border:0;border-top:1px solid #e5e7eb;margin:14px 0"/>'
        + _build_source_sections_html(sources)
        + "</div>"
    )
    return subject, text, html_body


def _subject_with_prefix(prefix: str, subject_core: str) -> str:
    return f"{prefix} {subject_core}".strip() if prefix else subject_core


def send_analysis_email(outcome: dict) -> bool:
    """Send an email notification about one completed analysis."""
    cfg = settings_store.get_all()
    host = (cfg.get("smtp_host") or "").strip()
    sender = (cfg.get("smtp_sender") or "").strip()
    if not host or not sender:
        logger.debug("smtp not configured - skipping email")
        return False

    recipients = list_recipients(enabled_only=True)
    if not recipients:
        logger.debug("no recipients configured - skipping email")
        return False

    prefix = (cfg.get("smtp_subject_prefix") or "").strip()
    subject_core, text, html_body = _build_bodies(outcome)
    subject = _subject_with_prefix(prefix, subject_core)

    try:
        msg = _build_message(sender, recipients, subject, text, html_body)
        _send_via_smtp(msg, recipients, cfg)
        logger.info(
            "email sent: keyword=%s recipients=%d", outcome.get("keyword"), len(recipients)
        )
        return True
    except Exception:
        logger.exception("email send failed")
        return False


def _group_digest_recipients(outcomes: list[dict], profiles: list[dict]) -> list[dict]:
    grouped: dict[tuple[int, ...], dict] = {}
    for profile in profiles:
        assigned = set(profile.get("keyword_ids") or [])
        selected = [
            item
            for item in outcomes
            if not assigned or item.get("keyword_id") in assigned
        ]
        if not selected:
            continue
        key = tuple(int(item.get("keyword_id") or 0) for item in selected)
        bucket = grouped.setdefault(key, {"recipients": [], "items": selected})
        bucket["recipients"].append(profile["email"])
    return list(grouped.values())


def _build_digest_bodies(items: list[dict]) -> tuple[str, str, str]:
    success_items = [item for item in items if item.get("ok") and item.get("outcome")]
    failed_items = [item for item in items if not item.get("ok")]
    keywords = [item.get("keyword", "") for item in items]
    subject = f"자동 수집 다이제스트 · 성공 {len(success_items)}/{len(items)}"

    text_lines = [
        "[SignalHub] 자동 수집 다이제스트",
        f"keywords: {', '.join(keywords) if keywords else '-'}",
        f"success: {len(success_items)} / {len(items)}",
        "",
    ]
    html_sections = [
        '<div style="font-family:Arial,Apple SD Gothic Neo,Malgun Gothic,sans-serif;'
        'font-size:14px;line-height:1.6;max-width:920px;margin:0 auto;color:#111827">',
        '<h2 style="margin:0 0 8px;color:#111827">SignalHub 자동 수집 다이제스트</h2>',
        f'<p style="color:#6b7280;margin:0 0 12px">성공 {len(success_items)} / '
        f'{len(items)} · {html.escape(", ".join(keywords) if keywords else "-")}</p>',
    ]

    for item in success_items:
        outcome = item["outcome"]
        keyword = outcome.get("keyword", "")
        sources = outcome.get("sources") or {}
        text_lines.extend(
            [
                f"## {keyword}",
                f"sources: {_count_summary(outcome)}",
                outcome.get("result") or "",
                "",
                "뉴스 출처",
                *(_plain_source_lines(sources, "news") or ["-"]),
                "",
                "논문·모델 출처",
                *(_plain_source_lines(sources, "papers") or ["-"]),
                "",
            ]
        )
        html_sections.extend(
            [
                '<section style="border-top:1px solid #e5e7eb;padding-top:18px;margin-top:18px">',
                f'<h3 style="margin:0 0 4px;color:#111827;font-size:18px">'
                f'{html.escape(keyword)}</h3>',
                f'<p style="color:#6b7280;margin:0 0 10px">'
                f'{html.escape(_count_summary(outcome))}</p>',
                _markdownish_to_html(outcome.get("result") or ""),
                '<div style="margin-top:12px">',
                _build_source_sections_html(sources),
                "</div>",
                "</section>",
            ]
        )

    if failed_items:
        text_lines.extend(["실패한 키워드"])
        html_sections.append(
            '<section style="border-top:1px solid #e5e7eb;padding-top:18px;margin-top:18px">'
            '<h3 style="margin:0 0 8px;color:#b91c1c;font-size:16px">실패한 키워드</h3>'
            '<ul style="margin:0 0 8px 20px;padding:0">'
        )
        for item in failed_items:
            line = f"- {item.get('keyword', '-')}: {item.get('error', '-')}"
            text_lines.append(line)
            html_sections.append(
                f'<li style="margin:5px 0">{html.escape(item.get("keyword", "-"))}: '
                f'{html.escape(item.get("error", "-"))}</li>'
            )
        html_sections.append("</ul></section>")

    html_sections.append("</div>")
    return subject, "\n".join(text_lines), "\n".join(html_sections)


def send_digest_email(outcomes: list[dict]) -> bool:
    """Send one digest per recipient keyword profile for automatic runs."""
    cfg = settings_store.get_all()
    host = (cfg.get("smtp_host") or "").strip()
    sender = (cfg.get("smtp_sender") or "").strip()
    if not host or not sender:
        logger.debug("smtp not configured - skipping digest email")
        return False

    profiles = list_recipient_profiles(enabled_only=True)
    if not profiles:
        logger.debug("no recipients configured - skipping digest email")
        return False

    groups = _group_digest_recipients(outcomes, profiles)
    if not groups:
        logger.debug("no digest recipients matched outcomes")
        return False

    prefix = (cfg.get("smtp_subject_prefix") or "").strip()
    sent_any = False
    for group in groups:
        recipients = group["recipients"]
        subject_core, text, html_body = _build_digest_bodies(group["items"])
        subject = _subject_with_prefix(prefix, subject_core)
        try:
            msg = _build_message(sender, recipients, subject, text, html_body)
            _send_via_smtp(msg, recipients, cfg)
            logger.info("digest email sent: recipients=%d", len(recipients))
            sent_any = True
        except Exception:
            logger.exception("digest email send failed")
    return sent_any


def send_async(outcome: dict) -> None:
    """Fire-and-forget wrapper for send_analysis_email."""
    t = threading.Thread(target=send_analysis_email, args=(outcome,), daemon=True)
    t.start()


def send_digest_async(outcomes: list[dict]) -> None:
    """Fire-and-forget wrapper for send_digest_email."""
    t = threading.Thread(target=send_digest_email, args=(outcomes,), daemon=True)
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
