from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    BASE_PATH: Path = Path(__file__).resolve().parent.parent
    LOGS_PATH: Path = BASE_PATH / "logs"
    APP_PATH: Path = BASE_PATH / "app"
    TEMPLATES_PATH: Path = APP_PATH / "templates"

    # Security
    admin_username: str
    admin_password: str
    secret_key: str

    # OpenAI
    openai_api_key: str
    max_request_cost: float = 1.0
    price_per_1k_prompt: float = 0.002
    price_per_1k_completion: float = 0.008

    # Telegram
    telegram_bot_token: str
    error_notification_channel_id: str = ""

    # Database
    database_url: str

    # Rate Limits
    user_request_limit_per_hour: int = 3
    thread_request_cooldown_hours: int = 6

    # Timeouts
    request_timeout_seconds: int = 30
    openai_timeout_seconds: int = 180

    model_config = SettingsConfigDict(env_file=BASE_PATH / ".env")
