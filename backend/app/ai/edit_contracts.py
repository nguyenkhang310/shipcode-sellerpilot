from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, model_validator


class ProductEditCopy(BaseModel):
    model_config=ConfigDict(extra='forbid')
    name: str | None=Field(default=None,min_length=3,max_length=200)
    description: str | None=Field(default=None,max_length=10000)
    price_vnd: int | None=Field(default=None,ge=1000,le=1_000_000_000,strict=True)
    stock: int | None=Field(default=None,ge=0,le=1_000_000,strict=True)
    name_evidence: str | None=Field(default=None,max_length=1000)
    description_evidence: str | None=Field(default=None,max_length=4000)
    price_evidence: str | None=Field(default=None,max_length=500)
    stock_evidence: str | None=Field(default=None,max_length=500)
    clarification: str | None=Field(default=None,max_length=400)

    @model_validator(mode='after')
    def requested_copy_cannot_be_silently_omitted(self,info:ValidationInfo):
        for field in (info.context or {}).get('rewrite_fields',[]):
            if getattr(self,field) is None and not self.clarification:
                raise ValueError('requested_rewrite_missing:'+field+'; write this field from verified product facts')
        return self
