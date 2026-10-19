import re

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, model_validator
from typing import Literal
from app.ai.fallback import normalize_text


def listing_validation_context(facts, history):
    return {'seller_text': '\n'.join([row.get('content', '') for row in history if row.get('role') == 'user']
                                    + [facts.get('current_message', '')])}


class ListingCopy(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=10_000)
    category_id: int | None = None
    clarification: str | None = Field(default=None, max_length=600)
    name_evidence: str | None = Field(default=None, max_length=2000)
    description_evidence: str | None = Field(default=None, max_length=4000)
    price_vnd: int | None = Field(default=None, ge=1000, le=1_000_000_000, strict=True)
    stock: int | None = Field(default=None, ge=0, le=1_000_000, strict=True)
    price_evidence: str | None = Field(default=None, max_length=500)
    stock_evidence: str | None = Field(default=None, max_length=500)
    next_question: str | None = Field(default=None, max_length=280)
    next_question_fields: list[Literal['name', 'price_vnd', 'stock', 'category_id', 'description']] = Field(default_factory=list, max_length=5)

    @model_validator(mode='after')
    def condition_claims_need_seller_evidence(self, info: ValidationInfo):
        if not info.context or 'seller_text' not in info.context:
            return self
        source = normalize_text(info.context['seller_text'])
        output = normalize_text((self.name or '') + '\n' + (self.description or ''))
        claims = {
            'condition_new': r'\bmới\b',
            'sealed': r'\b(?:nguyên tem|nguyên seal|niêm phong)\b',
            'authentic': r'\bchính hãng\b',
            'warranty': r'\bbảo hành(?:\s+(?:\d+\s*(?:tháng|năm)|trọn đời))?\b',
        }
        for label, pattern in claims.items():
            for claim in re.finditer(pattern, output):
                negation = r'\b(?:không|ko|khong|chưa|chua)(?:\s+\w+){0,2}\s*$'
                negative = bool(re.search(negation, output[max(0, claim.start() - 25):claim.start()]))
                supported = any(bool(re.search(negation, source[max(0, found.start() - 25):found.start()])) == negative
                                for found in re.finditer(re.escape(claim[0]), source))
                if not supported:
                    raise ValueError('unsupported_product_claim:' + label)
        return self
