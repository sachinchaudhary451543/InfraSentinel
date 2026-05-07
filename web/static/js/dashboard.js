/* Replaced file: dashboard.js - unified, robust, and responsive dashboard script */

let rawDataCache = null;

// Chart holders
const charts = {
  metrics: null,
  doughnut: null,
  bar: null,
};

let darkMode = false;

// Cached DOM elements (filled on DOMContentLoaded)
const E = {};

// Small helpers
const chartColors = { cpu: "#ef4444", ram: "#22c55e", ssd: "#f59e0b" };
const safe = (fn) => {
  try {
    return fn();
  } catch (e) {
    console.error(e);
  }
};

// Format timestamp robustly
function formatTime(ts) {
  if (!ts) return "";
  try {
    return new Date(ts).toLocaleString();
  } catch {
    return String(ts);
  }
}

function avg(arr) {
  if (!arr || !arr.length) return 0;
  return arr.reduce((a, b) => a + b, 0) / arr.length;
}

function colorClass(v) {
  const n = Number(v);
  if (!isFinite(n)) return "text-gray-600"; // non-numeric -> neutral
  if (n > 85) return "text-red-600"; // red only when > 85%
  if (n > 70) return "text-yellow-500";
  return "text-green-600";
}

function tryParseJSON(text) {
  try {
    return JSON.parse(text);
  } catch {
    return [];
  }
}

// Destroy chart safely
function safeDestroyChart(chartRef) {
  if (chartRef && typeof chartRef.destroy === "function") {
    try {
      chartRef.destroy();
    } catch (e) {
      console.warn("Chart destroy failed:", e);
    }
  }
  return null;
}

// Initialize charts dynamically based on data
function initChartsIfNeeded() {
  // Line chart (Usage Trends)
  const metricsCtx = document
    .getElementById("metricsChart")
    ?.getContext?.("2d");
  if (metricsCtx && !charts.metrics) {
    charts.metrics = new Chart(metricsCtx, {
      type: "line",
      data: { labels: [], datasets: [] },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        scales: {
          y: {
            beginAtZero: true,
            max: 100,
            ticks: {
              callback: function (v) {
                return v + "%";
              },
            },
          },
        },
        plugins: {
          legend: { position: "top", display: true },
          title: { display: true, text: "Usage Trends Over Time" },
        },
      },
    });
  }

  // Doughnut chart (Current Usage) - ONLY create on demand when we have data
  // Don't create with empty data
  const doughCtx = document.getElementById("doughnutChart")?.getContext?.("2d");
  if (doughCtx && !charts.doughnut) {
    charts.doughnut = new Chart(doughCtx, {
      type: "doughnut",
      data: {
        labels: ["CPU", "RAM", "SSD"],
        datasets: [
          {
            data: [0, 0, 0],
            backgroundColor: ["#ef4444", "#22c55e", "#f59e0b"],
            borderColor: ["#ffffff", "#ffffff", "#ffffff"],
            borderWidth: 2,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: "bottom", display: true },
          tooltip: {
            callbacks: {
              label: function (ctx) {
                const total = ctx.dataset.data.reduce((a, b) => a + b, 0);
                const percentage =
                  total > 0 ? ((ctx.parsed / total) * 100).toFixed(1) : 0;
                return `${ctx.label}: ${ctx.parsed}% (${percentage}%)`;
              },
            },
          },
        },
      },
    });
  }

  // Bar chart (Server Comparison)
  const barCtx = document.getElementById("serverBarChart")?.getContext?.("2d");
  if (barCtx && !charts.bar) {
    charts.bar = new Chart(barCtx, {
      type: "bar",
      data: {
        labels: [],
        datasets: [
          {
            label: "Avg CPU (%)",
            data: [],
            backgroundColor: "#ef4444",
            borderRadius: 4,
          },
          {
            label: "Avg RAM (%)",
            data: [],
            backgroundColor: "#22c55e",
            borderRadius: 4,
          },
          {
            label: "Avg SSD (%)",
            data: [],
            backgroundColor: "#f59e0b",
            borderRadius: 4,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: true,
        indexAxis: "x",
        scales: {
          y: {
            beginAtZero: true,
            max: 100,
            ticks: {
              callback: function (v) {
                return v + "%";
              },
            },
          },
        },
        plugins: {
          legend: { position: "top", display: true },
          title: { display: true, text: "Average Usage per Server" },
        },
      },
    });
  }
}

// Update line chart dynamically
function updateLineChart(labels, cpu, ram, ssd) {
  if (!charts.metrics) {
    initChartsIfNeeded();
    if (!charts.metrics) return;
  }

  charts.metrics.data.labels = labels;
  charts.metrics.data.datasets = [
    {
      label: "CPU (%)",
      data: cpu,
      borderColor: "#ef4444",
      backgroundColor: "rgba(239, 68, 68, 0.05)",
      tension: 0.4,
      fill: true,
      pointRadius: labels.length > 50 ? 0 : 3,
      pointBackgroundColor: "#ef4444",
    },
    {
      label: "RAM (%)",
      data: ram,
      borderColor: "#22c55e",
      backgroundColor: "rgba(34, 197, 94, 0.05)",
      tension: 0.4,
      fill: true,
      pointRadius: labels.length > 50 ? 0 : 3,
      pointBackgroundColor: "#22c55e",
    },
    {
      label: "SSD (%)",
      data: ssd,
      borderColor: "#f59e0b",
      backgroundColor: "rgba(245, 158, 11, 0.05)",
      tension: 0.4,
      fill: true,
      pointRadius: labels.length > 50 ? 0 : 3,
      pointBackgroundColor: "#f59e0b",
    },
  ];

  try {
    charts.metrics.update("none"); // Update without animation for performance
  } catch (e) {
    console.warn("Line chart update failed:", e);
  }
}

// Update doughnut chart dynamically - FIXED to show latest values properly
function updateDoughnut(cpu, ram, ssd) {
  if (!charts.doughnut) {
    initChartsIfNeeded();
  }

  if (!charts.doughnut) {
    console.warn("Doughnut chart not initialized");
    return;
  }

  // Ensure values are numbers and valid
  const cpuVal = isFinite(cpu) ? parseFloat(cpu) : 0;
  const ramVal = isFinite(ram) ? parseFloat(ram) : 0;
  const ssdVal = isFinite(ssd) ? parseFloat(ssd) : 0;

  console.log(
    `Updating doughnut with CPU=${cpuVal}, RAM=${ramVal}, SSD=${ssdVal}`,
  );

  // Update data
  charts.doughnut.data.datasets[0].data = [cpuVal, ramVal, ssdVal];

  // Update chart
  try {
    charts.doughnut.update("none");
  } catch (e) {
    console.error("Doughnut chart update failed:", e);
  }
}

// Update bar chart across servers dynamically
async function updateBarChartAcrossServers(hours) {
  try {
    const q = new URLSearchParams();
    if (hours && hours > 0) q.append("hours", String(hours));

    const res = await fetch(`/api/metrics?${q.toString()}`);
    if (!res.ok) throw new Error("Failed to fetch metrics for bar chart");

    const all = await res.json();
    if (!Array.isArray(all) || all.length === 0) {
      console.warn("No data for bar chart");
      return;
    }

    // Aggregate by server
    const serverMap = {};
    all.forEach((row) => {
      const hostname = row.Hostname || "unknown";
      const cpu = Number(row.CPU) || 0;
      const ram = Number(row.RAM) || 0;
      const ssd = Number(row.SSD) || 0;

      if (!serverMap[hostname]) {
        serverMap[hostname] = { cpus: [], rams: [], ssds: [] };
      }
      if (isFinite(cpu)) serverMap[hostname].cpus.push(cpu);
      if (isFinite(ram)) serverMap[hostname].rams.push(ram);
      if (isFinite(ssd)) serverMap[hostname].ssds.push(ssd);
    });
    const labels = Object.keys(serverMap).slice(0, 10); // Limit to 10 servers
    const cpuData = labels.map((h) =>
      serverMap[h].cpus.length > 0
        ? Math.round(
            (serverMap[h].cpus.reduce((a, b) => a + b) /
              serverMap[h].cpus.length) *
              100,
          ) / 100
        : 0,
    );
    const ramData = labels.map((h) =>
      serverMap[h].rams.length > 0
        ? Math.round(
            (serverMap[h].rams.reduce((a, b) => a + b) /
              serverMap[h].rams.length) *
              100,
          ) / 100
        : 0,
    );
    const ssdData = labels.map((h) =>
      serverMap[h].ssds.length > 0
        ? Math.round(
            (serverMap[h].ssds.reduce((a, b) => a + b) /
              serverMap[h].ssds.length) *
              100,
          ) / 100
        : 0,
    );

    if (!charts.bar) {
      initChartsIfNeeded();
    }
    if (!charts.bar) return;

    charts.bar.data.labels = labels;
    charts.bar.data.datasets[0].data = cpuData;
    charts.bar.data.datasets[1].data = ramData;
    charts.bar.data.datasets[2].data = ssdData;

    try {
      charts.bar.update("none");
    } catch (e) {
      console.warn("Bar chart update failed:", e);
    }
  } catch (e) {
    console.warn("updateBarChartAcrossServers error:", e);
  }
}

// Update renderCards function to be fully dynamic
function renderCards(data) {
  const latest = data[0] || {};
  const errorCount = data.reduce((acc, r) => acc + (r.Error ? 1 : 0), 0);
  const cpuVals = data.map((r) => Number(r.CPU)).filter((v) => !isNaN(v));
  const ramVals = data.map((r) => Number(r.RAM)).filter((v) => !isNaN(v));
  const ssdVals = data.map((r) => Number(r.SSD)).filter((v) => !isNaN(v));

  const avgCpu = Math.round(avg(cpuVals) || 0);
  const avgRam = Math.round(avg(ramVals) || 0);
  const avgSsd = Math.round(avg(ssdVals) || 0);
  const maxCpu = Math.round(Math.max(...cpuVals, 0));
  const maxRam = Math.round(Math.max(...ramVals, 0));
  const maxSsd = Math.round(Math.max(...ssdVals, 0));

  // Build dynamic cards array
  const cards = [
    {
      title: "Server",
      value: latest.Hostname || "—",
      // icon: "🖥️",
      color: "blue",
      size: "col-span-1",
    },
    {
      title: "CPU (Latest)",
      value: latest.CPU != null ? latest.CPU + "%" : "—",
      // icon: "📊",
      color: "red",
      size: "col-span-1",
      highlight: colorClass(latest.CPU || 0),
    },
    {
      title: "CPU (Avg/Max)",
      value: `${avgCpu}% / ${maxCpu}%`,
      // icon: "📈",
      color: "red",
      size: "col-span-1",
    },
    {
      title: "RAM (Latest)",
      value: latest.RAM != null ? latest.RAM + "%" : "—",
      // icon: "💾",
      color: "green",
      size: "col-span-1",
      highlight: colorClass(latest.RAM || 0),
    },
    {
      title: "RAM (Avg/Max)",
      value: `${avgRam}% / ${maxRam}%`,
      // icon: "📉",
      color: "green",
      size: "col-span-1",
    },
    {
      title: "SSD (Latest)",
      value: latest.SSD != null ? latest.SSD + "%" : "—",
      // icon: "💿",
      color: "yellow",
      size: "col-span-1",
      highlight: colorClass(latest.SSD || 0),
    },
    {
      title: "SSD (Avg/Max)",
      value: `${avgSsd}% / ${maxSsd}%`,
      // icon: "📦",
      color: "yellow",
      size: "col-span-1",
    },
    {
      title: "Data Points",
      value: data.length,
      // icon: "📋",
      color: "purple",
      size: "col-span-1",
    },
    {
      title: "Errors",
      value: errorCount,
      // icon: "⚠️",
      color: errorCount > 0 ? "red" : "gray",
      size: "col-span-1",
    },
  ];

  // Filter out empty cards and render
  const cardsEl = document.getElementById("cards");
  if (!cardsEl) return;

  const colorMap = {
    red: "border-red-500 bg-red-50",
    green: "border-green-500 bg-green-50",
    yellow: "border-yellow-500 bg-yellow-50",
    blue: "border-blue-500 bg-blue-50",
    purple: "border-purple-500 bg-purple-50",
    gray: "border-gray-500 bg-gray-50",
  };

  const textColorMap = {
    red: "text-red-600",
    green: "text-green-600",
    yellow: "text-yellow-600",
    blue: "text-blue-600",
    purple: "text-purple-600",
    gray: "text-gray-600",
  };

  cardsEl.innerHTML = cards
    .map(
      (card) => `
        <div class="bg-white p-4 rounded-xl shadow border-l-4 ${
          colorMap[card.color] || colorMap.blue
        }">
            <div class="flex justify-between items-start">
                <div class="flex-1">
                    <p class="text-xs font-semibold text-gray-600 uppercase tracking-wide">${
                      card.title
                    }</p>
                    <p class="text-2xl font-bold ${
                      card.highlight || textColorMap[card.color]
                    } mt-2">${card.value}</p>
                </div>
            </div>
        </div>
    `,
    )
    .join("");

  // Update legacy elements if they exist
  const errEl = document.getElementById("errorCount");
  const avgCpuEl = document.getElementById("avgCpu");
  if (errEl) errEl.textContent = String(errorCount);
  if (avgCpuEl) avgCpuEl.textContent = avgCpu + "%";
}

// Render everything from mapped data array
function renderAll(mapped) {
  if (!Array.isArray(mapped) || mapped.length === 0) {
    document.getElementById("cards").innerHTML =
      '<div class="col-span-full text-center text-gray-500 p-8">📊 No data available for the selected filters.</div>';
    console.warn("No data to render");
    return;
  }

  rawDataCache = mapped;
  renderCards(mapped);

  // Prepare chart data
  const labels = mapped.map((r) => formatTime(r.Timestamp)).reverse();
  const cpu = mapped
    .map((r) => Number(r.CPU))
    .reverse()
    .map((v) => (isFinite(v) ? v : 0));
  const ram = mapped
    .map((r) => Number(r.RAM))
    .reverse()
    .map((v) => (isFinite(v) ? v : 0));
  const ssd = mapped
    .map((r) => Number(r.SSD))
    .reverse()
    .map((v) => (isFinite(v) ? v : 0));

  // Initialize all charts
  initChartsIfNeeded();

  // Update each chart
  updateLineChart(labels, cpu, ram, ssd);

  // Use LATEST values (end of reversed array = most recent data)
  const latestCpu = cpu[cpu.length - 1] || 0;
  const latestRam = ram[ram.length - 1] || 0;
  const latestSsd = ssd[ssd.length - 1] || 0;

  console.log(
    `Latest values - CPU: ${latestCpu}, RAM: ${latestRam}, SSD: ${latestSsd}`,
  );

  updateDoughnut(latestCpu, latestRam, latestSsd);

  // Update bar chart separately (fetches all servers)
  const hours = Number(E.timeFilter?.value || 24);
  updateBarChartAcrossServers(hours);
}

// Fetch data and render (single entry point)
async function fetchAndRender() {
  if (!E.spinner || !E.lastUpdated) {
    console.warn("Required DOM elements not found");
    return;
  }

  try {
    E.spinner.classList.remove("hidden");
    E.lastUpdated.textContent = "Loading...";

    const params = new URLSearchParams();
    const server = E.serverSelect?.value;
    const timeFilter = E.timeFilter?.value;

    if (server) params.append("server", server);
    if (timeFilter === "custom") {
      const s = E.startDate?.value;
      const e = E.endDate?.value;
      if (s) params.append("start_date", s);
      if (e) params.append("end_date", e);
    } else if (timeFilter && timeFilter !== "0") {
      params.append("hours", timeFilter);
    }

    const res = await fetch(`/api/metrics?${params.toString()}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}: Failed to fetch metrics`);

    const data = await res.json();
    if (!Array.isArray(data)) throw new Error("Invalid response format");

    const mapped = data.map((row) => ({
      Timestamp: row.Timestamp,
      Hostname: row.Hostname,
      CPU: row.CPU,
      RAM: row.RAM,
      SSD: row.SSD,
      Error: row.Error,
    }));

    renderAll(mapped);
    E.lastUpdated.textContent = `Last updated: ${new Date().toLocaleString()}`;
  } catch (err) {
    console.error("Failed to fetch metrics:", err);
    E.lastUpdated.textContent = `Error: ${err.message}`;
    document.getElementById("cards").innerHTML =
      `<div class="col-span-full bg-red-50 border-l-4 border-red-500 p-4 rounded">
        <p class="text-red-700 font-semibold">⚠️ Error loading dashboard</p>
        <p class="text-red-600 text-sm">${err.message}</p>
      </div>`;
  } finally {
    E.spinner.classList.add("hidden");
  }
}

// Handle time filter dropdown (show/hide custom range)
function handleTimeFilterChange(ev) {
  const v = ev.target.value;
  if (v === "custom") E.customDateRange?.classList.remove("hidden");
  else E.customDateRange?.classList.add("hidden");
  // if not custom, trigger fetch
  if (v !== "custom") fetchAndRender();
}

// Utility to set quick filter programmatically
function setQuickFilter(hours) {
  const end = new Date();
  const start = new Date(end - hours * 60 * 60 * 1000);
  if (E.endDate) E.endDate.value = end.toISOString().slice(0, 16);
  if (E.startDate) E.startDate.value = start.toISOString().slice(0, 16);
  if (E.timeFilter) E.timeFilter.value = "custom";
  fetchAndRender();
}

function clearDateFilter() {
  if (E.startDate) E.startDate.value = "";
  if (E.endDate) E.endDate.value = "";
  if (E.timeFilter) E.timeFilter.value = "0";
  fetchAndRender();
}

// Initialization on DOM ready
document.addEventListener("DOMContentLoaded", () => {
  // populate element cache (IDs come from dashboard.html)
  E.spinner = document.getElementById("spinner");
  E.lastUpdated = document.getElementById("lastUpdated");
  E.serverSelect = document.getElementById("serverSelect");
  E.timeFilter = document.getElementById("timeFilter");
  E.customDateRange = document.getElementById("customDateRange");
  E.startDate = document.getElementById("startDate");
  E.endDate = document.getElementById("endDate");
  E.refreshBtn = document.getElementById("refreshBtn");
  E.downloadBtn = document.getElementById("downloadBtn");
  E.schedulerBtn = document.getElementById("schedulerBtn");
  E.stopSchedulerBtn = document.getElementById("stopSchedulerBtn");
  E.schedulerStatus = document.getElementById("schedulerStatus");
  E.themeToggle = document.getElementById("themeToggle"); // optional

  // read servers JSON injected by template
  const servers = tryParseJSON(
    document.getElementById("server-data")?.textContent || "[]",
  );
  if (E.serverSelect) {
    E.serverSelect.innerHTML =
      `<option value="">All Servers</option>` +
      servers.map((s) => `<option value="${s}">${s}</option>`).join("");
  }

  // Restore filters from localStorage if present (AFTER options are populated)
  const saved = tryParseJSON(localStorage.getItem("dashboardFilters") || "{}");

  // Always default to "All Time" if not set or invalid
  if (E.timeFilter) {
    const validOptions = Array.from(E.timeFilter.options).map(
      (opt) => opt.value,
    );
    if (saved.timeFilter && validOptions.includes(saved.timeFilter)) {
      E.timeFilter.value = saved.timeFilter;
    } else {
      E.timeFilter.value = "0"; // Force default to All Time
      saveDashboardFilters(); // Save this as the new default
    }
  }

  if (E.serverSelect && saved.server !== undefined)
    E.serverSelect.value = saved.server;
  if (E.startDate && saved.startDate !== undefined)
    E.startDate.value = saved.startDate;
  if (E.endDate && saved.endDate !== undefined) E.endDate.value = saved.endDate;
  if (E.timeFilter && E.timeFilter.value === "custom") {
    E.customDateRange?.classList.remove("hidden");
  } else {
    E.customDateRange?.classList.add("hidden");
  }

  // wire events
  E.serverSelect?.addEventListener("change", () => {
    saveDashboardFilters();
    fetchAndRender();
  });
  E.timeFilter?.addEventListener("change", (ev) => {
    handleTimeFilterChange(ev);
    saveDashboardFilters();
  });
  E.startDate?.addEventListener("change", () => {
    saveDashboardFilters();
    fetchAndRender();
  });
  E.endDate?.addEventListener("change", () => {
    saveDashboardFilters();
    fetchAndRender();
  });
  E.refreshBtn?.addEventListener("click", fetchAndRender);

  E.downloadBtn?.addEventListener("click", async () => {
    const server = encodeURIComponent(E.serverSelect?.value || "");
    const hours = encodeURIComponent(E.timeFilter?.value || "");
    const url = `/download-report?server=${server}&hours=${hours}`;
    try {
      E.spinner?.classList.remove("hidden");
      E.downloadBtn.disabled = true;
      const res = await fetch(url);
      if (!res.ok) throw new Error("Download failed");
      const blob = await res.blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `ServerMetrics_${new Date()
        .toISOString()
        .slice(0, 19)
        .replace(/[:T]/g, "")}.xlsx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
    } catch (err) {
      alert("Download error: " + (err.message || err));
    } finally {
      E.spinner?.classList.add("hidden");
      E.downloadBtn.disabled = false;
    }
  });

  E.schedulerBtn?.addEventListener("click", async () => {
    if (!confirm("Start scheduler now?")) return;
    try {
      const res = await fetch("/scheduler/start", { method: "POST" });
      const j = await res.json();
      if (j.error) alert("Start failed: " + j.error);
      updateSchedulerStatus();
    } catch (e) {
      alert("Start request failed");
    }
  });
  E.stopSchedulerBtn?.addEventListener("click", async () => {
    if (!confirm("Stop scheduler?")) return;
    try {
      const res = await fetch("/scheduler/stop", { method: "POST" });
      const j = await res.json();
      if (j.error) alert("Stop failed: " + j.error);
      updateSchedulerStatus();
    } catch (e) {
      alert("Stop request failed");
    }
  });

  // init charts and first load
  // initCharts();
  fetchAndRender();
  setInterval(fetchAndRender, 60000);
  setInterval(updateSchedulerStatus, 30000);
});

// Scheduler status helper (keeps element optional)
async function updateSchedulerStatus() {
  if (!E.schedulerStatus) return;
  try {
    const res = await fetch("/scheduler/status");
    const j = await res.json();
    if (j.running) {
      E.schedulerStatus.textContent = `Status: running (pid ${j.pid})`;
      E.schedulerStatus.classList.remove("text-red-500");
      E.schedulerStatus.classList.add("text-green-600");
    } else {
      E.schedulerStatus.textContent = "Status: stopped";
      E.schedulerStatus.classList.remove("text-green-600");
      E.schedulerStatus.classList.add("text-red-500");
    }
  } catch (e) {
    console.error("status err", e);
  }
}

// Ensure fetchAndRender is properly exported
window.fetchAndRender = fetchAndRender;
window.setQuickFilter = setQuickFilter;
window.updateSchedulerStatus = updateSchedulerStatus;

function saveDashboardFilters() {
  localStorage.setItem(
    "dashboardFilters",
    JSON.stringify({
      server: E.serverSelect?.value || "",
      timeFilter: E.timeFilter?.value || "",
      startDate: E.startDate?.value || "",
      endDate: E.endDate?.value || "",
    }),
  );
}

// Clear the dashboardFilters item on script load (for reset)
localStorage.removeItem("dashboardFilters");
