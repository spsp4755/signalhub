from dataclasses import dataclass
from html import unescape
import re
from xml.etree import ElementTree

import httpx

from ..config import settings


@dataclass
class NewsItem:
    title: str
    summary: str
    url: str


def fetch(keyword: str | None = None, max_results: int | None = None) -> list[NewsItem]:
    limit = max_results or settings.geeknews_max_results
    try:
        response = httpx.get(
            settings.geeknews_rss_url,
            timeout=30.0,
            follow_redirects=True,
        )
        response.raise_for_status()
    except Exception:
        return []

    try:
        root = ElementTree.fromstring(response.text)
    except ElementTree.ParseError:
        return []

    items: list[NewsItem] = []
    entries = root.findall(".//item")
    for entry in entries:
        title = (entry.findtext("title") or "").strip()
        summary = _strip_html(entry.findtext("description") or "").strip()
        url = (entry.findtext("link") or "").strip()

        if keyword:
            haystack = f"{title} {summary}".lower()
            if keyword.lower() not in haystack:
                continue

        items.append(NewsItem(title=title, summary=summary, url=url))
        if len(items) >= limit:
            break

    if keyword and not items:
        for entry in entries[:limit]:
            items.append(
                NewsItem(
                    title=(entry.findtext("title") or "").strip(),
                    summary=_strip_html(entry.findtext("description") or "").strip(),
                    url=(entry.findtext("link") or "").strip(),
                )
            )

    return items


def _strip_html(text: str) -> str:
    text = unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()
