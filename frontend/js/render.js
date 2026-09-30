// Rendering of validation results and the comparison report.
// Each evidence type (tested / theory / measured) is rendered in its own panel.
import { lineChart, legend, fmt } from "./charts.js";

const COLOR = { A: "#4f46e5", B: "#ea580c" };

export const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const codeify = (s) => esc(s).replace(/`([^`]+)`/g, "<code>$1</code>");

// ------------------------------------------------------------------------------------------
// Validation
// ------------------------------------------------------------------------------------------
export function renderValidation(el, v) {
  if (!v) { el.innerHTML = ""; return; }
  const lineLink = (i) => (i.line ? `<span class="line-link" data-line="${i.line}">line ${i.line}</span>: ` : "");
  let html = "";
  if (v.valid) {
    const smoke = v.smoke ? ` · ${esc(v.smoke.message)}` : "";
    html += `<div class="ok">✓ Valid — defines <code>solve</code>, syntax and safety checks passed${smoke}</div>`;
  } else {
    html += `<div class="err"><b>✗ Invalid</b><ul>${v.errors.map((e) => `<li>${lineLink(e)}${esc(e.message)}</li>`).join("")}</ul></div>`;
  }
  if (v.warnings && v.warnings.length) {
    html += `<div class="warn"><ul>${v.warnings.map((w) => `<li>⚠ ${lineLink(w)}${esc(w.message)}</li>`).join("")}</ul></div>`;
  }
  el.innerHTML = html;
}

// ------------------------------------------------------------------------------------------
// Summary + verdict cards
// ------------------------------------------------------------------------------------------
export function renderSummary(report, els) {
  const { names, functional: f, theory, empirical } = report;
  const cards = [];

  // tested
  if (f.verdict === "equivalent_on_tested") {
    cards.push(`<div class="verdict tested"><div class="kind">Tested equivalence</div>
      <div class="headline">✓ Equivalent on ${f.total} tested inputs</div>
      <div class="sub">Evidence, not a proof of equivalence for all inputs.</div></div>`);
  } else if (f.verdict === "not_equivalent") {
    cards.push(`<div class="verdict tested bad"><div class="kind">Tested equivalence</div>
      <div class="headline">✗ Not equivalent</div>
      <div class="sub">Counterexample found — disagreed on ${f.disagree} of ${f.total} inputs.</div></div>`);
  } else {
    cards.push(`<div class="verdict tested bad"><div class="kind">Tested equivalence</div>
      <div class="headline">? Inconclusive</div><div class="sub">${esc(f.error || "")}</div></div>`);
  }

  // theory
  const worst = (theory.comparison || []).find((r) => r.resource === "time" && r.case === "worst");
  if (worst) {
    const head = worst.better === "=" ? "Same worst-case class" : `${esc(names[worst.better])} scales better`;
    cards.push(`<div class="verdict theory"><div class="kind">Theoretical (static analysis)</div>
      <div class="headline">${head}</div>
      <div class="sub">Worst-case time: <b>${esc(worst.a)}</b> vs <b>${esc(worst.b)}</b></div></div>`);
  } else {
    cards.push(`<div class="verdict theory"><div class="kind">Theoretical</div><div class="headline">Not available</div></div>`);
  }

  // empirical
  const rows = empirical ? (empirical.comparison.rows || []).filter((r) => r.n) : [];
  if (rows.length) {
    const top = rows.reduce((a, b) => ((b.ratio || 0) > (a.ratio || 0) ? b : a));
    const allSame = rows.every((r) => r.faster === top.faster);
    cards.push(`<div class="verdict empirical"><div class="kind">Empirical (measured)</div>
      <div class="headline">${allSame ? `${esc(names[top.faster])} faster on all profiles` : "Winner depends on input"}</div>
      <div class="sub">Up to <b>${top.ratio ? top.ratio.toFixed(1) : "?"}×</b> faster (${esc(names[top.faster])}) at n = ${top.n}, “${esc(top.label)}”</div></div>`);
  } else {
    cards.push(`<div class="verdict empirical"><div class="kind">Empirical (measured)</div>
      <div class="headline">${empirical ? "No comparable data" : "Not run"}</div>
      <div class="sub">${empirical ? "The benchmark could not measure both algorithms." : "Enable “Run empirical benchmark”."}</div></div>`);
  }
  els.verdicts.innerHTML = cards.join("");

  const tagName = { tested: "Tested", theory: "Theory", empirical: "Measured" };
  els.summary.innerHTML = report.summary
    .map((s) => `<li><span class="tag ${s.kind}">${tagName[s.kind]}</span><span>${esc(s.text)}</span></li>`).join("");
  els.meta.textContent = `Task: ${report.task.name}${report.task_notes ? ` — “${report.task_notes}”` : ""} · seed ${report.seed} · ${report.elapsed_seconds}s`;
}

// ------------------------------------------------------------------------------------------
// Functional panel
// ------------------------------------------------------------------------------------------
export function renderFunctional(el, report) {
  const f = report.functional, names = report.names;
  if (f.verdict === "inconclusive") {
    el.innerHTML = `<div class="note bad"><b>Could not run the functional tests.</b> ${esc(f.error)}</div>`;
    return;
  }
  const good = f.verdict === "equivalent_on_tested";
  let html = `<div class="note ${good ? "tested" : "bad"}">
    ${good
      ? `<b>Equivalent on tested inputs.</b> ${esc(names.A)} and ${esc(names.B)} returned equivalent outputs for all ${f.total} generated inputs.`
      : `<b>Not equivalent.</b> At least one input produces different results — this <u>proves</u> the two programs are not equivalent.`}
    <div class="small" style="margin-top:6px">${esc(f.disclaimer)}</div></div>`;

  html += `<div class="stats">
    <div class="stat"><div class="v">${f.total}</div><div class="l">inputs tested (same for A and B)</div></div>
    <div class="stat ${good ? "good" : ""}"><div class="v">${f.agree}</div><div class="l">outputs agree</div></div>
    <div class="stat ${f.disagree ? "bad" : ""}"><div class="v">${f.disagree}</div><div class="l">outputs differ</div></div>
    <div class="stat ${f.errors_a ? "bad" : ""}"><div class="v">${f.errors_a}</div><div class="l">errors / timeouts in A</div></div>
    <div class="stat ${f.errors_b ? "bad" : ""}"><div class="v">${f.errors_b}</div><div class="l">errors / timeouts in B</div></div>`;
  if (f.correctness) {
    html += `<div class="stat ${f.correctness.A.passed === f.total ? "good" : "bad"}"><div class="v">${f.correctness.A.passed}/${f.total}</div><div class="l">A matches reference</div></div>
             <div class="stat ${f.correctness.B.passed === f.total ? "good" : "bad"}"><div class="v">${f.correctness.B.passed}/${f.total}</div><div class="l">B matches reference</div></div>`;
  }
  html += `</div>`;

  if (f.first_counterexample) {
    const c = f.first_counterexample;
    html += `<div class="note warn"><b>First counterexample (test #${c.index}):</b><br>
      input = <code class="mono">${esc(c.input)}</code><br>
      ${esc(names.A)} → <code class="mono">${esc(c.output_a)}</code><br>
      ${esc(names.B)} → <code class="mono">${esc(c.output_b)}</code>
      ${c.expected != null ? `<br>reference → <code class="mono">${esc(c.expected)}</code>` : ""}</div>`;
  }

  const hasRef = !!f.correctness;
  html += `<div class="toolbar"><h3>Test cases</h3>
    <label class="check small"><input type="checkbox" id="only-mismatch" ${good ? "" : "checked"}/> show only mismatches</label></div>
    <div class="table-wrap"><table><thead><tr><th>#</th><th>Kind</th><th>Profile</th><th>Input</th>
    <th>${esc(names.A)}</th><th>${esc(names.B)}</th>${hasRef ? "<th>Reference</th>" : ""}<th>A = B?</th></tr></thead><tbody>`;
  for (const c of f.cases) {
    const cell = (out, status, correct) =>
      `<td class="mono" ${status !== "ok" ? 'style="color:var(--bad)"' : ""}>${esc(out)}${hasRef && status === "ok" && correct === false ? ' <span class="pill bad">wrong</span>' : ""}</td>`;
    html += `<tr class="${c.match ? "" : "mismatch"}" data-match="${c.match}">
      <td>${c.index}</td><td>${esc(c.kind)}</td><td>${esc(c.profile)}</td><td class="mono">${esc(c.input)}</td>
      ${cell(c.output_a, c.status_a, c.correct_a)}${cell(c.output_b, c.status_b, c.correct_b)}
      ${hasRef ? `<td class="mono">${esc(c.expected)}</td>` : ""}
      <td>${c.match ? '<span class="pill ok">same</span>' : '<span class="pill bad">differ</span>'}</td></tr>`;
  }
  html += `</tbody></table></div>`;
  el.innerHTML = html;

  const toggle = el.querySelector("#only-mismatch");
  const apply = () => el.querySelectorAll("tbody tr").forEach((tr) => {
    tr.style.display = toggle.checked && tr.dataset.match === "true" ? "none" : "";
  });
  toggle.addEventListener("change", apply);
  apply();
}

// ------------------------------------------------------------------------------------------
// Theory panel
// ------------------------------------------------------------------------------------------
function growth(key, n) {           // key = [exp, poly, log] from the backend
  if (!key || key[0] < 0) return 1;
  if (key[0] === 1) return 2 ** n;
  return n ** key[1] * Math.max(Math.log2(n), 1) ** key[2];
}

export function renderTheory(el, report, onLineClick) {
  const { theory, names } = report;
  const A = theory.A, B = theory.B;
  if (!A.ok || !B.ok) {
    el.innerHTML = `<div class="note bad">Static analysis failed: ${esc(A.error || B.error)}</div>`;
    return;
  }
  let html = `<div class="note theory"><b>Theoretical complexity analysis (heuristic).</b> Derived from the code's structure
    without running it: loop nesting, halving loops, early exits, recursion (Master theorem), library costs and allocations.
    Space means <i>auxiliary</i> memory (the input itself is not counted).
    <div class="small" style="margin-top:6px">${esc(theory.model_note)}</div></div>`;

  html += `<table class="complexity-table"><thead><tr><th>Measure</th>
      <th><span class="pill a">A</span> ${esc(names.A)}</th><th><span class="pill b">B</span> ${esc(names.B)}</th><th>Asymptotically better</th></tr></thead><tbody>`;
  for (const r of theory.comparison) {
    const verdict = r.better === "=" ? '<span class="pill neutral">same class</span>'
      : `<span class="pill ${r.better.toLowerCase()}">${esc(names[r.better])}</span>`;
    html += `<tr><td>${esc(r.label.replace(/^./, (c) => c.toUpperCase()))}</td>
      <td class="big ${r.better === "A" ? "win" : ""}">${esc(r.a)}</td>
      <td class="big ${r.better === "B" ? "win" : ""}">${esc(r.b)}</td><td>${verdict}</td></tr>`;
  }
  html += `</tbody></table>`;

  // illustrative growth curves (worst case, constants ignored)
  const ns = [2, 4, 8, 16, 32, 64, 128, 256, 512, 1024];
  const curve = (t) => ns.map((n) => [n, growth(t.time.worst.key, n)]).filter(([, y]) => y < 1e30);
  const series = [
    { name: `${names.A} — ${A.time.worst.label}`, color: COLOR.A, points: curve(A) },
    { name: `${names.B} — ${B.time.worst.label}`, color: COLOR.B, points: curve(B) },
  ];
  html += `<div class="chart-row"><div class="chart-box"><h3>Worst-case growth functions (theory, constants ignored)</h3>
    ${lineChart(series, { yLabel: "f(n)", formatY: (v) => (v >= 1e4 ? v.toExponential(0) : String(Math.round(v))), formatX: fmt.n })}
    ${legend(series)}</div>
    <div class="chart-box"><h3>How to read best / average / worst</h3>
      <ul class="small" style="margin:6px 0 0;padding-left:18px;line-height:1.7">
        <li><b>Best case</b>: the cheapest input of size n (e.g. already sorted input, target found immediately).</li>
        <li><b>Average case</b>: expected cost over "typical" (random) inputs of size n.</li>
        <li><b>Worst case</b>: the most expensive input of size n — the usual guarantee quoted in Big-O.</li>
        <li>Recursion is solved with the <b>Master theorem</b> for halving (T(n)=aT(n/2)+f(n)) or unrolled for decrementing inputs (T(n)=T(n-1)+f(n)).</li>
        <li>An empirical check of these claims is in the <i>Empirical measurements</i> tab.</li>
      </ul></div></div>`;

  html += `<div class="two-col">`;
  for (const key of ["A", "B"]) {
    const t = theory[key];
    html += `<div class="algo-panel ${key.toLowerCase()}">
      <h3><span class="algo-badge ${key.toLowerCase()}">${key}</span>${esc(names[key])}
        <span class="conf ${t.confidence}" title="How sure the heuristic analysis is">confidence: ${t.confidence}</span></h3>
      ${t.recurrence ? `<div class="recurrence">${esc(t.recurrence)}</div>` : ""}
      <ul class="small" style="margin:6px 0;padding-left:18px">${t.summary.map((s) => `<li>${esc(s)}</li>`).join("")}</ul>
      <b class="small">Observations (click a line number to highlight it in the editor)</b>
      <ul class="obs">${t.observations.length ? t.observations.map((o) =>
        `<li><span class="ln" data-algo="${key}" data-line="${o.line}">${o.function}:${o.line}</span><span>${codeify(o.text)}</span></li>`).join("")
        : '<li class="muted">No loops, recursion or costly operations found — constant work.</li>'}</ul>
    </div>`;
  }
  html += `</div>`;
  el.innerHTML = html;
  el.querySelectorAll(".ln").forEach((n) => n.addEventListener("click", () => onLineClick(n.dataset.algo, +n.dataset.line)));
}

// ------------------------------------------------------------------------------------------
// Empirical panel
// ------------------------------------------------------------------------------------------
export function renderEmpirical(el, report) {
  const { empirical, names, task } = report;
  if (!empirical) {
    el.innerHTML = `<div class="note empirical">The empirical benchmark was not run. Enable “Run empirical benchmark” and compare again.</div>`;
    return;
  }
  const A = empirical.A, B = empirical.B;
  if (!A.ok || !B.ok) {
    el.innerHTML = `<div class="note bad">Benchmark failed: ${esc((A.ok ? B : A).error)}</div>`;
    return;
  }
  const profiles = task.profiles;
  let selected = profiles[profiles.length > 1 ? profiles.length - 1 : 0].id;

  const draw = () => {
    const pa = A.profiles[selected], pb = B.profiles[selected];
    const profile = profiles.find((p) => p.id === selected);
    const timeSeries = [
      { name: names.A, color: COLOR.A, points: pa.points.map((p) => [p.n, p.seconds]) },
      { name: names.B, color: COLOR.B, points: pb.points.map((p) => [p.n, p.seconds]) },
    ];
    const memSeries = [
      { name: names.A, color: COLOR.A, points: pa.points.filter((p) => p.peak_bytes != null).map((p) => [p.n, Math.max(p.peak_bytes, 1)]) },
      { name: names.B, color: COLOR.B, points: pb.points.filter((p) => p.peak_bytes != null).map((p) => [p.n, Math.max(p.peak_bytes, 1)]) },
    ];
    const fitText = (fit) => (fit ? `<b>${esc(fit.label)}</b>${fit.unreliable ? ' <span class="pill bad" title="All runs under 50 µs">unreliable</span>' : ""}` : '<span class="muted">not enough data</span>');

    let h = `<div class="toolbar"><div><b>Input profile:</b> <span class="muted small">${esc(profile.description)}</span></div>
      <div class="segmented">${profiles.map((p) => `<button data-profile="${p.id}" class="${p.id === selected ? "active" : ""}">${esc(p.label)}</button>`).join("")}</div></div>`;
    h += `<div class="chart-row">
      <div class="chart-box"><h3>Running time vs n</h3>${lineChart(timeSeries, { yLabel: "time", formatY: fmt.time, formatX: fmt.n })}${legend(timeSeries)}
        <div class="small" style="margin-top:6px">Empirical growth — ${esc(names.A)}: ${fitText(pa.time_fit)} · ${esc(names.B)}: ${fitText(pb.time_fit)}</div></div>
      <div class="chart-box"><h3>Peak extra memory vs n (tracemalloc)</h3>${lineChart(memSeries, { yLabel: "bytes", formatY: fmt.bytes, formatX: fmt.n })}${legend(memSeries)}
        <div class="small" style="margin-top:6px">Empirical growth — ${esc(names.A)}: ${fitText(pa.memory_fit)} · ${esc(names.B)}: ${fitText(pb.memory_fit)}</div></div></div>`;

    const notes = [[names.A, pa.note], [names.B, pb.note]].filter(([, n]) => n);
    if (notes.length) h += `<div class="small muted" style="margin-bottom:10px">${notes.map(([nm, n]) => `${esc(nm)}: ${esc(n)}`).join(" · ")}</div>`;

    // raw data for this profile
    const sizes = [...new Set([...pa.points, ...pb.points].map((p) => p.n))].sort((a, b) => a - b);
    const byN = (pts) => Object.fromEntries(pts.map((p) => [p.n, p]));
    const ma = byN(pa.points), mb = byN(pb.points);
    h += `<details><summary class="small"><b>Raw measurements for “${esc(profile.label)}”</b></summary>
      <div class="table-wrap" style="margin-top:8px"><table><thead><tr><th>n</th><th>time ${esc(names.A)}</th><th>time ${esc(names.B)}</th>
      <th>ratio</th><th>memory ${esc(names.A)}</th><th>memory ${esc(names.B)}</th></tr></thead><tbody>
      ${sizes.map((n) => {
        const a = ma[n], b = mb[n];
        const ratio = a && b ? (a.seconds > b.seconds ? `${esc(names.B)} ${(a.seconds / b.seconds).toFixed(1)}×` : `${esc(names.A)} ${(b.seconds / a.seconds).toFixed(1)}×`) : "—";
        return `<tr><td>${n}</td><td>${a ? fmt.time(a.seconds) : "—"}</td><td>${b ? fmt.time(b.seconds) : "—"}</td><td>${ratio}</td>
          <td>${a ? fmt.bytes(a.peak_bytes) : "—"}</td><td>${b ? fmt.bytes(b.peak_bytes) : "—"}</td></tr>`;
      }).join("")}</tbody></table></div></details>`;

    el.querySelector("#profile-view").innerHTML = h;
    el.querySelectorAll("[data-profile]").forEach((b) => b.addEventListener("click", () => { selected = b.dataset.profile; draw(); }));
  };

  let html = `<div class="note empirical"><b>Empirical runtime measurements.</b> Both algorithms were timed on identical inputs
    (same seed) of growing size n, for every input profile. Time = minimum of several repeats; memory = peak of new allocations
    measured with <code>tracemalloc</code>. Sizes stop growing once a single run gets slow. These numbers depend on this machine and
    the Python interpreter and only cover the tested sizes — they illustrate, but do not prove, asymptotic behaviour.</div>
    <div id="profile-view"></div>`;

  // per-profile comparison table
  html += `<h3 style="margin:18px 0 8px">Per-profile comparison</h3><div class="table-wrap"><table><thead><tr>
    <th>Profile</th><th>Largest common n</th><th>time ${esc(names.A)}</th><th>time ${esc(names.B)}</th><th>Faster</th>
    <th>Empirical growth A</th><th>Empirical growth B</th></tr></thead><tbody>`;
  for (const r of empirical.comparison.rows) {
    const fa = A.profiles[r.profile].time_fit, fb = B.profiles[r.profile].time_fit;
    html += `<tr><td>${esc(r.label)}</td><td>${r.n ?? "—"}</td><td>${fmt.time(r.time_a)}</td><td>${fmt.time(r.time_b)}</td>
      <td>${r.faster ? `<span class="pill ${r.faster.toLowerCase()}">${esc(names[r.faster])}</span> ${r.ratio ? r.ratio.toFixed(1) + "×" : ""}` : "—"}</td>
      <td>${fa ? esc(fa.label) : "—"}${fa && fa.unreliable ? " ⚠" : ""}</td><td>${fb ? esc(fb.label) : "—"}${fb && fb.unreliable ? " ⚠" : ""}</td></tr>`;
  }
  html += `</tbody></table></div>`;

  // observed best/worst profile + consistency with theory
  html += `<div class="two-col">`;
  for (const key of ["A", "B"]) {
    const cases = empirical.cases[key];
    const cons = empirical.consistency[key] || [];
    const theo = report.theory[key];
    html += `<div class="algo-panel ${key.toLowerCase()}"><h3><span class="algo-badge ${key.toLowerCase()}">${key}</span>${esc(names[key])}</h3>`;
    if (cases) {
      html += `<p class="small" style="margin:4px 0">At n = ${cases.n}: fastest on <b>${esc(cases.fastest)}</b> (${fmt.time(cases.fastest_time)}),
        slowest on <b>${esc(cases.slowest)}</b> (${fmt.time(cases.slowest_time)})${cases.spread ? ` — a ${cases.spread.toFixed(1)}× spread between input profiles` : ""}.
        ${cases.spread && cases.spread > 3 ? "The input's shape matters: best and worst case really differ." : "Performance is fairly insensitive to the input's shape."}</p>`;
    }
    if (theo && theo.ok) {
      html += `<p class="small" style="margin:8px 0 4px"><b>Theory vs measurement</b> (theory: best ${esc(theo.time.best.label)}, avg ${esc(theo.time.average.label)}, worst ${esc(theo.time.worst.label)})</p><ul class="small" style="margin:0;padding-left:18px">`;
      for (const c of cons) {
        const label = profiles.find((p) => p.id === c.profile)?.label || c.profile;
        html += `<li>${esc(label)}: measured ${esc(c.empirical)} → ${c.matches ? `consistent with the theoretical <b>${esc(c.matches)}</b> case` : c.close_to ? `close to the theoretical <b>${esc(c.close_to)}</b> case (differs by a log factor — hard to separate empirically; caches/noise)` : '<span style="color:var(--warn)">differs from the theoretical classes</span> (constant factors, caches, big integers or limited sizes)'}</li>`;
      }
      html += `</ul>`;
    }
    html += `</div>`;
  }
  html += `</div>`;
  el.innerHTML = html;
  draw();
}
