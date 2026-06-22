from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Optional

from services.margin_service import calculate_margin
from services.recommendation_service import build_repricing_recommendation


router = APIRouter(tags=["Margin and Recommendations"])


class MarginCalculateRequest(BaseModel):
    salePrice: float = Field(gt=0)
    productCost: float = Field(ge=0)
    amazonFees: float = Field(ge=0)
    shippingPrepCost: float = Field(ge=0)


class RepricingRecommendationRequest(BaseModel):
    asin: str
    sku: Optional[str] = None
    currentPrice: float = Field(gt=0)
    productCost: float = Field(ge=0)
    amazonFees: float = Field(ge=0)
    minMarginPercent: float = Field(ge=0)
    shippingPrepCost: float = Field(default=1.0, ge=0)


@router.post("/api/margin/calculate")
def margin_calculate(payload: MarginCalculateRequest):
    return calculate_margin(
        sale_price=payload.salePrice,
        product_cost=payload.productCost,
        amazon_fees=payload.amazonFees,
        shipping_prep_cost=payload.shippingPrepCost,
    )


@router.post("/api/recommendation/reprice")
def reprice_recommendation(payload: RepricingRecommendationRequest):
    return build_repricing_recommendation(
        asin=payload.asin,
        current_price=payload.currentPrice,
        product_cost=payload.productCost,
        amazon_fees=payload.amazonFees,
        min_margin_percent=payload.minMarginPercent,
        shipping_prep_cost=payload.shippingPrepCost,
        sku=payload.sku,
    )
