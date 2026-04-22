import logging

import httpx

from .arxiv_collector import Paper


logger = logging.getLogger(__name__)


def fetch_papers(keyword: str, max_results: int | None = None) -> list[Paper]:
    """Collect papers from HuggingFace."""
    if max_results is None:
        from ..config import settings

        max_results = settings.huggingface_max_results

    results: list[Paper] = []
    try:
        resp = httpx.get(
            "https://huggingface.co/api/papers",
            params={"search": keyword, "limit": max_results},
            timeout=30.0,
            follow_redirects=True,
        )
        resp.raise_for_status()
        for item in resp.json():
            title = (item.get("title") or "").strip()
            summary = (item.get("summary") or "").strip()
            url = (item.get("url") or item.get("paper_url") or "").strip()
            authors = [a.get("title", "") for a in item.get("authors", [])]
            if not url:
                slug = item.get("id", "")
                url = f"https://huggingface.co/papers/{slug}"
            if title or summary:
                results.append(Paper(title=title, summary=summary, url=url, authors=authors))
    except Exception:
        logger.exception("huggingface papers fetch failed")
    return results


def fetch_models(keyword: str, max_results: int | None = None) -> list[Paper]:
    """Collect models from HuggingFace."""
    if max_results is None:
        from ..config import settings

        max_results = settings.huggingface_max_results

    results: list[Paper] = []
    try:
        resp = httpx.get(
            "https://huggingface.co/api/models",
            params={"search": keyword, "limit": max_results},
            timeout=30.0,
            follow_redirects=True,
        )
        resp.raise_for_status()
        for item in resp.json():
            title = (item.get("modelId") or item.get("id") or "").strip()
            desc = item.get("description") or item.get("tags", [])
            if isinstance(desc, list):
                desc = ", ".join(desc[:5])
            summary = (desc or "").strip()[:500]
            slug = item.get("modelId") or item.get("id", "")
            url = f"https://huggingface.co/{slug}"
            if title:
                results.append(Paper(title=title, summary=summary, url=url, authors=[]))
    except Exception:
        logger.exception("huggingface models fetch failed")
    return results
