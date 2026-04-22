import re
import sqlite3
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr, Field

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
    created_at: datetime


class TestRequest(BaseModel):
    email: str | None = None


def _validate_email(email: str) -> str:
    email = email.strip()
    if not _EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="invalid email format")
    return email


def _row_to_out(row) -> RecipientOut:
    return RecipientOut(
        id=row["id"],
        email=row["email"],
        enabled=bool(row["enabled"]),
        created_at=row["created_at"],
    )


@router.get("", response_model=list[RecipientOut])
def list_recipients():
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, email, enabled, created_at FROM recipient ORDER BY id ASC"
        ).fetchall()
    return [_row_to_out(r) for r in rows]


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
        row = conn.execute(
            "SELECT id, email, enabled, created_at FROM recipient WHERE id = ?", (rid,)
        ).fetchone()
    return _row_to_out(row)


@router.delete("/{rid}", status_code=204)
def delete_recipient(rid: int):
    with connect() as conn:
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
