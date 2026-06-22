from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from services.dashboard_export_service import export_dashboard_workbook
from services.research_service import (
    analyze_research_catalog,
    clear_research_data_cache,
    data_source_signature,
    summarize_research_results,
)


_CURRENT_ANALYSIS: Optional[Dict[str, Any]] = None
LIVE_ACTIONS = {"PUSH_TO_AMAZON", "REPRICE_AND_PUSH"}
ANALYSIS_SCHEMA_VERSION = "2026-06-22-manufacturer-filter-v3"


def run_current_analysis(
    revenue_threshold: float = 2000,
    min_margin_percent: float = 20,
    priority: str = "researchScore",
) -> Dict[str, Any]:
    global _CURRENT_ANALYSIS

    clear_research_data_cache()
    generated_at = datetime.now(timezone.utc).isoformat()
    run_id = f"research-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:8]}"
    analysis = analyze_research_catalog(
        query=None,
        revenue_threshold=revenue_threshold,
        min_margin_percent=min_margin_percent,
        priority=priority,
        run_id=run_id,
        generated_at=generated_at,
        force_reload=True,
    )
    analysis["isReady"] = True
    analysis["generatedAt"] = generated_at
    analysis["runId"] = run_id
    analysis["schemaVersion"] = ANALYSIS_SCHEMA_VERSION
    analysis.setdefault("metadata", {})["generatedAt"] = generated_at
    analysis["metadata"]["runId"] = run_id
    analysis["metadata"]["schemaVersion"] = ANALYSIS_SCHEMA_VERSION
    analysis["metadata"]["dataSignature"] = data_source_signature()
    analysis["summary"] = summarize_research_results(analysis.get("results", []))
    _CURRENT_ANALYSIS = analysis
    export_dashboard_workbook(_CURRENT_ANALYSIS)
    return analysis


def get_current_analysis() -> Optional[Dict[str, Any]]:
    return _CURRENT_ANALYSIS


def clear_current_analysis() -> Dict[str, Any]:
    global _CURRENT_ANALYSIS

    _CURRENT_ANALYSIS = None
    clear_research_data_cache()
    return current_analysis_response()


def approve_current_items(record_ids: List[str]) -> Dict[str, Any]:
    if _CURRENT_ANALYSIS is None:
        return current_analysis_response()

    selected_ids = {str(record_id) for record_id in record_ids}
    approved_ids = []

    for item in _CURRENT_ANALYSIS.get("results", []):
        if str(item.get("recordId")) not in selected_ids or _is_skipped_item(item):
            continue

        item["approvalStatus"] = "APPROVED_BY_USER"
        item["decision"] = {
            "action": "PUSH_TO_AMAZON",
            "label": "Approved",
            "reason": "User approved this medium-risk SKU from the Review queue.",
        }

        push = item.setdefault("pushRecommendation", {})
        push.update(
            {
                "action": "PUSH_TO_AMAZON",
                "status": "READY_TO_PUSH",
                "priceAction": "Push approved listing",
                "message": "Approved from Review. Use the recommendation price and create or update the Amazon listing.",
                "sku": item.get("sku"),
                "asin": item.get("asin"),
                "recommendedPrice": item.get("recommendedAmazonPrice", 0),
                "riskLevel": item.get("riskAnalysis", {}).get("level"),
                "nextSteps": [
                    "Create or update the Amazon listing for this SKU.",
                    "Use the recommended price shown in the decision studio.",
                    "Monitor margin and competitor movement after launch.",
                ],
            }
        )
        approved_ids.append(str(item.get("recordId")))

    _CURRENT_ANALYSIS["summary"] = _summary_for(_CURRENT_ANALYSIS.get("results", []))
    _CURRENT_ANALYSIS["approvedRecordIds"] = approved_ids
    export_dashboard_workbook(_CURRENT_ANALYSIS)
    return _CURRENT_ANALYSIS


def reject_current_items(record_ids: List[str]) -> Dict[str, Any]:
    if _CURRENT_ANALYSIS is None:
        return current_analysis_response()

    selected_ids = {str(record_id) for record_id in record_ids}
    rejected_ids = []

    for item in _CURRENT_ANALYSIS.get("results", []):
        if str(item.get("recordId")) not in selected_ids or _is_skipped_item(item):
            continue

        item["approvalStatus"] = "REJECTED_BY_USER"
        item["decision"] = {
            "action": "REJECTED_BY_USER",
            "label": "Rejected",
            "reason": "User rejected this SKU from the Review queue.",
        }
        push = item.setdefault("pushRecommendation", {})
        push.update(
            {
                "action": "NO_OP",
                "status": "REJECTED",
                "priceAction": "Do not push",
                "message": "Rejected from Review. No Amazon payload should be sent.",
                "sku": item.get("sku"),
                "asin": item.get("asin"),
                "recommendedPrice": item.get("recommendedAmazonPrice", 0),
                "riskLevel": item.get("riskAnalysis", {}).get("level"),
                "nextSteps": [
                    "Hold the SKU back from Amazon listing changes.",
                    "Revisit margin, demand, or competitor fit in a later run.",
                ],
            }
        )
        rejected_ids.append(str(item.get("recordId")))

    _CURRENT_ANALYSIS["summary"] = _summary_for(_CURRENT_ANALYSIS.get("results", []))
    _CURRENT_ANALYSIS["rejectedRecordIds"] = rejected_ids
    export_dashboard_workbook(_CURRENT_ANALYSIS)
    return _CURRENT_ANALYSIS


def current_analysis_response() -> Dict[str, Any]:
    global _CURRENT_ANALYSIS

    current_signature = data_source_signature()
    if _CURRENT_ANALYSIS is None:
        return {
            "isReady": False,
            "message": "Run the Pipeline before opening Review or Dashboard.",
            "metadata": {
                "dataSignature": current_signature,
                "schemaVersion": ANALYSIS_SCHEMA_VERSION,
            },
        }

    stored_signature = _CURRENT_ANALYSIS.get("metadata", {}).get("dataSignature")
    stored_schema = _CURRENT_ANALYSIS.get("schemaVersion") or _CURRENT_ANALYSIS.get("metadata", {}).get("schemaVersion")
    if stored_signature != current_signature or stored_schema != ANALYSIS_SCHEMA_VERSION:
        _CURRENT_ANALYSIS = None
        clear_research_data_cache()
        return {
            "isReady": False,
            "isStale": True,
            "message": "Cached research results were cleared because the source data or analysis schema changed. Run the pipeline again for a fresh analysis.",
            "metadata": {
                "dataSignature": current_signature,
                "schemaVersion": ANALYSIS_SCHEMA_VERSION,
            },
        }

    return _CURRENT_ANALYSIS


def _summary_for(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    return summarize_research_results(results)


def _is_live_listing(item: Dict[str, Any]) -> bool:
    return (
        not _is_skipped_item(item)
        and (
            item.get("approvalStatus") == "APPROVED_BY_USER"
            or item.get("decision", {}).get("action") in LIVE_ACTIONS
        )
    )


def _is_skipped_item(item: Dict[str, Any]) -> bool:
    return bool(
        item.get("isSkipped")
        or item.get("analysisStatus") == "SKIPPED"
        or item.get("decision", {}).get("action") == "SKIPPED"
    )


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
