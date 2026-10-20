from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
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
    browser_connector_token: SecretStr = SecretStr('')
    database_url: str = "sqlite:///./data/sellerpilot.db"
    shop_database_path: Path = REPO_DIR / "UTE MALL" / "instance" / "ecommerce.db"
    shop_static_dir: Path = REPO_DIR / "UTE MALL" / "static"
    shop_product_upload_dir: Path = REPO_DIR / "UTE MALL" / "static" / "uploads" / "sellerpilot"
    seller_shop_slug: str = "utech-official"
    shop_timezone: str = "Asia/Ho_Chi_Minh"
    demo_mode: bool = True
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    ai_provider: Literal["ollama", "opencode", "antigravity", "gemini"] = "ollama"
    gemini_api_key: SecretStr = SecretStr('')
    gemini_project_id: str = ''
    gemini_api_key_2: SecretStr = SecretStr('')
    gemini_project_id_2: str = ''
    gemini_api_key_3: SecretStr = SecretStr('')
    gemini_project_id_3: str = ''
    gemini_model: Literal['gemini-3.5-flash-lite', 'gemini-3.8-flash'] = 'gemini-3.5-flash-lite'
    gemini_generation_timeout_seconds: float = Field(default=60, ge=5, le=90)
    gemini_max_output_tokens: int = Field(default=2048, ge=256, le=4096)
    gemini_advice_max_output_tokens: int = Field(default=4096, ge=256, le=8192)
    groq_fallback_enabled: bool = False
    groq_api_key: SecretStr = SecretStr('')
    groq_model: Literal['qwen/qwen3.8-27b', 'openai/gpt-oss-120b'] = 'qwen/qwen3.8-27b'
    antigravity_binary: str = "agy"
    antigravity_model: Literal["gemini-3.8-flash-low", "gemini-3.8-flash-medium", "gemini-3.8-flash-high"] = "gemini-3.8-flash-low"
    antigravity_generation_timeout_seconds: float = Field(default=120, ge=30, le=180)
    # This demo deliberately has no paid-model fallback.
    opencode_model: Literal["glm-5.3-flash-free"] = "glm-5.3-flash-free"
    opencode_binary: str = "opencode"
    opencode_generation_timeout_seconds: float = Field(default=90, gt=0, le=120)
    ollama_host: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3:4b-instruct"
    ollama_health_timeout_seconds: float = Field(default=2, gt=0, le=10)
    ollama_generation_timeout_seconds: float = Field(default=180, gt=0, le=300)
    ollama_context_length: int = Field(default=4_096, ge=512, le=32_768)
    ollama_max_output_tokens: int = Field(default=256, ge=32, le=1_024)
    ollama_keep_alive: str = "30m"
