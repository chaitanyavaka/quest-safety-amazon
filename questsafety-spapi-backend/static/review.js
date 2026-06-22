const reviewState = {
  analysis: null,
  activeTab: "high",
  selectedRecordId: null,
  selectedMediumIds: new Set(),
};

const reviewEmpty = document.querySelector("#reviewEmpty");
const highPanel = document.querySelector("#highReviewPanel");
const mediumPanel = document.querySelector("#mediumReviewPanel");
const historyPanel = document.querySelector("#historyReviewPanel");

initReview();

async function initReview() {
  bindReviewTabs();
  await loadReviewAnalysis();
}

function bindReviewTabs() {
  document.querySelector(".review-tabs").addEventListener("click", (event) => {
    const button = event.target.closest("[data-review-tab]");
    if (!button) {
      return;
    }

    reviewState.activeTab = button.dataset.reviewTab;
    document.querySelectorAll("[data-review-tab]").forEach((tab) => {
      tab.classList.toggle("is-active", tab === button);
    });
    renderReview();
  });

  document.querySelector("#highQueueList").addEventListener("click", (event) => {
    const item = event.target.closest("[data-record-id]");
    if (!item) {
      return;
    }

    reviewState.selectedRecordId = item.dataset.recordId;
    renderHighRisk();
  });

  document.querySelector("#mediumBatchRows").addEventListener("click", (event) => {
    const row = event.target.closest("[data-record-id]");
    if (!row) {
      return;
    }

    if (event.target.closest(".row-check")) {
      return;
    }

    const recordId = row.dataset.recordId;
    setMediumSelected(recordId, !reviewState.selectedMediumIds.has(recordId));
  });

  document.querySelector("#mediumBatchRows").addEventListener("change", (event) => {
    if (!event.target.matches(".row-check input")) {
      return;
    }

    const row = event.target.closest("[data-record-id]");
    if (!row) {
      return;
    }

    setMediumSelected(row.dataset.recordId, event.target.checked);
  });

  document.querySelector("#clearMediumSelection").addEventListener("click", () => {
    reviewState.selectedMediumIds.clear();
    setSelectAllState(false);
    renderMediumBatch(mediumRiskRows());
  });

  document.querySelector("#approveMediumSelection").addEventListener("click", approveSelectedMedium);
  document.querySelector("#mediumSelectAll").addEventListener("change", (event) => {
    toggleSelectAll(event.target.checked);
  });

  document.querySelector("#approveHighRisk").addEventListener("click", approveSelectedHigh);
  document.querySelector("#rejectHighRisk").addEventListener("click", rejectSelectedHigh);
}

async function loadReviewAnalysis() {
  const response = await fetch("/api/research/current");
  const data = await response.json();

  if (!data.isReady) {
    reviewState.analysis = null;
    renderReview();
    return;
  }

  reviewState.analysis = data;
  const high = highRiskRows();
  const medium = mediumRiskRows();
  reviewState.selectedRecordId = high[0]?.recordId || null;
  reviewState.selectedMediumIds = new Set(medium.map((item) => item.recordId));
  renderReview();
}

function renderReview() {
  const rows = reviewState.analysis?.results || [];
  const hasRun = Boolean(reviewState.analysis?.isReady);
  reviewEmpty.hidden = hasRun;

  const high = highRiskRows();
  const medium = mediumRiskRows();
  setText("highTabCount", high.length);
  setText("mediumTabCount", medium.length);
  setText("reviewNavCount", high.length + medium.length);
  setText("highQueueCount", high.length);
  syncSelectedMediumIds(medium);
  setText("mediumSelectedCount", `${reviewState.selectedMediumIds.size} selected`);
  syncSelectAllState(medium);

  highPanel.hidden = !hasRun || reviewState.activeTab !== "high";
  mediumPanel.hidden = !hasRun || reviewState.activeTab !== "medium";
  historyPanel.hidden = !hasRun || reviewState.activeTab !== "history";

  if (!hasRun) {
    return;
  }

  if (reviewState.activeTab === "high") {
    renderHighRisk();
  } else if (reviewState.activeTab === "medium") {
    renderMediumBatch(medium);
  } else {
    renderDecisionHistory(rows);
  }
}

function highRiskRows() {
  return (reviewState.analysis?.results || [])
    .filter((item) => item.riskAnalysis?.level === "HIGH" && item.decision?.action === "HUMAN_REVIEW")
    .sort((a, b) => (b.riskAnalysis?.score || 0) - (a.riskAnalysis?.score || 0));
}

function mediumRiskRows() {
  return (reviewState.analysis?.results || [])
    .filter((item) => item.riskAnalysis?.level !== "HIGH" && item.decision?.action === "HUMAN_REVIEW")
    .sort((a, b) => (b.monthlyRevenue || 0) - (a.monthlyRevenue || 0));
}

function renderHighRisk() {
  const rows = highRiskRows();
  const list = document.querySelector("#highQueueList");

  if (!rows.length) {
    list.innerHTML = '<div class="empty-state">No high-risk SKUs in the latest run.</div>';
    document.querySelector("#highReviewDetail").innerHTML = "";
    document.querySelector("#reviewReason").textContent = "No high-risk records require action.";
    return;
  }

  if (!rows.find((item) => item.recordId === reviewState.selectedRecordId)) {
    reviewState.selectedRecordId = rows[0].recordId;
  }

  list.innerHTML = rows.map((item) => `
    <button class="review-product-item${item.recordId === reviewState.selectedRecordId ? " is-selected" : ""}" type="button" data-record-id="${escapeAttr(item.recordId)}">
      <span></span>
      <strong>${escapeHtml(item.name || "-")}</strong>
      <small>${escapeHtml(item.sku || "-")} - ${escapeHtml(item.category || "Uncategorized")}</small>
      <em>List ${formatMoney(item.recommendedAmazonPrice || 0)}</em>
    </button>
  `).join("");

  const selected = rows.find((item) => item.recordId === reviewState.selectedRecordId) || rows[0];
  document.querySelector("#reviewReason").textContent = selected.riskAnalysis?.summary || "Routed because risk needs a human check.";
  document.querySelector("#highReviewDetail").innerHTML = `
    <section class="review-product-hero">
      <img src="${escapeAttr(selected.imageUrl || "")}" alt="">
      <div>
        <h1>${escapeHtml(selected.name || "-")}</h1>
        <p>${escapeHtml(selected.sku || "-")} - ${escapeHtml(selected.category || "Uncategorized")} - Discovered in latest run</p>
        <div class="tag-row">
          <span class="tag">Risk ${escapeHtml(selected.riskAnalysis?.level || "-")}</span>
          <span class="tag">Demand ${selected.monthlyRevenue >= 2000 ? "Clear" : "Review"}</span>
        </div>
      </div>
    </section>

    <section class="agent-recommendation">
      <div>
        <p>Agent recommendation</p>
        <h2>${selected.decision?.action === "HUMAN_REVIEW" ? "Hold for human review" : `List on Amazon at ${formatMoney(selected.recommendedAmazonPrice || 0)}`}</h2>
        <ul>
          ${(selected.explanation || []).slice(0, 4).map((line) => `<li>${escapeHtml(line)}</li>`).join("")}
        </ul>
      </div>
      <div>
        <span>Confidence</span>
        <strong>${Math.max(42, 100 - Number(selected.riskAnalysis?.score || 0))}%</strong>
      </div>
    </section>

    <section class="high-analysis-grid">
      <article>
        <h3>High-risk reason</h3>
        <ul class="risk-list">${renderRiskFactors(selected.riskAnalysis?.factors || [])}</ul>
      </article>
      <article>
        <h3>Decision gates</h3>
        <div class="criteria-grid">${renderCriteria(selected.criteria || {})}</div>
      </article>
    </section>

    <section class="high-analysis-grid">
      <article>
        <h3>Margin and pricing</h3>
        <dl class="detail-metrics">
          <div><dt>Recommended price</dt><dd>${formatMoney(selected.recommendedAmazonPrice || 0)}</dd></div>
          <div><dt>Projected margin</dt><dd>${formatNumber(selected.economics?.contributionMarginPercent || 0, 1)}%</dd></div>
          <div><dt>Monthly revenue</dt><dd>${formatMoney(selected.monthlyRevenue || 0)}</dd></div>
        </dl>
      </article>
      <article>
        <h3>Competitor context</h3>
        <ul class="competitor-list">${renderCompetitors(selected.competitors || [])}</ul>
      </article>
    </section>
  `;
}

function renderMediumBatch(rows) {
  const tbody = document.querySelector("#mediumBatchRows");

  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="7">No medium-risk SKUs in the latest run.</td></tr>';
    return;
  }

  tbody.innerHTML = rows.map((item) => {
    const isSelected = reviewState.selectedMediumIds.has(item.recordId);
    return `
    <tr class="${isSelected ? "is-selected" : ""}" data-record-id="${escapeAttr(item.recordId)}" tabindex="0">
      <td>
        <label class="row-check">
          <input type="checkbox" ${isSelected ? "checked" : ""} aria-label="Select ${escapeAttr(item.sku || item.name || "SKU")}">
          <span>${isSelected ? "OK" : ""}</span>
        </label>
      </td>
      <td><strong>${escapeHtml(item.name || "-")}</strong><small>${escapeHtml(item.sku || "-")}</small></td>
      <td>${escapeHtml(item.category || "Uncategorized")}</td>
      <td><span class="batch-pill">${escapeHtml(batchName(item))}</span></td>
      <td class="positive">${formatNumber(item.economics?.contributionMarginPercent || 0, 1)}%</td>
      <td>${formatMoney(item.recommendedAmazonPrice || 0)}</td>
      <td>${formatCompactMoney(item.monthlyRevenue || 0)}</td>
    </tr>
  `;
  }).join("");

  setText("mediumSelectedCount", `${reviewState.selectedMediumIds.size} selected`);
  syncSelectAllState(rows);
}

function renderDecisionHistory(rows) {
  const list = document.querySelector("#decisionHistoryList");
  const recent = [...rows]
    .sort((a, b) => (b.researchScore || 0) - (a.researchScore || 0))
    .slice(0, 12);

  list.innerHTML = recent.map((item, index) => {
    const action = historyAction(item);
    return `
      <article class="history-item">
        <span class="${action.className}">${action.icon}</span>
        <div>
          <h3>${escapeHtml(item.name || "-")}</h3>
          <p>${escapeHtml(item.sku || "-")} - ${escapeHtml(item.riskAnalysis?.level || "-")} -> ${item.decision?.action === "HUMAN_REVIEW" ? "human" : "auto"}</p>
        </div>
        <strong>${escapeHtml(action.label)}</strong>
        <small>${index + 2} min ago</small>
      </article>
    `;
  }).join("");
}

function historyAction(item) {
  if (isSkipped(item)) {
    return {
      className: "rejected-icon",
      icon: "!",
      label: `Skipped - ${item.skipCode || "unmatched"}`,
    };
  }

  if (item.approvalStatus === "APPROVED_BY_USER") {
    return {
      className: "approved-icon",
      icon: "OK",
      label: `Approved ${formatMoney(item.recommendedAmazonPrice || 0)}`,
    };
  }

  if (item.approvalStatus === "REJECTED_BY_USER" || item.decision?.action === "REJECTED_BY_USER") {
    return {
      className: "rejected-icon",
      icon: "X",
      label: "Rejected by human",
    };
  }

  if (item.decision?.action !== "HUMAN_REVIEW") {
    return {
      className: "approved-icon",
      icon: "OK",
      label: `Listed ${formatMoney(item.recommendedAmazonPrice || 0)}`,
    };
  }

  if ((item.economics?.contributionMarginPercent || 0) < 20) {
    return {
      className: "rejected-icon",
      icon: "X",
      label: "Rejected - margin below floor",
    };
  }

  return {
    className: "edited-icon",
    icon: "EDIT",
    label: "Routed to review",
  };
}

function setMediumSelected(recordId, isSelected) {
  if (isSelected) {
    reviewState.selectedMediumIds.add(recordId);
  } else {
    reviewState.selectedMediumIds.delete(recordId);
  }
  renderMediumBatch(mediumRiskRows());
}

function syncSelectedMediumIds(rows) {
  const validIds = new Set(rows.map((item) => item.recordId));
  reviewState.selectedMediumIds = new Set(
    [...reviewState.selectedMediumIds].filter((recordId) => validIds.has(recordId))
  );
}

async function approveSelectedMedium() {
  const recordIds = [...reviewState.selectedMediumIds];
  if (!recordIds.length) {
    return;
  }

  const button = document.querySelector("#approveMediumSelection");
  button.disabled = true;
  button.textContent = "Approving...";

  try {
    const response = await fetch("/api/research/approve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ recordIds }),
    });

    if (!response.ok) {
      throw new Error("Approval failed");
    }

    const data = await response.json();
    reviewState.analysis = data.isReady ? data : null;
    reviewState.selectedMediumIds = new Set(mediumRiskRows().map((item) => item.recordId));
    document.dispatchEvent(new CustomEvent("analysis:updated"));
    renderReview();
  } catch (error) {
    document.querySelector("#mediumBatchRows").insertAdjacentHTML(
      "afterbegin",
      `<tr><td colspan="7">${escapeHtml(error.message || "Approval failed.")}</td></tr>`
    );
  } finally {
    button.disabled = false;
    button.textContent = "Approve selected";
  }
}

async function approveSelectedHigh() {
  const recordId = reviewState.selectedRecordId;
  if (!recordId) {
    return;
  }

  try {
    await reviewAction("/api/research/approve", [recordId]);
  } catch (error) {
    document.querySelector("#reviewReason").textContent = error.message || "Approval failed.";
  }
}

async function rejectSelectedHigh() {
  const recordId = reviewState.selectedRecordId;
  if (!recordId) {
    return;
  }

  try {
    await reviewAction("/api/research/reject", [recordId]);
  } catch (error) {
    document.querySelector("#reviewReason").textContent = error.message || "Rejection failed.";
  }
}

async function reviewAction(url, recordIds) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ recordIds }),
  });

  if (!response.ok) {
    throw new Error("Review action failed");
  }

  const data = await response.json();
  reviewState.analysis = data.isReady ? data : null;
  reviewState.selectedRecordId = highRiskRows()[0]?.recordId || null;
  reviewState.selectedMediumIds = new Set(mediumRiskRows().map((item) => item.recordId));
  document.dispatchEvent(new CustomEvent("analysis:updated"));
  renderReview();
}

function toggleSelectAll(isSelected) {
  const rows = mediumRiskRows();
  reviewState.selectedMediumIds = isSelected
    ? new Set(rows.map((item) => item.recordId))
    : new Set();
  renderMediumBatch(rows);
}

function syncSelectAllState(rows = mediumRiskRows()) {
  const total = rows.length;
  const selected = reviewState.selectedMediumIds.size;
  setSelectAllState(total > 0 && selected === total, selected > 0 && selected < total);
}

function setSelectAllState(isChecked, isPartial = false) {
  const checkbox = document.querySelector("#mediumSelectAll");
  if (checkbox) {
    checkbox.checked = Boolean(isChecked);
    checkbox.indeterminate = Boolean(isPartial);
    checkbox.disabled = mediumRiskRows().length === 0;
  }
}

function renderCriteria(criteria) {
  const labels = {
    catalogMatch: "Amazon match",
    revenue: "Revenue",
    fbaCompetitive: "FBA fit",
    margin: "Margin",
  };

  return Object.entries(criteria).map(([key, value]) => `
    <section class="mini-gate">
      <span class="${value.passed ? "pass" : "fail"}">${value.passed ? "Clear" : "Review"}</span>
      <strong>${labels[key] || key}</strong>
      <p>${escapeHtml(value.explanation || "")}</p>
    </section>
  `).join("");
}

function renderRiskFactors(factors) {
  if (!factors.length) {
    return "<li>No detailed high-risk factors were returned.</li>";
  }

  return factors.map((factor) => `
    <li class="${String(factor.level || "").toLowerCase()}">
      <strong>${escapeHtml(factor.name || "-")} / ${escapeHtml(factor.level || "-")}</strong>
      <span>${escapeHtml(factor.message || "")}</span>
    </li>
  `).join("");
}

function renderCompetitors(competitors) {
  if (!competitors.length) {
    return "<li>No competitor records cleared the Amazon match and buy-box gates.</li>";
  }

  return competitors.slice(0, 6).map((competitor) => {
    const url = competitor.amazonProductUrl || (competitor.asin ? `https://www.amazon.com/dp/${encodeURIComponent(competitor.asin)}` : "");
    const unitType = competitor.normalization?.unitType || "unit";
    const seller = competitor.buyBoxSeller || competitor.sellerName || "Buy Box seller";

    return `
    <li class="competitor-row rich">
      <span class="rank-badge">${formatInteger(competitor.rank || 0)}</span>
      <img class="competitor-thumb" src="${escapeAttr(competitor.imageUrl || "")}" alt="">
      <div>
        <strong>${escapeHtml(competitor.competitorBrand || competitor.brand || "-")}</strong>
        <a class="competitor-title-link" href="${escapeAttr(url)}" target="_blank" rel="noopener">${escapeHtml(competitor.title || "Amazon product")}</a>
        <span>${escapeHtml(competitor.fulfillmentType || "-")} / ${formatNumber(competitor.matchScore || 0, 1)}% match / ${escapeHtml(seller)}</span>
        <span>ASIN ${url ? `<a href="${escapeAttr(url)}" target="_blank" rel="noopener">${escapeHtml(competitor.asin || "-")}</a>` : escapeHtml(competitor.asin || "-")}</span>
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

function isSkipped(item) {
  return Boolean(item?.isSkipped || item?.analysisStatus === "SKIPPED" || item?.decision?.action === "SKIPPED");
}

function batchName(item) {
  const category = String(item.category || "General").split(" ")[0];
  return `${category} - latest`;
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

function formatCompactMoney(value) {
  const number = Number(value || 0);
  if (Math.abs(number) >= 1000000) {
    return `$${formatNumber(number / 1000000, 1)}M`;
  }
  return `$${formatNumber(number / 1000, 1)}K`;
}

function formatInteger(value) {
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(Number(value || 0));
}

function formatNumber(value, decimals = 0) {
  return new Intl.NumberFormat("en-US", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(Number(value || 0));
}

function setText(id, value) {
  const element = document.querySelector(`#${id}`);
  if (element) {
    element.textContent = value;
  }
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

