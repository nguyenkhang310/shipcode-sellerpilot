import re
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class OrderUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: UUID
    expected_version: str = Field(pattern=r'^[a-f0-9]{64}$')
    status: Literal['paid', 'shipped', 'delivered', 'cancelled'] | None = None
    shipping_name: str | None = Field(default=None, min_length=1, max_length=150)
    shipping_phone: str | None = Field(default=None, min_length=8, max_length=30)
    shipping_address: str | None = Field(default=None, min_length=5, max_length=500)
    note: str | None = Field(default=None, max_length=500)
    shipping_carrier: str | None = Field(default=None, max_length=80)
    tracking_number: str | None = Field(default=None, max_length=80)

    @field_validator('shipping_name', 'shipping_phone', 'shipping_address', 'note', 'shipping_carrier', 'tracking_number', mode='before')
    @classmethod
    def clean_text(cls, value):
        if isinstance(value, str):
            value = value.strip()
            if any(ord(char) < 32 and char not in '\n\t' for char in value):
                raise ValueError('Thông tin có ký tự không hợp lệ.')
        return value

    @field_validator('shipping_phone')
    @classmethod
    def valid_phone(cls, value):
        if value is not None and (not re.fullmatch(r'\+?[\d ()-]+', value)
                                  or not 8 <= len(re.sub(r'\D', '', value)) <= 15):
            raise ValueError('Số điện thoại cần từ 8 đến 15 chữ số.')
        return value

    @field_validator('tracking_number')
    @classmethod
    def valid_tracking(cls, value):
        if value and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/-]{2,79}', value):
            raise ValueError('Mã vận đơn cần 3–80 ký tự chữ/số, dấu chấm, gạch, gạch dưới hoặc dấu /.')
        return value

    @model_validator(mode='after')
    def changes_required(self):
        changes = self.model_fields_set - {'request_id', 'expected_version'}
        if not changes or any(getattr(self, name) is None for name in changes):
            raise ValueError('Gửi ít nhất một thay đổi, không gửi giá trị null.')
        return self
