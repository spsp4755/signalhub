import json

from fastapi import APIRouter, HTTPException, Query

from ..database import connect
from ..schemas import AnalysisOut, AnalysisPage, RunRequest
from ..services.runner import collect_and_analyze, run_auto_jobs


router = APIRouter(tags=["analysis"])


def _row_to_out(row) -> AnalysisOut:
    sources = None
    if row["sources"]:
        try:
            sources = json.loads(row["sources"])
        except Exception:
            sources = None
    tags: list[str] = []
    if row["tags"]:
        try:
            parsed = json.loads(row["tags"])
            if isinstance(parsed, list):
                tags = [str(x) for x in parsed]
        except Exception:
            tags = []
    return AnalysisOut(
        id=row["id"],
        keyword=row["keyword"],
        result=row["result"],
        run_type=row["run_type"],
        sources=sources,
        tags=tags,
        created_at=row["created_at"],
    )


COLS = "id, keyword, result, run_type, sources, tags, created_at"


@router.get("/results", response_model=AnalysisPage)
def list_results(
    limit: int = Query(20, ge=1, le=200),
    before_id: int | None = Query(None, ge=1),
    keyword: str | None = None,
    run_type: str | None = None,
):
    conds: list[str] = []
    params: list = []
    if keyword:
        conds.append("keyword = ?")
        params.append(keyword)
    if run_type:
        conds.append("run_type = ?")
        params.append(run_type)

    where_base = (" WHERE " + " AND ".join(conds)) if conds else ""

    with connect() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM analysis{where_base}", params
        ).fetchone()[0]

        page_params = list(params)
        cursor_where = where_base
        if before_id is not None:
            cursor_where = (
                cursor_where + " AND id < ?" if cursor_where else " WHERE id < ?"
            )
            page_params.append(before_id)

        page_params.append(limit + 1)
        rows = conn.execute(
            f"SELECT {COLS} FROM analysis{cursor_where} ORDER BY id DESC LIMIT ?",
            page_params,
        ).fetchall()

    has_more = len(rows) > limit
    page_rows = rows[:limit]
    next_before_id = page_rows[-1]["id"] if has_more and page_rows else None

    return AnalysisPage(
        items=[_row_to_out(r) for r in page_rows],
        total=total,
        has_more=has_more,
        next_before_id=next_before_id,
    )


@router.get("/results/{analysis_id}", response_model=AnalysisOut)
def get_result(analysis_id: int):
    with connect() as conn:
        row = conn.execute(
            f"SELECT {COLS} FROM analysis WHERE id = ?", (analysis_id,)
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="analysis not found")
    return _row_to_out(row)


@router.post("/run")
def run_now(payload: RunRequest):
    try:
        outcome = collect_and_analyze(payload.keyword, run_type="manual")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"run failed: {exc}")
    return outcome


@router.post("/run-all")
def run_all():
    return {"outcomes": run_auto_jobs()}
