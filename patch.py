import sys

with open('web/templates/dashboard.html', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Fix the layout going out of bounds
content = content.replace(
    ".noc-page {\n        margin: -24px -32px !important;\n    }",
    ".noc-page {\n        margin: 0 !important;\n        width: 100%;\n        box-sizing: border-box;\n    }"
)

# 2. Add createCombinedLineChart function right after createLineChart
create_combined_func = """
        // -- Real-Time COMBINED Line Chart Factory --
        function createCombinedLineChart(canvasId, labelsArray, cpuData, ramData) {
            if (typeof Chart === 'undefined') {
                console.error('Chart.js not loaded; cannot render combined chart');
                return null;
            }
            const el = document.getElementById(canvasId);
            if (!el) return null;
            const ctx = el.getContext('2d');

            const cpuColor = '#818cf8';
            const ramColor = '#34d399';

            const gradientCpu = ctx.createLinearGradient(0, 0, 0, el.parentElement.clientHeight || 300);
            gradientCpu.addColorStop(0, cpuColor + '20');
            gradientCpu.addColorStop(1, cpuColor + '00');

            const gradientRam = ctx.createLinearGradient(0, 0, 0, el.parentElement.clientHeight || 300);
            gradientRam.addColorStop(0, ramColor + '20');
            gradientRam.addColorStop(1, ramColor + '00');

            return new Chart(ctx, {
                type: 'line',
                data: {
                    labels: labelsArray,
                    datasets: [
                        {
                            label: 'CPU',
                            data: cpuData,
                            borderColor: cpuColor,
                            backgroundColor: gradientCpu,
                            borderWidth: 1.5,
                            fill: true,
                            tension: 0.4,
                            pointRadius: 0,
                            pointHoverRadius: 4,
                            pointHoverBackgroundColor: cpuColor,
                            pointHoverBorderColor: '#0d1422',
                            pointHoverBorderWidth: 2
                        },
                        {
                            label: 'RAM',
                            data: ramData,
                            borderColor: ramColor,
                            backgroundColor: gradientRam,
                            borderWidth: 1.5,
                            fill: true,
                            tension: 0.4,
                            pointRadius: 0,
                            pointHoverRadius: 4,
                            pointHoverBackgroundColor: ramColor,
                            pointHoverBorderColor: '#0d1422',
                            pointHoverBorderWidth: 2
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    animation: { duration: 400, easing: 'easeOutQuart' },
                    interaction: { intersect: false, mode: 'index' },
                    scales: {
                        y: {
                            min: 0,
                            max: 100,
                            display: true,
                            grid: { color: 'rgba(56,189,248,0.04)', drawBorder: false },
                            ticks: {
                                font: { size: 9, weight: '700', family: "'JetBrains Mono', monospace" },
                                color: '#334155',
                                stepSize: 25,
                                callback: v => v + '%'
                            },
                            border: { display: false }
                        },
                        x: {
                            display: true,
                            grid: { color: 'rgba(56,189,248,0.03)', drawBorder: false },
                            ticks: {
                                color: '#334155',
                                font: { size: 8, weight: '700', family: "'JetBrains Mono', monospace" },
                                autoSkip: true,
                                maxTicksLimit: 8,
                                maxRotation: 0,
                                callback: function (value, index) {
                                    const raw = this.getLabelForValue(value) || '';
                                    if (!raw) return '';
                                    const parts = raw.split(', ');
                                    if (parts.length >= 2) {
                                        const datePart = parts[0].substring(0, 5);
                                        const timePart = parts[1].replace(/:00 /, ' ');
                                        return datePart + ' ' + timePart;
                                    }
                                    return raw;
                                }
                            }
                        }
                    },
                    plugins: {
                        legend: { display: true, position: 'top', labels: { color: '#64748b', font: { size: 10, family: "'JetBrains Mono', monospace" }, boxWidth: 10 } },
                        tooltip: {
                            backgroundColor: '#0d1422',
                            borderColor: 'rgba(34,211,238,0.2)',
                            borderWidth: 1,
                            titleFont: { size: 9, weight: '700', family: "'JetBrains Mono', monospace" },
                            bodyFont: { size: 10, family: "'JetBrains Mono', monospace" },
                            titleColor: '#64748b',
                            bodyColor: '#e2e8f0',
                            padding: 10,
                            cornerRadius: 3,
                            displayColors: true,
                            callbacks: {
                                title: items => {
                                    const lbl = items?.[0]?.label || '';
                                    return lbl ? lbl + ' IST' : '';
                                },
                                label: ctx => `${ctx.dataset.label}: ${ctx.parsed.y.toFixed(1)}%`
                            }
                        }
                    }
                }
            });
        }
"""

if "function createCombinedLineChart" not in content:
    content = content.replace(
        "// -- Disk Doughnut",
        create_combined_func + "\n\n        // -- Disk Doughnut"
    )

old_charts_row = """                    <!-- Charts Row: CPU + RAM -->
                    <div class="noc-grid-2" style="margin-bottom:14px;">
                        <!-- CPU Chart -->
                        <div class="chart-panel">
                            <div class="chart-header">
                                <div class="chart-label">
                                    <i class="fa-solid fa-microchip" style="color:var(--noc-indigo);"></i>
                                    CPU Utilization
                                </div>
                                <span class="chart-value" id="live-cpu-val-{{ server.id }}"
                                    style="color:var(--noc-indigo);">
                                    {% if server.cpu_percent %}{{ server.cpu_percent|round(1) }}%{% else %}--{% endif %}
                                </span>
                            </div>
                            <div style="height:220px; position:relative;">
                                <canvas id="chart-cpu-{{ server.id }}"></canvas>
                            </div>
                        </div>

                        <!-- RAM Chart -->
                        <div class="chart-panel">
                            <div class="chart-header">
                                <div class="chart-label">
                                    <i class="fa-solid fa-memory" style="color:var(--noc-emerald);"></i>
                                    Memory Utilization
                                </div>
                                <span class="chart-value" id="live-ram-val-{{ server.id }}"
                                    style="color:var(--noc-emerald);">
                                    {% if server.memory_percent %}{{ server.memory_percent|round(1) }}%{% else %}--{%
                                    endif %}
                                </span>
                            </div>
                            <div style="height:220px; position:relative;">
                                <canvas id="chart-ram-{{ server.id }}"></canvas>
                            </div>
                        </div>
                    </div>"""

new_charts_row = """                    <!-- Combined Charts Row: CPU + RAM -->
                    <div style="margin-bottom:14px;">
                        <div class="chart-panel">
                            <div class="chart-header">
                                <div class="chart-label">
                                    <i class="fa-solid fa-chart-line" style="color:var(--noc-cyan);"></i>
                                    System Performance
                                </div>
                                <div style="display:flex; gap:16px;">
                                    <span class="chart-value" id="live-cpu-val-{{ server.id }}" style="color:var(--noc-indigo);">
                                        <i class="fa-solid fa-microchip" style="font-size:0.8rem; margin-right:4px;"></i>{% if server.cpu_percent %}{{ server.cpu_percent|round(1) }}%{% else %}--{% endif %}
                                    </span>
                                    <span class="chart-value" id="live-ram-val-{{ server.id }}" style="color:var(--noc-emerald);">
                                        <i class="fa-solid fa-memory" style="font-size:0.8rem; margin-right:4px;"></i>{% if server.memory_percent %}{{ server.memory_percent|round(1) }}%{% else %}--{% endif %}
                                    </span>
                                </div>
                            </div>
                            <div style="height:320px; position:relative;">
                                <canvas id="chart-combined-{{ server.id }}"></canvas>
                            </div>
                        </div>
                    </div>"""

content = content.replace(old_charts_row, new_charts_row)

old_init = """            if (!charts['cpu-' + serverId]) {
                charts['cpu-' + serverId] = createLineChart('chart-cpu-' + serverId, '#818cf8', buf.liveCpu, buf.labels, 'CPU Live');
            }
            if (!charts['ram-' + serverId]) {
                charts['ram-' + serverId] = createLineChart('chart-ram-' + serverId, '#34d399', buf.liveRam, buf.labels, 'RAM Live');
            }"""

new_init = """            if (!charts['combined-' + serverId]) {
                charts['combined-' + serverId] = createCombinedLineChart('chart-combined-' + serverId, buf.labels, buf.liveCpu, buf.liveRam);
            }"""

content = content.replace(old_init, new_init)

old_socket = """                if (charts['cpu-' + sid]) {
                    charts['cpu-' + sid].data.labels = buf.labels;
                    charts['cpu-' + sid].data.datasets[0].data = buf.liveCpu;
                    charts['cpu-' + sid].update('none');
                }
                if (charts['ram-' + sid]) {
                    charts['ram-' + sid].data.labels = buf.labels;
                    charts['ram-' + sid].data.datasets[0].data = buf.liveRam;
                    charts['ram-' + sid].update('none');
                }"""

new_socket = """                if (charts['combined-' + sid]) {
                    charts['combined-' + sid].data.labels = buf.labels;
                    charts['combined-' + sid].data.datasets[0].data = buf.liveCpu;
                    charts['combined-' + sid].data.datasets[1].data = buf.liveRam;
                    charts['combined-' + sid].update('none');
                }"""

content = content.replace(old_socket, new_socket)

old_hist = """            const cpuChart = charts['cpu-' + serverId];
            if (cpuChart) {
                cpuChart.data.labels = labels;
                cpuChart.data.datasets[0].data = [...cpu];
                cpuChart.update('none');
            }

            const ramChart = charts['ram-' + serverId];
            if (ramChart) {
                ramChart.data.labels = labels;
                ramChart.data.datasets[0].data = [...ram];
                ramChart.update('none');
            }"""

new_hist = """            const combinedChart = charts['combined-' + serverId];
            if (combinedChart) {
                combinedChart.data.labels = labels;
                combinedChart.data.datasets[0].data = [...cpu];
                combinedChart.data.datasets[1].data = [...ram];
                combinedChart.update('none');
            }"""

content = content.replace(old_hist, new_hist)

with open('web/templates/dashboard.html', 'w', encoding='utf-8') as f:
    f.write(content)

print("Patch applied")
