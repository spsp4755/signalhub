from fastapi import APIRouter

from .. import settings_store
from ..database import connect


router = APIRouter(tags=["stats"])


@router.get("/stats")
def get_stats():
    with connect() as conn:
        total_keywords = conn.execute("SELECT COUNT(*) FROM keyword").fetchone()[0]
        enabled_keywords = conn.execute(
            "SELECT COUNT(*) FROM keyword WHERE enabled = 1"
        ).fetchone()[0]
        total_analyses = conn.execute("SELECT COUNT(*) FROM analysis").fetchone()[0]
        auto_count = conn.execute(
            "SELECT COUNT(*) FROM analysis WHERE run_type = 'auto'"
        ).fetchone()[0]
        manual_count = conn.execute(
            "SELECT COUNT(*) FROM analysis WHERE run_type = 'manual'"
        ).fetchone()[0]
        last = conn.execute(
            "SELECT keyword, run_type, created_at FROM analysis ORDER BY id DESC LIMIT 1"
        ).fetchone()
        per_keyword = conn.execute(
            """
            SELECT k.name AS keyword, COUNT(a.id) AS cnt,
                   MAX(a.created_at) AS last_run
            FROM keyword k
            LEFT JOIN analysis a ON a.keyword = k.name
            GROUP BY k.name
            ORDER BY cnt DESC, k.name ASC
            """
        ).fetchall()

    cfg = settings_store.get_all()

    return {
        "total_keywords": total_keywords,
        "enabled_keywords": enabled_keywords,
        "total_analyses": total_analyses,
        "auto_count": auto_count,
        "manual_count": manual_count,
        "last_analysis": (
            {
                "keyword": last["keyword"],
                "run_type": last["run_type"],
                "created_at": last["created_at"],
            }
            if last
            else None
        ),
        "per_keyword": [
            {
                "keyword": r["keyword"],
                "count": r["cnt"],
                "last_run": r["last_run"],
            }
            for r in per_keyword
        ],
        "schedule": {
            "hour": cfg["auto_run_hour"],
            "minute": cfg["auto_run_minute"],
        },
        "model": cfg["vllm_model"],
        "base_url": cfg["vllm_base_url"],
    }
