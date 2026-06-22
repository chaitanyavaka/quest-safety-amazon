const dashboardState = {
  analysis: null,
  year: 2026,
  month: 6,
  risk: "all",
  sku: "all",
};

const DASHBOARD_MONTHS = [
  { value: 1, label: "Jan" },
  { value: 2, label: "Feb" },
  { value: 3, label: "Mar" },
  { value: 4, label: "Apr" },
  { value: 5, label: "May" },
  { value: 6, label: "Jun" },
  { value: 7, label: "Jul" },
  { value: 8, label: "Aug" },
  { value: 9, label: "Sep" },
  { value: 10, label: "Oct" },
  { value: 11, label: "Nov" },
  { value: 12, label: "Dec" },
];

initDashboard();

async function initDashboard() {
  bindDashboardFilters();
  const response = await fetch("/api/research/current");
  const data = await response.json();
  dashboardState.analysis = data.isReady ? data : null;
  renderDashboard();
}

function bindDashboardFilters() {
  document.querySelector("#dashboardYear")?.addEventListener("change", (event) => {
    dashboardState.year = Number(event.target.value || 2026);
    syncMonthOptions();
    const maxMonth = maxMonthForYear(dashboardState.year);
    dashboardState.month = maxMonth;
    const monthSelect = document.querySelector("#dashboardMonth");
    if (monthSelect) {
      monthSelect.value = String(maxMonth);
    }
    renderDashboard();
  });

  document.querySelector("#dashboardMonth")?.addEventListener("change", (event) => {
    dashboardState.month = Number(event.target.value || 6);
    renderDashboard();
  });

  document.querySelector("#dashboardSku")?.addEventListener("change", (event) => {
    dashboardState.sku = event.target.value || "all";
    renderDashboard();
  });

  document.querySelector(".dashboard-risk-filter")?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-dashboard-risk]");
    if (!button) {
      return;
    }

    dashboardState.risk = button.dataset.dashboardRisk || "all";
    document.querySelectorAll("[data-dashboard-risk]").forEach((item) => {
      item.classList.toggle("is-active", item === button);
    });
    renderDashboard();
  });

  syncMonthOptions();
}

function syncMonthOptions() {
  const monthSelect = document.querySelector("#dashboardMonth");
  if (!monthSelect) {
    return;
  }

  const maxMonth = maxMonthForYear(dashboardState.year);
  Array.from(monthSelect.options).forEach((option) => {
    const optionMonth = Number(option.value);
    const allowed = optionMonth <= maxMonth;
    option.hidden = !allowed;
    option.disabled = !allowed;
  });

  if (Number(monthSelect.value) > maxMonth) {
    monthSelect.value = String(maxMonth);
    dashboardState.month = maxMonth;
  }
}

function renderDashboard() {
  const rows = dashboardState.analysis?.results || [];
  const approved = rows.filter((item) => isLiveListing(item));
  syncSkuFilterOptions(approved);
  const filteredApproved = filterBySku(filterByRisk(approved));
  const hasRun = Boolean(dashboardState.analysis?.isReady);
  const year = dashboardState.year;
  const month = dashboardState.month;

  document.querySelector("#dashboardEmpty").hidden = hasRun;
  document.querySelector("#dashboardContent").hidden = !hasRun;

  if (!hasRun) {
    return;
  }

  const live = periodLiveCount(filteredApproved.length, year, month);
  const monthlyRunRate = filteredApproved.reduce((sum, item) => sum + periodRevenue(item, year, month), 0);
  const revenueYtd = filteredApproved.reduce((sum, item) => sum + ytdRevenue(item, year, month), 0);
  const weightedMargin = weightedMarginPercent(filteredApproved, year, month);
  const [priorYear, priorMonth] = previousPeriod(year, month);
  const priorMonthRevenue = filteredApproved.reduce((sum, item) => sum + periodRevenue(item, priorYear, priorMonth), 0);
  const growth = priorMonthRevenue ? ((monthlyRunRate - priorMonthRevenue) / priorMonthRevenue) * 100 : 0;
  const addedThisMonth = Math.max(0, live - periodLiveCount(filteredApproved.length, priorYear, priorMonth));

  setText("dashProductsLive", formatInteger(live));
  setText("dashAddedMonth", `+${formatInteger(addedThisMonth)} added this month`);
  setText("dashRevenueYtd", formatCompactMoney(revenueYtd));
  setText("dashRunRate", `${formatCompactMoney(monthlyRunRate)}/mo run-rate`);
  setText("dashGrowth", `${growth >= 0 ? "+" : ""}${formatNumber(growth, 1)}%`);
  setText("dashGrowthPeriod", `${monthLabel(month)} ${year} vs ${monthLabel(priorMonth)} ${priorYear}`);
  setText("dashMargin", `${formatNumber(weightedMargin, 1)}%`);
  setText("dashMarginDelta", `${weightedMargin >= 20 ? "+" : ""}${formatNumber(weightedMargin - 20, 1)} pp vs 20% floor`);
  setText("reviewNavCount", rows.filter((item) => item.decision?.action === "HUMAN_REVIEW").length);
  const skuScope = dashboardState.sku === "all" ? "all eligible SKUs" : `SKU ${dashboardState.sku}`;
  setText("dashboardTitleScope", `${year} through ${monthLabel(month)} - ${skuScope}`);

  renderGrowthChart(filteredApproved, year, month);
  renderDashboardRisk(filteredApproved);
  renderTopProducts(filteredApproved, year, month);
}

function filterByRisk(rows) {
  if (dashboardState.risk === "all") {
    return rows;
  }

  return rows.filter((item) => {
    return String(item.riskAnalysis?.level || "").toLowerCase() === dashboardState.risk;
  });
}

function filterBySku(rows) {
  if (!dashboardState.sku || dashboardState.sku === "all") {
    return rows;
  }
  return rows.filter((item) => String(item.sku || "") === dashboardState.sku);
}

function syncSkuFilterOptions(approvedRows) {
  const select = document.querySelector("#dashboardSku");
  if (!select) {
    return;
  }

  const current = dashboardState.sku || "all";
  const skus = [...new Set(approvedRows.map((item) => String(item.sku || "").trim()).filter(Boolean))].sort((a, b) => a.localeCompare(b));
  const options = ['<option value="all">All eligible SKUs</option>'].concat(
    skus.map((sku) => `<option value="${escapeAttr(sku)}">${escapeHtml(sku)}</option>`)
  );
  select.innerHTML = options.join("");

  if (current !== "all" && skus.includes(current)) {
    select.value = current;
  } else {
    dashboardState.sku = "all";
    select.value = "all";
  }
}

function renderGrowthChart(approved, year, selectedMonth) {
  const months = DASHBOARD_MONTHS.filter((item) => item.value <= maxMonthForYear(year) && item.value <= selectedMonth);
  const series = months.map((month) => {
    return {
      label: month.label,
      revenue: approved.reduce((sum, item) => sum + periodRevenue(item, year, month.value), 0),
      live: periodLiveCount(approved.length, year, month.value),
    };
  });
  const rawMaxRevenue = Math.max(...series.map((item) => item.revenue), 1);
  const rawMaxLive = Math.max(...series.map((item) => item.live), 1);
  const width = 900;
  const height = 360;
  const left = 92;
  const right = 68;
  const top = 28;
  const bottom = 58;
  const plotWidth = width - left - right;
  const plotHeight = height - top - bottom;
  const baseline = top + plotHeight;
  const maxRevenue = Math.max(50000, Math.ceil(rawMaxRevenue / 50000) * 50000);
  const maxLive = Math.max(10, Math.ceil(rawMaxLive / 10) * 10);
  const revenueTicks = Array.from({ length: 7 }, (_, index) => maxRevenue - (maxRevenue / 6) * index);
  const liveTicks = Array.from({ length: 6 }, (_, index) => maxLive - (maxLive / 5) * index);
  const barWidth = Math.min(66, Math.max(34, plotWidth / Math.max(series.length, 1) * 0.46));
  const slot = plotWidth / Math.max(series.length, 1);
  const points = series.map((item, index) => {
    const x = left + slot * index + slot / 2;
    const y = baseline - (item.live / maxLive) * plotHeight;
    return { x, y };
  });

  document.querySelector("#dashboardGrowthChart").innerHTML = `
    <svg class="dashboard-chart-svg" viewBox="0 0 ${width} ${height}" aria-label="Revenue and catalogue growth chart">
      ${revenueTicks.map((value) => {
        const y = baseline - (value / maxRevenue) * plotHeight;
        return `
          <line class="chart-grid-line" x1="${left}" y1="${y}" x2="${width - right}" y2="${y}"></line>
          <text class="chart-axis-label left" x="${left - 14}" y="${y + 5}">${formatChartMoney(value)}</text>
        `;
      }).join("")}
      ${liveTicks.map((value) => {
        const y = baseline - (value / maxLive) * plotHeight;
        return `<text class="chart-axis-label right" x="${width - right + 16}" y="${y + 5}">${formatInteger(value)}</text>`;
      }).join("")}
      <line class="chart-baseline" x1="${left}" y1="${baseline}" x2="${width - right}" y2="${baseline}"></line>
      ${series.map((item, index) => {
        const x = left + slot * index + slot / 2;
        const barHeight = Math.max(10, (item.revenue / maxRevenue) * plotHeight);
        const y = baseline - barHeight;
        return `
          <rect class="chart-bar" x="${x - barWidth / 2}" y="${y}" width="${barWidth}" height="${barHeight}" rx="9"></rect>
          <text class="chart-month-label" x="${x}" y="${baseline + 32}">${item.label}</text>
        `;
      }).join("")}
      <polyline class="chart-product-line" points="${points.map((point) => `${point.x},${point.y}`).join(" ")}"></polyline>
      ${points.map((point) => `<circle class="chart-product-point" cx="${point.x}" cy="${point.y}" r="8"></circle>`).join("")}
    </svg>
  `;
}

function renderDashboardRisk(approved) {
  const counts = {
    low: approved.filter((item) => item.riskAnalysis?.level === "LOW").length,
    medium: approved.filter((item) => item.riskAnalysis?.level === "MEDIUM").length,
    high: approved.filter((item) => item.riskAnalysis?.level === "HIGH").length,
  };
  const total = counts.low + counts.medium + counts.high;
  const slices = [
    { key: "low", label: "Low", value: counts.low, color: "#1f925b" },
    { key: "medium", label: "Medium", value: counts.medium, color: "#d18400" },
    { key: "high", label: "High", value: counts.high, color: "#bb3a3d" },
  ];
  const ring = buildDonutSlices(slices, total);

  document.querySelector("#dashboardRiskDonut").innerHTML = `
    <svg class="risk-donut-svg" viewBox="0 0 320 320" aria-label="Live catalogue by risk tier">
      <circle class="risk-donut-track" cx="160" cy="160" r="112"></circle>
      ${ring}
      <circle class="risk-donut-hole" cx="160" cy="160" r="70"></circle>
      <text class="risk-donut-total" x="160" y="154">${formatInteger(total)}</text>
      <text class="risk-donut-subtitle" x="160" y="182">live</text>
    </svg>
  `;
  document.querySelector("#dashboardRiskLegend").innerHTML = [
    ["low", "Low", counts.low],
    ["medium", "Medium", counts.medium],
    ["high", "High", counts.high],
  ].map(([key, label, value]) => `
    <button type="button">
      <span class="legend-dot ${key}"></span>
      <strong>${label}</strong>
      <em>${formatInteger(value)} live</em>
    </button>
  `).join("");
}

function buildDonutSlices(slices, total) {
  if (!total) {
    return "";
  }

  const cx = 160;
  const cy = 160;
  const radius = 112;
  const stroke = 46;
  const gapDegrees = slices.filter((slice) => slice.value > 0).length > 1 ? 3.2 : 0;
  const available = 360 - gapDegrees * slices.filter((slice) => slice.value > 0).length;
  let angle = -90;

  return slices.map((slice) => {
    if (!slice.value) {
      return "";
    }

    const size = (slice.value / total) * available;
    const start = angle + gapDegrees / 2;
    const end = angle + size - gapDegrees / 2;
    angle += size + gapDegrees;
    return `<path class="risk-donut-slice" d="${describeArc(cx, cy, radius, start, end)}" stroke="${slice.color}" stroke-width="${stroke}"></path>`;
  }).join("");
}

function describeArc(cx, cy, radius, startAngle, endAngle) {
  const start = polarToCartesian(cx, cy, radius, endAngle);
  const end = polarToCartesian(cx, cy, radius, startAngle);
  const largeArcFlag = endAngle - startAngle <= 180 ? "0" : "1";
  return `M ${start.x} ${start.y} A ${radius} ${radius} 0 ${largeArcFlag} 0 ${end.x} ${end.y}`;
}

function polarToCartesian(cx, cy, radius, angleDegrees) {
  const angleRadians = (angleDegrees * Math.PI) / 180;
  return {
    x: cx + radius * Math.cos(angleRadians),
    y: cy + radius * Math.sin(angleRadians),
  };
}

function renderTopProducts(approved, year, month) {
  const table = document.querySelector("#dashboardTopProducts");
  const rows = [...approved]
    .sort((a, b) => periodRevenue(b, year, month) - periodRevenue(a, year, month))
    .slice(0, 6);

  if (!rows.length) {
    table.innerHTML = '<tr><td colspan="7">No approved products match the selected dashboard filters.</td></tr>';
    return;
  }

  table.innerHTML = rows.map((item, index) => {
    const risk = String(item.riskAnalysis?.level || "LOW").toLowerCase();
    const margin = periodMargin(item, year, month);
    const [priorYear, priorMonth] = previousPeriod(year, month);
    const currentRevenue = periodRevenue(item, year, month);
    const previousRevenue = periodRevenue(item, priorYear, priorMonth);
    const growth = previousRevenue ? ((currentRevenue - previousRevenue) / previousRevenue) * 100 : 0;

    return `
      <tr>
        <td><strong>${escapeHtml(item.name || "-")}</strong><small>${escapeHtml(item.sku || "-")}${primaryAmazonUrl(item) ? ` / ${renderAmazonLink(primaryAmazonUrl(item), "Amazon match")}` : ""}</small></td>
        <td>${escapeHtml(item.category || "Uncategorized")}</td>
        <td><span class="risk-pill ${risk}">${titleCase(item.riskAnalysis?.level || "LOW")}</span></td>
        <td>${escapeHtml(approvalSource(item))}</td>
        <td class="${margin >= 20 ? "positive" : "negative"}">${formatNumber(margin, 1)}%</td>
        <td>${formatCompactMoney(currentRevenue)}</td>
        <td class="${growth >= 0 ? "positive" : "negative"}">${growth >= 0 ? "+" : ""}${formatNumber(growth, 1)}%</td>
      </tr>
    `;
  }).join("");
}

function primaryAmazonUrl(item) {
  const first = item?.competitors?.[0] || {};
  return first.amazonProductUrl || item?.amazonProductUrl || "";
}

function renderAmazonLink(url, label) {
  if (!url) {
    return escapeHtml(label || "-");
  }
  return `<a href="${escapeAttr(url)}" target="_blank" rel="noopener">${escapeHtml(label || url)}</a>`;
}

function approvalSource(item) {
  if (item.approvalStatus === "APPROVED_BY_USER") {
    return "Review";
  }

  if (item.riskAnalysis?.level === "MEDIUM") {
    return "Batch";
  }

  return "Auto";
}

function isLiveListing(item) {
  return (
    item?.approvalStatus === "APPROVED_BY_USER" ||
    ["PUSH_TO_AMAZON", "REPRICE_AND_PUSH"].includes(item?.decision?.action)
  );
}

function weightedMarginPercent(rows, year, month) {
  const revenue = rows.reduce((sum, item) => sum + periodRevenue(item, year, month), 0);
  if (!revenue) {
    return 0;
  }

  return rows.reduce((sum, item) => {
    return sum + periodRevenue(item, year, month) * periodMargin(item, year, month);
  }, 0) / revenue;
}

function periodRevenue(item, year, month) {
  return Number(item.monthlyRevenue || 0) * periodFactor(year, month);
}

function ytdRevenue(item, year, month) {
  return DASHBOARD_MONTHS
    .filter((period) => period.value <= month)
    .reduce((sum, period) => sum + periodRevenue(item, year, period.value), 0);
}

function periodFactor(year, month) {
  const monthRamp = 0.62 + (Number(month || 1) - 1) * 0.074;
  const yearFactor = Number(year) === 2026 ? 1 : 0.86;
  return Math.max(0.35, monthRamp * yearFactor);
}

function periodLiveCount(count, year, month) {
  const monthFactor = Math.min(1, 0.68 + (Number(month || 1) - 1) * 0.064);
  const yearFactor = Number(year) === 2026 ? 1 : 0.84;
  return Math.round(Number(count || 0) * monthFactor * yearFactor);
}

function periodMargin(item, year, month) {
  const baseMargin = Number(item.economics?.contributionMarginPercent || 0);
  const monthMovement = (Number(month || 1) - 6) * 0.08;
  const yearMovement = Number(year) === 2026 ? 0 : -0.6;
  return Math.min(Math.max(baseMargin + monthMovement + yearMovement, 0), 60);
}

function previousPeriod(year, month) {
  if (month > 1) {
    return [year, month - 1];
  }

  return [year - 1, 12];
}

function monthLabel(month) {
  return DASHBOARD_MONTHS.find((item) => item.value === Number(month))?.label || "Jan";
}

function maxMonthForYear(year) {
  return Number(year) === 2025 ? 12 : 6;
}

function formatCompactMoney(value) {
  const number = Number(value || 0);
  if (Math.abs(number) >= 1000000) {
    return `$${formatNumber(number / 1000000, 2)}M`;
  }
  return `$${formatNumber(number / 1000, 1)}K`;
}

function formatChartMoney(value) {
  return `$${formatNumber(Number(value || 0) / 1000, 0)}K`;
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

function titleCase(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
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
