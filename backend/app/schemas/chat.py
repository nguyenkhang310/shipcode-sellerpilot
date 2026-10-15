from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.seller_tools import ProposalData
from app.schemas.product_drafts import ProductDraftData


class ChatRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    message: str = Field(min_length=1, max_length=2_000)
    conversation_id: UUID | None = None
    request_id: UUID | None = None


class ChatData(BaseModel):
    run_id: int
    conversation_id: str | None = None
    answer: str
    intent: Literal["shop_summary", "inventory_query", "change_price", "product_search", "sales_advice", "create_product", "unknown"]
    mode: Literal["ai", "fallback"]
    provider: Literal["ollama", "opencode", "deterministic_parser"]
    model: str | None
    fallback_reason: Literal[
        "provider_unavailable",
        "provider_timeout",
        "model_unavailable",
        "invalid_response",
        "provider_rejected",
        "free_model_unavailable",
        "tool_not_allowed",
    ] | None
    tool: str | None
    facts: dict[str, Any]
    proposal: ProposalData | None
    product_draft: ProductDraftData | None = None
    suggestions: list[str] = Field(default_factory=list)
    integration_mode: Literal["local_store"] = "local_store"


class ChatResponse(BaseModel):
    data: ChatData
