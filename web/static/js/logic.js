const fileInput = document.getElementById("fileInput");
const statusEl = document.getElementById("status");
const summaryEl = document.getElementById("summary");
const chartsEl = document.getElementById("charts");
const previewSection = document.getElementById("previewSection");
const previewTable = document.getElementById("previewTable");
const downloadBtn = document.getElementById("downloadBtn");

let datasetId = null;

function renderSummary(summary, types) {
  let html = `<h2 class="text-xl font-bold mb-3">📘 Summary</h2>
        <p><b>Rows:</b> ${summary.rows}, <b>Columns:</b> ${summary.columns}</p>`;
  if (Object.keys(summary.numeric).length) {
    html += `<h3 class="mt-3 font-semibold">Numeric Columns:</h3><ul class="list-disc list-inside">`;
    for (const [col, stats] of Object.entries(summary.numeric)) {
      html += `<li>${col}: mean=${stats.mean?.toFixed(2) || "N/A"}, count=${
        stats.count
      }</li>`;
    }
    html += "</ul>";
  }
  html += `<h3 class="mt-3 font-semibold">Detected Types:</h3>
        <p><b>Date:</b> ${types.datetime.join(", ") || "-"}<br>
        <b>Numeric:</b> ${types.numeric.join(", ") || "-"}<br>
        <b>Categorical:</b> ${types.categorical.join(", ") || "-"}<br>
        <b>Text:</b> ${types.text.join(", ") || "-"}</p>`;
  summaryEl.innerHTML = html;
  summaryEl.classList.remove("hidden");
}

function renderPreview(preview) {
  if (!preview.length) return;
  const cols = Object.keys(preview[0]);
  let html =
    "<thead><tr>" +
    cols
      .map((c) => `<th class='border px-2 py-1 bg-gray-100'>${c}</th>`)
      .join("") +
    "</tr></thead><tbody>";
  preview.forEach((row) => {
    html +=
      "<tr>" +
      cols
        .map((c) => `<td class='border px-2 py-1'>${row[c] ?? ""}</td>`)
        .join("") +
      "</tr>";
  });
  html += "</tbody>";
  previewTable.innerHTML = html;
  previewSection.classList.remove("hidden");
}

function renderCharts(recommendations, data) {
  chartsEl.innerHTML = "";
  const num = recommendations.length;
  if (!num) {
    chartsEl.innerHTML =
      "<p class='text-gray-500'>No chart recommendations available.</p>";
    return;
  }
  const chartData = {};
  recommendations.forEach((rec, i) => {
    const div = document.createElement("div");
    div.className = "bg-white p-4 rounded shadow";
    div.innerHTML = `<h3 class="font-semibold mb-2">${rec.title}</h3><canvas id="chart${i}"></canvas>`;
    chartsEl.appendChild(div);
    chartData[`chart${i}`] = rec;
  });
  recommendations.forEach((rec, i) => {
    const ctx = document.getElementById(`chart${i}`);
    const chartType = rec.type;
    if (chartType === "hist") {
      const col = rec.col;
      const values = data.map((r) => r[col]).filter((v) => !isNaN(v));
      new Chart(ctx, {
        type: "bar",
        data: {
          labels: values.slice(0, 20),
          datasets: [
            {
              label: col,
              data: values.slice(0, 20),
              backgroundColor: "#60a5fa",
            },
          ],
        },
      });
    } else if (chartType === "bar_count") {
      const col = rec.col;
      const counts = {};
      data.forEach((r) => {
        const v = r[col];
        counts[v] = (counts[v] || 0) + 1;
      });
      const labels = Object.keys(counts).slice(0, 10);
      const vals = Object.values(counts).slice(0, 10);
      new Chart(ctx, {
        type: "bar",
        data: {
          labels,
          datasets: [{ label: col, data: vals, backgroundColor: "#34d399" }],
        },
      });
    }
  });
}

fileInput.addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  statusEl.textContent = "📤 Uploading and analyzing data...";
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch("/upload-any-data", {
    method: "POST",
    body: formData,
  });
  const result = await res.json();
  if (result.error) {
    statusEl.textContent = `❌ Error: ${result.error}`;
    return;
  }
  statusEl.textContent = "✅ Analysis complete!";
  datasetId = result.id;
  renderSummary(result.summary, result.types);
  renderPreview(result.preview);
  renderCharts(result.recommendations, result.preview);
  downloadBtn.classList.remove("hidden");
});

downloadBtn.addEventListener("click", () => {
  if (!datasetId) return;
  window.location = `/generate-report/${datasetId}`;
});
