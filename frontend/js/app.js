// AlgoCompare — frontend controller.
// Data flow: user input → api.validate / api.compare → render* functions.
import { api } from "./api.js";
import { CodeEditor } from "./editor.js";
import { renderValidation, renderSummary, renderFunctional, renderTheory, renderEmpirical, esc } from "./render.js";

const $ = (sel) => document.querySelector(sel);

const state = { tasks: [], examples: [], busy: false };

const editors = {
  A: new CodeEditor($("#editor-a"), { onChange: () => renderValidation($("#validation-a"), null) }),
  B: new CodeEditor($("#editor-b"), { onChange: () => renderValidation($("#validation-b"), null) }),
};

// ------------------------------------------------------------------------------------------
// Pipeline indicator
// ------------------------------------------------------------------------------------------
const STAGES = ["input", "validate", "functional", "theory", "bench", "report"];
let stageTimer = null;

function setStage(active, { failed = false } = {}) {
  const idx = STAGES.indexOf(active);
  document.querySelectorAll(".stage").forEach((el) => {
    const i = STAGES.indexOf(el.dataset.stage);
    el.classList.toggle("done", i < idx || (active === "report" && i === idx));
    el.classList.toggle("active", i === idx && active !== "report" && !failed);
    el.classList.toggle("failed", i === idx && failed);
  });
}

// The compare request is a single HTTP call, so we animate the stages while waiting.
function animateStages(withBench) {
  const plan = [["validate", 400], ["functional", 1800], ["theory", 700]];
  if (withBench) plan.push(["bench", 0]);
  let i = 0;
  const next = () => {
    if (i >= plan.length) return;
    const [stage, ms] = plan[i++];
    setStage(stage);
    setStatus(`<span class="spinner"></span> ${stageMessage(stage)}`);
    if (ms) stageTimer = setTimeout(next, ms);
  };
  next();
}

function stageMessage(stage) {
  return {
    validate: "Validating both algorithms…",
    functional: "Running both algorithms on the same generated test inputs…",
    theory: "Analysing time and space complexity from the source code…",
    bench: "Benchmarking on growing input sizes for every input profile (this can take up to ~30 s)…",
  }[stage];
}

function setStatus(html, isError = false) {
  const el = $("#status");
  el.innerHTML = html;
  el.classList.toggle("hidden", !html);
  el.classList.toggle("error", isError);
}

// ------------------------------------------------------------------------------------------
// Task & examples
// ------------------------------------------------------------------------------------------
function currentTask() {
  return state.tasks.find((t) => t.id === $("#task-select").value);
}

function showTask() {
  const t = currentTask();
  if (!t) return;
  $("#task-description").textContent = t.description;
  $("#task-signature").textContent = t.signature;
  $("#task-size").textContent = t.size_meaning;
  $("#task-profiles").innerHTML = t.profiles
    .map((p) => `<span class="profile-chip" title="${esc(p.description)}">${esc(p.label)}</span>`).join("");
  const exSelect = $("#example-select");
  exSelect.innerHTML = `<option value="">— choose an example —</option>` + state.examples
    .map((e) => `<option value="${e.id}" ${e.task_id === t.id ? "" : 'class="other"'}>${esc(e.title)}${e.task_id === t.id ? "" : ` (${esc(taskName(e.task_id))})`}</option>`).join("");
}

const taskName = (id) => state.tasks.find((t) => t.id === id)?.name || id;

function loadExample(id) {
  const ex = state.examples.find((e) => e.id === id);
  if (!ex) return;
  $("#task-select").value = ex.task_id;
  showTask();
  $("#example-select").value = ex.id;
  editors.A.value = ex.a_code;
  editors.B.value = ex.b_code;
  $("#name-a").value = ex.a_name;
  $("#name-b").value = ex.b_name;
  renderValidation($("#validation-a"), null);
  renderValidation($("#validation-b"), null);
  $("#results").classList.add("hidden");
  setStatus("");
  setStage("input");
}

function payload() {
  const seed = parseInt($("#opt-seed").value, 10);
  return {
    task_id: $("#task-select").value,
    code_a: editors.A.value,
    code_b: editors.B.value,
    name_a: $("#name-a").value,
    name_b: $("#name-b").value,
    notes: $("#task-notes").value,
    benchmark: $("#opt-benchmark").checked,
    quick: $("#opt-quick").checked,
    seed: Number.isFinite(seed) ? seed : undefined,
  };
}

function setBusy(busy) {
  state.busy = busy;
  $("#btn-validate").disabled = busy;
  $("#btn-compare").disabled = busy;
}

// ------------------------------------------------------------------------------------------
// Actions
// ------------------------------------------------------------------------------------------
async function validate() {
  if (state.busy) return;
  setBusy(true);
  setStage("validate");
  setStatus(`<span class="spinner"></span> Validating (static checks + a quick smoke test)…`);
  try {
    const { data } = await api.validate(payload());
    renderValidation($("#validation-a"), data.A);
    renderValidation($("#validation-b"), data.B);
    const ok = data.A.valid && data.B.valid;
    setStage(ok ? "functional" : "validate", { failed: !ok });
    if (ok) document.querySelector('[data-stage="validate"]').classList.add("done");
    setStatus(ok ? "✓ Both algorithms are valid. Run the full comparison when ready." : "Fix the validation errors shown below the editors.", !ok);
  } catch (err) {
    setStatus(`Error: ${esc(err.message)}`, true);
  } finally {
    setBusy(false);
  }
}

async function compare() {
  if (state.busy) return;
  setBusy(true);
  $("#results").classList.add("hidden");
  const p = payload();
  animateStages(p.benchmark);
  try {
    const { ok, data } = await api.compare(p);
    clearTimeout(stageTimer);
    if (!ok && data.validation) {
      renderValidation($("#validation-a"), data.validation.A);
      renderValidation($("#validation-b"), data.validation.B);
      setStage("validate", { failed: true });
      setStatus("Validation failed — see the messages below the editors.", true);
      return;
    }
    renderValidation($("#validation-a"), data.validation.A);
    renderValidation($("#validation-b"), data.validation.B);
    showReport(data);
    setStage("report");
    setStatus("");
  } catch (err) {
    clearTimeout(stageTimer);
    setStage("report", { failed: true });
    setStatus(`Error: ${esc(err.message)}`, true);
  } finally {
    setBusy(false);
  }
}

function showReport(report) {
  renderSummary(report, { verdicts: $("#verdicts"), summary: $("#summary-list"), meta: $("#result-meta") });
  renderFunctional($("#panel-functional"), report);
  renderTheory($("#panel-theory"), report, (algo, line) => editors[algo].highlightLine(line));
  renderEmpirical($("#panel-empirical"), report);
  $("#results").classList.remove("hidden");
  $("#results").scrollIntoView({ behavior: "smooth", block: "start" });
}

// ------------------------------------------------------------------------------------------
// Wiring
// ------------------------------------------------------------------------------------------
document.querySelectorAll(".tab").forEach((tab) => tab.addEventListener("click", () => {
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t === tab));
  document.querySelectorAll(".tab-panel").forEach((p) => p.classList.toggle("hidden", p.id !== `panel-${tab.dataset.tab}`));
}));
$("#toggle-about").addEventListener("click", () => $("#about").classList.toggle("hidden"));
$("#task-select").addEventListener("change", () => { showTask(); $("#results").classList.add("hidden"); });
$("#example-select").addEventListener("change", (e) => loadExample(e.target.value));
$("#btn-validate").addEventListener("click", validate);
$("#btn-compare").addEventListener("click", compare);
document.querySelectorAll("[data-clear]").forEach((b) => b.addEventListener("click", () => {
  const key = b.dataset.clear.toUpperCase();
  editors[key].value = `def solve(${(currentTask()?.signature.match(/solve\(([^)]*)\)/) || [, "arr"])[1].replace(/:[^,]+/g, "")}):\n    pass\n`;
}));
// clicking "line N" in validation messages highlights the line
["a", "b"].forEach((k) => $(`#validation-${k}`).addEventListener("click", (e) => {
  const line = e.target.dataset?.line;
  if (line) editors[k.toUpperCase()].highlightLine(+line);
}));

async function init() {
  try {
    const { data } = await api.tasks();
    state.tasks = data.tasks;
    state.examples = data.examples;
    $("#task-select").innerHTML = state.tasks.map((t) => `<option value="${t.id}">${esc(t.name)}</option>`).join("");
    showTask();
    loadExample("bubble_vs_merge");
    setStage("input");
  } catch (err) {
    setStatus(`Could not reach the backend: ${esc(err.message)}`, true);
  }
}
init();
