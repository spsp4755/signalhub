from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import scheduler, settings_store


router = APIRouter(tags=["settings"])


class SettingsUpdate(BaseModel):
    vllm_base_url: str | None = None
    vllm_api_key: str | None = None
    vllm_model: str | None = None
    llm_max_tokens: int | None = None
    llm_temperature: float | None = None
    auto_run_hour: int | None = None
    auto_run_minute: int | None = None
    arxiv_max_results: int | None = None
    geeknews_max_results: int | None = None
    geeknews_rss_url: str | None = None
    huggingface_max_results: int | None = None
    aitimes_max_results: int | None = None
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_sender: str | None = None
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_use_tls: bool | None = None
    smtp_subject_prefix: str | None = None
    retention_days: int | None = None


@router.get("/settings")
def get_settings():
    return {
        "values": settings_store.get_all_public(),
        "editable": list(settings_store.EDITABLE_KEYS.keys()),
        "secret_keys": list(settings_store.SECRET_KEYS),
    }


@router.put("/settings")
def put_settings(payload: SettingsUpdate):
    updates = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    if payload.vllm_api_key == "••••••":
        updates.pop("vllm_api_key", None)
    if payload.smtp_password == "••••••":
        updates.pop("smtp_password", None)
    try:
        new_values = settings_store.update(updates)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if any(k in updates for k in ("auto_run_hour", "auto_run_minute")):
        try:
            scheduler.reschedule()
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"reschedule failed: {exc}")

    masked = settings_store.get_all_public()
    return {"values": masked, "updated_keys": list(updates.keys()), "raw": new_values and True}


@router.post("/settings/reset")
def reset_settings():
    settings_store.reset()
    scheduler.reschedule()
    return {"values": settings_store.get_all_public()}
