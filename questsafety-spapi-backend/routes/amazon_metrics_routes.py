from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from services.amazon_metrics_service import amazon_metrics_answer, amazon_metrics_summary


router = APIRouter(prefix="/api/amazon-metrics", tags=["Amazon Metrics"])


class MetricsSummaryRequest(BaseModel):
    query: Optional[str] = None
    year: int = Field(default=2026, ge=2025, le=2026)
    month: int = Field(default=6, ge=1, le=12)
    riskCategory: str = "all"


class MetricsAskRequest(MetricsSummaryRequest):
    question: str = ""


@router.post("/summary")
def metrics_summary(payload: MetricsSummaryRequest):
    return amazon_metrics_summary(
        query=payload.query,
        year=payload.year,
        month=payload.month,
        risk_category=payload.riskCategory,
    )


@router.post("/ask")
def metrics_ask(payload: MetricsAskRequest):
    return amazon_metrics_answer(
        question=payload.question,
        query=payload.query,
        year=payload.year,
        month=payload.month,
        risk_category=payload.riskCategory,
    )
