from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.ai.text import assistant_text

from app.schemas.seller_tools import ProposalData
from app.schemas.product_drafts import ProductDraftData
from app.schemas.product_edits import ProductEditData


class ChatRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    message: str = Field(min_length=1, max_length=4_000)
    conversation_id: UUID | None = None
    request_id: UUID | None = None


class ChatData(BaseModel):
    run_id: int
    conversation_id: str | None = None
    answer: str

    @field_validator('answer')
    @classmethod
    def decode_answer(cls, value):
        return assistant_text(value)
    intent: Literal["shop_summary", "inventory_query", "change_price", "product_search", "sales_advice", "create_product", "update_product", "unknown"]
    mode: Literal["ai", "fallback"]
    provider: Literal["ollama", "opencode", "antigravity", "gemini", "groq", "deterministic_parser"]
    model: str | None
    fallback_reason: Literal[
        "provider_unavailable",
        "provider_timeout",
        "model_unavailable",
        "invalid_response",
        "provider_rejected",
        "provider_rate_limited",
        "free_tier_restricted",
        "free_model_unavailable",
        "tool_not_allowed",
    ] | None
    tool: str | None
    facts: dict[str, Any]
    proposal: ProposalData | None
    product_draft: ProductDraftData | None = None
    product_edit_proposal: ProductEditData | None = None
    suggestions: list[str] = Field(default_factory=list)
    integration_mode: Literal["local_store"] = "local_store"


class ChatResponse(BaseModel):
    data: ChatData
