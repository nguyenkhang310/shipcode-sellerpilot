from datetime import date
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator


Intent = Literal["shop_summary", "inventory_query", "change_price", "product_search", "sales_advice", "unknown"]
InventoryScope = Literal["overview", "single_sku", "low_stock"]
FallbackReason = Literal[
    "provider_unavailable",
    "provider_timeout",
    "model_unavailable",
    "invalid_response",
    "provider_rejected",
    "provider_rate_limited",
    "free_tier_restricted",
    "free_model_unavailable",
    "tool_not_allowed",
]


class ParsedCommand(BaseModel):
    """Small, closed contract that an LLM may produce.

    This object contains intent and arguments only. It never contains SQL, tool names,
    confirmation decisions, or arbitrary URLs.
    """

    model_config = ConfigDict(extra="forbid")

    intent: Intent
    sku: str | None = Field(default=None, max_length=100)
    new_price_vnd: int | None = None
    inventory_scope: InventoryScope | None = None
    day: date | None = None
    low_stock_threshold: int | None = Field(default=None, ge=0, le=10_000)
    query: str | None = Field(default=None, max_length=200)
    min_price_vnd: int | None = Field(default=None, ge=0, le=1_000_000_001)
    max_price_vnd: int | None = Field(default=None, ge=0, le=1_000_000_000)
    days: int | None = Field(default=None, ge=1, le=30)

    @field_validator("sku")
    @classmethod
    def normalize_sku(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().upper()
        if not normalized:
            return None
        allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")
        if any(character not in allowed for character in normalized):
            raise ValueError("SKU contains unsupported characters")
        return normalized


class ModelCommand(BaseModel):
    """Fully required, nullable schema sent to Ollama for constrained decoding."""

    model_config = ConfigDict(extra="forbid")

    intent: Intent
    sku: str | None = Field(max_length=200)
    new_price_vnd: int | None
    inventory_scope: InventoryScope | None
    day: date | None
    low_stock_threshold: int | None = Field(ge=0, le=10_000)
    query: str | None = Field(default=None, max_length=200)
    days: int | None = Field(default=None, ge=1, le=30)


class ProviderHealth(BaseModel):
    availability: Literal["available", "unavailable"]
    model_available: bool = False


class ClassificationResult(BaseModel):
    command: ParsedCommand
    provider: Literal["ollama", "opencode", "antigravity", "gemini", "groq"] = "ollama"
    model: str


class AIProviderError(RuntimeError):
    def __init__(self, reason: FallbackReason, *, stage: str | None = None, retryable: bool = False):
        super().__init__(reason)
        self.reason = reason
        self.stage = stage
        self.retryable = retryable


class AIProvider(Protocol):
    async def check_health(self) -> ProviderHealth: ...

    async def classify(self, message: str, *, today: date) -> ClassificationResult: ...
