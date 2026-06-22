from copy import deepcopy
import hashlib
import re
from typing import Any, Dict, Optional

import requests

from services.amazon_auth import (
    SP_API_SANDBOX_BASE_URL,
    get_lwa_access_token,
    get_marketplace_id,
    use_live_sandbox_api,
)


SANDBOX_CATALOG_KEYWORDS = "samsung,tv"
SANDBOX_CATALOG_PRODUCT = {
    "asin": "B07N4M94X4",
    "productName": "Samsung QLED TV",
    "brand": "SAMSUNG",
    "upc": "887276302195",
}


def search_catalog(
    product_name: Optional[str] = None,
    asin: Optional[str] = None,
    sku: Optional[str] = None,
) -> Dict[str, str]:
    fallback_product = _build_dynamic_sandbox_product(
        product_name=product_name,
        asin=asin,
        sku=sku,
    )

    if not use_live_sandbox_api():
        return fallback_product

    try:
        access_token = get_lwa_access_token()
        data = _fetch_catalog_sandbox(access_token)
        return _clean_catalog_response(data, fallback_product)
    except Exception:
        return fallback_product


def _fetch_catalog_sandbox(access_token: str) -> Dict[str, Any]:
    url = f"{SP_API_SANDBOX_BASE_URL}/catalog/2022-04-01/items"

    headers = {
        "x-amz-access-token": access_token,
        "Content-Type": "application/json",
    }

    params = {
        "keywords": SANDBOX_CATALOG_KEYWORDS,
        "marketplaceIds": get_marketplace_id(),
        "includedData": (
            "classifications,dimensions,identifiers,images,productTypes,"
            "relationships,salesRanks,summaries,vendorDetails"
        ),
    }

    response = requests.get(url, headers=headers, params=params, timeout=15)
    response.raise_for_status()
    return response.json()


def _clean_catalog_response(
    data: Dict[str, Any],
    fallback_product: Dict[str, str],
) -> Dict[str, str]:
    item = (data.get("items") or [None])[0]
    if not item:
        return deepcopy(fallback_product)

    summary = (item.get("summaries") or [{}])[0]
    upc = ""

    for identifier_group in item.get("identifiers", []):
        for identifier in identifier_group.get("identifiers", []):
            if identifier.get("identifierType") == "UPC":
                upc = identifier.get("identifier", "")
                break
        if upc:
            break

    return {
        "asin": item.get("asin") or fallback_product["asin"],
        "productName": summary.get("itemName")
        or fallback_product["productName"],
        "brand": summary.get("brand") or fallback_product["brand"],
        "upc": upc or fallback_product["upc"],
    }


def _build_dynamic_sandbox_product(
    product_name: Optional[str],
    asin: Optional[str],
    sku: Optional[str],
) -> Dict[str, str]:
    normalized_asin = _normalize_asin(asin)
    seed = product_name or sku or normalized_asin or "samsung tv"

    if not product_name and normalized_asin == SANDBOX_CATALOG_PRODUCT["asin"]:
        return deepcopy(SANDBOX_CATALOG_PRODUCT)

    return {
        "asin": normalized_asin or _generate_asin(seed),
        "productName": _format_product_name(product_name, sku, normalized_asin),
        "brand": _infer_brand(product_name, sku),
        "upc": _generate_upc(seed),
    }


def _normalize_asin(asin: Optional[str]) -> str:
    if not asin:
        return ""

    return re.sub(r"[^A-Za-z0-9]", "", asin).upper()[:10]


def _generate_asin(seed: str) -> str:
    digest = hashlib.sha256(seed.lower().encode("utf-8")).hexdigest().upper()
    return f"B0{digest[:8]}"


def _generate_upc(seed: str) -> str:
    digest = hashlib.sha256(seed.lower().encode("utf-8")).hexdigest()
    return str(int(digest[:12], 16) % 10**12).zfill(12)


def _format_product_name(
    product_name: Optional[str],
    sku: Optional[str],
    asin: Optional[str],
) -> str:
    source = product_name or sku or asin or SANDBOX_CATALOG_PRODUCT["productName"]
    cleaned = re.sub(r"[_,-]+", " ", source).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)

    if not cleaned:
        return SANDBOX_CATALOG_PRODUCT["productName"]

    return " ".join(word.capitalize() for word in cleaned.split(" "))


def _infer_brand(product_name: Optional[str], sku: Optional[str]) -> str:
    source = f"{product_name or ''} {sku or ''}".lower()
    known_brands = {
        "samsung": "SAMSUNG",
        "apple": "APPLE",
        "sony": "SONY",
        "3m": "3M",
        "ansell": "ANSELL",
        "honeywell": "HONEYWELL",
        "dewalt": "DEWALT",
    }

    for token, brand in known_brands.items():
        if token in source:
            return brand

    return "QUESTSAFETY"
