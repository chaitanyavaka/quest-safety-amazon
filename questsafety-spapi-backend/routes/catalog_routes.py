from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from services.catalog_service import search_catalog


router = APIRouter(prefix="/api/catalog", tags=["Catalog"])


class CatalogSearchRequest(BaseModel):
    productName: Optional[str] = Field(default=None)
    asin: Optional[str] = Field(default=None)
    sku: Optional[str] = Field(default=None)


@router.post("/search")
def catalog_search(payload: CatalogSearchRequest):
    return search_catalog(
        product_name=payload.productName,
        asin=payload.asin,
        sku=payload.sku,
    )
