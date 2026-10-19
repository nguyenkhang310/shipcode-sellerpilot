"""Browser facts are untrusted, partial snapshots; never a local-shop identity."""
from datetime import datetime, timezone
from typing import Annotated, Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
import json


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


class BrowserResource(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source_url: str = Field(max_length=2000)
    observed_at: datetime
    pages_read: int = Field(ge=1, le=100, strict=True)
    complete: bool
    scope: str = Field(max_length=100)
    reason: str | None = Field(default=None, max_length=500)

    _origin = field_validator('source_url')(BrowserSnapshot.seller_origin_only.__func__)

    @field_validator('observed_at')
    @classmethod
    def recent_observation(cls, value):
        if value.tzinfo is None or not -30 <= (datetime.now(timezone.utc) - value).total_seconds() <= 300:
            raise ValueError('Synchronized facts expired; refresh the shop data')
        return value


class BrowserMetric(BaseModel):
    model_config = ConfigDict(extra='forbid')
    label: str = Field(max_length=100)
    value: str = Field(max_length=100)


class BrowserPageFacts(BrowserResource):
    rows_read: int = Field(default=0, ge=0, le=50000, strict=True)
    sampled_rows: int = Field(default=0, ge=0, le=50000, strict=True)
    sample_truncated: bool = False
    metrics: list[BrowserMetric] = Field(default_factory=list, max_length=20)
    tables: list[list[list[Annotated[str, Field(max_length=200)]]]] = Field(default_factory=list, max_length=3)

    @field_validator('tables')
    @classmethod
    def bounded_tables(cls, value):
        if any(len(table) > 16 or any(len(row) > 20 for row in table) for table in value):
            raise ValueError('Too many sampled rows or columns')
        return value


class BrowserInventoryItem(BaseModel):
    model_config = ConfigDict(extra='forbid')
    key: str = Field(max_length=200)
    name: str = Field(min_length=1, max_length=200)
    sku: str | None = Field(default=None, max_length=100)
    stock: int = Field(ge=0, le=1000000000, strict=True)


class BrowserInventoryFacts(BrowserResource):
    records_count: int = Field(ge=0, le=50000, strict=True)
    quantities_known: int = Field(ge=0, le=50000, strict=True)
    quantities_unknown: int = Field(ge=0, le=50000, strict=True)
    conflicting_records: int = Field(ge=0, le=50000, strict=True)
    unverified_identities: int = Field(ge=0, le=50000, strict=True)
    total_units: int = Field(ge=0, le=50000000000000, strict=True)
    threshold: int = Field(ge=1, le=1000000, strict=True)
    low_stock_count: int = Field(ge=0, le=50000, strict=True)
    out_of_stock_count: int = Field(ge=0, le=50000, strict=True)
    omitted_low_stock_count: int = Field(ge=0, le=50000, strict=True)
    omitted_out_of_stock_count: int = Field(ge=0, le=50000, strict=True)
    low_stock_items: list[BrowserInventoryItem] = Field(max_length=40)
    out_of_stock_items: list[BrowserInventoryItem] = Field(max_length=20)

    @model_validator(mode='after')
    def consistent_counts(self):
        if (self.quantities_known + self.quantities_unknown != self.records_count
                or self.low_stock_count + self.out_of_stock_count > self.quantities_known
                or self.conflicting_records > self.quantities_unknown
                or self.unverified_identities > self.records_count
                or len(self.low_stock_items) + self.omitted_low_stock_count != self.low_stock_count
                or len(self.out_of_stock_items) + self.omitted_out_of_stock_count != self.out_of_stock_count
                or any(not 0 < row.stock <= self.threshold for row in self.low_stock_items)
                or any(row.stock != 0 for row in self.out_of_stock_items)
                or sum(row.stock for row in self.low_stock_items) > self.total_units
                or not self.quantities_known and self.total_units != 0
                or len({row.key for row in self.low_stock_items + self.out_of_stock_items})
                != len(self.low_stock_items) + len(self.out_of_stock_items)):
            raise ValueError('Inventory observations are inconsistent')
        return self


class BrowserShopContext(BaseModel):
    model_config = ConfigDict(extra='forbid')
    connection_id: UUID
    account_label: str = Field(min_length=1, max_length=80)
    sync_status: Literal['idle', 'running', 'interrupted', 'partial', 'completed', 'cancelled', 'failed']
    products: BrowserInventoryFacts | None = None
    dashboard: BrowserPageFacts | None = None
    orders: BrowserPageFacts | None = None


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
    shop_context: BrowserShopContext | None = None
    history: list[BrowserTurn] = Field(default_factory=list, max_length=20)
    draft: BrowserDraft = Field(default_factory=BrowserDraft)
    images: list[Annotated[str, Field(max_length=1500000)]] = Field(default_factory=list, max_length=6)

    @model_validator(mode='after')
    def same_shop_context(self):
        if self.shop_context:
            if self.shop_context.connection_id != self.connection_id:
                raise ValueError('Shop context belongs to another connection')
            try:
                account = json.loads(self.snapshot.text).get('account_label')
            except (ValueError, AttributeError):
                account = None
            if account != self.shop_context.account_label:
                raise ValueError('Shop context does not match the observed account')
        return self
