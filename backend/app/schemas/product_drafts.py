from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ProductImageDataRequest(BaseModel):
    image_base64: str = Field(min_length=4, max_length=11_200_000)
    conversation_id: UUID | None = None


class ProductImagesDataRequest(BaseModel):
    images_base64: list[Annotated[str, Field(min_length=4, max_length=11_200_000)]] = Field(min_length=1, max_length=6)
    conversation_id: UUID | None = None
    request_id: UUID | None = None


class ProductDraftData(BaseModel):
    id: int
    status: Literal["collecting", "ready", "published", "cancelled", "conflict"]
    preview_url: str
    preview_urls: list[str]
    image_count: int
    name: str | None
    description: str | None
    category_id: int | None
    category_name: str | None
    price_vnd: int | None
    stock: int | None
    sku: str | None
    missing_fields: list[str]
    published_product_id: int | None
    created_at: datetime
    decided_at: datetime | None


class ProductDraftResponse(BaseModel):
    data: ProductDraftData
