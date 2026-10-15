from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_DIR / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "ShipCode SellerPilot"
    database_url: str = "sqlite:///./data/sellerpilot.db"
    shop_database_path: Path = REPO_DIR / "UTE MALL" / "instance" / "ecommerce.db"
    shop_static_dir: Path = REPO_DIR / "UTE MALL" / "static"
    shop_product_upload_dir: Path = REPO_DIR / "UTE MALL" / "static" / "uploads" / "sellerpilot"
    seller_shop_slug: str = "utech-official"
    shop_timezone: str = "Asia/Ho_Chi_Minh"
    demo_mode: bool = True
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    ai_provider: Literal["ollama", "opencode"] = "ollama"
    # This demo deliberately has no paid-model fallback.
    opencode_model: Literal["muse-spark-1.3-contributor-free"] = "muse-spark-1.3-contributor-free"
    opencode_binary: str = "opencode"
    opencode_generation_timeout_seconds: float = Field(default=90, gt=0, le=120)
    ollama_host: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3:4b-instruct"
    ollama_health_timeout_seconds: float = Field(default=2, gt=0, le=10)
    ollama_generation_timeout_seconds: float = Field(default=180, gt=0, le=300)
    ollama_context_length: int = Field(default=4_096, ge=512, le=32_768)
    ollama_max_output_tokens: int = Field(default=256, ge=32, le=1_024)
    ollama_keep_alive: str = "30m"
