from typing import Any, Dict, List

from services.catalog_service import search_catalog
from services.margin_service import calculate_margin
from services.pricing_service import get_competitor_summary
from services.recommendation_service import build_repricing_recommendation


def analyze_bulk_products(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    results = [
        _analyze_bulk_product(index=index, item=item)
        for index, item in enumerate(items, start=1)
    ]

    return {
        "count": len(results),
        "summary": _build_summary(results),
        "results": results,
    }


def _analyze_bulk_product(index: int, item: Dict[str, Any]) -> Dict[str, Any]:
    product_name = item.get("productName")
    asin = item.get("asin")
    sku = item.get("sku")
    sale_price = float(item.get("salePrice", 0))
    product_cost = float(item.get("productCost", 0))
    amazon_fees = float(item.get("amazonFees", 0))
    shipping_prep_cost = float(item.get("shippingPrepCost", 0))
    min_margin_percent = float(item.get("minMarginPercent", 20))

    catalog = search_catalog(
        product_name=product_name,
        asin=asin,
        sku=sku,
    )
    analysis_asin = asin or catalog.get("asin")
    competitors = get_competitor_summary(analysis_asin)
    margin = calculate_margin(
        sale_price=sale_price,
        product_cost=product_cost,
        amazon_fees=amazon_fees,
        shipping_prep_cost=shipping_prep_cost,
    )
    recommendation = build_repricing_recommendation(
        asin=analysis_asin,
        current_price=sale_price,
        product_cost=product_cost,
        amazon_fees=amazon_fees,
        min_margin_percent=min_margin_percent,
        shipping_prep_cost=shipping_prep_cost,
        sku=sku,
    )

    return {
        "rowNumber": index,
        "input": {
            "productName": product_name,
            "asin": asin,
            "sku": sku,
            "salePrice": sale_price,
            "productCost": product_cost,
            "amazonFees": amazon_fees,
            "shippingPrepCost": shipping_prep_cost,
            "minMarginPercent": min_margin_percent,
        },
        "catalog": catalog,
        "competitors": {
            "asin": competitors.get("asin"),
            "lowestNewOffer": _lowest_new_offer(competitors),
            "newOfferCount": _new_offer_count(competitors),
        },
        "margin": margin,
        "recommendation": recommendation,
    }


def _build_summary(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    actions: Dict[str, int] = {}
    risks: Dict[str, int] = {}

    for result in results:
        action = result["recommendation"].get("recommendedAction", "UNKNOWN")
        risk = result["recommendation"].get("riskLevel", "UNKNOWN")
        actions[action] = actions.get(action, 0) + 1
        risks[risk] = risks.get(risk, 0) + 1

    return {
        "actions": actions,
        "risks": risks,
        "profitableCount": sum(
            1 for result in results if result["margin"].get("isProfitable")
        ),
    }


def _lowest_new_offer(competitors: Dict[str, Any]) -> float:
    prices: List[float] = []

    for offer_group in competitors.get("lowestPricedOffers", []):
        if offer_group.get("itemCondition") not in (None, "New"):
            continue

        for offer in offer_group.get("offers", []):
            if offer.get("condition") not in (None, "New"):
                continue

            price = offer.get("totalPrice")
            if isinstance(price, (int, float)):
                prices.append(float(price))

    return round(min(prices), 2) if prices else 0


def _new_offer_count(competitors: Dict[str, Any]) -> int:
    count = 0

    for offer_group in competitors.get("lowestPricedOffers", []):
        if offer_group.get("itemCondition") not in (None, "New"):
            continue

        count += len(offer_group.get("offers", []))

    return count
