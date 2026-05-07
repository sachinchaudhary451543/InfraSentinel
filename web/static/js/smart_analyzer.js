// web/static/js/smart_analyzer.js
console.log("Smart Analyzer JS loaded");
const fileInput = document.getElementById("fileInput");
const summaryDiv = document.getElementById("summary");
const chartsDiv = document.getElementById("charts");
const downloadBtn = document.getElementById("downloadBtn");
const statusDiv = document.getElementById("status");
let charts = {};
let currentData = null;
let currentUID = null;

// Show/hide loading spinner
function showLoading(show = true) {
  const spinner = document.getElementById("loadingSpinner");
  if (show) spinner?.classList.remove("hidden");
  else spinner?.classList.add("hidden");
}

// Show message
function showMessage(elementId, text, type = "info") {
  const el = document.getElementById(elementId);
  if (!el) return;

  el.textContent = text;
  el.classList.remove(
    "hidden",
    "bg-blue-50",
    "text-blue-700",
    "bg-green-50",
    "text-green-700",
    "bg-red-50",
    "text-red-700"
  );

  if (type === "success") {
    el.classList.add("bg-green-50", "text-green-700");
  } else if (type === "error") {
    el.classList.add("bg-red-50", "text-red-700");
  } else {
    el.classList.add("bg-blue-50", "text-blue-700");
  }
}

// Hide message
function hideMessage(elementId) {
  const el = document.getElementById(elementId);
  if (el) el.classList.add("hidden");
}

// Destroy chart safely
function destroyChart(chartRef) {
  if (chartRef && typeof chartRef.destroy === "function") {
    try {
      chartRef.destroy();
    } catch (e) {
      console.warn("Chart destroy failed:", e);
    }
  }
}

// Show results container
function showResults() {
  document.getElementById("emptyState")?.classList.add("hidden");
  document.getElementById("resultsContainer")?.classList.remove("hidden");
}

// Hide results container
function hideResults() {
  document.getElementById("emptyState")?.classList.remove("hidden");
  document.getElementById("resultsContainer")?.classList.add("hidden");
}

// Render summary cards
function renderSummaryCards(summary) {
  const container = document.getElementById("summaryCards");
  if (!container) return;

  const cards = [
    {
      title: "Total Records",
      value: summary.rows || 0,
      icon: "📋",
      color: "blue",
    },
    {
      title: "Columns",
      value: summary.columns || 0,
      icon: "📊",
      color: "green",
    },
    {
      title: "Rows Inserted",
      value: summary.inserted || 0,
      icon: "✅",
      color: "purple",
    },
    {
      title: "Missing Values",
      value: summary.missing || 0,
      icon: "⚠️",
      color: "yellow",
    },
  ];

  const colorMap = {
    blue: "bg-blue-50 border-blue-500 text-blue-600",
    green: "bg-green-50 border-green-500 text-green-600",
    purple: "bg-purple-50 border-purple-500 text-purple-600",
    yellow: "bg-yellow-50 border-yellow-500 text-yellow-600",
  };

  container.innerHTML = cards
    .map(
      (card) => `
        <div class="border-l-4 p-4 rounded-lg ${colorMap[card.color]}">
            <div class="flex justify-between items-start">
                <div>
                    <p class="text-sm font-semibold uppercase opacity-75">${
                      card.title
                    }</p>
                    <p class="text-3xl font-bold mt-2">${card.value}</p>
                </div>
            </div>
        </div>
    `
    )
    .join("");
}

// Render data preview table
function renderDataPreview(preview) {
  if (!preview || preview.length === 0) return;

  const tableHeader = document.getElementById("tableHeader");
  const tableBody = document.getElementById("tableBody");
  if (!tableHeader || !tableBody) return;

  const columns = Object.keys(preview[0]);

  tableHeader.innerHTML = columns
    .map(
      (col) =>
        `<th class="p-3 text-left bg-gray-200 font-bold border">${col}</th>`
    )
    .join("");

  tableBody.innerHTML = preview
    .slice(0, 20)
    .map(
      (row) => `
        <tr class="hover:bg-gray-50">
            ${columns
              .map(
                (col) => `
                <td class="p-3 border text-sm">${
                  row[col] !== null && row[col] !== undefined ? row[col] : "—"
                }</td>
            `
              )
              .join("")}
        </tr>
    `
    )
    .join("");
}

// Render statistics table
function renderStatisticsTable(summary) {
  if (!summary.numeric) return;

  const statsContainer = document.getElementById("statsTable");
  if (!statsContainer) return;

  const stats = Object.entries(summary.numeric)
    .map(
      ([col, data]) => `
        <div class="mb-4 p-4 bg-gray-50 rounded-lg">
            <h4 class="font-bold text-blue-600 mb-3">${col}</h4>
            <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div>
                    <span class="text-xs text-gray-600">Count</span>
                    <p class="text-lg font-bold">${data.count || 0}</p>
                </div>
                <div>
                    <span class="text-xs text-gray-600">Mean</span>
                    <p class="text-lg font-bold">${
                      data.mean ? data.mean.toFixed(2) : "N/A"
                    }</p>
                </div>
                <div>
                    <span class="text-xs text-gray-600">Min</span>
                    <p class="text-lg font-bold">${
                      data.min !== undefined ? data.min : "N/A"
                    }</p>
                </div>
                <div>
                    <span class="text-xs text-gray-600">Max</span>
                    <p class="text-lg font-bold">${
                      data.max !== undefined ? data.max : "N/A"
                    }</p>
                </div>
            </div>
        </div>
    `
    )
    .join("");

  statsContainer.innerHTML = `
        <div class="space-y-2">
            ${stats}
        </div>
    `;
}

// Render dynamic charts
function renderCharts(recommendations, preview) {
  const chartsGrid = document.getElementById("chartsGrid");
  if (!chartsGrid || !recommendations) return;

  chartsGrid.innerHTML = "";

  recommendations.slice(0, 4).forEach((rec, idx) => {
    const chartId = `chart-${idx}`;
    const container = document.createElement("div");
    container.className = "bg-white rounded-lg shadow p-4";
    container.innerHTML = `
            <h4 class="font-bold mb-4">${rec.title || "Chart " + (idx + 1)}</h4>
            <div style="position: relative; height: 300px;">
                <canvas id="${chartId}"></canvas>
            </div>
        `;
    chartsGrid.appendChild(container);

    const ctx = document.getElementById(chartId)?.getContext("2d");
    if (!ctx) return;

    try {
      if (rec.type === "hist" && rec.col && preview) {
        renderHistogram(ctx, rec.col, preview, idx);
      } else if (rec.type === "bar_count" && rec.col && preview) {
        renderBarCount(ctx, rec.col, preview, idx);
      } else if (rec.type === "line_time" && rec.x && rec.ys && preview) {
        renderLineChart(ctx, rec.x, rec.ys, preview, idx);
      } else {
        ctx.font = "14px Arial";
        ctx.fillText("Chart type not supported for preview", 10, 50);
      }
    } catch (e) {
      console.error("Chart rendering error:", e);
    }
  });
}

// Histogram chart
function renderHistogram(ctx, column, preview, idx) {
  if (charts[`hist-${idx}`]) destroyChart(charts[`hist-${idx}`]);

  const data = preview
    .map((r) => r[column])
    .filter((v) => v !== null && v !== undefined && !isNaN(v))
    .map((v) => parseFloat(v))
    .sort((a, b) => a - b);

  if (data.length === 0) {
    ctx.fillText("No numeric data available", 10, 50);
    return;
  }

  const bins = 20;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const binSize = (max - min) / bins || 1;
  const binCounts = Array(bins).fill(0);

  data.forEach((v) => {
    const binIdx = Math.floor((v - min) / binSize);
    if (binIdx >= 0 && binIdx < bins) binCounts[binIdx]++;
  });

  charts[`hist-${idx}`] = new Chart(ctx, {
    type: "bar",
    data: {
      labels: binCounts.map((_, i) => `${(min + i * binSize).toFixed(1)}`),
      datasets: [
        {
          label: column,
          data: binCounts,
          backgroundColor: "#3b82f6",
          borderColor: "#1e40af",
          borderWidth: 1,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: { y: { beginAtZero: true } },
      plugins: { legend: { display: false } },
    },
  });
}

// Bar count chart
function renderBarCount(ctx, column, preview, idx) {
  if (charts[`bar-${idx}`]) destroyChart(charts[`bar-${idx}`]);

  const freq = {};
  preview.forEach((r) => {
    const k = String(r[column] || "");
    freq[k] = (freq[k] || 0) + 1;
  });

  const sorted = Object.entries(freq)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 10);

  charts[`bar-${idx}`] = new Chart(ctx, {
    type: "bar",
    data: {
      labels: sorted.map(([k]) => k),
      datasets: [
        {
          label: column,
          data: sorted.map(([, v]) => v),
          backgroundColor: "#10b981",
          borderColor: "#059669",
          borderWidth: 1,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: { y: { beginAtZero: true } },
      plugins: { legend: { display: false } },
    },
  });
}

// Line chart
function renderLineChart(ctx, xCol, yCols, preview, idx) {
  if (charts[`line-${idx}`]) destroyChart(charts[`line-${idx}`]);

  const colors = ["#ef4444", "#22c55e", "#f59e0b", "#3b82f6"];

  const labels = preview.map((r) => String(r[xCol] || "").substring(0, 10));
  const datasets = yCols.slice(0, 3).map((yCol, i) => ({
    label: yCol,
    data: preview.map((r) => {
      const v = parseFloat(r[yCol]);
      return isNaN(v) ? null : v;
    }),
    borderColor: colors[i],
    backgroundColor: colors[i] + "15",
    tension: 0.3,
    fill: false,
  }));

  charts[`line-${idx}`] = new Chart(ctx, {
    type: "line",
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { position: "top" } },
      scales: { y: { beginAtZero: true } },
    },
  });
}

// --- Replace template URLs (static JS can't use Jinja) ---
try {
  // ...existing code...
} catch (e) {
  console.error(e);
}

// --- CHANGED: use concrete endpoints under the blueprint ---
// File upload handler
document.getElementById("uploadForm")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const formData = new FormData();
  const fileInput = e.target.querySelector("input[type='file']");

  if (!fileInput?.files[0]) {
    showMessage("uploadMessage", "❌ Please select a file", "error");
    return;
  }

  formData.append("file", fileInput.files[0]);
  showLoading(true);
  hideMessage("uploadMessage");

  try {
    // <-- changed: use concrete endpoint path -->
    const res = await fetch("/smart-analyzer/upload-analyze", {
      method: "POST",
      body: formData,
    });

    const data = await res.json();
    if (data.error) {
      showMessage("uploadMessage", `❌ ${data.error}`, "error");
      return;
    }

    currentUID = data.id;
    currentData = data;

    renderSummaryCards(data.summary);
    renderDataPreview(data.preview);
    renderStatisticsTable(data.summary);
    renderCharts(data.recommendations, data.preview);

    showResults();
    showMessage(
      "uploadMessage",
      `✅ File analyzed successfully! ${data.summary.rows} records processed.`,
      "success"
    );

    // Update stats
    document.getElementById("statRecords").textContent = data.summary.rows;
    document.getElementById("statColumns").textContent = data.summary.columns;
    document.getElementById("statTime").textContent =
      new Date().toLocaleString();

    // Clear file input
    fileInput.value = "";
  } catch (err) {
    showMessage("uploadMessage", `❌ Error: ${err.message}`, "error");
  } finally {
    showLoading(false);
  }
});

// Analyze current database
document
  .getElementById("analyzeCurrentBtn")
  ?.addEventListener("click", async () => {
    showLoading(true);

    try {
      // <-- changed: concrete endpoint -->
      const res = await fetch("/smart-analyzer/analyze-current-metrics");
      const data = await res.json();

      if (data.error) {
        alert(`Error: ${data.error}`);
        return;
      }

      currentData = data;

      const summary = {
        rows: data.stats?.total_records || 0,
        columns: data.stats?.columns || 0,
        inserted: 0,
        missing: 0,
      };

      renderSummaryCards(summary);
      renderCharts(data.recommendations, data.preview);

      showResults();
      showMessage(
        "uploadMessage",
        "✅ Current database analyzed successfully!",
        "success"
      );

      // Update stats
      document.getElementById("statRecords").textContent = summary.rows;
      document.getElementById("statColumns").textContent = summary.columns;
      document.getElementById("statTime").textContent =
        new Date().toLocaleString();
    } catch (err) {
      alert(`Error: ${err.message}`);
    } finally {
      showLoading(false);
    }
  });

// Download report
document
  .getElementById("downloadDbReportBtn")
  ?.addEventListener("click", () => {
    // <-- changed: concrete download URL -->
    window.location.href = "/smart-analyzer/download-analysis-report";
  });

// Mobile menu toggle
document.getElementById("menuToggle")?.addEventListener("click", () => {
  const menu = document.getElementById("mobileMenu");
  menu?.classList.toggle("hidden");
});

// Navbar highlighting
document.addEventListener("DOMContentLoaded", () => {
  const path = window.location.pathname;
  if (path.includes("smart-analyzer")) {
    document
      .getElementById("nav-analyzer")
      ?.classList.add("text-yellow-500", "underline");
  }
});
