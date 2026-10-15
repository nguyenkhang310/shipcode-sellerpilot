from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class EconomicsUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    field: Literal[
        'unit_cost_vnd', 'packaging_vnd', 'shipping_subsidy_vnd', 'ads_per_order_vnd',
        'other_cost_vnd', 'fee_percent', 'target_margin_percent', 'target_profit_vnd',
        'selling_price_vnd', 'units_per_order', 'target_markup_percent', 'discount_percent',
    ]
    value: Decimal = Field(ge=0, le=1_000_000_000)
    evidence: str = Field(min_length=1, max_length=300)


class PreferenceUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    field: Literal['target_audience', 'business_goal', 'response_style', 'brand_voice', 'business_constraints']
    value: str = Field(min_length=1, max_length=500)
    evidence: str = Field(min_length=1, max_length=600)


class AdviceExtraction(BaseModel):
    model_config = ConfigDict(extra='forbid')
    topic: Literal['general', 'pricing', 'strategy', 'content'] = 'general'
    product_query: str | None = Field(default=None, max_length=120)
    new_scenario: bool = False
    economics: list[EconomicsUpdate] = Field(default_factory=list, max_length=12)
    preferences: list[PreferenceUpdate] = Field(default_factory=list, max_length=5)
