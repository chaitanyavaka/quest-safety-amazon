from copy import deepcopy
import hashlib
import re
from typing import Any, Dict, List, Optional

import requests

from services.amazon_auth import (
    SP_API_SANDBOX_BASE_URL,
    get_lwa_access_token,
    get_marketplace_id,
    use_live_sandbox_api,
)


SANDBOX_PRICING_ASIN = "B00ZIAODGE"
SANDBOX_LOWEST_COMPETITOR_PRICE = 17.15
SANDBOX_COMPETITOR_SUMMARY = {
    "asin": SANDBOX_PRICING_ASIN,
    "featuredOffers": [],
    "lowestPricedOffers": [],
    "referencePrices": [],
}


def get_competitor_summary(asin: Optional[str] = None) -> Dict[str, Any]:
    requested_asin = _normalize_asin(asin) or SANDBOX_PRICING_ASIN

    if not use_live_sandbox_api():
        return _build_dynamic_sandbox_competitor_summary(requested_asin)

    try:
        access_token = get_lwa_access_token()
        data = _fetch_competitive_summary_sandbox(access_token)
        return _clean_competitor_summary(data)
    except Exception:
        return _build_dynamic_sandbox_competitor_summary(requested_asin)


def get_lowest_competitor_price(asin: Optional[str] = None) -> float:
    summary = get_competitor_summary(asin)

    prices: List[float] = []
    for offer_group in summary.get("lowestPricedOffers", []):
        item_condition = offer_group.get("itemCondition")
        if item_condition and item_condition != "New":
            continue

        for offer in offer_group.get("offers", []):
            if offer.get("condition") and offer.get("condition") != "New":
                continue

            price = offer.get("totalPrice")
            if isinstance(price, (int, float)):
                prices.append(float(price))

    if not prices:
        return SANDBOX_LOWEST_COMPETITOR_PRICE

    return round(min(prices), 2)


def _fetch_competitive_summary_sandbox(access_token: str) -> Dict[str, Any]:
    url = (
        f"{SP_API_SANDBOX_BASE_URL}"
        "/batches/products/pricing/2022-05-01/items/competitiveSummary"
    )

    headers = {
        "x-amz-access-token": access_token,
        "Content-Type": "application/json",
    }

    body = {
        "requests": [
            {
                "asin": SANDBOX_PRICING_ASIN,
                "marketplaceId": get_marketplace_id(),
                "includedData": [
                    "featuredBuyingOptions",
                    "referencePrices",
                    "lowestPricedOffers",
                    "similarItems",
                ],
                "lowestPricedOffersInputs": [
                    {
                        "itemCondition": "New",
                        "offerType": "Consumer",
                    },
                    {
                        "itemCondition": "Used",
                        "offerType": "Consumer",
                    },
                ],
                "uri": "/products/pricing/2022-05-01/items/competitiveSummary",
                "method": "GET",
            },
            {
                "asin": "11_AABB_123",
                "marketplaceId": get_marketplace_id(),
                "includedData": ["featuredBuyingOptions"],
                "uri": "/products/pricing/2022-05-01/items/competitiveSummary",
                "method": "GET",
            },
        ]
    }

    response = requests.post(url, headers=headers, json=body, timeout=15)
    response.raise_for_status()
    return response.json()


def _clean_competitor_summary(data: Dict[str, Any]) -> Dict[str, Any]:
    for result in data.get("responses", []):
        status_code = result.get("status", {}).get("statusCode")
        body = result.get("body", {})

        if body.get("asin") != SANDBOX_PRICING_ASIN or status_code != 200:
            continue

        return {
            "asin": SANDBOX_PRICING_ASIN,
            "featuredOffers": _clean_featured_offers(body),
            "lowestPricedOffers": _clean_lowest_priced_offers(body),
            "referencePrices": body.get("referencePrices", []),
        }

    return deepcopy(SANDBOX_COMPETITOR_SUMMARY)


def _clean_featured_offers(body: Dict[str, Any]) -> List[Dict[str, Any]]:
    offers: List[Dict[str, Any]] = []

    for buying_option in body.get("featuredBuyingOptions", []):
        for offer in buying_option.get("segmentedFeaturedOffers", []):
            offers.append(_clean_offer(offer))

    return offers


def _clean_lowest_priced_offers(body: Dict[str, Any]) -> List[Dict[str, Any]]:
    offer_groups: List[Dict[str, Any]] = []

    for offer_group in body.get("lowestPricedOffers", []):
        cleaned_offers = [
            _clean_offer(offer)
            for offer in offer_group.get("offers", [])
        ]
        offer_groups.append(
            {
                "itemCondition": offer_group.get(
                    "lowestPricedOffersInput", {}
                ).get("itemCondition"),
                "offers": cleaned_offers,
            }
        )

    return offer_groups


def _clean_offer(offer: Dict[str, Any]) -> Dict[str, Any]:
    listing_price = offer.get("listingPrice", {})
    shipping_options = offer.get("shippingOptions", [])
    shipping_price = 0

    if shipping_options:
        shipping_price = (
            shipping_options[0]
            .get("price", {})
            .get("amount", 0)
        )

    listing_amount = listing_price.get("amount", 0)

    return {
        "sellerId": offer.get("sellerId"),
        "condition": offer.get("condition"),
        "fulfillmentType": offer.get("fulfillmentType"),
        "listingPrice": listing_amount,
        "shippingPrice": shipping_price,
        "totalPrice": round(listing_amount + shipping_price, 2),
        "currencyCode": listing_price.get("currencyCode", "USD"),
    }


def _build_dynamic_sandbox_competitor_summary(asin: str) -> Dict[str, Any]:
    lowest_price = _get_dynamic_lowest_price(asin)
    new_offer_prices = [
        lowest_price,
        round(lowest_price + 0.84, 2),
        round(lowest_price + 1.29, 2),
        round(lowest_price + 1.95, 2),
        round(lowest_price + 2.49, 2),
    ]
    featured_price = round(lowest_price + 1.35, 2)
    used_price = round(max(lowest_price - 3.2, 1), 2)

    return {
        "asin": asin,
        "featuredOffers": [
            _build_offer(
                seller_id="SANDBOX_FEATURED_SELLER",
                condition="New",
                fulfillment_type="AFN",
                listing_price=featured_price,
                shipping_price=0,
            )
        ],
        "lowestPricedOffers": [
            {
                "itemCondition": "New",
                "offers": _build_new_competitor_offers(new_offer_prices),
            },
            {
                "itemCondition": "Used",
                "offers": [
                    _build_offer(
                        seller_id="SANDBOX_USED_SELLER",
                        condition="Used",
                        fulfillment_type="MFN",
                        listing_price=used_price,
                        shipping_price=0,
                    )
                ],
            },
        ],
        "referencePrices": [
            {
                "name": "Competitive price threshold",
                "price": {
                    "amount": lowest_price,
                    "currencyCode": "USD",
                },
            },
            {
                "name": "Featured offer benchmark",
                "price": {
                    "amount": featured_price,
                    "currencyCode": "USD",
                },
            },
        ],
    }


def _build_new_competitor_offers(prices: List[float]) -> List[Dict[str, Any]]:
    sellers = [
        ("SANDBOX_LOWEST_SELLER", "MFN"),
        ("SANDBOX_SECOND_SELLER", "AFN"),
        ("SANDBOX_VALUE_SELLER", "MFN"),
        ("SANDBOX_FAST_SHIP_SELLER", "AFN"),
        ("SANDBOX_PREMIUM_SELLER", "AFN"),
    ]

    return [
        _build_offer(
            seller_id=seller_id,
            condition="New",
            fulfillment_type=fulfillment_type,
            listing_price=prices[index],
            shipping_price=0,
        )
        for index, (seller_id, fulfillment_type) in enumerate(sellers)
    ]


def _build_offer(
    seller_id: str,
    condition: str,
    fulfillment_type: str,
    listing_price: float,
    shipping_price: float,
) -> Dict[str, Any]:
    return {
        "sellerId": seller_id,
        "condition": condition,
        "fulfillmentType": fulfillment_type,
        "listingPrice": listing_price,
        "shippingPrice": shipping_price,
        "totalPrice": round(listing_price + shipping_price, 2),
        "currencyCode": "USD",
    }


def _get_dynamic_lowest_price(asin: str) -> float:
    if asin == SANDBOX_PRICING_ASIN:
        return SANDBOX_LOWEST_COMPETITOR_PRICE

    digest = hashlib.sha256(asin.encode("utf-8")).hexdigest()
    cents = int(digest[:8], 16) % 4000
    return round(9.99 + (cents / 100), 2)


def _normalize_asin(asin: Optional[str]) -> str:
    if not asin:
        return ""

    return re.sub(r"[^A-Za-z0-9]", "", asin).upper()[:10]
