
import hashlib
from datetime import datetime, timezone
import json
import re
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


DATA_DIR = Path(__file__).resolve().parents[1] / "data"
PRODUCTS_FILE = DATA_DIR / "Quest_safety_products.json"
COMPETITORS_FILE = DATA_DIR / "amazon_seller_competitor.json"
MARKUP_MIN_PERCENT = 17.0
MARKUP_MAX_PERCENT = 35.0
AMAZON_REFERRAL_FEE_RATE = 0.15
FBA_FEE_RATE = 0.08
FBA_FEE_MIN = 4.35
FBA_FEE_MAX = 18.0
MIN_SEARCH_GROUP_MATCH_SCORE = 60
MIN_AMAZON_TITLE_MATCH_SCORE = 60
MAX_COMPETITORS_PER_PRODUCT = 5
REPRICE_ACTIONS = {"PUSH_TO_AMAZON", "REPRICE_AND_PUSH"}


def analyze_research_catalog(
    query: Optional[str] = None,
    revenue_threshold: float = 2000,
    min_margin_percent: float = 20,
    priority: str = "researchScore",
    run_id: Optional[str] = None,
    generated_at: Optional[str] = None,
    force_reload: bool = True,
) -> Dict[str, Any]:
    if force_reload:
        clear_research_data_cache()

    generated_at = generated_at or datetime.now(timezone.utc).isoformat()
    run_id = run_id or _fallback_run_id(generated_at)
    products = _load_product_records(PRODUCTS_FILE)
    amazon_payload = _load_amazon_payload(COMPETITORS_FILE)
    amazon_groups = amazon_payload.get("results", [])
    analyses: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    rejected_competitors = 0

    raw_competitor_count = _raw_competitor_count(amazon_groups)
    usable_amazon_match_records = _usable_amazon_match_record_count(amazon_groups)
    grouped_competitor_sku_count = sum(1 for group in amazon_groups if group.get("competitors"))

    for product in products:
        group, group_score = _best_amazon_group(product, amazon_groups)
        if not group:
            skipped.append(
                _skipped_product(
                    product=product,
                    reason="No related Amazon search group met the minimum Quest product-name similarity threshold.",
                    skip_code="NO_SEARCH_GROUP",
                    search_group_score=group_score,
                )
            )
            continue

        raw = len(group.get("competitors") or [])
        candidates = _valid_competitor_candidates(product, group, group_score)
        rejected_competitors += max(0, raw - len(candidates))

        if not candidates:
            skipped.append(
                _skipped_product(
                    product=product,
                    reason="No Amazon candidate cleared the 45% title-match, buy-box, ASIN, URL, and image gates.",
                    skip_code="NO_VALID_AMAZON_COMPETITOR",
                    search_group_score=group_score,
                    amazon_input=group.get("input_product_name"),
                )
            )
            continue

        analyses.append(
            _analyze_product(
                product=product,
                competitor_candidates=candidates,
                source_group=group,
                search_group_score=group_score,
                revenue_threshold=revenue_threshold,
                min_margin_percent=min_margin_percent,
            )
        )

    all_results = analyses + skipped
    filtered = _filter_results(all_results, query)
    sorted_results = _sort_results(filtered, priority)
    summary = _build_summary(sorted_results)
    full_summary = _build_summary(all_results)
    matched_competitors = sum(len(item.get("competitors") or []) for item in analyses)
    skipped_products = [_skip_metadata(item) for item in skipped]
    data_signature = data_source_signature()

    metadata = {
        "runId": run_id,
        "generatedAt": generated_at,
        "dataSignature": data_signature,
        "productCount": len(all_results),
        "resultCount": len(sorted_results),
        "finalResultCount": len(all_results),
        "sourceProductCount": len(products),
        "analyzedProductCount": len(analyses),
        "riskCategorizedCount": len(analyses),
        "competitorMatchedProductCount": full_summary["competitorMatchedProductCount"],
        "marginQualifiedProductCount": full_summary["marginQualifiedCount"],
        "revenueQualifiedProductCount": full_summary["revenueQualifiedCount"],
        "reviewQueueCount": full_summary["reviewCount"],
        "approvedProductCount": full_summary["pushCount"],
        "listableProductCount": full_summary["pushCount"],
        "skippedProductCount": len(skipped),
        "unmatchedProductCount": len(skipped),
        "rawAmazonSearchGroupCount": len(amazon_groups),
        "groupedCompetitorSkuCount": grouped_competitor_sku_count,
        "rawAmazonCompetitorCount": raw_competitor_count,
        "competitorRecordCount": raw_competitor_count,
        "usableAmazonMatchRecordCount": usable_amazon_match_records,
        "competitorCount": matched_competitors,
        "qualifiedCompetitorCount": matched_competitors,
        "rejectedCompetitorCount": rejected_competitors,
        "competitorsPerProduct": MAX_COMPETITORS_PER_PRODUCT,
        "query": query or "",
        "priority": priority,
        "minimumSearchGroupMatchScore": MIN_SEARCH_GROUP_MATCH_SCORE,
        "minimumAmazonTitleMatchScore": MIN_AMAZON_TITLE_MATCH_SCORE,
        "competitorBrands": amazon_payload.get("competitor_brands", []),
        "criteria": {
            "monthlyRevenueGreaterThan": revenue_threshold,
            "minimumContributionMarginPercent": min_margin_percent,
            "amazonTitleMatchAtLeastPercent": MIN_AMAZON_TITLE_MATCH_SCORE,
            "buyBoxPriceRequired": True,
            "asinUrlImageRequired": True,
            "fbaCompetitiveRequired": True,
            "costBasis": "Highest positive supplier cost from the QuestSafety ERP product record.",
        },
        "debug": {
            "sourceProductCount": len(products),
            "competitorRecordCount": raw_competitor_count,
            "usableAmazonMatchRecordCount": usable_amazon_match_records,
            "groupedCompetitorSkuCount": grouped_competitor_sku_count,
            "finalResultCount": len(all_results),
            "analyzedProductCount": len(analyses),
            "skippedCount": len(skipped),
            "timestamp": generated_at,
            "runId": run_id,
        },
        "estimateNote": (
            "QuestSafety ERP products are matched to SP-API competitor records. Only Amazon "
            "records with ASIN, URL, image, buy-box price, and 60%+ title match are used."
        ),
        "normalizationNote": (
            "Package prices are converted to comparable unit prices from product descriptions, "
            "pack/count text, and case/box notation."
        ),
        "skippedProducts": skipped_products,
        "unmatchedProducts": skipped_products,
    }

    return {
        "runId": run_id,
        "generatedAt": generated_at,
        "isReady": True,
        "metadata": metadata,
        "summary": summary,
        "results": sorted_results,
    }


def clear_research_data_cache() -> None:
    _load_product_records.cache_clear()
    _load_amazon_payload.cache_clear()


def data_source_signature() -> Dict[str, Any]:
    return {
        "products": _file_signature(PRODUCTS_FILE),
        "competitors": _file_signature(COMPETITORS_FILE),
    }


def summarize_research_results(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    return _build_summary(results)


def _file_signature(path: Path) -> Dict[str, Any]:
    stat = path.stat()
    identity = f"{path.name}:{stat.st_size}:{stat.st_mtime_ns}"
    return {
        "name": path.name,
        "path": str(path),
        "sizeBytes": stat.st_size,
        "modifiedTimeNs": stat.st_mtime_ns,
        "fingerprint": hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20],
    }


def _fallback_run_id(generated_at: str) -> str:
    seed = f"{generated_at}:{data_source_signature()}"
    return f"research-{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:12]}"


def _raw_competitor_count(groups: List[Dict[str, Any]]) -> int:
    return sum(len(group.get("competitors") or []) for group in groups)


def _usable_amazon_match_record_count(groups: List[Dict[str, Any]]) -> int:
    count = 0
    for group in groups:
        for competitor in group.get("competitors") or []:
            match = _competitor_match_payload(competitor)
            asin = _normalize_asin(match.get("asin") or competitor.get("selected_asin"))
            if asin:
                count += 1
    return count


def _group_input_product(group: Dict[str, Any]) -> Dict[str, Any]:
    value = group.get("input_product")
    return value if isinstance(value, dict) else {}


def _group_sku(group: Dict[str, Any]) -> str:
    product = _group_input_product(group)
    return str(
        product.get("sku")
        or group.get("source_quest_sku")
        or group.get("sku")
        or ""
    ).strip()


def _group_name(group: Dict[str, Any]) -> str:
    product = _group_input_product(group)
    return str(
        group.get("input_product_name")
        or product.get("name")
        or product.get("Product Name")
        or ""
    ).strip()


def _group_match_text(group: Dict[str, Any]) -> str:
    product = _group_input_product(group)
    return " ".join(
        str(part or "")
        for part in [
            _group_sku(group),
            product.get("manufacturer"),
            _group_name(group),
            product.get("description"),
            product.get("raw"),
        ]
    ).strip()


def _is_header_amazon_group(group: Dict[str, Any]) -> bool:
    sku = _normalize_text(_group_sku(group))
    name = _normalize_text(_group_name(group))
    return sku == "sku" or name == "product name"


def _competitor_match_payload(competitor: Dict[str, Any]) -> Dict[str, Any]:
    match = competitor.get("match")
    if isinstance(match, dict):
        return match
    return competitor



def _skip_metadata(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "sku": item.get("sku"),
        "name": item.get("name"),
        "reason": item.get("skipReason") or item.get("reason"),
        "skipCode": item.get("skipCode"),
        "amazonSearchInput": item.get("amazonSearchInput"),
        "searchGroupMatchScore": item.get("searchGroupMatchScore", 0),
    }


@lru_cache(maxsize=4)
def _load_product_records(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    return data if isinstance(data, list) else data.get("records", [])


@lru_cache(maxsize=4)
def _load_amazon_payload(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    return data if isinstance(data, dict) else {"results": []}


def _best_amazon_group(product: Dict[str, Any], groups: List[Dict[str, Any]]) -> Tuple[Optional[Dict[str, Any]], float]:
    product_text = _product_match_text(product)
    product_sku = _normalize_text(_product_sku(product))

    # Strongest path: exact SKU match between Quest ERP and the new_file Amazon JSON.
    if product_sku:
        for group in groups:
            if _is_header_amazon_group(group):
                continue
            group_sku = _normalize_text(_group_sku(group))
            if group_sku and group_sku == product_sku:
                return group, 100.0

    best_group = None
    best_score = 0.0
    for group in groups:
        if _is_header_amazon_group(group):
            continue
        score = _text_similarity(product_text, _group_match_text(group))
        if score > best_score:
            best_score = score
            best_group = group

    if best_group and best_score >= MIN_SEARCH_GROUP_MATCH_SCORE:
        return best_group, round(best_score, 2)

    return None, round(best_score, 2)


def _valid_competitor_candidates(product: Dict[str, Any], group: Dict[str, Any], group_score: float) -> List[Dict[str, Any]]:
    product_text = _product_match_text(product)
    candidates = []

    for index, competitor in enumerate(group.get("competitors") or [], start=1):
        match = _competitor_match_payload(competitor)
        if not isinstance(match, dict):
            continue

        asin = _normalize_asin(
            match.get("asin")
            or competitor.get("selected_asin")
            or competitor.get("asin")
        )
        title = str(
            match.get("matched_amazon_product_title")
            or match.get("title")
            or match.get("matchedAmazonTitle")
            or ""
        ).strip()
        product_url = str(
            match.get("product_url")
            or match.get("amazonProductUrl")
            or match.get("amazon_product_url")
            or competitor.get("product_url")
            or ""
        ).strip()
        image_url = str(
            match.get("image_url")
            or match.get("imageUrl")
            or competitor.get("image_url")
            or competitor.get("imageUrl")
            or ""
        ).strip()
        buy_box_price = _money_amount(
            match.get("buy_box_price")
            or match.get("buyBoxPrice")
            or competitor.get("buy_box_price")
            or competitor.get("buyBoxPrice")
        )

        if not asin or not title or not product_url or not image_url or buy_box_price <= 0:
            continue

        extractor_score = _number(
            match.get("product_match_score")
            or match.get("matchScore")
            or competitor.get("product_match_score")
            or competitor.get("matchScore")
        )
        title_score = _text_similarity(product_text, title)
        match_score = round(max(extractor_score, title_score), 2)
        if match_score < MIN_AMAZON_TITLE_MATCH_SCORE:
            continue

        seller = (
            match.get("buy_box_competitor_seller")
            or match.get("buyBoxSeller")
            or competitor.get("buy_box_competitor_seller")
            or {}
        )
        competitor_text = _competitor_description_text(match)
        normalization = _normalize_price(buy_box_price, competitor_text, _unit_type_for_text(product_text))
        competitor_brand = (
            competitor.get("competitor_brand")
            or competitor.get("competitorBrand")
            or match.get("competitor_brand")
            or match.get("competitor_name")
            or match.get("product_competitor")
            or "Amazon competitor"
        )
        candidates.append(
            {
                "sourceRank": index,
                "competitorBrand": competitor_brand,
                "searchQuery": competitor.get("search_query") or match.get("search_query") or "",
                "selectionReason": competitor.get("selection_reason") or match.get("selection_reason") or "",
                "asin": asin,
                "title": title,
                "description": match.get("description") or "",
                "bulletPoints": match.get("bullet_points") or match.get("bulletPoints") or [],
                "imageUrl": image_url,
                "amazonProductUrl": product_url,
                "productCompetitor": match.get("product_competitor") or match.get("competitor_name") or competitor_brand,
                "productType": match.get("product_type") or match.get("productType"),
                "salesRank": match.get("sales_rank") or match.get("salesRank"),
                "buyBoxPrice": round(buy_box_price, 2),
                "listPrice": _optional_money(match.get("list_price") or match.get("listPrice")),
                "numberOfOffers": match.get("number_of_offers") or match.get("numberOfOffers"),
                "monthlyBoughtRaw": match.get("monthly_bought_raw") or match.get("monthlyBoughtRaw"),
                "monthlyBoughtLowerBound": match.get("monthly_bought_lower_bound") or match.get("monthlyBoughtLowerBound"),
                "monthlyBoughtIsLowerBound": match.get("monthly_bought_is_lower_bound") or match.get("monthlyBoughtIsLowerBound"),
                "unitsSoldLastMonth": match.get("units_sold_last_month") or match.get("unitsSoldLastMonth"),
                "buyBoxSeller": seller,
                "fulfillmentType": "FBA" if seller.get("is_fulfilled_by_amazon") or seller.get("isFulfilledByAmazon") else "FBM",
                "matchScore": match_score,
                "extractorMatchScore": round(extractor_score, 2),
                "titleSimilarityScore": round(title_score, 2),
                "searchGroupMatchScore": group_score,
                "matchConfidence": _match_confidence(match_score),
                "normalization": normalization,
            }
        )

    candidates.sort(
        key=lambda item: (
            -_number(item.get("matchScore")),
            _number(item.get("normalization", {}).get("unitPrice")),
            item.get("sourceRank", 999),
        )
    )
    return candidates[:MAX_COMPETITORS_PER_PRODUCT]


def _analyze_product(
    product: Dict[str, Any],
    competitor_candidates: List[Dict[str, Any]],
    source_group: Dict[str, Any],
    search_group_score: float,
    revenue_threshold: float,
    min_margin_percent: float,
) -> Dict[str, Any]:
    vendor_cost = _product_cost(product)
    markup_percent = _product_markup_percent(product)
    base_price = _product_sale_price(product, vendor_cost, markup_percent)
    sku = _product_sku(product)
    category = _product_category(product)
    monthly_units = _estimate_monthly_units(product)
    target_margin_percent = _target_margin_percent(product, min_margin_percent)
    price_normalization = _product_price_normalization(product, vendor_cost, base_price)
    min_viable_price = _price_for_margin(vendor_cost, category, min_margin_percent)
    target_margin_price = _price_for_margin(vendor_cost, category, target_margin_percent)
    competitors = _build_competitor_analysis(competitor_candidates, price_normalization, monthly_units)
    lowest_fba = _lowest_fba_market(competitors, price_normalization)
    lowest_fba_price = lowest_fba["packageEquivalentPrice"]
    recommended_price = _recommended_price(base_price, lowest_fba_price, min_viable_price, target_margin_price)
    economics = _estimate_economics(
        product,
        vendor_cost,
        base_price,
        recommended_price,
        markup_percent,
        min_margin_percent,
        target_margin_percent,
        price_normalization,
    )
    monthly_revenue = round(recommended_price * monthly_units, 2)
    can_compete_fba = lowest_fba_price > 0 and recommended_price <= lowest_fba_price * 1.02
    primary = competitors[0]
    match_score = _number(primary.get("matchScore"))
    match_confidence = primary.get("matchConfidence") or "unknown"
    risk_analysis = _risk_analysis(
        product,
        economics,
        monthly_revenue,
        revenue_threshold,
        min_margin_percent,
        can_compete_fba,
        match_confidence,
        match_score,
        price_normalization,
    )
    criteria = {
        "catalogMatch": {
            "passed": match_score >= MIN_AMAZON_TITLE_MATCH_SCORE,
            "actual": match_score,
            "threshold": MIN_AMAZON_TITLE_MATCH_SCORE,
            "explanation": f"Best Amazon title match is {match_score:.1f}%, above the {MIN_AMAZON_TITLE_MATCH_SCORE:.0f}% requirement.",
        },
        "revenue": {
            "passed": monthly_revenue >= revenue_threshold,
            "actual": monthly_revenue,
            "threshold": revenue_threshold,
            "explanation": f"Estimated monthly revenue is ${monthly_revenue:,.0f}, measured against the ${revenue_threshold:,.0f} threshold.",
        },
        "fbaCompetitive": {
            "passed": can_compete_fba,
            "actual": lowest_fba_price,
            "threshold": economics["minViablePrice"],
            "explanation": (
                "Quest can meet or beat the lowest normalized FBA buy-box price while protecting margin."
                if can_compete_fba
                else "The lowest normalized FBA buy-box price is below the margin-safe recommended price."
            ),
        },
        "margin": {
            "passed": economics["contributionMarginPercent"] >= min_margin_percent,
            "actual": economics["contributionMarginPercent"],
            "threshold": min_margin_percent,
            "explanation": (
                f"Recommended package price is ${recommended_price:,.2f}. It protects at least "
                f"{min_margin_percent:.1f}% contribution margin after estimated referral, FBA, and prep costs. "
                f"Projected margin is {economics['contributionMarginPercent']:.1f}%."
            ),
        },
    }
    decision = _decision(criteria, risk_analysis, base_price, recommended_price)
    score = _research_score(criteria, economics, monthly_revenue, revenue_threshold, risk_analysis)

    return {
        "recordId": sku,
        "analysisStatus": "ANALYZED",
        "isSkipped": False,
        "skipReason": "",
        "skipCode": None,
        "status": decision.get("label"),
        "sku": sku,
        "asin": primary.get("asin"),
        "name": _product_name(product),
        "description": _product_description(product),
        "brand": _product_brand(product),
        "manufacturer": _product_manufacturer(product),
        "manufacturerType": _product_manufacturer_type(product),
        "manufacturerLabel": _product_manufacturer_label(product),
        "category": category,
        "imageUrl": primary.get("imageUrl"),
        "questProductUrl": None,
        "amazonProductUrl": primary.get("amazonProductUrl"),
        "matchedAmazonTitle": primary.get("title"),
        "matchScore": match_score,
        "amazonSearchInput": _group_name(source_group),
        "searchGroupMatchScore": search_group_score,
        "Cost": vendor_cost,
        "markupPercent": markup_percent,
        "price": base_price,
        "priceNormalization": price_normalization,
        "monthlyUnits": monthly_units,
        "monthlyRevenue": monthly_revenue,
        "economics": economics,
        "competitors": competitors,
        "criteria": criteria,
        "riskAnalysis": risk_analysis,
        "decision": decision,
        "researchScore": score,
        "recommendedAmazonPrice": recommended_price,
        "pricingBasis": _pricing_basis(
            base_price,
            recommended_price,
            lowest_fba,
            min_margin_percent,
            target_margin_percent,
            price_normalization,
        ),
        "pushRecommendation": _push_recommendation(product, primary.get("asin"), decision, recommended_price, risk_analysis),
        "explanation": _build_explanation(criteria, decision, risk_analysis, competitors, lowest_fba, price_normalization),
    }


def _estimate_monthly_units(product: Dict[str, Any]) -> int:
    category = _product_category(product)
    base_units = _stable_int(_product_sku(product), 12, 105)
    boost = 1.0
    if "Coverall" in category:
        boost = 1.18
    elif "Glove" in category:
        boost = 1.28
    elif "Hard Hat" in category:
        boost = 1.12
    elif "Respirator" in category or "Mask" in category:
        boost = 1.22
    return max(4, round(base_units * boost))


def _estimate_economics(product, vendor_cost, base_price, sale_price, markup_percent, min_margin_percent, target_margin_percent, normalization):
    category = _product_category(product)
    referral_fee = round(sale_price * AMAZON_REFERRAL_FEE_RATE, 2)
    fba_fee = _estimate_fba_fee(sale_price)
    prep_cost = round(_category_prep_cost(category), 2)
    profit = round(sale_price - vendor_cost - referral_fee - fba_fee - prep_cost, 2)
    margin = round((profit / sale_price) * 100, 2) if sale_price else 0
    quantity = _number(normalization.get("packageQuantity")) or 1
    return {
        "Cost": round(vendor_cost, 2),
        "basePrice": round(base_price, 2),
        "salePrice": round(sale_price, 2),
        "recommendedPrice": round(sale_price, 2),
        "recommendedUnitPrice": round(sale_price / quantity, 4),
        "baseUnitPrice": round(base_price / quantity, 4),
        "unitCost": round(vendor_cost / quantity, 4),
        "packageQuantity": quantity,
        "unitType": normalization.get("unitType") or "each",
        "costMarkupPercent": markup_percent,
        "grossMarkupDollars": round(sale_price - vendor_cost, 2),
        "estimatedProductCost": round(vendor_cost, 2),
        "amazonReferralFee": referral_fee,
        "estimatedFbaFee": fba_fee,
        "shippingPrepCost": prep_cost,
        "profitPerUnit": profit,
        "contributionMarginPercent": margin,
        "minViablePrice": _price_for_margin(vendor_cost, category, min_margin_percent),
        "requiredMarginPercent": min_margin_percent,
        "targetMarginPercent": target_margin_percent,
    }


def _build_competitor_analysis(candidates, product_normalization, monthly_units):
    competitors = []
    quest_quantity = _number(product_normalization.get("packageQuantity")) or 1
    for candidate in candidates:
        seller = candidate.get("buyBoxSeller") or {}
        price = _number(candidate.get("buyBoxPrice"))
        normalization = candidate.get("normalization") or {}
        unit_price = _number(normalization.get("unitPrice")) or price
        estimated_units = _competitor_monthly_units(candidate, monthly_units)
        competitors.append(
            {
                "rank": len(competitors) + 1,
                "sellerName": seller.get("competitor_name") or candidate.get("productCompetitor") or candidate.get("competitorBrand") or "Amazon competitor",
                "buyBoxSeller": seller.get("competitor_name") or seller.get("seller_id") or "",
                "sellerProfileUrl": seller.get("seller_profile_url"),
                "brand": candidate.get("productCompetitor") or candidate.get("competitorBrand") or "Unknown",
                "competitorBrand": candidate.get("competitorBrand"),
                "asin": candidate.get("asin"),
                "title": candidate.get("title"),
                "description": candidate.get("description") or _first(candidate.get("bulletPoints"), ""),
                "bulletPoints": candidate.get("bulletPoints") or [],
                "imageUrl": candidate.get("imageUrl"),
                "category": _sales_rank_category(candidate.get("salesRank")) or candidate.get("productType"),
                "fulfillmentType": candidate.get("fulfillmentType"),
                "estimatedPrice": round(price, 2),
                "buyBoxPrice": round(price, 2),
                "listPrice": candidate.get("listPrice"),
                "normalizedUnitPrice": round(unit_price, 4),
                "packageEquivalentPrice": round(unit_price * quest_quantity, 2),
                "normalization": normalization,
                "priceSource": "buy_box",
                "estimatedMonthlyRevenue": round(price * estimated_units, 2),
                "matchConfidence": candidate.get("matchConfidence") or "unknown",
                "matchScore": candidate.get("matchScore"),
                "titleSimilarityScore": candidate.get("titleSimilarityScore"),
                "searchGroupMatchScore": candidate.get("searchGroupMatchScore"),
                "amazonProductUrl": candidate.get("amazonProductUrl"),
                "amazonSearchUrl": candidate.get("searchQuery"),
                "reason": candidate.get("selectionReason"),
                "numberOfOffers": candidate.get("numberOfOffers"),
                "salesRank": candidate.get("salesRank"),
                "monthlyBoughtRaw": candidate.get("monthlyBoughtRaw"),
                "monthlyBoughtLowerBound": candidate.get("monthlyBoughtLowerBound"),
                "monthlyBoughtIsLowerBound": candidate.get("monthlyBoughtIsLowerBound"),
                "unitsSoldLastMonth": candidate.get("unitsSoldLastMonth"),
                "feedbackRating": seller.get("seller_positive_feedback_rating"),
                "feedbackCount": seller.get("feedback_count"),
            }
        )
    return _rerank_competitors(competitors)


def _competitor_monthly_units(candidate, product_monthly_units):
    score = _number(candidate.get("matchScore"))
    rank = int(candidate.get("sourceRank") or 1)
    match_factor = min(1.15, max(0.72, score / 82))
    rank_factor = max(0.58, 1.08 - rank * 0.08)
    return max(2, round(product_monthly_units * match_factor * rank_factor))


def _risk_analysis(product, economics, monthly_revenue, revenue_threshold, min_margin_percent, can_compete_fba, match_confidence, match_score, normalization):
    margin_buffer = round(economics["contributionMarginPercent"] - min_margin_percent, 2)
    factors = [
        _factor(
            "Revenue quality",
            "LOW" if monthly_revenue >= revenue_threshold else "HIGH",
            "Estimated demand clears the monthly revenue threshold." if monthly_revenue >= revenue_threshold else "Estimated revenue is below the push threshold.",
        ),
        _factor(
            "Margin buffer",
            "LOW" if margin_buffer >= 4 else "MEDIUM" if margin_buffer >= 0 else "HIGH",
            f"Margin has {margin_buffer:.1f}% buffer above requirement." if margin_buffer >= 0 else f"Margin is {abs(margin_buffer):.1f}% below requirement.",
        ),
        _factor(
            "FBA competitiveness",
            "LOW" if can_compete_fba else "HIGH",
            "Quest can be lowest or competitive FBA seller on normalized unit price." if can_compete_fba else "Quest cannot safely match the lowest normalized FBA price.",
        ),
        _factor(
            "Amazon title match",
            _confidence_level(match_confidence),
            f"Best Amazon product title match is {match_score:.1f}% ({match_confidence}).",
        ),
        _factor(
            "Price normalization",
            "LOW" if normalization.get("packageQuantity", 1) != 1 else "MEDIUM",
            normalization.get("evidence") or "No package quantity was detected; pricing is compared as one unit.",
        ),
        _factor("Category compliance", _category_risk_level(product), _category_risk_message(product)),
    ]
    score = _risk_score(factors)
    return {
        "score": score,
        "level": _risk_level(score),
        "factors": factors,
        "marginBufferPercent": margin_buffer,
        "summary": _risk_summary(factors),
    }


def _push_recommendation(product, asin, decision, recommended_price, risk_analysis):
    should_push = decision["action"] in REPRICE_ACTIONS
    is_reprice = decision["action"] == "REPRICE_AND_PUSH"
    return {
        "shouldPush": should_push,
        "action": "REPRICE_AND_UPDATE_LISTING" if is_reprice else "CREATE_OR_UPDATE_LISTING" if should_push else "HUMAN_REVIEW",
        "priceAction": "Reprice and push listing" if is_reprice else "Set Amazon listing price" if should_push else "Do not update Amazon yet",
        "sku": _product_sku(product),
        "asin": asin,
        "recommendedPrice": recommended_price,
        "currencyCode": "USD",
        "message": (
            "Reprice candidate: recommended price clears margin, FBA, match, and risk checks."
            if is_reprice
            else "Push candidate: criteria clear and risk is controlled."
            if should_push
            else "Hold for review: one or more criteria or risk checks failed."
        ),
        "nextSteps": _push_next_steps(should_push),
        "riskLevel": risk_analysis["level"],
    }


def _decision(criteria, risk_analysis, base_price, recommended_price):
    passed = all(item["passed"] for item in criteria.values())
    low_or_medium_risk = risk_analysis["level"] in {"LOW", "MEDIUM"}
    if passed and low_or_medium_risk:
        if abs(recommended_price - base_price) >= 0.02:
            return {
                "action": "REPRICE_AND_PUSH",
                "label": "Reprice & Push",
                "reason": "Revenue, normalized FBA competitiveness, match quality, margin, and risk checks are acceptable after using the recommended Amazon price.",
            }
        return {
            "action": "PUSH_TO_AMAZON",
            "label": "Push to Amazon",
            "reason": "Revenue, normalized FBA competitiveness, match quality, margin, and risk checks are acceptable.",
        }
    return {
        "action": "HUMAN_REVIEW",
        "label": "Human Review",
        "reason": "At least one push gate needs review before Amazon listing changes.",
    }


def _research_score(criteria, economics, monthly_revenue, revenue_threshold, risk_analysis):
    revenue_score = min(100, round((monthly_revenue / max(revenue_threshold, 1)) * 100))
    margin_score = min(100, max(0, round(economics["contributionMarginPercent"] * 3)))
    fba_score = 100 if criteria["fbaCompetitive"]["passed"] else 35
    match_score = min(100, max(0, round(_number(criteria["catalogMatch"]["actual"]))))
    risk_component = max(0, 100 - int(risk_analysis["score"]))
    return round(revenue_score * 0.26 + margin_score * 0.24 + fba_score * 0.2 + match_score * 0.16 + risk_component * 0.14)


def _build_explanation(criteria, decision, risk_analysis, competitors, lowest_fba, normalization):
    competitor_names = ", ".join(competitor["sellerName"] for competitor in competitors[:3])
    unit_type = normalization.get("unitType") or "each"
    lowest_package = lowest_fba.get("packageEquivalentPrice") or 0
    lowest_unit = lowest_fba.get("normalizedUnitPrice") or 0
    return [
        criteria["catalogMatch"]["explanation"],
        criteria["revenue"]["explanation"],
        criteria["margin"]["explanation"],
        criteria["fbaCompetitive"]["explanation"],
        f"Lowest normalized FBA buy-box competitor is ${lowest_package:,.2f} per Quest package, or ${lowest_unit:,.4f} per {unit_type}." if lowest_package else "No FBA buy-box competitor cleared the Amazon match and price gates.",
        f"Primary competitor brands/sellers: {competitor_names}.",
        f"Risk level is {risk_analysis['level']} because {risk_analysis['summary']}",
        decision["reason"],
    ]


def _build_summary(results):
    analyzed = [item for item in results if not _is_skipped_item(item)]
    skipped = [item for item in results if _is_skipped_item(item)]
    push_count = sum(1 for item in analyzed if _is_live_listing_summary(item))
    review_count = sum(1 for item in analyzed if item.get("decision", {}).get("action") == "HUMAN_REVIEW")
    margin_qualified = sum(1 for item in analyzed if item.get("criteria", {}).get("margin", {}).get("passed"))
    revenue_qualified = sum(1 for item in analyzed if item.get("criteria", {}).get("revenue", {}).get("passed"))
    competitor_matched = sum(1 for item in analyzed if item.get("competitors"))
    total_revenue = round(sum(_number(item.get("monthlyRevenue")) for item in analyzed), 2)
    weighted_margin = (
        round(
            sum(
                _number(item.get("monthlyRevenue"))
                * _number(item.get("economics", {}).get("contributionMarginPercent"))
                for item in analyzed
            )
            / total_revenue,
            2,
        )
        if total_revenue
        else 0
    )
    average_score = round(sum(_number(item.get("researchScore")) for item in analyzed) / len(analyzed)) if analyzed else 0
    risk_counts = {
        "low": sum(1 for item in analyzed if item.get("riskAnalysis", {}).get("level") == "LOW"),
        "medium": sum(1 for item in analyzed if item.get("riskAnalysis", {}).get("level") == "MEDIUM"),
        "high": sum(1 for item in analyzed if item.get("riskAnalysis", {}).get("level") == "HIGH"),
        "skipped": len(skipped),
    }
    return {
        "resultCount": len(results),
        "productCount": len(results),
        "analyzedCount": len(analyzed),
        "riskCategorizedCount": len(analyzed),
        "competitorMatchedProductCount": competitor_matched,
        "marginQualifiedCount": margin_qualified,
        "revenueQualifiedCount": revenue_qualified,
        "pushCount": push_count,
        "approvedCount": push_count,
        "listableProductCount": push_count,
        "reviewCount": review_count,
        "skippedCount": len(skipped),
        "unmatchedCount": len(skipped),
        "variantCollapsedCount": 0,
        "averageScore": average_score,
        "averageMarginPercent": weighted_margin,
        "weightedMarginPercent": weighted_margin,
        "totalEstimatedMonthlyRevenue": total_revenue,
        "riskBreakdown": risk_counts,
    }


def _filter_results(results, query):
    if not query:
        return results
    needle = query.lower().strip()
    filtered = []
    for item in results:
        haystack = " ".join(
            [
                str(item.get("sku", "")),
                str(item.get("asin", "")),
                str(item.get("name", "")),
                str(item.get("description", "")),
                str(item.get("brand", "")),
                str(item.get("category", "")),
                str(item.get("matchedAmazonTitle", "")),
                str(item.get("analysisStatus", "")),
                str(item.get("skipReason", "")),
                str(item.get("skipCode", "")),
                str(item.get("decision", {}).get("label", "")),
                " ".join(str(c.get("asin", "")) for c in item.get("competitors", [])),
                " ".join(str(c.get("title", "")) for c in item.get("competitors", [])),
            ]
        ).lower()
        if needle in haystack:
            filtered.append(item)
    return filtered


def _sort_results(results, priority):
    if priority == "sku":
        return sorted(results, key=lambda item: (_is_skipped_item(item), str(item.get("sku", "")).lower()))
    if priority == "status":
        return sorted(results, key=lambda item: (_status_rank(item), str(item.get("sku", "")).lower()))

    sorters = {
        "revenue": lambda item: _number(item.get("monthlyRevenue")),
        "margin": lambda item: _number(item.get("economics", {}).get("contributionMarginPercent")),
        "risk": lambda item: _number(item.get("riskAnalysis", {}).get("score")),
        "match": lambda item: _number(item.get("matchScore")),
        "researchScore": lambda item: _number(item.get("researchScore")),
    }
    sorter = sorters.get(priority, sorters["researchScore"])
    return sorted(results, key=lambda item: (0 if not _is_skipped_item(item) else -1, sorter(item)), reverse=True)


def _is_skipped_item(item):
    return bool(item.get("isSkipped") or item.get("analysisStatus") == "SKIPPED" or item.get("decision", {}).get("action") == "SKIPPED")


def _is_live_listing_summary(item):
    return item.get("approvalStatus") == "APPROVED_BY_USER" or item.get("decision", {}).get("action") in REPRICE_ACTIONS


def _status_rank(item):
    if _is_skipped_item(item):
        return 4
    action = item.get("decision", {}).get("action")
    if action in REPRICE_ACTIONS:
        return 0
    if action == "HUMAN_REVIEW":
        return 2
    return 3


def _recommended_price(current_price, lowest_fba_price, min_viable_price, target_margin_price):
    if not lowest_fba_price:
        return round(max(current_price, target_margin_price, min_viable_price), 2)
    competitor_beat = round(lowest_fba_price - 0.01, 2)
    if competitor_beat >= min_viable_price:
        return round(min(max(current_price, target_margin_price, min_viable_price), competitor_beat), 2)
    return round(max(current_price, min_viable_price), 2)


def _rerank_competitors(competitors):
    for index, competitor in enumerate(competitors, start=1):
        competitor["rank"] = index
    return competitors


def _pricing_basis(base_price, recommended_price, lowest_fba, min_margin_percent, target_margin_percent, normalization):
    quantity = _number(normalization.get("packageQuantity")) or 1
    unit_type = normalization.get("unitType") or "each"
    return {
        "basePrice": round(base_price, 2),
        "baseUnitPrice": round(base_price / quantity, 4),
        "recommendedPrice": round(recommended_price, 2),
        "recommendedUnitPrice": round(recommended_price / quantity, 4),
        "lowestFbaCompetitorPrice": round(_number(lowest_fba.get("packageEquivalentPrice")), 2),
        "lowestFbaCompetitorUnitPrice": round(_number(lowest_fba.get("normalizedUnitPrice")), 4),
        "lowestFbaCompetitorAsin": lowest_fba.get("asin"),
        "lowestFbaCompetitorTitle": lowest_fba.get("title"),
        "requiredMarginPercent": round(min_margin_percent, 2),
        "targetMarginPercent": round(target_margin_percent, 2),
        "packageQuantity": quantity,
        "unitType": unit_type,
        "normalizationEvidence": normalization.get("evidence"),
        "notes": [
            "Recommended price protects the required contribution margin after estimated referral, FBA, and prep costs.",
            "Amazon buy-box prices are normalized to a unit price before comparing against the Quest package quantity.",
        ],
    }


def _product_price_normalization(product, vendor_cost, sale_price):
    text = _product_match_text(product)
    quantity, unit_type, evidence = _extract_package_quantity(text)
    quantity = quantity or _number(product.get("SalesPricingUnitSize")) or 1
    if not evidence:
        unit_type = "each"
    return {
        "packagePrice": round(sale_price, 2),
        "packageCost": round(vendor_cost, 2),
        "packageQuantity": quantity,
        "packageUnit": product.get("SalesPricingUnit") or product.get("DefaultSellingUnit") or "EA",
        "unitType": unit_type or _unit_type_for_text(text),
        "unitPrice": round(sale_price / quantity, 4) if quantity else sale_price,
        "unitCost": round(vendor_cost / quantity, 4) if quantity else vendor_cost,
        "evidence": evidence or "No package quantity found; compared as one sellable unit.",
    }


def _normalize_price(price, text, fallback_unit):
    quantity, unit_type, evidence = _extract_package_quantity(text)
    quantity = quantity or 1
    if not evidence:
        unit_type = fallback_unit or "each"
    else:
        unit_type = unit_type or fallback_unit or _unit_type_for_text(text)
    return {
        "packagePrice": round(price, 2),
        "packageQuantity": quantity,
        "unitType": unit_type,
        "unitPrice": round(price / quantity, 4),
        "evidence": evidence or "No package quantity found; compared as one sellable unit.",
    }


def _lowest_fba_market(competitors, normalization):
    fba = [item for item in competitors if item.get("fulfillmentType") == "FBA" and _number(item.get("normalizedUnitPrice")) > 0]
    if not fba:
        return {"packageEquivalentPrice": 0, "normalizedUnitPrice": 0, "asin": None, "title": None}
    lowest = min(fba, key=lambda item: _number(item.get("normalizedUnitPrice")))
    quantity = _number(normalization.get("packageQuantity")) or 1
    return {
        "packageEquivalentPrice": round(_number(lowest.get("normalizedUnitPrice")) * quantity, 2),
        "normalizedUnitPrice": round(_number(lowest.get("normalizedUnitPrice")), 4),
        "asin": lowest.get("asin"),
        "title": lowest.get("title"),
        "sellerName": lowest.get("sellerName"),
        "amazonProductUrl": lowest.get("amazonProductUrl"),
    }


def _product_cost(product):
    costs = [_number(s.get("Cost")) for s in product.get("Suppliers", []) if _number(s.get("Cost")) > 0]
    if costs:
        return round(max(costs), 2)
    return round(_number(product.get("Cost")) or _number(product.get("Price4")) or 0, 2)


def _product_markup_percent(product):
    cost = _product_cost(product)
    price = _erp_sale_price(product)
    if cost > 0 and price > 0:
        return round(((price - cost) / cost) * 100, 2)
    return _cost_markup_percent(product)


def _product_sale_price(product, vendor_cost, markup_percent):
    sale_price = _erp_sale_price(product)
    if sale_price > 0:
        return round(sale_price, 2)
    return _sale_price_from_cost(vendor_cost, markup_percent)


def _erp_sale_price(product):
    for key in ("Price1", "Price2", "Price3", "Price4"):
        value = _number(product.get(key))
        if value > 0:
            return value
    return 0


def _cost_markup_percent(product):
    seed = f"{_product_sku(product)}:markup"
    basis_points = _stable_int(seed, round(MARKUP_MIN_PERCENT * 100), round(MARKUP_MAX_PERCENT * 100))
    cents = _stable_int(f"{seed}:float", 0, 99) / 100
    return round(min(MARKUP_MAX_PERCENT, (basis_points / 100) + cents), 2)


def _target_margin_percent(product, min_margin_percent):
    seed = f"{_product_sku(product)}:target-margin"
    buffer = _stable_int(seed, 150, 750) / 100
    return round(min(min_margin_percent + buffer, 48.0), 2)


def _price_for_margin(vendor_cost, category, margin_percent):
    margin_rate = min(max(margin_percent / 100, 0), 0.75)
    denominator = max(0.08, 1 - AMAZON_REFERRAL_FEE_RATE - margin_rate)
    prep_cost = round(_category_prep_cost(category), 2)
    price = max(vendor_cost * (1 + MARKUP_MIN_PERCENT / 100), vendor_cost + prep_cost + FBA_FEE_MIN)
    for _ in range(8):
        fba_fee = _estimate_fba_fee(price)
        price = (vendor_cost + fba_fee + prep_cost) / denominator
    return round(price, 2)


def _sale_price_from_cost(vendor_cost, markup_percent):
    return round(vendor_cost * (1 + (markup_percent / 100)), 2)


def _estimate_fba_fee(sale_price):
    return round(min(max(sale_price * FBA_FEE_RATE, FBA_FEE_MIN), FBA_FEE_MAX), 2)


def _category_prep_cost(category):
    lower = category.lower()
    if "coverall" in lower:
        return 2.35
    if "hard hat" in lower:
        return 1.75
    if "respirator" in lower:
        return 1.55
    return 1.25


def _factor(name, level, message):
    return {"name": name, "level": level, "message": message}


def _confidence_level(confidence):
    normalized = confidence.lower()
    if normalized == "high":
        return "LOW"
    if normalized == "medium":
        return "MEDIUM"
    return "HIGH"


def _match_confidence(score):
    if score >= 75:
        return "high"
    if score >= MIN_AMAZON_TITLE_MATCH_SCORE:
        return "medium"
    return "low"


def _category_risk_level(product):
    text = f"{_product_name(product)} {_product_description(product)} {_product_category(product)}".lower()
    if any(term in text for term in ["respirator", "hazmat", "chemical", "cartridge", "asbestos", "sharps"]):
        return "HIGH"
    if any(term in text for term in ["coverall", "glove", "sleeve", "safety", "goggle", "lockout"]):
        return "MEDIUM"
    return "LOW"


def _category_risk_message(product):
    level = _category_risk_level(product)
    if level == "HIGH":
        return "Product category may require compliance review before listing."
    if level == "MEDIUM":
        return "PPE category should be checked for listing restrictions and claims."
    return "No category-specific risk signal found in the catalog text."


def _risk_score(factors):
    weights = {"LOW": 15, "MEDIUM": 45, "HIGH": 80}
    return round(sum(weights.get(item["level"], 45) for item in factors) / len(factors))


def _risk_level(score):
    if score >= 60:
        return "HIGH"
    if score >= 35:
        return "MEDIUM"
    return "LOW"


def _risk_summary(factors):
    high = [item["name"] for item in factors if item["level"] == "HIGH"]
    medium = [item["name"] for item in factors if item["level"] == "MEDIUM"]
    if high:
        return f"high risk factors include {', '.join(high)}."
    if medium:
        return f"medium risk factors include {', '.join(medium)}."
    return "all tracked risk factors are low."


def _push_next_steps(should_push):
    if should_push:
        return [
            "Create or update the Amazon listing for this SKU.",
            "Use the recommended price shown in the decision studio.",
            "Keep FBA fulfillment competitive while protecting the required margin.",
        ]
    return [
        "Do not push this item yet.",
        "Review the failed decision gates and high-risk factors.",
        "Re-run research after pricing, cost, ASIN confidence, or compliance issues are corrected.",
    ]


def _extract_package_quantity(text):
    cleaned = _ascii(text).lower()
    unit_type = _unit_type_for_text(cleaned)
    patterns = [
        (r"\b(\d{1,5})\s*(?:ea|each|pcs?|pieces?|ct|count|sleeves?|wipes?|filters?|pairs?|pr|gloves?|earplugs?|respirators?|masks?|rolls?)\s*/\s*(?:cs|case|bx|box|pk|pack|bag|carton)\b", "count per package"),
        (r"\b(\d{1,5})\s*/\s*(?:cs|case|bx|box|pk|pack|bag|carton)\b", "count per package"),
        (r"\b(?:pack|case|box|carton|bag)\s+of\s+(\d{1,5})\b", "pack of count"),
        (r"\((?:pack|case|box|carton|bag)\s+of\s+(\d{1,5})\)", "pack of count"),
        (r"\b(\d{1,5})\s*[- ]?(?:pack|pk|count|ct)\b", "count package"),
        (r"\b(\d{1,5})\s*(?:per|/)\s*(?:case|cs|box|bx|pack|pk|bag|carton)\b", "count per package"),
    ]
    for pattern, label in patterns:
        match = re.search(pattern, cleaned)
        if match:
            quantity = _number(match.group(1))
            if quantity > 0:
                return quantity, unit_type, f"Detected {quantity:g} {unit_type} from {label}: '{match.group(0)}'."
    return 1, unit_type, ""


def _unit_type_for_text(text):
    normalized = _ascii(text).lower()
    for token, unit in [
        ("sleeve", "sleeve"),
        ("wipe", "wipe"),
        ("filter", "filter"),
        ("roll", "roll"),
        ("earplug", "pair"),
        ("pair", "pair"),
        ("glove", "glove"),
        ("respirator", "each"),
        ("mask", "each"),
        ("label", "label"),
        ("cap", "cap"),
        ("blade", "blade"),
        ("tie", "tie"),
        ("tube", "tube"),
    ]:
        if token in normalized:
            return unit
    return "each"


def _text_similarity(left, right):
    left_norm = _normalize_text(left)
    right_norm = _normalize_text(right)
    if not left_norm or not right_norm:
        return 0
    sequence_score = SequenceMatcher(None, left_norm, right_norm).ratio() * 100
    left_tokens = set(left_norm.split())
    right_tokens = set(right_norm.split())
    overlap_score = 0
    containment_score = 0
    if left_tokens and right_tokens:
        overlap_score = (2 * len(left_tokens & right_tokens) / (len(left_tokens) + len(right_tokens))) * 100
        containment_score = (len(left_tokens & right_tokens) / min(len(left_tokens), len(right_tokens))) * 100
    return round(max(sequence_score, overlap_score, containment_score), 2)


def _normalize_text(value):
    cleaned = _ascii(value).lower().replace("&", " and ")
    cleaned = re.sub(r"\b(tm|r)\b", " ", cleaned)
    cleaned = re.sub(r"[^a-z0-9]+", " ", cleaned)
    stop = {"the", "and", "with", "for", "of", "to", "in", "a", "an"}
    return " ".join(token for token in cleaned.split() if token not in stop)


def _ascii(value):
    return str(value or "").encode("ascii", "ignore").decode("ascii")


def _product_sku(product):
    return str(product.get("ItemId") or product.get("sku") or product.get("recordId") or "").strip()


def _product_name(product):
    return _ascii(product.get("ItemDesc") or product.get("name") or _product_sku(product)).strip()


def _product_description(product):
    return _ascii(product.get("ExtendedDesc") or product.get("description") or "").strip()


def _product_match_text(product):
    return " ".join(part for part in [_product_name(product), _product_description(product), str(product.get("SalesPricingUnit") or "")] if part)


def _product_brand(product):
    return _product_manufacturer(product)


def _product_manufacturer(product):
    explicit = _explicit_manufacturer(product)
    if explicit:
        return explicit

    text = f"{_product_name(product)} {_product_description(product)}".lower()
    known = {
        "thomas and betts": "Thomas & Betts",
        "first aid only": "First Aid Only",
        "kimberly": "Kimberly-Clark",
        "nightstick": "Nightstick",
        "honeywell": "Honeywell",
        "ergodyne": "Ergodyne",
        "pyramex": "Pyramex",
        "radians": "Radians",
        "safewaze": "Safewaze",
        "personna": "Personna",
        "dupont": "DuPont",
        "brady": "Brady",
        "chums": "Chums",
        "fluke": "Fluke",
        "windex": "Windex",
        "gojo": "GOJO",
        "purell": "PURELL",
        "bayco": "Bayco",
        "guardian": "Guardian",
        "mcr": "MCR Safety",
        "msa": "MSA",
        "abb": "ABB",
        "ty rap": "Thomas & Betts",
        "ty-rap": "Thomas & Betts",
        "3m": "3M",
    }
    for token, manufacturer in known.items():
        if token in text:
            return manufacturer

    if _has_quest_manufacturer_signal(product):
        return "QuestSafety"

    return "Other manufacturer"


def _explicit_manufacturer(product):
    for key in ("Manufacturer", "ManufacturerName", "MfgName", "Brand", "brand", "manufacturer"):
        value = str(product.get(key) or "").strip()
        if value:
            return value
    return ""


def _product_manufacturer_type(product):
    manufacturer = _normalize_text(_product_manufacturer(product))
    if manufacturer in {"quest safety", "questsafety", "quest", "quantumwear"}:
        return "quest"
    return "nonquest"


def _has_quest_manufacturer_signal(product):
    class_id = _normalize_text(product.get("ClassId1") or "")
    if class_id == "quest":
        return True
    text = _normalize_text(f"{_product_sku(product)} {_product_name(product)} {_product_description(product)}")
    tokens = set(text.split())
    return (
        "questsafety" in tokens
        or {"quest", "safety"}.issubset(tokens)
        or "quantumwear" in tokens
        or _product_sku(product).upper().startswith("QPA")
    )


def _product_manufacturer_label(product):
    return "QuestSafety" if _product_manufacturer_type(product) == "quest" else "Other manufacturers"


def _product_category(product):
    text = f"{_product_name(product)} {_product_description(product)}".lower()
    categories = [
        ("respirator", "Respiratory Protection"),
        ("filter", "Respiratory Protection"),
        ("glove", "Hand Protection"),
        ("sleeve", "Sleeves & Apparel"),
        ("coverall", "Protective Apparel"),
        ("cover", "Protective Apparel"),
        ("goggle", "Eye Protection"),
        ("eyewear", "Eye Protection"),
        ("glass", "Eye Protection"),
        ("earplug", "Hearing Protection"),
        ("lockout", "Lockout Tagout"),
        ("loto", "Lockout Tagout"),
        ("label", "Labels & Signs"),
        ("tape", "Labels & Signs"),
        ("wipe", "Wipes & Cleaning"),
        ("cleaner", "Wipes & Cleaning"),
        ("repellent", "Insect & Animal Control"),
        ("wasp", "Insect & Animal Control"),
        ("first aid", "First Aid"),
        ("sharps", "First Aid"),
        ("harness", "Fall Protection"),
        ("lanyard", "Fall Protection"),
        ("cable tie", "Cable Ties"),
        ("knife", "Cutting Tools"),
        ("blade", "Cutting Tools"),
    ]
    for token, category in categories:
        if token in text:
            return category
    return str(product.get("ClassId2") or "Uncategorized")


def _competitor_description_text(match):
    return " ".join(
        [
            str(match.get("matched_amazon_product_title") or ""),
            str(match.get("description") or ""),
            " ".join(str(item) for item in (match.get("bullet_points") or [])),
        ]
    )


def _sales_rank_category(value):
    return value.get("category") if isinstance(value, dict) else None


def _skipped_product(product, reason, skip_code, search_group_score=0, amazon_input=None):
    sku = _product_sku(product)
    vendor_cost = _product_cost(product)
    markup_percent = _product_markup_percent(product) if vendor_cost else 0
    base_price = _product_sale_price(product, vendor_cost, markup_percent) if vendor_cost else _erp_sale_price(product)
    category = _product_category(product)
    normalization = _product_price_normalization(product, vendor_cost, base_price or vendor_cost or 1)
    criteria = {
        "catalogMatch": {
            "passed": False,
            "actual": round(search_group_score, 2),
            "threshold": MIN_AMAZON_TITLE_MATCH_SCORE,
            "explanation": reason,
        },
        "revenue": {
            "passed": False,
            "actual": 0,
            "threshold": 0,
            "explanation": "Revenue was not estimated because the SKU did not produce a qualified Amazon match.",
        },
        "fbaCompetitive": {
            "passed": False,
            "actual": 0,
            "threshold": 0,
            "explanation": "FBA competitiveness was not evaluated because no qualified buy-box competitor was available.",
        },
        "margin": {
            "passed": False,
            "actual": 0,
            "threshold": 0,
            "explanation": "Margin was not evaluated against Amazon because the product was skipped before pricing comparison.",
        },
    }
    risk_analysis = {
        "score": 0,
        "level": "SKIPPED",
        "factors": [_factor("Pipeline skip", "HIGH", reason)],
        "marginBufferPercent": 0,
        "summary": reason,
    }
    decision = {"action": "SKIPPED", "label": "Skipped", "reason": reason}
    economics = {
        "Cost": round(vendor_cost, 2),
        "basePrice": round(base_price, 2),
        "salePrice": 0,
        "recommendedPrice": 0,
        "recommendedUnitPrice": 0,
        "baseUnitPrice": round(_number(normalization.get("unitPrice")), 4),
        "unitCost": round(_number(normalization.get("unitCost")), 4),
        "packageQuantity": _number(normalization.get("packageQuantity")) or 1,
        "unitType": normalization.get("unitType") or "each",
        "costMarkupPercent": markup_percent,
        "grossMarkupDollars": 0,
        "estimatedProductCost": round(vendor_cost, 2),
        "amazonReferralFee": 0,
        "estimatedFbaFee": 0,
        "shippingPrepCost": 0,
        "profitPerUnit": 0,
        "contributionMarginPercent": 0,
        "minViablePrice": 0,
        "requiredMarginPercent": 0,
        "targetMarginPercent": 0,
    }
    return {
        "recordId": sku,
        "analysisStatus": "SKIPPED",
        "isSkipped": True,
        "skipReason": reason,
        "skipCode": skip_code,
        "status": "Skipped",
        "sku": sku,
        "asin": None,
        "name": _product_name(product),
        "description": _product_description(product),
        "brand": _product_brand(product),
        "manufacturer": _product_manufacturer(product),
        "manufacturerType": _product_manufacturer_type(product),
        "manufacturerLabel": _product_manufacturer_label(product),
        "category": category,
        "imageUrl": None,
        "questProductUrl": None,
        "amazonProductUrl": None,
        "matchedAmazonTitle": None,
        "matchScore": 0,
        "amazonSearchInput": amazon_input,
        "searchGroupMatchScore": round(search_group_score, 2),
        "Cost": round(vendor_cost, 2),
        "markupPercent": markup_percent,
        "price": round(base_price, 2),
        "priceNormalization": normalization,
        "monthlyUnits": 0,
        "monthlyRevenue": 0,
        "economics": economics,
        "competitors": [],
        "criteria": criteria,
        "riskAnalysis": risk_analysis,
        "decision": decision,
        "researchScore": 0,
        "recommendedAmazonPrice": 0,
        "pricingBasis": {
            "basePrice": round(base_price, 2),
            "baseUnitPrice": round(_number(normalization.get("unitPrice")), 4),
            "recommendedPrice": 0,
            "recommendedUnitPrice": 0,
            "lowestFbaCompetitorPrice": 0,
            "lowestFbaCompetitorUnitPrice": 0,
            "lowestFbaCompetitorAsin": None,
            "lowestFbaCompetitorTitle": None,
            "requiredMarginPercent": 0,
            "targetMarginPercent": 0,
            "packageQuantity": _number(normalization.get("packageQuantity")) or 1,
            "unitType": normalization.get("unitType") or "each",
            "normalizationEvidence": normalization.get("evidence"),
            "notes": [reason],
        },
        "pushRecommendation": {
            "shouldPush": False,
            "action": "SKIPPED",
            "status": "SKIPPED",
            "priceAction": "No Amazon action",
            "sku": sku,
            "asin": None,
            "recommendedPrice": 0,
            "currencyCode": "USD",
            "message": reason,
            "nextSteps": [
                "Review the skip reason and source data for this SKU.",
                "Add or correct Amazon competitor records, then reset and rerun the pipeline.",
            ],
            "riskLevel": "SKIPPED",
        },
        "explanation": [reason],
        "reason": reason,
    }


def _unmatched_product(product, reason, search_group_score=0, amazon_input=None):
    return _skipped_product(
        product=product,
        reason=reason,
        skip_code="UNMATCHED",
        search_group_score=search_group_score,
        amazon_input=amazon_input,
    )


def _money_amount(value):
    if isinstance(value, dict):
        return _number(value.get("amount"))
    return _number(value)


def _optional_money(value):
    amount = _money_amount(value)
    return round(amount, 2) if amount > 0 else None


def _normalize_asin(value):
    return re.sub(r"[^A-Za-z0-9]", "", str(value or "")).upper()[:10]


def _stable_int(seed, minimum, maximum):
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    value = int(digest[:8], 16)
    return minimum + (value % (maximum - minimum + 1))


def _first(values, fallback):
    if isinstance(values, list) and values:
        return str(values[0])
    return fallback


def _number(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0

