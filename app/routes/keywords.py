import re
import sqlite3

from fastapi import APIRouter, HTTPException, status

from ..database import connect
from ..schemas import KeywordBulkCreate, KeywordBulkOut, KeywordCreate, KeywordOut, KeywordUpdate


router = APIRouter(prefix="/keywords", tags=["keywords"])


def _row_to_out(row) -> KeywordOut:
    return KeywordOut(
        id=row["id"],
        name=row["name"],
        enabled=bool(row["enabled"]),
        created_at=row["created_at"],
    )


def _normalize_keyword(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _split_keywords(payload: KeywordBulkCreate) -> tuple[list[str], list[str]]:
    raw: list[str] = []
    if payload.text:
        raw.extend(re.split(r"[\n,;]+", payload.text))
    raw.extend(payload.names)

    names: list[str] = []
    invalid: list[str] = []
    seen: set[str] = set()
    for item in raw:
        name = _normalize_keyword(str(item))
        if not name:
            continue
        if len(name) > 100:
            invalid.append(name)
            continue
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        names.append(name)
    return names, invalid


@router.get("", response_model=list[KeywordOut])
def list_keywords():
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, name, enabled, created_at FROM keyword ORDER BY id DESC"
        ).fetchall()
    return [_row_to_out(r) for r in rows]


@router.post("", response_model=KeywordOut, status_code=status.HTTP_201_CREATED)
def create_keyword(payload: KeywordCreate):
    name = _normalize_keyword(payload.name)
    if not name:
        raise HTTPException(status_code=400, detail="keyword is empty")
    with connect() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO keyword (name, enabled) VALUES (?, ?)",
                (name, 1 if payload.enabled else 0),
            )
            conn.commit()
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=409, detail=f"keyword exists: {exc}")
        row = conn.execute(
            "SELECT id, name, enabled, created_at FROM keyword WHERE id = ?",
            (cur.lastrowid,),
        ).fetchone()
    return _row_to_out(row)


@router.post("/bulk", response_model=KeywordBulkOut, status_code=status.HTTP_201_CREATED)
def create_keywords_bulk(payload: KeywordBulkCreate):
    names, invalid = _split_keywords(payload)
    if not names and not invalid:
        raise HTTPException(status_code=400, detail="no keywords provided")

    created_rows = []
    existing: list[str] = []
    with connect() as conn:
        for name in names:
            try:
                cur = conn.execute(
                    "INSERT INTO keyword (name, enabled) VALUES (?, ?)",
                    (name, 1 if payload.enabled else 0),
                )
                row = conn.execute(
                    "SELECT id, name, enabled, created_at FROM keyword WHERE id = ?",
                    (cur.lastrowid,),
                ).fetchone()
                created_rows.append(row)
            except sqlite3.IntegrityError:
                existing.append(name)
        conn.commit()

    return KeywordBulkOut(
        created=[_row_to_out(row) for row in created_rows],
        existing=existing,
        invalid=invalid,
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
    return _row_to_out(row)


@router.delete("/{keyword_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_keyword(keyword_id: int):
    with connect() as conn:
        conn.execute("DELETE FROM recipient_keyword WHERE keyword_id = ?", (keyword_id,))
        cur = conn.execute("DELETE FROM keyword WHERE id = ?", (keyword_id,))
        conn.commit()
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="keyword not found")
