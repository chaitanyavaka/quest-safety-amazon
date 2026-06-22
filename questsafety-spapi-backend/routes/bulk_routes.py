from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from services.bulk_service import analyze_bulk_products


router = APIRouter(prefix="/api/bulk", tags=["Bulk Analysis"])


class BulkAnalyzeItem(BaseModel):
    productName: Optional[str] = None
    asin: Optional[str] = None
    sku: Optional[str] = None
    salePrice: float = Field(gt=0)
    productCost: float = Field(ge=0)
    amazonFees: float = Field(ge=0)
    shippingPrepCost: float = Field(default=1.0, ge=0)
    minMarginPercent: float = Field(default=20, ge=0)


class BulkAnalyzeRequest(BaseModel):
    items: List[BulkAnalyzeItem] = Field(min_items=1, max_items=100)


@router.post("/analyze")
def bulk_analyze(payload: BulkAnalyzeRequest):
    items = [item.dict() for item in payload.items]
    return analyze_bulk_products(items)
