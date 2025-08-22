from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    BASE_PATH: Path = Path(__file__).resolve().parent.parent
    LOGS_PATH: Path = BASE_PATH / "logs"
    APP_PATH: Path = BASE_PATH / "app"
    TEMPLATES_PATH: Path = APP_PATH / "templates"

    admin_username: str
    admin_password: str

    openai_api_key: str
    price_per_1k_prompt: float
    price_per_1k_completion: float

    telegram_bot_token: str
    error_notification_channel_id: str

    database_url: str = "sqlite:///./summaries.db"

    MAX_REQUEST_COST: float = 1.0

    USER_REQUEST_LIMIT_PER_HOUR: int = 3
    THREAD_REQUEST_COOLDOWN_HOURS: int = 6
    REQUEST_TIMEOUT_SECONDS: int = 30
    OPENAI_TIMEOUT_SECONDS: int = 180

    model_config = SettingsConfigDict(env_file=Path.joinpath(BASE_PATH, ".env"))
