from dataclasses import dataclass
from xml.etree import ElementTree

import httpx

from ..config import settings


@dataclass
class Paper:
    title: str
    summary: str
    url: str
    authors: list[str]


def fetch(keyword: str, max_results: int | None = None) -> list[Paper]:
    limit = max_results or settings.arxiv_max_results
    papers: list[Paper] = []
    params = {
        "search_query": f"all:{keyword}",
        "start": 0,
        "max_results": limit,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }
    try:
        response = httpx.get(
            "https://export.arxiv.org/api/query",
            params=params,
            timeout=30.0,
            follow_redirects=True,
        )
        response.raise_for_status()
    except Exception:
        return papers

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    try:
        root = ElementTree.fromstring(response.text)
    except ElementTree.ParseError:
        return papers

    for entry in root.findall("atom:entry", ns):
        title = (entry.findtext("atom:title", default="", namespaces=ns) or "").strip()
        summary = (entry.findtext("atom:summary", default="", namespaces=ns) or "").strip()
        url = (entry.findtext("atom:id", default="", namespaces=ns) or "").strip()
        authors = [
            (author.findtext("atom:name", default="", namespaces=ns) or "").strip()
            for author in entry.findall("atom:author", ns)
        ]
        if title or summary:
            papers.append(
                Paper(
                    title=title,
                    summary=summary,
                    url=url,
                    authors=[name for name in authors if name],
                )
            )
    return papers
