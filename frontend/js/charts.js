// Tiny dependency-free SVG line chart (log-scaled axes supported).

const W = 560, H = 300, M = { top: 14, right: 16, bottom: 44, left: 66 };

function niceLogTicks(min, max) {
  const ticks = [];
  for (let e = Math.floor(Math.log10(min)); e <= Math.ceil(Math.log10(max)); e++) ticks.push(10 ** e);
  return ticks.filter((t) => t >= min / 1.0001 && t <= max * 1.0001);
}

function niceLinearTicks(min, max, count = 5) {
  const span = max - min || 1;
  const step0 = span / count;
  const mag = 10 ** Math.floor(Math.log10(step0));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= step0) || step0;
  const ticks = [];
  for (let v = Math.ceil(min / step) * step; v <= max + 1e-12; v += step) ticks.push(v);
  return ticks;
}

/**
 * series: [{ name, color, dashed?, points: [[x, y], ...] }]
 * options: { logX, logY, xLabel, yLabel, formatY, formatX }
 */
export function lineChart(series, options = {}) {
  const all = series.flatMap((s) => s.points).filter(([x, y]) => x > 0 && y > 0 && Number.isFinite(y));
  if (all.length === 0) return `<div class="muted small" style="padding:40px;text-align:center">No data to plot</div>`;
  const { logX = true, logY = true, xLabel = "n", yLabel = "", formatY = String, formatX = String } = options;

  let [xMin, xMax] = [Math.min(...all.map((p) => p[0])), Math.max(...all.map((p) => p[0]))];
  let [yMin, yMax] = [Math.min(...all.map((p) => p[1])), Math.max(...all.map((p) => p[1]))];
  if (xMin === xMax) { xMin /= 2; xMax *= 2; }
  if (logY) { if (yMin === yMax) { yMin /= 2; yMax *= 2; } yMin /= 1.4; yMax *= 1.4; }
  else { yMin = 0; yMax *= 1.1; }

  const fx = logX ? (x) => Math.log10(x) : (x) => x;
  const fy = logY ? (y) => Math.log10(y) : (y) => y;
  const sx = (x) => M.left + ((fx(x) - fx(xMin)) / (fx(xMax) - fx(xMin))) * (W - M.left - M.right);
  const sy = (y) => H - M.bottom - ((fy(y) - fy(yMin)) / (fy(yMax) - fy(yMin))) * (H - M.top - M.bottom);

  let svg = `<svg viewBox="0 0 ${W} ${H}" role="img">`;
  // grid + y ticks
  const yTicks = logY ? niceLogTicks(yMin, yMax) : niceLinearTicks(yMin, yMax);
  for (const t of yTicks) {
    const y = sy(t);
    svg += `<line x1="${M.left}" x2="${W - M.right}" y1="${y}" y2="${y}" stroke="#eceef5"/>`;
    svg += `<text x="${M.left - 8}" y="${y + 4}" font-size="11" text-anchor="end" fill="#6b7085">${formatY(t)}</text>`;
  }
  // x ticks: use the actual measured sizes
  const xs = [...new Set(all.map((p) => p[0]))].sort((a, b) => a - b);
  const every = Math.max(1, Math.ceil(xs.length / 8));
  xs.forEach((x, i) => {
    if (i % every) return;
    const px = sx(x);
    svg += `<line x1="${px}" x2="${px}" y1="${M.top}" y2="${H - M.bottom}" stroke="#f3f4f8"/>`;
    svg += `<text x="${px}" y="${H - M.bottom + 16}" font-size="11" text-anchor="middle" fill="#6b7085">${formatX(x)}</text>`;
  });
  svg += `<line x1="${M.left}" x2="${W - M.right}" y1="${H - M.bottom}" y2="${H - M.bottom}" stroke="#c9ccd9"/>`;
  svg += `<line x1="${M.left}" x2="${M.left}" y1="${M.top}" y2="${H - M.bottom}" stroke="#c9ccd9"/>`;
  svg += `<text x="${(W + M.left) / 2}" y="${H - 8}" font-size="12" text-anchor="middle" fill="#3a3f55">${xLabel}${logX ? " (log scale)" : ""}</text>`;
  svg += `<text transform="translate(14 ${(H - M.bottom + M.top) / 2}) rotate(-90)" font-size="12" text-anchor="middle" fill="#3a3f55">${yLabel}${logY ? " (log)" : ""}</text>`;

  for (const s of series) {
    const pts = s.points.filter(([x, y]) => x > 0 && y > 0 && Number.isFinite(y));
    if (!pts.length) continue;
    const d = pts.map(([x, y], i) => `${i ? "L" : "M"}${sx(x).toFixed(1)},${sy(y).toFixed(1)}`).join(" ");
    svg += `<path d="${d}" fill="none" stroke="${s.color}" stroke-width="${s.dashed ? 1.8 : 2.5}" ${s.dashed ? 'stroke-dasharray="6 5"' : ""} stroke-linejoin="round"/>`;
    if (!s.dashed) {
      for (const [x, y] of pts) {
        svg += `<circle cx="${sx(x).toFixed(1)}" cy="${sy(y).toFixed(1)}" r="3.5" fill="#fff" stroke="${s.color}" stroke-width="2"><title>${s.name}: n=${x}, ${formatY(y)}</title></circle>`;
      }
    }
  }
  return svg + "</svg>";
}

export function legend(series) {
  return `<div class="legend">${series.map((s) => `<span style="color:${s.color}">${s.name}</span>`).join("")}</div>`;
}

export const fmt = {
  time(seconds) {
    if (seconds == null) return "—";
    if (seconds < 1e-6) return `${(seconds * 1e9).toFixed(0)} ns`;
    if (seconds < 1e-3) return `${(seconds * 1e6).toFixed(seconds < 1e-5 ? 1 : 0)} µs`;
    if (seconds < 1) return `${(seconds * 1e3).toFixed(seconds < 1e-2 ? 2 : 1)} ms`;
    return `${seconds.toFixed(2)} s`;
  },
  bytes(b) {
    if (b == null) return "—";
    if (b < 1024) return `${Math.round(b)} B`;
    if (b < 1024 ** 2) return `${(b / 1024).toFixed(1)} KB`;
    return `${(b / 1024 ** 2).toFixed(2)} MB`;
  },
  n(x) { return x >= 1000 ? `${x / 1000}k` : String(x); },
};
