import json
from collections import Counter, defaultdict

from fastapi import APIRouter, Query

from ..database import connect


router = APIRouter(tags=["insights"])


def _day(ts) -> str:
    if ts is None:
        return ""
    s = str(ts)
    return s[:10]


@router.get("/insights")
def get_insights(limit: int = Query(500, ge=10, le=5000)):
    with connect() as conn:
        rows = conn.execute(
            """SELECT keyword, run_type, tags, created_at
               FROM analysis
               ORDER BY id DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()

    tag_count: Counter[str] = Counter()
    tag_by_keyword: dict[str, Counter[str]] = defaultdict(Counter)
    tag_pair: Counter[tuple[str, str]] = Counter()

    by_day_all: Counter[str] = Counter()
    by_day_auto: Counter[str] = Counter()
    by_day_manual: Counter[str] = Counter()

    for row in rows:
        day = _day(row["created_at"])
        if day:
            by_day_all[day] += 1
            if row["run_type"] == "auto":
                by_day_auto[day] += 1
            elif row["run_type"] == "manual":
                by_day_manual[day] += 1

        tags: list[str] = []
        if row["tags"]:
            try:
                parsed = json.loads(row["tags"])
                if isinstance(parsed, list):
                    tags = [str(t).strip() for t in parsed if str(t).strip()]
            except Exception:
                tags = []

        for t in tags:
            tag_count[t] += 1
            tag_by_keyword[row["keyword"]][t] += 1
        for i in range(len(tags)):
            for j in range(i + 1, len(tags)):
                a, b = sorted([tags[i], tags[j]])
                tag_pair[(a, b)] += 1

    days = sorted(by_day_all.keys())
    timeline = [
        {
            "date": d,
            "total": by_day_all[d],
            "auto": by_day_auto[d],
            "manual": by_day_manual[d],
        }
        for d in days
    ]

    top_tags = [
        {"tag": t, "count": c}
        for t, c in tag_count.most_common(60)
    ]

    network_nodes = []
    seen_nodes = set()
    for kw, counts in tag_by_keyword.items():
        nid = f"kw::{kw}"
        if nid not in seen_nodes:
            network_nodes.append({
                "id": nid,
                "label": kw,
                "group": "keyword",
                "value": sum(counts.values()),
            })
            seen_nodes.add(nid)
    for tag, c in tag_count.items():
        nid = f"tag::{tag}"
        if nid not in seen_nodes:
            network_nodes.append({
                "id": nid,
                "label": tag,
                "group": "tag",
                "value": c,
            })
            seen_nodes.add(nid)

    network_edges = []
    for kw, counts in tag_by_keyword.items():
        for tag, c in counts.items():
            network_edges.append({
                "from": f"kw::{kw}",
                "to": f"tag::{tag}",
                "value": c,
            })

    top_pairs = [
        {"a": a, "b": b, "count": c}
        for (a, b), c in tag_pair.most_common(30)
    ]

    return {
        "sample_size": len(rows),
        "timeline": timeline,
        "top_tags": top_tags,
        "network": {"nodes": network_nodes, "edges": network_edges},
        "top_pairs": top_pairs,
    }
