from typing import Any, Dict, List, Optional, Tuple

from services.analysis_store import get_current_analysis


FORECAST_MONTHS = [
    {"value": 1, "label": "Jan"},
    {"value": 2, "label": "Feb"},
    {"value": 3, "label": "Mar"},
    {"value": 4, "label": "Apr"},
    {"value": 5, "label": "May"},
    {"value": 6, "label": "Jun"},
    {"value": 7, "label": "Jul"},
    {"value": 8, "label": "Aug"},
    {"value": 9, "label": "Sep"},
    {"value": 10, "label": "Oct"},
    {"value": 11, "label": "Nov"},
    {"value": 12, "label": "Dec"},
]


def amazon_metrics_summary(
    query: Optional[str] = None,
    year: int = 2026,
    month: int = 6,
    risk_category: str = "all",
) -> Dict[str, Any]:
    year = _normalize_year(year)
    month = _normalize_month(year, month)
    risk_category = (risk_category or "all").lower()

    research = get_current_analysis()
    if research is None:
        return _empty_summary(query, year, month, risk_category)

    products = research.get("results", [])
    filtered_products = _filter_products(products, query, risk_category)
    current_rows = [_metric_row(item, year, month) for item in filtered_products]
    previous_year, previous_month = _previous_period(year, month)
    previous_rows = [
        _metric_row(item, previous_year, previous_month) for item in filtered_products
    ]
    monthly_series = [
        _period_summary(filtered_products, year, month_item["value"])
        for month_item in _available_months(year)
    ]

    current_summary = _aggregate_rows(current_rows)
    previous_summary = _aggregate_rows(previous_rows)
    risk_counts = _risk_counts(current_rows)
    top_sku = max(current_rows, key=lambda item: item["revenue"], default=None)

    return {
        "filters": {
            "query": query or "",
            "year": year,
            "month": month,
            "monthLabel": _month_label(month),
            "riskCategory": risk_category,
        },
        "available": {
            "years": [2025, 2026],
            "months": _available_months(year),
            "riskCategories": ["all", "low", "medium", "high"],
            "skuCount": len(products),
        },
        "kpis": {
            "revenue": current_summary["revenue"],
            "revenueGrowthPercent": _growth_percent(
                current_summary["revenue"], previous_summary["revenue"]
            ),
            "marginPercent": current_summary["marginPercent"],
            "marginGrowthPoints": round(
                current_summary["marginPercent"] - previous_summary["marginPercent"],
                2,
            ),
            "units": current_summary["units"],
            "skuCount": len(current_rows),
        },
        "monthlySeries": monthly_series,
        "riskCounts": risk_counts,
        "skuRows": sorted(
            current_rows,
            key=lambda item: (item["revenue"], item["marginPercent"]),
            reverse=True,
        ),
        "insights": _build_insights(current_summary, previous_summary, risk_counts, top_sku),
        "source": {
            "questSafetyProducts": "data/Quest_safety_products.json",
            "amazonCompetitors": "data/amazon_seller_competitor.json",
            "note": (
                "Metrics are deterministic MVP estimates generated from the latest "
                "main-page research run, recommended prices, margins, and risk."
            ),
        },
        "isReady": True,
    }


def amazon_metrics_answer(
    question: str,
    query: Optional[str] = None,
    year: int = 2026,
    month: int = 6,
    risk_category: str = "all",
) -> Dict[str, str]:
    summary = amazon_metrics_summary(
        query=query,
        year=year,
        month=month,
        risk_category=risk_category,
    )
    if not summary.get("isReady"):
        return {
            "answer": "Run the Pipeline first. Dashboard metrics are generated from the latest completed research run."
        }

    normalized = (question or "").lower()
    kpis = summary["kpis"]
    top_rows = summary["skuRows"][:3]
    month_label = summary["filters"]["monthLabel"]
    year_value = summary["filters"]["year"]

    if "risk" in normalized:
        answer = (
            f"For {month_label} {year_value}, risk mix is "
            f"{summary['riskCounts']['low']} low, "
            f"{summary['riskCounts']['medium']} medium, and "
            f"{summary['riskCounts']['high']} high SKUs. "
            f"The main review work is the high-risk tier, usually caused by ASIN "
            f"confidence, FBA competitiveness, or category checks."
        )
    elif "margin" in normalized:
        answer = (
            f"Revenue-weighted margin is {kpis['marginPercent']:.1f}%, "
            f"{kpis['marginGrowthPoints']:+.1f} percentage points versus the prior month. "
            f"Top margin SKUs include {_sku_names(top_rows)}."
        )
    elif "revenue" in normalized or "performance" in normalized:
        answer = (
            f"{month_label} {year_value} estimated Amazon revenue is "
            f"${kpis['revenue']:,.0f}, {kpis['revenueGrowthPercent']:+.1f}% "
            f"versus the prior month. The strongest revenue drivers are {_sku_names(top_rows)}."
        )
    else:
        answer = (
            f"Current scope has {kpis['skuCount']} SKUs, "
            f"${kpis['revenue']:,.0f} estimated revenue, "
            f"{kpis['marginPercent']:.1f}% blended margin, and "
            f"{summary['riskCounts']['high']} high-risk SKUs. "
            f"Ask about revenue, margin, growth, or high-risk products for more detail."
        )

    return {"answer": answer}


def _empty_summary(
    query: Optional[str],
    year: int,
    month: int,
    risk_category: str,
) -> Dict[str, Any]:
    return {
        "isReady": False,
        "message": "Run the Pipeline before opening Dashboard metrics.",
        "filters": {
            "query": query or "",
            "year": year,
            "month": month,
            "monthLabel": _month_label(month),
            "riskCategory": risk_category,
        },
        "available": {
            "years": [2025, 2026],
            "months": _available_months(year),
            "riskCategories": ["all", "low", "medium", "high"],
            "skuCount": 0,
        },
        "kpis": {
            "revenue": 0,
            "revenueGrowthPercent": 0,
            "marginPercent": 0,
            "marginGrowthPoints": 0,
            "units": 0,
            "skuCount": 0,
        },
        "monthlySeries": [
            {
                "year": year,
                "month": month_item["value"],
                "label": month_item["label"],
                "revenue": 0,
                "marginPercent": 0,
                "units": 0,
            }
            for month_item in _available_months(year)
        ],
        "riskCounts": {"low": 0, "medium": 0, "high": 0, "total": 0},
        "skuRows": [],
        "insights": [],
        "source": {
            "questSafetyProducts": "data/Quest_safety_products.json",
            "amazonCompetitors": "data/amazon_seller_competitor.json",
            "note": "No metrics are generated until the main research page runs all SKUs.",
        },
    }


def _filter_products(
    products: List[Dict[str, Any]],
    query: Optional[str],
    risk_category: str,
) -> List[Dict[str, Any]]:
    needle = (query or "").strip().lower()
    filtered: List[Dict[str, Any]] = []

    for item in products:
        risk = str(item.get("riskAnalysis", {}).get("level", "")).lower()
        if risk_category != "all" and risk != risk_category:
            continue

        haystack = " ".join(
            [
                str(item.get("sku", "")),
                str(item.get("asin", "")),
                str(item.get("name", "")),
                str(item.get("brand", "")),
                str(item.get("category", "")),
            ]
        ).lower()
        if needle and needle not in haystack:
            continue

        filtered.append(item)

    return filtered


def _metric_row(item: Dict[str, Any], year: int, month: int) -> Dict[str, Any]:
    revenue_factor = _period_factor(item, year, month)
    base_revenue = float(item.get("monthlyRevenue") or 0)
    base_units = int(item.get("monthlyUnits") or 0)
    revenue = round(base_revenue * revenue_factor, 2)
    units = max(1, round(base_units * revenue_factor))
    margin = _period_margin(item, year, month)
    previous_year, previous_month = _previous_period(year, month)
    previous_revenue = round(
        base_revenue * _period_factor(item, previous_year, previous_month),
        2,
    )

    return {
        "recordId": item.get("recordId"),
        "sku": item.get("sku"),
        "asin": item.get("asin"),
        "productName": item.get("name"),
        "brand": item.get("brand"),
        "category": item.get("category") or "Uncategorized",
        "risk": item.get("riskAnalysis", {}).get("level") or "UNKNOWN",
        "riskSummary": item.get("riskAnalysis", {}).get("summary") or "",
        "decision": item.get("decision", {}).get("label") or "-",
        "marginPercent": margin,
        "revenue": revenue,
        "growthPercent": _growth_percent(revenue, previous_revenue),
        "units": units,
        "recommendedPrice": item.get("recommendedAmazonPrice") or 0,
        "competitorCount": len(item.get("competitors") or []),
        "topCompetitors": [
            competitor.get("sellerName")
            for competitor in (item.get("competitors") or [])[:3]
        ],
    }


def _period_summary(products: List[Dict[str, Any]], year: int, month: int) -> Dict[str, Any]:
    rows = [_metric_row(item, year, month) for item in products]
    aggregate = _aggregate_rows(rows)
    return {
        "year": year,
        "month": month,
        "label": _month_label(month),
        "revenue": aggregate["revenue"],
        "marginPercent": aggregate["marginPercent"],
        "units": aggregate["units"],
    }


def _aggregate_rows(rows: List[Dict[str, Any]]) -> Dict[str, float]:
    revenue = round(sum(item["revenue"] for item in rows), 2)
    units = sum(int(item["units"]) for item in rows)
    margin = (
        round(
            sum(item["revenue"] * item["marginPercent"] for item in rows) / revenue,
            2,
        )
        if revenue
        else 0
    )
    return {"revenue": revenue, "marginPercent": margin, "units": units}


def _risk_counts(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    counts = {"low": 0, "medium": 0, "high": 0}
    for item in rows:
        risk = str(item.get("risk", "")).lower()
        if risk in counts:
            counts[risk] += 1

    counts["total"] = sum(counts.values())
    return counts


def _build_insights(
    current: Dict[str, float],
    previous: Dict[str, float],
    risk_counts: Dict[str, int],
    top_sku: Optional[Dict[str, Any]],
) -> List[str]:
    top_text = (
        f"{top_sku['sku']} is the top revenue SKU at ${top_sku['revenue']:,.0f}."
        if top_sku
        else "No SKU rows match the current filters."
    )
    return [
        f"Revenue is ${current['revenue']:,.0f}, {_growth_percent(current['revenue'], previous['revenue']):+.1f}% versus prior month.",
        f"Blended margin is {current['marginPercent']:.1f}%, {current['marginPercent'] - previous['marginPercent']:+.1f} points versus prior month.",
        f"Risk mix contains {risk_counts['low']} low, {risk_counts['medium']} medium, and {risk_counts['high']} high-risk SKUs.",
        top_text,
    ]


def _period_factor(item: Dict[str, Any], year: int, month: int) -> float:
    seed = f"{item.get('recordId')}:{year}:{month}:revenue"
    noise = _stable_int(seed, -6, 8) / 100
    seasonal = 0.78 + (month * 0.035)
    year_lift = 0.08 if year == 2026 else 0
    category = str(item.get("category") or "").lower()
    category_lift = 0.04 if "glove" in category or "coverall" in category else 0
    return max(0.35, round(seasonal + year_lift + category_lift + noise, 4))


def _period_margin(item: Dict[str, Any], year: int, month: int) -> float:
    base_margin = float(item.get("economics", {}).get("contributionMarginPercent") or 0)
    seed = f"{item.get('recordId')}:{year}:{month}:margin"
    movement = _stable_int(seed, -90, 120) / 100
    trend = (month - 6) * 0.08
    return round(min(max(base_margin + movement + trend, 0), 60), 2)


def _growth_percent(current: float, previous: float) -> float:
    if not previous:
        return 0
    return round(((current - previous) / previous) * 100, 2)


def _previous_period(year: int, month: int) -> Tuple[int, int]:
    if month > 1:
        return year, month - 1
    return year - 1, 12


def _month_label(month: int) -> str:
    return next((item["label"] for item in FORECAST_MONTHS if item["value"] == month), "Jun")


def _normalize_year(year: int) -> int:
    return 2025 if int(year or 2026) <= 2025 else 2026


def _normalize_month(year: int, month: int) -> int:
    return min(max(int(month or 6), 1), _max_month_for_year(year))


def _available_months(year: int) -> List[Dict[str, Any]]:
    return [item for item in FORECAST_MONTHS if item["value"] <= _max_month_for_year(year)]


def _max_month_for_year(year: int) -> int:
    return 12 if int(year or 2026) <= 2025 else 6


def _stable_int(seed: str, minimum: int, maximum: int) -> int:
    import hashlib

    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    value = int(digest[:8], 16)
    return minimum + (value % (maximum - minimum + 1))


def _sku_names(rows: List[Dict[str, Any]]) -> str:
    names = [f"{item['sku']} ({item['productName']})" for item in rows if item]
    return ", ".join(names) if names else "no matching SKUs"

