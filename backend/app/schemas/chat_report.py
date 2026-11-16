"""Read-only report contract. Values come from shop tools, never model output."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Unit = Literal['vnd', 'count', 'percent']


class ReportModel(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class ReportMetric(ReportModel):
    label: str
    value: float | None
    unit: Unit
    change_percent: float | None = None


class ReportPoint(ReportModel):
    label: str
    value: float = Field(ge=0)


class ReportChart(ReportModel):
    kind: Literal['line', 'bar']
    title: str
    unit: Unit
    points: list[ReportPoint] = Field(max_length=32)


class ReportColumn(ReportModel):
    label: str
    unit: Literal['text', 'count', 'vnd']


class ReportTable(ReportModel):
    title: str
    columns: list[ReportColumn] = Field(min_length=1, max_length=4)
    rows: list[list[str | int | float | None]] = Field(max_length=50)

    @model_validator(mode='after')
    def matching_columns(self):
        if any(len(row) != len(self.columns) for row in self.rows):
            raise ValueError('Report rows must match column count')
        return self


class ChatReport(ReportModel):
    title: str
    subtitle: str
    source: Literal['local_store'] = 'local_store'
    as_of: datetime | None = None
    timezone: str | None = None
    metrics: list[ReportMetric] = Field(default_factory=list, max_length=6)
    charts: list[ReportChart] = Field(default_factory=list, max_length=2)
    table: ReportTable | None = None
    notes: list[str] = Field(default_factory=list, max_length=6)
