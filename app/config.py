from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    vllm_base_url: str = "http://localhost:11434/v1"
    vllm_api_key: str = "ollama"
    vllm_model: str = "gemma4:e2b"

    db_path: str = "./data/analysis.db"

    auto_run_hour: int = 9
    auto_run_minute: int = 0

    arxiv_max_results: int = 3
    geeknews_max_results: int = 3
    geeknews_rss_url: str = "https://news.hada.io/rss/news"
    huggingface_max_results: int = 3
    aitimes_max_results: int = 3

    llm_max_tokens: int = 4096
    llm_temperature: float = 0.2

    default_keywords: list[str] = ["AI", "Agents", "에이전트"]

    # SMTP defaults — plain, no-auth SMTP by default (must be explicit)
    smtp_host: str = ""
    smtp_port: int = 25
    smtp_sender: str = "signalhub@localhost"
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = False
    smtp_subject_prefix: str = "[SignalHub]"

    # Retention: delete analyses older than N days (0 = unlimited)
    retention_days: int = 0


settings = Settings()
