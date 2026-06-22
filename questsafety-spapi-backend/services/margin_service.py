from typing import Dict, Union


def calculate_margin(
    sale_price: float,
    product_cost: float,
    amazon_fees: float,
    shipping_prep_cost: float,
) -> Dict[str, Union[float, bool]]:
    profit_per_unit = round(
        sale_price - product_cost - amazon_fees - shipping_prep_cost,
        2,
    )

    contribution_margin_percent = 0.0
    if sale_price > 0:
        contribution_margin_percent = round(
            (profit_per_unit / sale_price) * 100,
            2,
        )

    return {
        "profitPerUnit": profit_per_unit,
        "contributionMarginPercent": contribution_margin_percent,
        "isProfitable": profit_per_unit > 0,
    }


def calculate_risk(
    contribution_margin_percent: float,
    min_margin_percent: float,
    is_profitable: bool,
) -> str:
    if not is_profitable or contribution_margin_percent < min_margin_percent:
        return "HIGH"

    if contribution_margin_percent < min_margin_percent + 2:
        return "MEDIUM"

    return "LOW"
