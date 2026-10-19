from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ProductChanges(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str | None = Field(default=None, min_length=3, max_length=200)
    description: str | None = Field(default=None, max_length=10000)
    price_vnd: int | None = Field(default=None, ge=1000, le=1_000_000_000, strict=True)
    stock: int | None = Field(default=None, ge=0, le=1_000_000, strict=True)

    @field_validator('name','description')
    @classmethod
    def trim_text(cls,value):
        return value.strip() if value is not None else None

    @model_validator(mode='after')
    def not_empty(self):
        if not self.model_dump(exclude_none=True):
            raise ValueError('Provide at least one changed field')
        if self.name is not None and len(self.name) < 3:
            raise ValueError('Product title is too short')
        return self


class ProductEditRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    sku: str = Field(min_length=1,max_length=100)
    changes: ProductChanges


class FieldChange(BaseModel):
    field: Literal['name','description','price_vnd','stock']
    before: str | int | None
    after: str | int


class ProductEditData(BaseModel):
    id: int
    sku: str
    product_name: str
    target_kind: Literal['product','variant']
    status: Literal['pending','executing','approved','rejected','conflict']
    changes: list[FieldChange]
    shared_content: bool
    created_at: datetime
    decided_at: datetime | None
    idempotent: bool = False


class ProductEditResponse(BaseModel):
    data: ProductEditData
