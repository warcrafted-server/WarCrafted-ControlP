from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"


class Settings(BaseSettings):
    app_name: str = "WarCrafted-ControlP"
    app_env: str = "production"
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    secret_key: str = "CHANGE_ME"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 120
    cookie_secure: bool = False

    app_db_url: str = "sqlite:///./data/app.db"

    github_plugin_token: str = ""
    github_plugin_repo: str = "tortosi/WarCraftedCP-plugins"
    github_core_repo: str = "tortosi/WarCrafted-ControlP"

    instances_logs_dir: str = "./logs/instances"
    logs_retention_days: int = 7
    logs_max_runs: int = 15

    shutdown_stuck_timeout: int = 180

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    DATA_DIR.mkdir(exist_ok=True)
    return Settings()
