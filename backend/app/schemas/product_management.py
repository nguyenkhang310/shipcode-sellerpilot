from uuid import UUID
from pydantic import Field, model_validator
from app.schemas.product_edits import ProductChanges


class ProductUpdate(ProductChanges):
    request_id: UUID
    expected_version: str = Field(pattern=r'^[a-f0-9]{64}$')
    variant_id: int | None = Field(default=None, ge=1, strict=True)

    @model_validator(mode='after')
    def require_changes(self):
        changed = self.model_fields_set & {'name', 'description', 'price_vnd', 'stock'}
        if not changed or any(getattr(self, key) is None for key in changed):
            raise ValueError('Cần ít nhất một trường thay đổi; không nhận giá trị null.')
        return self
