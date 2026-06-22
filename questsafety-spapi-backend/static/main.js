const mainState = {
  analysis: null,
  selectedRecordId: null,
  query: "",
  statusFilter: "all",
  manufacturerFilter: "all",
  sort: "researchScore",
};

const analysisResults = document.querySelector("#analysisResults");
const pipelineFlow = document.querySelector("#pipelineFlow");
const runButton = document.querySelector("#runResearchButton");
const runStatus = document.querySelector("#runStatus");
const headerStatus = document.querySelector("#headerStatus");
const productQueue = document.querySelector("#productQueue");
const studioSku = document.querySelector("#studioSku");
const studioScore = document.querySelector("#studioScore");
const studioBody = document.querySelector("#studioBody");
const mainSearch = document.querySelector("#mainSearch");
const mainStatusFilter = document.querySelector("#mainStatusFilter");
const mainManufacturerFilter = document.querySelector("#mainManufacturerFilter");
const mainSort = document.querySelector("#mainSort");
const resetMain = document.querySelector("#resetMain");
const lastRunTime = document.querySelector("#lastRunTime");
const runIdLabel = document.querySelector("#runId");

initMainPage();

async function initMainPage() {
  bindMainEvents();
  resetPipelineStats();
  await loadCurrentAnalysis();
}

function bindMainEvents() {
  runButton.addEventListener("click", runAllSkus);

  mainSearch.addEventListener("input", debounce(() => {
    mainState.query = mainSearch.value.trim().toLowerCase();
    renderAnalysis();
  }, 180));

  mainStatusFilter?.addEventListener("change", (event) => {
    mainState.statusFilter = event.target.value || "all";
    renderAnalysis();
  });

  mainManufacturerFilter?.addEventListener("change", (event) => {
    mainState.manufacturerFilter = event.target.value || "all";
    renderAnalysis();
  });

  mainSort?.addEventListener("change", (event) => {
    mainState.sort = event.target.value || "researchScore";
    renderAnalysis();
  });

  resetMain.addEventListener("click", resetAnalysis);

  productQueue.addEventListener("click", (event) => {
    const card = event.target.closest("[data-record-id]");
    if (!card) {
      return;
    }

    mainState.selectedRecordId = card.dataset.recordId;
    renderAnalysis();
  });
}

async function loadCurrentAnalysis() {
  try {
    const response = await fetch("/api/research/current", { cache: "no-store" });
    if (!response.ok) {
      return;
    }

    const data = await response.json();
    if (data.isReady) {
      mainState.analysis = data;
      mainState.selectedRecordId = defaultSelectedId(data.results || []);
      renderAnalysis();
      return;
    }

    if (pipelineFlow) pipelineFlow.hidden = true;
    analysisResults.hidden = true;
    resetPipelineStats();
    if (data.isStale) {
      runStatus.textContent = "Stale run cleared";
      headerStatus.textContent = "Needs rerun";
    }
  } catch {
    resetPipelineStats();
  }
}

async function runAllSkus() {
  setRunning(true);

  try {
    const response = await fetch("/api/research/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query: null,
        monthlyRevenueThreshold: Number(document.querySelector("#revenueThreshold").value || 2000),
        minMarginPercent: Number(document.querySelector("#minMargin").value || 20),
        priority: mainState.sort || "researchScore",
      }),
    });

    if (!response.ok) {
      throw new Error("Research API failed");
    }

    const data = await response.json();
    mainState.analysis = data;
    mainState.selectedRecordId = defaultSelectedId(data.results || []);
    renderAnalysis();
    runStatus.textContent = "Complete - fresh data loaded";
    document.dispatchEvent(new CustomEvent("analysis:updated"));
  } catch (error) {
    runStatus.textContent = "Failed";
    headerStatus.textContent = "Error";
    studioBody.innerHTML = `<div class="empty-state">${escapeHtml(error.message || "Research failed.")}</div>`;
  } finally {
    setRunning(false);
  }
}

async function resetAnalysis() {
  resetMain.disabled = true;
  runStatus.textContent = "Resetting";

  try {
    await fetch("/api/research/reset", { method: "POST", cache: "no-store" });
  } finally {
    mainState.analysis = null;
    mainState.selectedRecordId = null;
    mainState.query = "";
    mainState.statusFilter = "all";
    mainState.manufacturerFilter = "all";
    mainState.sort = "researchScore";
    mainSearch.value = "";
    if (mainStatusFilter) mainStatusFilter.value = "all";
    if (mainManufacturerFilter) mainManufacturerFilter.value = "all";
    if (mainSort) mainSort.value = "researchScore";
    analysisResults.hidden = true;
    if (pipelineFlow) pipelineFlow.hidden = true;
    headerStatus.textContent = "Not run";
    runStatus.textContent = "Waiting";
    resetPipelineStats();
    resetRunMeta();
    document.dispatchEvent(new CustomEvent("analysis:updated"));
    studioSku.textContent = "Run analysis";
    studioScore.textContent = "0/100";
    studioBody.innerHTML = '<div class="empty-state">Run the pipeline to see recommendation, competitors, decision gates, and risk analysis.</div>';
    resetMain.disabled = false;
  }
}

function setRunning(isRunning) {
  runButton.disabled = isRunning;
  resetMain.disabled = isRunning;
  runButton.textContent = isRunning ? "Analyzing..." : "Run pipeline";
  if (isRunning) {
    runStatus.textContent = "Loading current ERP and Amazon data";
    headerStatus.textContent = "Running";
  }
}

function renderAnalysis() {
  const analysis = mainState.analysis;
  if (!analysis?.results?.length) {
    analysisResults.hidden = true;
    if (pipelineFlow) pipelineFlow.hidden = true;
    return;
  }

  if (pipelineFlow) pipelineFlow.hidden = false;
  analysisResults.hidden = false;
  renderSummary(analysis);
  renderPipelineStats(analysis);
  renderRunMeta(analysis);

  const rows = visibleRows(analysis.results);
  if (!rows.find((item) => item.recordId === mainState.selectedRecordId)) {
    mainState.selectedRecordId = rows[0]?.recordId || null;
  }

  renderQueue(rows);
  renderStudio(selectedItem(analysis.results, rows));
}

function renderSummary(analysis) {
  const counts = getCounts(analysis);
  setText("summarySourceCount", formatInteger(counts.source));
  setText("summarySkuCount", formatInteger(counts.analyzed));
  setText("summarySkippedCount", formatInteger(counts.skipped));
  setText("summaryReviewCount", formatInteger(counts.review));
  setText("summaryPushCount", formatInteger(counts.approved));
  setText("summaryRevenue", formatMoney(counts.revenue));
  setText("summaryMargin", `${formatNumber(counts.margin, 1)}%`);
  headerStatus.textContent = `${formatInteger(counts.source)} source / ${formatInteger(counts.analyzed)} analyzed / ${formatInteger(counts.skipped)} skipped`;
}

function renderPipelineStats(analysis) {
  const rows = analysis.results || [];
  const metadata = analysis.metadata || {};
  const counts = getCounts(analysis);
  const withCost = rows.filter((item) => Number(item.Cost || item.economics?.Cost || 0) > 0).length;
  const risk = counts.riskBreakdown;

  setText("flowDiscovered", formatInteger(counts.source));
  setText("flowMatched", formatInteger(counts.matched));
  setText("flowRiskCategorized", formatInteger(counts.analyzed));
  setText("flowMarginQualified", formatInteger(counts.marginQualified));
  setText("flowRevenueQualified", formatInteger(counts.revenueQualified));
  setText("flowReviewQueue", formatInteger(counts.review));
  setText("flowApproved", formatInteger(counts.approved));
  setText("flowSkipped", formatInteger(counts.skipped));
  setText("flowMarginRate", `${percent(counts.marginQualified, counts.analyzed)}% of analyzed`);
  setText("flowRevenueRate", `${percent(counts.revenueQualified, counts.analyzed)}% of analyzed`);
  setText("flowApproveRate", `${percent(counts.approved, counts.analyzed)}% of analyzed`);
  setText("flowRiskBreakdown", `${formatInteger(risk.low)} Low / ${formatInteger(risk.medium)} Med / ${formatInteger(risk.high)} High`);
  setText("flowReviewNote", `${formatInteger(counts.review)} need human review`);
  setText("flowSkippedNote", `${formatInteger(counts.skipped)} explained`);
  setText("p21SkuCount", `${formatInteger(counts.source)} SKUs`);
  setText("p21CostCoverage", `${percent(withCost, counts.source)}%`);
  setText("amazonCandidateCount", `${formatInteger(metadata.qualifiedCompetitorCount ?? metadata.competitorCount ?? 0)} qualified`);
  setText("amazonMatchRate", `${percent(counts.matched, counts.source)}%`);
  setText("amazonExceptionCount", formatInteger(counts.skipped));
  setText("reviewNavCount", formatInteger(counts.review));
}

function renderRunMeta(analysis) {
  const metadata = analysis.metadata || {};
  const runId = analysis.runId || metadata.runId || "-";
  const generatedAt = analysis.generatedAt || metadata.generatedAt;
  lastRunTime.textContent = generatedAt ? `Last run: ${formatDateTime(generatedAt)}` : "Last run: unknown";
  runIdLabel.textContent = `Run ID: ${shortRunId(runId)}`;
  runIdLabel.title = runId;
}

function resetPipelineStats() {
  [
    "flowDiscovered",
    "flowMatched",
    "flowMarginQualified",
    "flowRevenueQualified",
    "flowRiskCategorized",
    "flowReviewQueue",
    "flowApproved",
    "flowSkipped",
    "p21CostCoverage",
    "amazonMatchRate",
    "amazonExceptionCount",
    "reviewNavCount",
    "summarySourceCount",
    "summarySkuCount",
    "summarySkippedCount",
    "summaryReviewCount",
    "summaryPushCount",
  ].forEach((id) => setText(id, "0"));
  setText("flowMarginRate", "0% of analyzed");
  setText("flowRevenueRate", "0% of analyzed");
  setText("flowApproveRate", "0% of analyzed");
  setText("flowRiskBreakdown", "0 Low / 0 Med / 0 High");
  setText("flowReviewNote", "0 need human review");
  setText("flowSkippedNote", "0 explained");
  setText("p21SkuCount", "0 SKUs");
  setText("amazonCandidateCount", "0 qualified");
  setText("summaryRevenue", "$0");
  setText("summaryMargin", "0%");
}

function resetRunMeta() {
  lastRunTime.textContent = "Last run: never";
  runIdLabel.textContent = "Run ID: -";
  runIdLabel.title = "";
}

function getCounts(analysis) {
  const rows = analysis.results || [];
  const summary = analysis.summary || {};
  const metadata = analysis.metadata || {};
  const source = Number(metadata.sourceProductCount ?? metadata.productCount ?? rows.length);
  const skippedRows = rows.filter((item) => isSkipped(item));
  const analyzedRows = rows.filter((item) => !isSkipped(item));
  const riskBreakdown = summary.riskBreakdown || {
    low: analyzedRows.filter((item) => item.riskAnalysis?.level === "LOW").length,
    medium: analyzedRows.filter((item) => item.riskAnalysis?.level === "MEDIUM").length,
    high: analyzedRows.filter((item) => item.riskAnalysis?.level === "HIGH").length,
    skipped: skippedRows.length,
  };

  return {
    source,
    final: Number(metadata.finalResultCount ?? rows.length),
    analyzed: Number(summary.analyzedCount ?? metadata.analyzedProductCount ?? analyzedRows.length),
    skipped: Number(summary.skippedCount ?? metadata.skippedProductCount ?? skippedRows.length),
    matched: Number(summary.competitorMatchedProductCount ?? metadata.competitorMatchedProductCount ?? analyzedRows.filter((item) => item.competitors?.length).length),
    marginQualified: Number(summary.marginQualifiedCount ?? metadata.marginQualifiedProductCount ?? analyzedRows.filter((item) => item.criteria?.margin?.passed).length),
    revenueQualified: Number(summary.revenueQualifiedCount ?? metadata.revenueQualifiedProductCount ?? analyzedRows.filter((item) => item.criteria?.revenue?.passed).length),
    review: Number(summary.reviewCount ?? metadata.reviewQueueCount ?? analyzedRows.filter((item) => item.decision?.action === "HUMAN_REVIEW").length),
    approved: Number(summary.pushCount ?? metadata.approvedProductCount ?? analyzedRows.filter((item) => isLiveListing(item)).length),
    revenue: Number(summary.totalEstimatedMonthlyRevenue || 0),
    margin: Number(summary.weightedMarginPercent ?? summary.averageMarginPercent ?? 0),
    riskBreakdown,
  };
}

function visibleRows(rows) {
  return sortRows(rows.filter((item) => matchesStatus(item) && matchesManufacturer(item) && matchesQuery(item)));
}

function matchesStatus(item) {
  switch (mainState.statusFilter) {
    case "analyzed":
      return !isSkipped(item);
    case "approved":
      return isLiveListing(item);
    case "review":
      return item.decision?.action === "HUMAN_REVIEW";
    case "skipped":
      return isSkipped(item);
    default:
      return true;
  }
}

function matchesManufacturer(item) {
  const filter = mainState.manufacturerFilter || "all";
  if (filter === "all") {
    return true;
  }
  const type = manufacturerType(item);
  return filter === type;
}

function matchesQuery(item) {
  const query = mainState.query;
  if (!query) {
    return true;
  }

  return [
    item.sku,
    item.asin,
    item.name,
    item.brand,
    item.manufacturer,
    item.manufacturerLabel,
    item.category,
    item.matchedAmazonTitle,
    item.analysisStatus,
    item.skipReason,
    item.skipCode,
    item.amazonSearchInput,
    ...(item.competitors || []).flatMap((competitor) => [
      competitor.asin,
      competitor.title,
      competitor.sellerName,
      competitor.buyBoxSeller,
      competitor.competitorBrand,
    ]),
  ].join(" ").toLowerCase().includes(query);
}

function sortRows(rows) {
  const sorted = [...rows];
  switch (mainState.sort) {
    case "sku":
      return sorted.sort((a, b) => String(a.sku || "").localeCompare(String(b.sku || "")));
    case "status":
      return sorted.sort((a, b) => statusRank(a) - statusRank(b) || String(a.sku || "").localeCompare(String(b.sku || "")));
    case "match":
      return sortNumeric(sorted, (item) => item.matchScore);
    case "revenue":
      return sortNumeric(sorted, (item) => item.monthlyRevenue);
    case "margin":
      return sortNumeric(sorted, (item) => item.economics?.contributionMarginPercent);
    case "risk":
      return sortNumeric(sorted, (item) => item.riskAnalysis?.score);
    default:
      return sortNumeric(sorted, (item) => item.researchScore);
  }
}

function sortNumeric(rows, getter) {
  return rows.sort((a, b) => {
    const skipDelta = Number(isSkipped(a)) - Number(isSkipped(b));
    if (skipDelta) {
      return skipDelta;
    }
    return Number(getter(b) || 0) - Number(getter(a) || 0);
  });
}

function renderQueue(rows) {
  document.querySelector("#queueCount").textContent = `${formatInteger(rows.length)} products`;

  if (!rows.length) {
    productQueue.innerHTML = '<div class="empty-state">No products match the current search, status, manufacturer type, and sort filters.</div>';
    return;
  }

  productQueue.innerHTML = rows.map((item) => {
    const selected = item.recordId === mainState.selectedRecordId;
    const skipped = isSkipped(item);
    const decisionClass = statusClass(item);
    const riskLevel = item.riskAnalysis?.level || (skipped ? "SKIPPED" : "-");
    const match = primaryAmazonMatch(item);
    const manufacturer = item.manufacturer || item.brand || "QuestSafety";
    const type = manufacturerType(item);

    return `
      <article class="product-card premium-card${selected ? " is-selected" : ""}${skipped ? " is-skipped" : ""}" data-record-id="${escapeAttr(item.recordId)}">
        <div class="card-topline">
          <strong>${escapeHtml(item.sku || "-")}</strong>
          <span class="decision-pill ${decisionClass}">${escapeHtml(statusLabel(item))}</span>
        </div>
        <div class="product-main">
          ${renderImage(match.imageUrl || item.imageUrl, "product-image", item.name)}
          <div>
            <div class="manufacturer-line">
              <span class="manufacturer-chip ${type}">${type === "quest" ? "QuestSafety" : "Other"}</span>
              <span>${escapeHtml(manufacturer)}</span>
            </div>
            <h3>${escapeHtml(item.name || "-")}</h3>
            <p class="product-meta">${escapeHtml(item.category || "Uncategorized")}</p>
            ${renderAmazonMatchSummary(match, item)}
            ${skipped ? `<p class="skip-reason">${escapeHtml(item.skipReason || "Skipped before Amazon analysis.")}</p>` : ""}
          </div>
        </div>
        <div class="score-bar"><span style="width:${Math.min(Math.max(item.researchScore || 0, 0), 100)}%"></span></div>
        <div class="card-metrics premium-metrics">
          <div><span class="metric-label">Score</span><strong>${formatInteger(item.researchScore || 0)}/100</strong></div>
          <div><span class="metric-label">Match</span><strong>${formatNumber(item.matchScore || item.searchGroupMatchScore || 0, 1)}%</strong></div>
          <div><span class="metric-label">Cost</span><strong>${formatMoney(item.Cost || economicsCost(item) || 0)}</strong></div>
          <div><span class="metric-label">Revenue</span><strong>${formatMoney(item.monthlyRevenue || 0)}</strong></div>
          <div><span class="metric-label">Margin</span><strong>${formatNumber(item.economics?.contributionMarginPercent || 0, 1)}%</strong></div>
          <div><span class="metric-label">Risk</span><strong><span class="risk-pill ${String(riskLevel).toLowerCase()}">${escapeHtml(riskLevel)}</span></strong></div>
        </div>
      </article>
    `;
  }).join("");
}

function selectedItem(allRows, visible) {
  return (
    visible.find((item) => item.recordId === mainState.selectedRecordId) ||
    allRows.find((item) => item.recordId === mainState.selectedRecordId) ||
    visible[0] ||
    allRows[0]
  );
}

function renderStudio(item) {
  if (!item) {
    studioSku.textContent = "No SKU";
    studioScore.textContent = "0/100";
    studioBody.innerHTML = '<div class="empty-state">No product is selected.</div>';
    return;
  }

  if (isSkipped(item)) {
    renderSkippedStudio(item);
    return;
  }

  const decision = item.decision || {};
  const isPush = isLiveListing(item);
  const economics = item.economics || {};
  const pricing = item.pricingBasis || {};
  const push = item.pushRecommendation || {};
  const riskLevel = item.riskAnalysis?.level || "-";
  const match = primaryAmazonMatch(item);

  studioSku.textContent = item.sku || "-";
  studioScore.textContent = `${formatInteger(item.researchScore || 0)}/100`;
  studioBody.innerHTML = `
    <section class="studio-product">
      ${renderImage(item.imageUrl || item.competitors?.[0]?.imageUrl, "studio-image", item.name)}
      <div>
        <span class="decision-pill ${isPush ? "push" : "review"}">${escapeHtml(decision.label || "-")}</span>
        <h3>${escapeHtml(item.name || "-")}</h3>
        <div class="tag-row">
          <span class="tag">${escapeHtml(item.manufacturer || item.brand || "-")}</span>
          <span class="tag">${escapeHtml(item.manufacturerLabel || (manufacturerType(item) === "quest" ? "QuestSafety" : "Other manufacturers"))}</span>
          <span class="tag">${escapeHtml(item.category || "Uncategorized")}</span>
          <span class="tag">SKU ${escapeHtml(item.sku || "-")}</span>
          <span class="tag">Amazon ASIN ${renderAmazonLink(match.amazonProductUrl, match.asin || item.asin || "-")}</span>
        </div>
      </div>
    </section>

    ${renderPrimaryMatch(item)}

    <section class="studio-metrics">
      <div><span class="metric-label">Monthly revenue</span><strong>${formatMoney(item.monthlyRevenue || 0)}</strong></div>
      <div><span class="metric-label">Cost</span><strong>${formatMoney(item.Cost || economics.Cost || 0)}</strong></div>
      <div><span class="metric-label">Recommended price</span><strong>${formatMoney(item.recommendedAmazonPrice || 0)}</strong></div>
      <div><span class="metric-label">Margin</span><strong>${formatNumber(economics.contributionMarginPercent || 0, 1)}%</strong></div>
      <div><span class="metric-label">Risk</span><strong><span class="risk-pill ${String(riskLevel).toLowerCase()}">${escapeHtml(riskLevel)}</span></strong></div>
    </section>

    <section class="panel-block">
      <h3>Decision gates</h3>
      <div class="criteria-grid">${renderCriteria(item.criteria || {})}</div>
    </section>

    <section class="panel-block">
      <h3>Pricing basis</h3>
      <div class="pricing-basis">
        <div><span class="metric-label">Required margin</span><strong>${formatNumber(pricing.requiredMarginPercent || economics.requiredMarginPercent || 0, 1)}%</strong></div>
        <div><span class="metric-label">Target margin</span><strong>${formatNumber(pricing.targetMarginPercent || economics.targetMarginPercent || 0, 1)}%</strong></div>
        <div><span class="metric-label">Lowest FBA</span><strong>${formatMoney(pricing.lowestFbaCompetitorPrice || 0)}</strong></div>
        <div><span class="metric-label">Lowest FBA unit</span><strong>${formatUnitPrice(pricing.lowestFbaCompetitorUnitPrice || 0, pricing.unitType)}</strong></div>
        <div><span class="metric-label">Recommended unit</span><strong>${formatUnitPrice(pricing.recommendedUnitPrice || economics.recommendedUnitPrice || 0, pricing.unitType)}</strong></div>
        <div><span class="metric-label">Quest package</span><strong>${formatNumber(pricing.packageQuantity || economics.packageQuantity || 1, 0)} ${escapeHtml(pricing.unitType || economics.unitType || "units")}</strong></div>
      </div>
    </section>

    <section class="panel-block">
      <h3>Competitors</h3>
      <ul class="competitor-list">${renderCompetitors(item.competitors || [])}</ul>
    </section>

    <section class="panel-block">
      <h3>Risk analysis</h3>
      <ul class="risk-list">${renderRiskFactors(item.riskAnalysis?.factors || [])}</ul>
    </section>

    <section class="panel-block">
      <h3>Why this decision</h3>
      <ul class="why-list">${(item.explanation || []).map((line) => `<li>${escapeHtml(line)}</li>`).join("")}</ul>
    </section>

    <section class="push-suggestion ${isPush ? "push" : "review"}">
      <div>
        <span class="criteria-pill ${isPush ? "pass" : "fail"}">${isPush ? "Ready to push" : "Review first"}</span>
        <h3>${escapeHtml(push.priceAction || decision.label || "-")}</h3>
        <p>${escapeHtml(push.message || decision.reason || "")}</p>
        <dl class="suggestion-list">
          <div><dt>SKU</dt><dd>${escapeHtml(push.sku || item.sku || "-")}</dd></div>
          <div><dt>ASIN</dt><dd>${renderAmazonLink(match.amazonProductUrl, push.asin || match.asin || item.asin || "-")}</dd></div>
          <div><dt>Risk</dt><dd>${escapeHtml(push.riskLevel || riskLevel)}</dd></div>
        </dl>
        <ul class="why-list">${(push.nextSteps || []).map((line) => `<li>${escapeHtml(line)}</li>`).join("")}</ul>
      </div>
      <div class="push-price">
        <span>Recommended price</span>
        <strong>${formatMoney(push.recommendedPrice || item.recommendedAmazonPrice || 0)}</strong>
      </div>
    </section>
  `;
}

function renderSkippedStudio(item) {
  studioSku.textContent = item.sku || "-";
  studioScore.textContent = "Skipped";
  const pricing = item.pricingBasis || {};

  studioBody.innerHTML = `
    <section class="studio-product skipped-studio">
      ${renderImage(item.imageUrl, "studio-image", item.name)}
      <div>
        <span class="decision-pill skipped">Skipped</span>
        <h3>${escapeHtml(item.name || "-")}</h3>
        <div class="tag-row">
          <span class="tag">SKU ${escapeHtml(item.sku || "-")}</span>
          <span class="tag">${escapeHtml(item.category || "Uncategorized")}</span>
          <span class="tag">${escapeHtml(item.skipCode || "UNMATCHED")}</span>
        </div>
      </div>
    </section>

    <section class="skip-panel">
      <span class="metric-label">Skip reason</span>
      <h3>${escapeHtml(item.skipReason || item.reason || "Skipped before Amazon analysis.")}</h3>
      <p>Search group: ${escapeHtml(item.amazonSearchInput || "No qualified search group")}</p>
    </section>

    <section class="studio-metrics">
      <div><span class="metric-label">Source cost</span><strong>${formatMoney(item.Cost || 0)}</strong></div>
      <div><span class="metric-label">ERP price</span><strong>${formatMoney(item.price || 0)}</strong></div>
      <div><span class="metric-label">Search match</span><strong>${formatNumber(item.searchGroupMatchScore || 0, 1)}%</strong></div>
      <div><span class="metric-label">Package</span><strong>${formatNumber(pricing.packageQuantity || 1, 0)} ${escapeHtml(pricing.unitType || "unit")}</strong></div>
    </section>

    <section class="panel-block">
      <h3>Decision gates</h3>
      <div class="criteria-grid">${renderCriteria(item.criteria || {})}</div>
    </section>

    <section class="panel-block">
      <h3>Next action</h3>
      <ul class="why-list">${(item.pushRecommendation?.nextSteps || item.explanation || []).map((line) => `<li>${escapeHtml(line)}</li>`).join("")}</ul>
    </section>
  `;
}

function renderPrimaryMatch(item) {
  const match = primaryAmazonMatch(item);
  if (!match.amazonProductUrl && !match.title) {
    return "";
  }

  const url = match.amazonProductUrl || (match.asin ? `https://www.amazon.com/dp/${encodeURIComponent(match.asin)}` : "");
  const title = match.title || "Matched Amazon product";
  const description = match.description || "";
  const image = match.imageUrl || "";
  const monthlyBought = match.monthlyBoughtLowerBound || match.unitsSoldLastMonth;

  return `
    <section class="match-panel premium-match-panel">
      ${renderImage(image, "match-image", title)}
      <div>
        <span class="metric-label">Amazon match from amazon_seller_competitor.json</span>
        <h3>${renderAmazonLink(url, title)}</h3>
        <div class="tag-row">
          <span class="tag">${formatNumber(item.matchScore || match.matchScore || 0, 1)}% title match</span>
          <span class="tag">ASIN ${renderAmazonLink(url, match.asin || item.asin || "-")}</span>
          <span class="tag">${escapeHtml(match.competitorBrand || match.brand || "Amazon")}</span>
          ${monthlyBought ? `<span class="tag">${formatInteger(monthlyBought)}+ bought past month</span>` : ""}
        </div>
        ${description ? `<p>${escapeHtml(description)}</p>` : ""}
      </div>
    </section>
  `;
}

function renderCriteria(criteria) {
  const labels = {
    catalogMatch: "Amazon match",
    revenue: "Revenue",
    fbaCompetitive: "FBA fit",
    margin: "Margin",
  };

  const entries = Object.entries(criteria);
  if (!entries.length) {
    return '<article class="criteria-card"><span class="criteria-pill fail">Missing</span><h3>No gates</h3><p>No decision gates were returned.</p></article>';
  }

  return entries.map(([key, value]) => `
    <article class="criteria-card">
      <span class="criteria-pill ${value.passed ? "pass" : "fail"}">${value.passed ? "Clear" : "Review"}</span>
      <h3>${labels[key] || titleCase(key)}</h3>
      <p>${escapeHtml(value.explanation || "")}</p>
    </article>
  `).join("");
}

function renderCompetitors(competitors) {
  if (!competitors.length) {
    return '<li class="empty-state">No competitor records cleared the Amazon match and buy-box gates.</li>';
  }

  return competitors.slice(0, 5).map((competitor) => {
    const url = competitor.amazonProductUrl || (competitor.asin ? `https://www.amazon.com/dp/${encodeURIComponent(competitor.asin)}` : "");
    const title = competitor.title || competitor.matchedAmazonTitle || "Amazon product";
    const unitType = competitor.normalization?.unitType || "unit";
    const seller = competitor.buyBoxSeller || competitor.sellerName || "Buy Box seller";
    const bought = competitor.monthlyBoughtLowerBound || competitor.unitsSoldLastMonth;

    return `
    <li class="competitor-row rich premium-competitor-row">
      <span class="rank-badge">${formatInteger(competitor.rank || 0)}</span>
      ${renderImage(competitor.imageUrl, "competitor-thumb", title)}
      <div>
        <strong>${escapeHtml(competitor.competitorBrand || competitor.brand || "-")}</strong>
        ${renderAmazonLink(url, title, "competitor-title-link")}
        <span>${escapeHtml(competitor.fulfillmentType || "-")} / ${formatNumber(competitor.matchScore || 0, 1)}% match / ${escapeHtml(seller)}</span>
        <span>ASIN ${renderAmazonLink(url, competitor.asin || "-")}${bought ? ` / ${formatInteger(bought)}+ bought past month` : ""}</span>
      </div>
      <div class="price-stack">
        <span>Buy Box</span>
        <strong>${formatMoney(competitor.buyBoxPrice || competitor.estimatedPrice || 0)}</strong>
        <span>${formatUnitPrice(competitor.normalizedUnitPrice || 0, unitType)}</span>
      </div>
    </li>
  `;
  }).join("");
}

function primaryAmazonMatch(item) {
  const first = item?.competitors?.[0] || {};
  return {
    asin: first.asin || item?.asin || "",
    title: first.title || item?.matchedAmazonTitle || "",
    amazonProductUrl: first.amazonProductUrl || item?.amazonProductUrl || "",
    imageUrl: first.imageUrl || item?.imageUrl || "",
    description: first.description || item?.description || "",
    competitorBrand: first.competitorBrand || first.brand || item?.brand || "",
    brand: first.brand || item?.brand || "",
    matchScore: first.matchScore || item?.matchScore || 0,
    monthlyBoughtLowerBound: first.monthlyBoughtLowerBound || item?.monthlyBoughtLowerBound,
    unitsSoldLastMonth: first.unitsSoldLastMonth || item?.unitsSoldLastMonth,
  };
}

function renderAmazonMatchSummary(match, item) {
  if (!match?.title && !match?.asin) {
    return "";
  }

  const url = match.amazonProductUrl || (match.asin ? `https://www.amazon.com/dp/${encodeURIComponent(match.asin)}` : "");
  const label = match.title || `ASIN ${match.asin}`;
  return `
    <div class="amazon-json-link">
      <span>Amazon match</span>
      ${renderAmazonLink(url, label, "amazon-json-title")}
    </div>
  `;
}

function manufacturerType(item) {
  const explicit = String(item?.manufacturerType || "").toLowerCase();
  if (explicit === "quest" || explicit === "nonquest") {
    return explicit;
  }
  const manufacturer = String(item?.manufacturer || item?.brand || "").trim().toLowerCase();
  if (["quest", "quest safety", "questsafety", "quantumwear"].includes(manufacturer)) {
    return "quest";
  }
  return "nonquest";
}


function renderRiskFactors(factors) {
  if (!factors.length) {
    return '<li>No risk factors returned.</li>';
  }

  return factors.map((factor) => `
    <li class="${String(factor.level || "").toLowerCase()}">
      <strong>${escapeHtml(factor.name || "-")} / ${escapeHtml(factor.level || "-")}</strong>
      <span>${escapeHtml(factor.message || "")}</span>
    </li>
  `).join("");
}

function renderImage(src, className, alt = "") {
  if (src) {
    return `<img class="${escapeAttr(className)}" src="${escapeAttr(src)}" alt="${escapeAttr(alt || "")}">`;
  }
  return `<div class="${escapeAttr(className)} image-placeholder" aria-hidden="true">No image</div>`;
}

function renderAmazonLink(url, label, className = "") {
  const text = escapeHtml(label || "-");
  if (!url || label === "-") {
    return text;
  }
  return `<a${className ? ` class="${escapeAttr(className)}"` : ""} href="${escapeAttr(url)}" target="_blank" rel="noopener">${text}</a>`;
}

function defaultSelectedId(rows) {
  return rows.find((item) => !isSkipped(item))?.recordId || rows[0]?.recordId || null;
}

function economicsCost(item) {
  return Number(item?.economics?.Cost || 0);
}

function isSkipped(item) {
  return Boolean(item?.isSkipped || item?.analysisStatus === "SKIPPED" || item?.decision?.action === "SKIPPED");
}

function isLiveListing(item) {
  return (
    !isSkipped(item) &&
    (item?.approvalStatus === "APPROVED_BY_USER" || ["PUSH_TO_AMAZON", "REPRICE_AND_PUSH"].includes(item?.decision?.action))
  );
}

function statusLabel(item) {
  if (isSkipped(item)) return "Skipped";
  if (item?.approvalStatus === "APPROVED_BY_USER") return "Approved";
  if (item?.decision?.action === "REJECTED_BY_USER") return "Rejected";
  if (isLiveListing(item)) return "Listable";
  if (item?.decision?.action === "HUMAN_REVIEW") return "Review";
  return item?.decision?.label || "Analyzed";
}

function statusClass(item) {
  if (isSkipped(item)) return "skipped";
  if (item?.decision?.action === "REJECTED_BY_USER") return "rejected";
  if (isLiveListing(item)) return "push";
  return "review";
}

function statusRank(item) {
  if (isLiveListing(item)) return 0;
  if (item?.decision?.action === "HUMAN_REVIEW") return 1;
  if (item?.decision?.action === "REJECTED_BY_USER") return 2;
  if (isSkipped(item)) return 3;
  return 4;
}

function formatUnitPrice(value, unitType = "unit") {
  const amount = formatMoney(value || 0);
  return `${amount}/${escapeHtml(unitType || "unit")}`;
}

function formatMoney(value) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: Number(value || 0) >= 1000 ? 0 : 2,
  }).format(Number(value || 0));
}

function percent(value, total) {
  return total ? Math.round((Number(value || 0) / Number(total || 1)) * 100) : 0;
}

function setText(id, value) {
  const element = document.querySelector(`#${id}`);
  if (element) {
    element.textContent = value;
  }
}

function formatInteger(value) {
  return new Intl.NumberFormat("en-US", {
    maximumFractionDigits: 0,
  }).format(Number(value || 0));
}

function formatNumber(value, decimals = 0) {
  return new Intl.NumberFormat("en-US", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(Number(value || 0));
}

function formatDateTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "unknown";
  }
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

function shortRunId(value) {
  const text = String(value || "-");
  if (text.length <= 18) {
    return text;
  }
  return `${text.slice(0, 13)}...${text.slice(-4)}`;
}

function titleCase(value) {
  return String(value || "")
    .replace(/([A-Z])/g, " $1")
    .replace(/\b\w/g, (letter) => letter.toUpperCase())
    .trim();
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttr(value) {
  return escapeHtml(value);
}

function debounce(callback, delay) {
  let timer;
  return (...args) => {
    window.clearTimeout(timer);
    timer = window.setTimeout(() => callback(...args), delay);
  };
}
