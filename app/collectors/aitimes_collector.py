from dataclasses import dataclass

from bs4 import BeautifulSoup
import httpx

from ..config import settings


@dataclass
class NewsItem:
    title: str
    summary: str
    url: str


def fetch(keyword: str | None = None, max_results: int | None = None) -> list[NewsItem]:
    limit = max_results or settings.aitimes_max_results
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64; rv:109.0) "
            "Gecko/20100101 Firefox/115.0"
        ),
    }
    try:
        resp = httpx.get(
            "https://www.aitimes.com/",
            headers=headers,
            timeout=15.0,
            follow_redirects=True,
        )
        resp.raise_for_status()
    except Exception:
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    items: list[NewsItem] = []

    for div in soup.find_all("div", class_="auto-article"):
        link = div.find("a", href=True)
        if not link:
            continue
        url = link["href"]
        if not url.startswith("http"):
            url = "https://www.aitimes.com" + url
        text = div.get_text(separator=" ", strip=True)
        title = (link.get_text(strip=True) or "").strip()
        summary = text[:500]

        if keyword and keyword.lower() not in f"{title} {summary}".lower():
            continue

        items.append(NewsItem(title=title, summary=summary, url=url))
        if len(items) >= limit:
            break

    return items
