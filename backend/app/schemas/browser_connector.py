"""Browser facts are untrusted, partial snapshots; never a local-shop identity."""
from datetime import datetime, timezone
from typing import Annotated, Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class BrowserSnapshot(BaseModel):
    model_config = ConfigDict(extra='forbid')
    url: str = Field(max_length=2000)
    title: str = Field(max_length=300)
    captured_at: datetime
    text: str = Field(max_length=16000)
    scope: Literal['visible_page'] = 'visible_page'

    @field_validator('url')
    @classmethod
    def seller_origin_only(cls, value):
        parsed = urlsplit(value)
        if (parsed.scheme != 'https' or parsed.netloc != 'banhang.shopee.vn'
                or parsed.username or parsed.password or parsed.fragment):
            raise ValueError('Only Shopee Seller Centre is supported')
        return value

    @field_validator('captured_at')
    @classmethod
    def recent_snapshot(cls, value):
        if value.tzinfo is None or not -30 <= (datetime.now(timezone.utc) - value).total_seconds() <= 180:
            raise ValueError('Read the current Shopee page again')
        return value


class BrowserTurn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    role: Literal['user', 'assistant']
    content: str = Field(max_length=6000)


class BrowserDraft(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=10000)
    price_vnd: int | None = Field(default=None, ge=1000, le=1000000000, strict=True)
    stock: int | None = Field(default=None, ge=0, le=1000000, strict=True)


class BrowserAssistRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: UUID
    connection_id: UUID
    mode: Literal['chat', 'listing'] = 'chat'
    message: str = Field(min_length=1, max_length=4000)
    snapshot: BrowserSnapshot
    history: list[BrowserTurn] = Field(default_factory=list, max_length=20)
    draft: BrowserDraft = Field(default_factory=BrowserDraft)
    images: list[Annotated[str, Field(max_length=1500000)]] = Field(default_factory=list, max_length=6)
