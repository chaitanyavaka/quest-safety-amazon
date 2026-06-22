from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.analysis_store import clear_current_analysis, current_analysis_response, run_current_analysis


def main() -> None:
    clear_current_analysis()
    after_reset = current_analysis_response()
    assert after_reset.get("isReady") is False, "reset should clear current analysis"

    first = run_current_analysis()
    second = run_current_analysis()
    assert first.get("runId") != second.get("runId"), "each analyze run should create a new run id"

    metadata = second.get("metadata", {})
    summary = second.get("summary", {})
    results = second.get("results", [])
    source_count = metadata.get("sourceProductCount")
    final_count = metadata.get("finalResultCount")
    analyzed_count = summary.get("analyzedCount")
    skipped_count = summary.get("skippedCount")

    assert source_count == final_count == len(results), "fresh results should include every source product"
    assert analyzed_count + skipped_count == source_count, "analyzed plus skipped should equal source products"
    assert summary.get("riskCategorizedCount") == analyzed_count, "risk categorized should equal analyzed products"
    assert metadata.get("skippedProductCount") == skipped_count, "metadata and summary skipped counts should reconcile"
    assert metadata.get("competitorRecordCount", 0) >= metadata.get("qualifiedCompetitorCount", 0), "raw competitors should exceed or equal qualified competitors"

    skipped = [row for row in results if row.get("analysisStatus") == "SKIPPED" or row.get("isSkipped")]
    assert len(skipped) == skipped_count, "skipped row count should match summary"
    assert all(row.get("skipReason") for row in skipped), "every skipped product needs a skip reason"
    assert all(row.get("sku") for row in skipped), "every skipped product needs a SKU"

    quest_manufacturer_rows = [row for row in results if row.get("manufacturerType") == "quest"]
    other_manufacturer_rows = [row for row in results if row.get("manufacturerType") == "nonquest"]
    assert len(quest_manufacturer_rows) + len(other_manufacturer_rows) == source_count, "manufacturer filters should partition all source products"
    assert all(row.get("manufacturer") == "QuestSafety" for row in quest_manufacturer_rows), "QuestSafety filter should contain QuestSafety manufacturer rows only"

    output = {
        "resetReady": after_reset.get("isReady"),
        "firstRunId": first.get("runId"),
        "secondRunId": second.get("runId"),
        "sourceProductCount": source_count,
        "finalResultCount": final_count,
        "analyzedCount": analyzed_count,
        "riskCategorizedCount": summary.get("riskCategorizedCount"),
        "skippedCount": skipped_count,
        "reviewCount": summary.get("reviewCount"),
        "approvedCount": summary.get("pushCount"),
        "marginQualifiedCount": summary.get("marginQualifiedCount"),
        "revenueQualifiedCount": summary.get("revenueQualifiedCount"),
        "competitorRecordCount": metadata.get("competitorRecordCount"),
        "usableAmazonMatchRecordCount": metadata.get("usableAmazonMatchRecordCount"),
        "qualifiedCompetitorCount": metadata.get("qualifiedCompetitorCount"),
        "manufacturerCounts": {
            "questSafety": len(quest_manufacturer_rows),
            "otherManufacturers": len(other_manufacturer_rows),
        },
        "otherManufacturerSamples": sorted({row.get("manufacturer") for row in other_manufacturer_rows if row.get("manufacturer")})[:10],
        "sampleSkipped": [
            {
                "sku": row.get("sku"),
                "skipCode": row.get("skipCode"),
                "skipReason": row.get("skipReason"),
            }
            for row in skipped[:3]
        ],
    }
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
