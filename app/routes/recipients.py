import re
import sqlite3
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..database import connect
from ..services import mailer


router = APIRouter(prefix="/recipients", tags=["recipients"])


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class RecipientIn(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    enabled: bool = True


class RecipientPatch(BaseModel):
    email: str | None = Field(default=None, min_length=3, max_length=200)
    enabled: bool | None = None


class RecipientOut(BaseModel):
    id: int
    email: str
    enabled: bool
    keyword_ids: list[int] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    created_at: datetime


class RecipientKeywordsPatch(BaseModel):
    keyword_ids: list[int] = Field(default_factory=list)


class TestRequest(BaseModel):
    email: str | None = None


def _validate_email(email: str) -> str:
    email = email.strip()
    if not _EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="invalid email format")
    return email


def _keyword_map(conn) -> dict[int, list[tuple[int, str]]]:
    rows = conn.execute(
        """
        SELECT rk.recipient_id, k.id AS keyword_id, k.name
        FROM recipient_keyword rk
        JOIN keyword k ON k.id = rk.keyword_id
        ORDER BY k.name ASC
        """
    ).fetchall()
    out: dict[int, list[tuple[int, str]]] = {}
    for row in rows:
        out.setdefault(row["recipient_id"], []).append((row["keyword_id"], row["name"]))
    return out


def _row_to_out(row, keywords: list[tuple[int, str]] | None = None) -> RecipientOut:
    keywords = keywords or []
    return RecipientOut(
        id=row["id"],
        email=row["email"],
        enabled=bool(row["enabled"]),
        keyword_ids=[kid for kid, _ in keywords],
        keywords=[name for _, name in keywords],
        created_at=row["created_at"],
    )


def _get_recipient(conn, rid: int) -> RecipientOut | None:
    row = conn.execute(
        "SELECT id, email, enabled, created_at FROM recipient WHERE id = ?", (rid,)
    ).fetchone()
    if row is None:
        return None
    keyword_rows = conn.execute(
        """
        SELECT k.id, k.name
        FROM recipient_keyword rk
        JOIN keyword k ON k.id = rk.keyword_id
        WHERE rk.recipient_id = ?
        ORDER BY k.name ASC
        """,
        (rid,),
    ).fetchall()
    return _row_to_out(row, [(r["id"], r["name"]) for r in keyword_rows])


@router.get("", response_model=list[RecipientOut])
def list_recipients():
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, email, enabled, created_at FROM recipient ORDER BY id ASC"
        ).fetchall()
        kw_map = _keyword_map(conn)
    return [_row_to_out(r, kw_map.get(r["id"], [])) for r in rows]


@router.post("", response_model=RecipientOut, status_code=201)
def create_recipient(payload: RecipientIn):
    email = _validate_email(payload.email)
    with connect() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO recipient (email, enabled) VALUES (?, ?)",
                (email, 1 if payload.enabled else 0),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail="email already exists")
        row = conn.execute(
            "SELECT id, email, enabled, created_at FROM recipient WHERE id = ?",
            (cur.lastrowid,),
        ).fetchone()
    return _row_to_out(row)


@router.patch("/{rid}", response_model=RecipientOut)
def update_recipient(rid: int, payload: RecipientPatch):
    fields: list[str] = []
    params: list = []
    if payload.email is not None:
        fields.append("email = ?")
        params.append(_validate_email(payload.email))
    if payload.enabled is not None:
        fields.append("enabled = ?")
        params.append(1 if payload.enabled else 0)
    if not fields:
        raise HTTPException(status_code=400, detail="no fields to update")

    params.append(rid)
    with connect() as conn:
        try:
            cur = conn.execute(
                f"UPDATE recipient SET {', '.join(fields)} WHERE id = ?", params
            )
            conn.commit()
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail="email already exists")
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="recipient not found")
        out = _get_recipient(conn, rid)
    return out


@router.patch("/{rid}/keywords", response_model=RecipientOut)
def update_recipient_keywords(rid: int, payload: RecipientKeywordsPatch):
    requested_ids = list(dict.fromkeys(int(kid) for kid in payload.keyword_ids))
    with connect() as conn:
        if conn.execute("SELECT 1 FROM recipient WHERE id = ?", (rid,)).fetchone() is None:
            raise HTTPException(status_code=404, detail="recipient not found")
        if requested_ids:
            placeholders = ",".join("?" for _ in requested_ids)
            rows = conn.execute(
                f"SELECT id FROM keyword WHERE id IN ({placeholders})", requested_ids
            ).fetchall()
            found = {row["id"] for row in rows}
            missing = [kid for kid in requested_ids if kid not in found]
            if missing:
                raise HTTPException(
                    status_code=400,
                    detail=f"unknown keyword ids: {', '.join(map(str, missing))}",
                )
        conn.execute("DELETE FROM recipient_keyword WHERE recipient_id = ?", (rid,))
        conn.executemany(
            "INSERT INTO recipient_keyword (recipient_id, keyword_id) VALUES (?, ?)",
            [(rid, kid) for kid in requested_ids],
        )
        conn.commit()
        out = _get_recipient(conn, rid)
    return out


@router.delete("/{rid}", status_code=204)
def delete_recipient(rid: int):
    with connect() as conn:
        conn.execute("DELETE FROM recipient_keyword WHERE recipient_id = ?", (rid,))
        cur = conn.execute("DELETE FROM recipient WHERE id = ?", (rid,))
        conn.commit()
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="recipient not found")
    return None


@router.post("/test")
def send_test(payload: TestRequest):
    result = mailer.send_test(payload.email)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "send failed"))
    return result
