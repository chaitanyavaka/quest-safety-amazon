from typing import Dict, List, Optional

from services.margin_service import calculate_margin, calculate_risk
from services.pricing_service import get_lowest_competitor_price


DEFAULT_REPRICE_SHIPPING_PREP_COST = 1.0


def build_repricing_recommendation(
    asin: str,
    current_price: float,
    product_cost: float,
    amazon_fees: float,
    min_margin_percent: float,
    shipping_prep_cost: float = DEFAULT_REPRICE_SHIPPING_PREP_COST,
    sku: Optional[str] = None,
) -> Dict[str, object]:
    lowest_competitor_price = get_lowest_competitor_price(asin)
    competitor_beat_price = round(lowest_competitor_price - 0.01, 2)
    min_viable_price = _calculate_min_viable_price(
        product_cost=product_cost,
        amazon_fees=amazon_fees,
        shipping_prep_cost=shipping_prep_cost,
        min_margin_percent=min_margin_percent,
    )

    can_beat_competitor = competitor_beat_price >= min_viable_price
    recommended_price = (
        competitor_beat_price
        if can_beat_competitor
        else round(max(current_price, min_viable_price), 2)
    )

    margin = calculate_margin(
        sale_price=recommended_price,
        product_cost=product_cost,
        amazon_fees=amazon_fees,
        shipping_prep_cost=shipping_prep_cost,
    )

    contribution_margin_percent = float(margin["contributionMarginPercent"])
    is_profitable = bool(margin["isProfitable"])
    margin_risk_level = calculate_risk(
        contribution_margin_percent=contribution_margin_percent,
        min_margin_percent=min_margin_percent,
        is_profitable=is_profitable,
    )
    risk_analysis = _build_risk_analysis(
        current_price=current_price,
        recommended_price=recommended_price,
        lowest_competitor_price=lowest_competitor_price,
        min_viable_price=min_viable_price,
        contribution_margin_percent=contribution_margin_percent,
        min_margin_percent=min_margin_percent,
        is_profitable=is_profitable,
        can_beat_competitor=can_beat_competitor,
        margin_risk_level=margin_risk_level,
    )
    risk_level = str(risk_analysis["level"])

    can_reprice = is_profitable and contribution_margin_percent >= min_margin_percent
    recommended_action = _get_recommended_action(
        current_price=current_price,
        recommended_price=recommended_price,
        can_beat_competitor=can_beat_competitor,
        can_reprice=can_reprice,
    )

    return {
        "recommendedAction": recommended_action,
        "recommendedPrice": recommended_price,
        "riskLevel": risk_level,
        "riskAnalysis": risk_analysis,
        "contributionMarginPercent": contribution_margin_percent,
        "amazonPushSuggestion": _build_amazon_push_suggestion(
            asin=asin,
            sku=sku,
            current_price=current_price,
            recommended_price=recommended_price,
            recommended_action=recommended_action,
            risk_level=risk_level,
            can_reprice=can_reprice,
            can_beat_competitor=can_beat_competitor,
        ),
        "reasons": _build_reasons(
            lowest_competitor_price=lowest_competitor_price,
            recommended_price=recommended_price,
            min_margin_percent=min_margin_percent,
            can_beat_competitor=can_beat_competitor,
            can_reprice=can_reprice,
        ),
    }


def _build_reasons(
    lowest_competitor_price: float,
    recommended_price: float,
    min_margin_percent: float,
    can_beat_competitor: bool,
    can_reprice: bool,
) -> List[str]:
    formatted_min_margin = _format_percent(min_margin_percent)

    if can_reprice and can_beat_competitor:
        return [
            f"Lowest competitor price is {lowest_competitor_price:.2f}",
            "Recommended price beats competitor by 0.01",
            f"Margin remains above {formatted_min_margin}%",
            "Product is eligible for repricing",
        ]

    return [
        f"Lowest competitor price is {lowest_competitor_price:.2f}",
        f"Recommended price is {recommended_price:.2f}",
        f"Margin would fall below {formatted_min_margin}%",
        "Product is not eligible for repricing",
    ]


def _format_percent(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))

    return str(value)


def _build_risk_analysis(
    current_price: float,
    recommended_price: float,
    lowest_competitor_price: float,
    min_viable_price: float,
    contribution_margin_percent: float,
    min_margin_percent: float,
    is_profitable: bool,
    can_beat_competitor: bool,
    margin_risk_level: str,
) -> Dict[str, object]:
    margin_buffer = round(contribution_margin_percent - min_margin_percent, 2)
    price_delta = round(recommended_price - current_price, 2)
    price_delta_percent = 0.0
    if current_price > 0:
        price_delta_percent = round((price_delta / current_price) * 100, 2)

    factors = [
        _risk_factor(
            name="Margin buffer",
            level=margin_risk_level,
            message=(
                f"Recommended margin is {margin_buffer:.2f}% above target."
                if margin_buffer >= 0
                else f"Recommended margin is {abs(margin_buffer):.2f}% below target."
            ),
        ),
        _risk_factor(
            name="Competitor pressure",
            level="LOW" if can_beat_competitor else "HIGH",
            message=(
                "Recommended price can beat the lowest new competitor by 0.01."
                if can_beat_competitor
                else "Lowest competitor price is below your minimum viable price."
            ),
        ),
        _risk_factor(
            name="Price movement",
            level=_level_from_price_move(price_delta_percent),
            message=f"Suggested price change is {price_delta_percent:.2f}% from current price.",
        ),
    ]

    score = _risk_score(factors)

    return {
        "score": score,
        "level": _level_from_score(score),
        "marginBufferPercent": margin_buffer,
        "minViablePrice": min_viable_price,
        "lowestCompetitorPrice": lowest_competitor_price,
        "priceDelta": price_delta,
        "priceDeltaPercent": price_delta_percent,
        "factors": factors,
    }


def _calculate_min_viable_price(
    product_cost: float,
    amazon_fees: float,
    shipping_prep_cost: float,
    min_margin_percent: float,
) -> float:
    cost_basis = product_cost + amazon_fees + shipping_prep_cost
    margin_ratio = min(min_margin_percent / 100, 0.99)
    return round(cost_basis / (1 - margin_ratio), 2)


def _get_recommended_action(
    current_price: float,
    recommended_price: float,
    can_beat_competitor: bool,
    can_reprice: bool,
) -> str:
    if not can_reprice:
        return "HOLD"

    if not can_beat_competitor and recommended_price > current_price:
        return "RAISE_PRICE"

    if abs(current_price - recommended_price) < 0.01:
        return "HOLD"

    return "REPRICE"


def _risk_factor(name: str, level: str, message: str) -> Dict[str, str]:
    return {
        "name": name,
        "level": level,
        "message": message,
    }


def _level_from_price_move(price_delta_percent: float) -> str:
    absolute_delta = abs(price_delta_percent)

    if absolute_delta >= 20:
        return "HIGH"

    if absolute_delta >= 8:
        return "MEDIUM"

    return "LOW"


def _risk_score(factors: List[Dict[str, str]]) -> int:
    weights = {
        "LOW": 15,
        "MEDIUM": 45,
        "HIGH": 80,
    }

    if not factors:
        return 0

    return round(
        sum(weights.get(factor.get("level", "LOW"), 15) for factor in factors)
        / len(factors)
    )


def _level_from_score(score: int) -> str:
    if score >= 60:
        return "HIGH"

    if score >= 35:
        return "MEDIUM"

    return "LOW"


def _build_amazon_push_suggestion(
    asin: str,
    sku: Optional[str],
    current_price: float,
    recommended_price: float,
    recommended_action: str,
    risk_level: str,
    can_reprice: bool,
    can_beat_competitor: bool,
) -> Dict[str, object]:
    price_delta = round(recommended_price - current_price, 2)
    should_push = recommended_action in {"REPRICE", "RAISE_PRICE"} and can_reprice
    push_message = _build_push_message(
        recommended_action=recommended_action,
        recommended_price=recommended_price,
        can_beat_competitor=can_beat_competitor,
        should_push=should_push,
    )

    return {
        "shouldPush": should_push,
        "pushAction": "UPDATE_LISTING_PRICE" if should_push else "NO_PUSH",
        "submitMode": "SUGGESTION_ONLY",
        "target": "Amazon listing price",
        "apiFamily": "Listings Items API",
        "asin": asin,
        "sku": sku,
        "skuRequired": not bool(sku),
        "currentPrice": round(current_price, 2),
        "recommendedPrice": recommended_price,
        "priceDelta": price_delta,
        "currencyCode": "USD",
        "riskLevel": risk_level,
        "message": push_message,
        "nextSteps": _build_push_next_steps(
            should_push=should_push,
            sku=sku,
        ),
    }


def _build_push_message(
    recommended_action: str,
    recommended_price: float,
    can_beat_competitor: bool,
    should_push: bool,
) -> str:
    if should_push and recommended_action == "REPRICE":
        return f"Push price {recommended_price:.2f} to Amazon."

    if should_push and recommended_action == "RAISE_PRICE":
        return f"Push higher price {recommended_price:.2f} to protect margin."

    if not can_beat_competitor:
        return "Do not push a lower price because it would break the margin rule."

    return "No Amazon price push needed right now."


def _build_push_next_steps(
    should_push: bool,
    sku: Optional[str],
) -> List[str]:
    if should_push and sku:
        return [
            "Confirm the seller SKU and ASIN mapping.",
            "Review the recommended price with the category owner.",
            "Submit the price update through the Listings Items workflow after approval.",
        ]

    if should_push:
        return [
            "Add the seller SKU before any Amazon update.",
            "Confirm the ASIN match and category restrictions.",
            "Submit the price update only after SKU mapping is complete.",
        ]

    return [
        "Do not submit an Amazon update for this item yet.",
        "Review the margin, competitor pressure, and risk factors.",
        "Re-run the recommendation after the blocking issue is corrected.",
    ]
