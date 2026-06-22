from __future__ import annotations

import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence
from xml.sax.saxutils import escape


BASE_DIR = Path(__file__).resolve().parents[1]
EXPORT_DIR = BASE_DIR / "exports"
LATEST_EXPORT = EXPORT_DIR / "dashboard_latest.xlsx"


def export_dashboard_workbook(analysis: Dict[str, Any]) -> Path | None:
    if not analysis or not analysis.get("isReady"):
        return None

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    snapshot_path = EXPORT_DIR / f"dashboard_{timestamp}.xlsx"
    summary = analysis.get("summary", {})
    results = analysis.get("results", [])

    workbook = {
        "Summary": _summary_rows(analysis, summary),
        "Top Products": _top_products_rows(results),
        "All Products": _all_products_rows(results),
    }
    _write_xlsx(snapshot_path, workbook)
    _write_xlsx(LATEST_EXPORT, workbook)
    return snapshot_path


def _summary_rows(analysis: Dict[str, Any], summary: Dict[str, Any]) -> List[List[Any]]:
    filters = analysis.get("filters", {})
    available = analysis.get("available", {})
    metadata = analysis.get("metadata", {})
    return [
        ["Metric", "Value"],
        ["Generated at", analysis.get("generatedAt", "")],
        ["Run ID", analysis.get("runId", metadata.get("runId", ""))],
        ["Source products", metadata.get("sourceProductCount", 0)],
        ["Final result rows", metadata.get("finalResultCount", 0)],
        ["Analyzed products", summary.get("analyzedCount", 0)],
        ["Skipped products", summary.get("skippedCount", 0)],
        ["Competitor records", metadata.get("competitorRecordCount", metadata.get("rawAmazonCompetitorCount", 0))],
        ["Grouped competitor SKUs", metadata.get("groupedCompetitorSkuCount", 0)],
        ["Year", filters.get("year", "")],
        ["Month", filters.get("monthLabel", "")],
        ["Risk filter", filters.get("riskCategory", "all")],
        ["Products live", summary.get("pushCount", 0)],
        ["Products in review", summary.get("reviewCount", 0)],
        ["Weighted margin", summary.get("weightedMarginPercent", 0)],
        ["Total estimated monthly revenue", summary.get("totalEstimatedMonthlyRevenue", 0)],
        ["Available SKUs", available.get("skuCount", 0)],
    ]


def _top_products_rows(results: Sequence[Dict[str, Any]]) -> List[List[Any]]:
    rows = sorted(
        results,
        key=lambda item: (
            float(item.get("monthlyRevenue", 0) or 0),
            float(item.get("economics", {}).get("contributionMarginPercent", 0) or 0),
        ),
        reverse=True,
    )[:10]

    output = [[
        "SKU",
        "Name",
        "Category",
        "Risk",
        "Decision",
        "Cost",
        "Recommended Price",
        "Monthly Revenue",
        "Margin %",
    ]]
    for item in rows:
        economics = item.get("economics", {})
        output.append(
            [
                item.get("sku", ""),
                item.get("name", ""),
                item.get("category", ""),
                item.get("riskAnalysis", {}).get("level", ""),
                item.get("decision", {}).get("label", ""),
                round(float(item.get("Cost", 0) or 0), 2),
                round(float(item.get("recommendedAmazonPrice", 0) or 0), 2),
                round(float(item.get("monthlyRevenue", 0) or 0), 2),
                round(float(economics.get("contributionMarginPercent", 0) or 0), 2),
            ]
        )
    return output


def _all_products_rows(results: Sequence[Dict[str, Any]]) -> List[List[Any]]:
    output = [[
        "SKU",
        "ASIN",
        "Name",
        "Analysis Status",
        "Skip Reason",
        "Risk",
        "Decision",
        "Cost",
        "Recommended Price",
        "Monthly Revenue",
        "Margin %",
    ]]
    for item in sorted(results, key=lambda row: row.get("researchScore", 0), reverse=True):
        economics = item.get("economics", {})
        output.append(
            [
                item.get("sku", ""),
                item.get("asin", ""),
                item.get("name", ""),
                item.get("analysisStatus", "ANALYZED"),
                item.get("skipReason", ""),
                item.get("riskAnalysis", {}).get("level", ""),
                item.get("decision", {}).get("action", ""),
                round(float(item.get("Cost", 0) or 0), 2),
                round(float(item.get("recommendedAmazonPrice", 0) or 0), 2),
                round(float(item.get("monthlyRevenue", 0) or 0), 2),
                round(float(economics.get("contributionMarginPercent", 0) or 0), 2),
            ]
        )
    return output


def _write_xlsx(path: Path, sheets: Dict[str, List[List[Any]]]) -> None:
    content_types = _content_types(sheets)
    workbook_xml = _workbook_xml(sheets)
    workbook_rels = _workbook_rels(sheets)
    app_xml = _app_xml(sheets)
    core_xml = _core_xml()
    rels_xml = _root_rels()

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", rels_xml)
        archive.writestr("docProps/app.xml", app_xml)
        archive.writestr("docProps/core.xml", core_xml)
        archive.writestr("xl/workbook.xml", workbook_xml)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        archive.writestr("xl/styles.xml", _styles_xml())

        for index, (sheet_name, rows) in enumerate(sheets.items(), start=1):
            archive.writestr(f"xl/worksheets/sheet{index}.xml", _sheet_xml(rows))


def _content_types(sheets: Dict[str, List[List[Any]]]) -> str:
    sheet_overrides = "".join(
        f'<Override PartName="/xl/worksheets/sheet{index}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for index, _ in enumerate(sheets.items(), start=1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
        '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
        f"{sheet_overrides}"
        "</Types>"
    )


def _root_rels() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
        '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>'
        "</Relationships>"
    )


def _workbook_xml(sheets: Dict[str, List[List[Any]]]) -> str:
    sheet_nodes = "".join(
        f'<sheet name="{escape(name)}" sheetId="{index}" r:id="rId{index}"/>'
        for index, name in enumerate(sheets.keys(), start=1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<sheets>{sheet_nodes}</sheets>"
        "</workbook>"
    )


def _workbook_rels(sheets: Dict[str, List[List[Any]]]) -> str:
    rel_nodes = "".join(
        f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{index}.xml"/>'
        for index, _ in enumerate(sheets.items(), start=1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f"{rel_nodes}"
        "</Relationships>"
    )


def _app_xml(sheets: Dict[str, List[List[Any]]]) -> str:
    titles = "".join(f"<vt:lpstr>{escape(name)}</vt:lpstr>" for name in sheets.keys())
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
        'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
        "<Application>QuestSafety MVP</Application>"
        f"<TitlesOfParts><vt:vector size=\"{len(sheets)}\" baseType=\"lpstr\">{titles}</vt:vector></TitlesOfParts>"
        "</Properties>"
    )


def _core_xml() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:dcmitype="http://purl.org/dc/dcmitype/" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        "<dc:title>QuestSafety Dashboard Export</dc:title>"
        "<dc:creator>Codex</dc:creator>"
        "<cp:lastModifiedBy>Codex</cp:lastModifiedBy>"
        f"<dcterms:created xsi:type=\"dcterms:W3CDTF\">{timestamp}</dcterms:created>"
        f"<dcterms:modified xsi:type=\"dcterms:W3CDTF\">{timestamp}</dcterms:modified>"
        "</cp:coreProperties>"
    )


def _styles_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        "<fonts count=\"1\"><font><sz val=\"11\"/><name val=\"Calibri\"/></font></fonts>"
        "<fills count=\"1\"><fill><patternFill patternType=\"none\"/></fill></fills>"
        "<borders count=\"1\"><border/></borders>"
        "<cellStyleXfs count=\"1\"><xf numFmtId=\"0\" fontId=\"0\" fillId=\"0\" borderId=\"0\"/></cellStyleXfs>"
        "<cellXfs count=\"1\"><xf numFmtId=\"0\" fontId=\"0\" fillId=\"0\" borderId=\"0\" xfId=\"0\"/></cellXfs>"
        "</styleSheet>"
    )


def _sheet_xml(rows: Iterable[Sequence[Any]]) -> str:
    row_nodes = []
    for row_index, row in enumerate(rows, start=1):
        cells = []
        for column_index, value in enumerate(row, start=1):
            ref = f"{_column_name(column_index)}{row_index}"
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                cells.append(f'<c r="{ref}"><v>{value}</v></c>')
            else:
                cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>')
        row_nodes.append(f'<row r="{row_index}">{"".join(cells)}</row>')

    body = "".join(row_nodes)
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{body}</sheetData>"
        "</worksheet>"
    )


def _column_name(index: int) -> str:
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name
