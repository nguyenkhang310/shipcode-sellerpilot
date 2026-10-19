from typing import Literal

from pydantic import BaseModel


class HealthData(BaseModel):
    status: Literal["ok", "degraded"]
    database: Literal["ok", "unavailable"]
    shop_database: Literal["ok", "unavailable"]
    provider: Literal["ollama", "opencode", "antigravity", "gemini"]
    ai_availability: Literal["available", "unavailable"]
    ollama: Literal["available", "unavailable"]
    model: str
    model_available: bool
    demo_mode: bool
    integration_mode: Literal["local_store", "not_connected"] = "not_connected"


class HealthResponse(BaseModel):
    data: HealthData
