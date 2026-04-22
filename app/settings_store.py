from typing import Any

from .config import settings as defaults
from .database import connect


EDITABLE_KEYS: dict[str, type] = {
    "vllm_base_url": str,
    "vllm_api_key": str,
    "vllm_model": str,
    "llm_max_tokens": int,
    "llm_temperature": float,
    "auto_run_hour": int,
    "auto_run_minute": int,
    "arxiv_max_results": int,
    "geeknews_max_results": int,
    "geeknews_rss_url": str,
    "huggingface_max_results": int,
    "aitimes_max_results": int,
    "smtp_host": str,
    "smtp_port": int,
    "smtp_sender": str,
    "smtp_username": str,
    "smtp_password": str,
    "smtp_use_tls": bool,
    "smtp_subject_prefix": str,
    "retention_days": int,
}


SECRET_KEYS = {"vllm_api_key", "smtp_password"}


def _coerce(value: str, target: type) -> Any:
    if target is int:
        return int(value)
    if target is float:
        return float(value)
    if target is bool:
        return value.lower() in ("1", "true", "yes", "on")
    return value


def _read_overrides() -> dict[str, str]:
    with connect() as conn:
        rows = conn.execute("SELECT key, value FROM setting").fetchall()
    return {r["key"]: r["value"] for r in rows}


def get(key: str) -> Any:
    if key not in EDITABLE_KEYS:
        return getattr(defaults, key)
    overrides = _read_overrides()
    if key in overrides:
        try:
            return _coerce(overrides[key], EDITABLE_KEYS[key])
        except Exception:
            pass
    return getattr(defaults, key)


def get_all() -> dict[str, Any]:
    overrides = _read_overrides()
    out: dict[str, Any] = {}
    for k, t in EDITABLE_KEYS.items():
        if k in overrides:
            try:
                out[k] = _coerce(overrides[k], t)
                continue
            except Exception:
                pass
        out[k] = getattr(defaults, k)
    return out


def get_all_public() -> dict[str, Any]:
    """Same as get_all but masks secrets."""
    data = get_all()
    for k in SECRET_KEYS:
        if data.get(k):
            data[k] = "••••••"
    return data


def update(updates: dict[str, Any]) -> dict[str, Any]:
    with connect() as conn:
        for raw_key, raw_val in updates.items():
            if raw_key not in EDITABLE_KEYS:
                continue
            if raw_val is None or raw_val == "":
                conn.execute("DELETE FROM setting WHERE key = ?", (raw_key,))
                continue
            try:
                _coerce(str(raw_val), EDITABLE_KEYS[raw_key])
            except Exception as exc:
                raise ValueError(f"invalid value for {raw_key}: {exc}")
            conn.execute(
                """INSERT INTO setting (key, value) VALUES (?, ?)
                   ON CONFLICT(key) DO UPDATE SET
                     value = excluded.value,
                     updated_at = CURRENT_TIMESTAMP""",
                (raw_key, str(raw_val)),
            )
        conn.commit()
    return get_all()


def reset(keys: list[str] | None = None) -> dict[str, Any]:
    with connect() as conn:
        if keys is None:
            conn.execute("DELETE FROM setting")
        else:
            for k in keys:
                if k in EDITABLE_KEYS:
                    conn.execute("DELETE FROM setting WHERE key = ?", (k,))
        conn.commit()
    return get_all()
