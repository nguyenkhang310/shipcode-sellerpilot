import re

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, model_validator
from typing import Literal
from app.ai.fallback import normalize_text
from app.ai.money import plain
from app.ai.listing_text import _is_generic_product_command, _wants_ai_description


def contextual_product_reference(value):
    text = ' '.join(plain(value).strip(' .!,?').split())
    text = re.sub(r'^(?:khong[, ]*|y (?:minh|toi) la\s+)', '', text)
    return bool(re.fullmatch(r'(?:(?:cai|chiec|con|mau|loai|san pham|mat hang|xe|ao|quan|may|mon|ban phim|chuot|hinh|anh)\s+)?'
                             r'(?:nay|do|kia|day|ay|no)(?:\s+(?:ne|nhe|nha|nay|ban))?', text))


def listing_validation_context(facts, history):
    return {'seller_text': '\n'.join([row.get('content', '') for row in history if row.get('role') == 'user']
                                    + [facts.get('current_message', ''), facts.get('name') or '', facts.get('description') or '']),
            'listing_facts': facts}


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
    def meaningful_title(self):
        if self.name and contextual_product_reference(self.name):
            raise ValueError('Resolve the product reference from images/history; do not use it as a title')
        return self

    @model_validator(mode='after')
    def usable_copy(self, info: ValidationInfo):
        if not info.context or 'listing_facts' not in info.context:
            return self
        facts = info.context['listing_facts']
        allowed = facts.get('allowed_categories')
        if allowed is not None and self.category_id is not None and self.category_id not in {item['id'] for item in allowed}:
            raise ValueError('listing_category: choose an ID from allowed_categories')
        if self.name is not None and (len(self.name.strip()) < 5 or _is_generic_product_command(self.name) or _wants_ai_description(self.name)):
            raise ValueError('listing_title: write a product title, not an instruction')
        if self.description is not None:
            # A normal caption may contain a closing CTA. It is not itself a
            # seller instruction merely because it ends with "thêm sản phẩm này".
            text = plain(self.description).strip()
            instruction = bool(re.match(r'^(?:(?:hay|vui long|lam on|ban|ai|sellerpilot)\s+)?(?:dang|tao|them|dua|viet|soan|tu viet|tu soan)\b', text))
            if len(self.description.strip()) < 10 or instruction and (_is_generic_product_command(self.description) or _wants_ai_description(self.description)):
                raise ValueError('listing_description: write product copy, not a request to generate it')
        has_details = any((self.name, self.description, self.price_vnd, self.stock is not None, self.category_id, self.clarification))
        question_fields = set(self.next_question_fields)
        missing = facts.get('missing_fields')
        if missing is None:
            missing = [field for field in ('name','description','category_id','price_vnd','stock') if facts.get(field) is None]
        followup = bool(self.next_question and question_fields and question_fields <= set(missing))
        if not has_details and not followup:
            raise ValueError('listing_empty: provide known facts or ask about a genuinely missing field')
        return self

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
                if label == 'condition_new' and re.search(r'(?:trải nghiệm|nội dung|ý tưởng|khởi đầu|góc làm việc|công việc)\s*$', output[max(0,claim.start()-30):claim.start()]):
                    continue
                negation = r'\b(?:không|ko|khong|chưa|chua)(?:\s+\w+){0,2}\s*$'
                negative = bool(re.search(negation, output[max(0, claim.start() - 25):claim.start()]))
                supported = any(bool(re.search(negation, source[max(0, found.start() - 25):found.start()])) == negative
                                for found in re.finditer(re.escape(claim[0]), source))
                if not supported:
                    raise ValueError('unsupported_product_claim:' + label)
        return self
