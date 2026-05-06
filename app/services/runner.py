import json
import logging

from ..collectors import aitimes_collector, arxiv_collector, geeknews_collector, huggingface_collector
from ..database import connect
from .. import settings_store
from . import analyzer, mailer


logger = logging.getLogger(__name__)


def collect_and_analyze(
    keyword: str,
    run_type: str = "manual",
    *,
    keyword_id: int | None = None,
    send_email: bool = True,
) -> dict:
    cfg = settings_store.get_all()
    papers = arxiv_collector.fetch(keyword, max_results=int(cfg["arxiv_max_results"]))
    hf_papers = huggingface_collector.fetch_papers(
        keyword, max_results=int(cfg["huggingface_max_results"])
    )
    hf_models = huggingface_collector.fetch_models(
        keyword, max_results=int(cfg["huggingface_max_results"])
    )
    news = geeknews_collector.fetch(keyword, max_results=int(cfg["geeknews_max_results"]))
    aitimes_news = aitimes_collector.fetch(keyword, max_results=int(cfg["aitimes_max_results"]))

    all_papers = papers + hf_papers + hf_models
    all_news = news + aitimes_news

    result, tags = analyzer.analyze(all_papers, all_news)

    sources = {
        "arxiv": [
            {"title": p.title, "url": p.url, "authors": p.authors} for p in papers
        ],
        "huggingface_papers": [
            {"title": p.title, "url": p.url, "authors": p.authors} for p in hf_papers
        ],
        "huggingface_models": [
            {"title": p.title, "url": p.url, "authors": p.authors} for p in hf_models
        ],
        "geeknews": [{"title": n.title, "url": n.url} for n in news],
        "aitimes": [{"title": n.title, "url": n.url} for n in aitimes_news],
    }

    with connect() as conn:
        cur = conn.execute(
            """INSERT INTO analysis (keyword, result, run_type, sources, tags)
               VALUES (?, ?, ?, ?, ?)""",
            (
                keyword,
                result,
                run_type,
                json.dumps(sources, ensure_ascii=False),
                json.dumps(tags, ensure_ascii=False),
            ),
        )
        conn.commit()
        analysis_id = cur.lastrowid

    outcome = {
        "id": analysis_id,
        "keyword_id": keyword_id,
        "keyword": keyword,
        "run_type": run_type,
        "result": result,
        "tags": tags,
        "sources": sources,
        "arxiv": len(papers),
        "huggingface": len(hf_papers) + len(hf_models),
        "geeknews": len(news),
        "aitimes": len(aitimes_news),
    }

    if send_email:
        try:
            mailer.send_async(outcome)
        except Exception:
            logger.exception("mailer dispatch failed")

    return outcome


def cleanup_old_analyses(retention_days: int) -> int:
    if retention_days is None or retention_days <= 0:
        return 0
    with connect() as conn:
        cur = conn.execute(
            "DELETE FROM analysis WHERE created_at < datetime('now', ?)",
            (f"-{int(retention_days)} days",),
        )
        conn.commit()
    removed = cur.rowcount or 0
    if removed:
        logger.info("retention cleanup removed %d analyses (older than %d days)",
                    removed, retention_days)
    return removed


def run_auto_jobs() -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, name FROM keyword WHERE enabled = 1 ORDER BY name ASC"
        ).fetchall()

    outcomes: list[dict] = []
    for row in rows:
        keyword_id = row["id"]
        keyword = row["name"]
        try:
            outcome = collect_and_analyze(
                keyword,
                run_type="auto",
                keyword_id=keyword_id,
                send_email=False,
            )
            outcomes.append(
                {
                    "keyword_id": keyword_id,
                    "keyword": keyword,
                    "ok": True,
                    "id": outcome["id"],
                    "outcome": outcome,
                }
            )
        except Exception as exc:
            logger.exception("auto job failed for keyword=%s", keyword)
            outcomes.append(
                {
                    "keyword_id": keyword_id,
                    "keyword": keyword,
                    "ok": False,
                    "error": str(exc),
                }
            )
    try:
        mailer.send_digest_async(outcomes)
    except Exception:
        logger.exception("digest mailer dispatch failed")
    return outcomes
