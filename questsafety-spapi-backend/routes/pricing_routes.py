from fastapi import APIRouter
from pydantic import BaseModel

from services.pricing_service import get_competitor_summary


router = APIRouter(prefix="/api/competitors", tags=["Competitors"])


class CompetitorSummaryRequest(BaseModel):
    asin: str


@router.post("/summary")
def competitor_summary(payload: CompetitorSummaryRequest):
    return get_competitor_summary(payload.asin)
