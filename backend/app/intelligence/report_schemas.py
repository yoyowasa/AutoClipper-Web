"""Native/derived metric shapes shared by the dashboard and fixed-age evaluation."""
from datetime import date, datetime
from typing import Literal
from pydantic import BaseModel


class MetricRead(BaseModel):
    value: float | None = None
    missingReason: str | None = None
    observedSubtotal: float | None = None


class ReportRead(BaseModel):
    source: Literal["youtube_analytics", "independent_aggregation"] = "youtube_analytics"
    start: date | None = None
    end: date | None = None
    observedAt: datetime | None = None
    metrics: dict[str, MetricRead]
    reason: str | None = None
    returned: int | None = None
    expected: int | None = None
    format: str = "unknown"
