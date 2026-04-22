from fastapi import APIRouter, HTTPException, status

from ..database import connect
from ..schemas import KeywordCreate, KeywordOut, KeywordUpdate


router = APIRouter(prefix="/keywords", tags=["keywords"])


@router.get("", response_model=list[KeywordOut])
def list_keywords():
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, name, enabled, created_at FROM keyword ORDER BY id DESC"
        ).fetchall()
    return [
        KeywordOut(
            id=r["id"],
            name=r["name"],
            enabled=bool(r["enabled"]),
            created_at=r["created_at"],
        )
        for r in rows
    ]


@router.post("", response_model=KeywordOut, status_code=status.HTTP_201_CREATED)
def create_keyword(payload: KeywordCreate):
    with connect() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO keyword (name, enabled) VALUES (?, ?)",
                (payload.name, 1 if payload.enabled else 0),
            )
            conn.commit()
        except Exception as exc:
            raise HTTPException(status_code=409, detail=f"keyword exists: {exc}")
        row = conn.execute(
            "SELECT id, name, enabled, created_at FROM keyword WHERE id = ?",
            (cur.lastrowid,),
        ).fetchone()
    return KeywordOut(
        id=row["id"],
        name=row["name"],
        enabled=bool(row["enabled"]),
        created_at=row["created_at"],
    )


@router.patch("/{keyword_id}", response_model=KeywordOut)
def update_keyword(keyword_id: int, payload: KeywordUpdate):
    with connect() as conn:
        conn.execute(
            "UPDATE keyword SET enabled = ? WHERE id = ?",
            (1 if payload.enabled else 0, keyword_id),
        )
        conn.commit()
        row = conn.execute(
            "SELECT id, name, enabled, created_at FROM keyword WHERE id = ?",
            (keyword_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="keyword not found")
    return KeywordOut(
        id=row["id"],
        name=row["name"],
        enabled=bool(row["enabled"]),
        created_at=row["created_at"],
    )


@router.delete("/{keyword_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_keyword(keyword_id: int):
    with connect() as conn:
        cur = conn.execute("DELETE FROM keyword WHERE id = ?", (keyword_id,))
        conn.commit()
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="keyword not found")
