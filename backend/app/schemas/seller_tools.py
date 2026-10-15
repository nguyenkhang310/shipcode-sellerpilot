from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class ShopSummary(BaseModel):
    date: date
    timezone: str
    order_count: int
    revenue_vnd: int
    pending_count: int
    cancelled_count: int
    status_counts: dict[str, int]


class ShopSummaryResponse(BaseModel):
    data: ShopSummary


class InventoryItem(BaseModel):
    target_kind: Literal["product", "variant"]
    product_id: int
    variant_id: int | None
    sku: str
    product_name: str
    variant_title: str | None
    size: str | None
    color: str | None
    price_vnd: int
    stock: int
    is_active: bool


class InventoryResponse(BaseModel):
    data: InventoryItem


class LowStockData(BaseModel):
    threshold: int
    count: int
    items: list[InventoryItem]


class LowStockResponse(BaseModel):
    data: LowStockData


class PriceChangeRequest(BaseModel):
    sku: str = Field(min_length=1, max_length=100)
    new_price_vnd: int = Field(gt=0, le=1_000_000_000)


class ProposalData(BaseModel):
    id: int
    kind: Literal["change_price"]
    status: Literal["pending", "approved", "rejected", "conflict"]
    target_kind: Literal["product", "variant"]
    sku: str
    product_name: str
    old_price_vnd: int
    new_price_vnd: int
    created_at: datetime
    decided_at: datetime | None
    idempotent: bool = False


class ProposalResponse(BaseModel):
    data: ProposalData
