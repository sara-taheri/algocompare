# AlgoCompare — Architecture & Implementation Plan

## 1. Goal

Compare two algorithms (A and B) that claim to solve **the same task**, and report three
*clearly separated* kinds of evidence:

| Kind of evidence | Question it answers | How we get it | Strength |
|---|---|---|---|
| **Equivalent on tested inputs** | "Did A and B return the same answers on the inputs we tried?" | Run both on identical generated inputs, compare outputs | Evidence, **not proof**. One mismatch disproves equivalence; no amount of passing tests proves it. (Program equivalence is undecidable in general — Rice's theorem.) |
| **Theoretical complexity analysis** | "How do the costs grow asymptotically (best/avg/worst)?" | Static analysis of the source code's syntax tree (loops, recursion, known library costs) | A *heuristic estimate* of Big-O, with a written explanation and a confidence level |
| **Empirical runtime measurements** | "How fast / how much memory on this machine, for these sizes?" | Timed benchmark runs over growing input sizes and several input profiles, plus curve fitting | Real measurements, but affected by constants, hardware, the Python interpreter and noise |

The UI never merges these into one "A is equivalent to B" claim.

## 2. Language & scope decisions (Phase 1)

* The algorithms are written in **Python** (the course language most students already know, and
  Python's `ast` module makes static analysis easy to explain).
* Each algorithm must define a function called **`solve(...)`** whose parameters depend on the task.
  It may define helper functions.
* Tasks are **predefined** (sorting, searching, max subarray, Fibonacci, duplicate detection) plus one
  **generic custom task** (`solve(arr: list[int]) -> anything`). Each task knows how to *generate inputs*,
  which *input profiles* exist (e.g. sorted / reversed / random), and how to *compare outputs*.
* No AI / LLM features. Everything is deterministic and explainable.

## 3. High-level architecture

```
┌──────────────────────────┐   HTTP/JSON    ┌────────────────────────────────────────────┐
│ Frontend (HTML/CSS/JS)   │ ─────────────▶ │ Backend API (Flask)            app.py      │
│  task picker, 2 editors, │ ◀───────────── │  GET  /api/tasks                            │
│  results + SVG charts    │                │  POST /api/validate                         │
└──────────────────────────┘                │  POST /api/compare                          │
                                            └───────────────┬────────────────────────────┘
                                                            │
                                            ┌───────────────▼────────────────────────────┐
                                            │ Algorithm Analysis Service  (services/)     │
                                            │                                             │
                                            │  1. validation.py   syntax, safety, solve() │
                                            │  2. tasks.py        task definitions + gens │
                                            │  3. functional.py   equivalence testing     │
                                            │  4. complexity.py   static time+space Big-O │
                                            │  5. benchmark.py    timing, memory, fitting │
                                            │  6. report.py       builds final result     │
                                            │                                             │
                                            │  sandbox.py ──spawns──▶ runner.py           │
                                            │  (separate Python process, time/memory      │
                                            │   limits, restricted builtins/imports)      │
                                            └─────────────────────────────────────────────┘
```

### Data flow for `POST /api/compare`

```
request {task_id, code_a, code_b}
   │
   ├─▶ validation.validate(code, task)  ── fails? → return errors, stop
   │
   ├─▶ functional.run_tests(task, code_a, code_b)
   │       tasks.generate_test_inputs(seed)  → same inputs for A and B
   │       sandbox.run(code_a, inputs), sandbox.run(code_b, inputs)
   │       task.compare(out_a, out_b)  (+ optional check vs. trusted reference)
   │
   ├─▶ complexity.analyze(code_a), complexity.analyze(code_b)   (no execution)
   │
   ├─▶ benchmark.run(task, code_a), benchmark.run(task, code_b)
   │       sizes n = 100, 200, 400, …  × profiles (random / sorted / …)
   │       same seed ⇒ identical inputs for A and B
   │       adaptive stop when a single run gets too slow
   │       curve fitting → "empirically ~O(n²)"
   │
   └─▶ report.build(...)  → JSON with three separate sections + summary
```

## 4. Module responsibilities

| Module | Responsibility | Key idea to explain in class |
|---|---|---|
| `tasks.py` | Registry of tasks: signature, input generators, profiles, edge cases, output comparator, reference solution | The *task* defines what "same result" means |
| `validation.py` | Parse code with `ast`, check `solve` exists with the right arity, block unsafe imports/builtins, warnings | Validate before executing |
| `sandbox.py` / `runner.py` | Execute untrusted code in a child process with timeouts and memory limits | Isolation; the parent never `exec`s user code |
| `functional.py` | Generate identical test inputs, run A and B, compare, collect counterexamples | Testing can *disprove* but not *prove* equivalence |
| `bigo.py` | Tiny symbolic Big-O algebra: `n^k · log^j n`, `2^n`; multiply, max, pretty-print | Rules: sequential = max, nested = multiply |
| `complexity.py` | Static AST analysis: loop nesting, halving loops, early exits, recursion + Master theorem, known library costs, auxiliary space | Best/avg/worst from code structure |
| `benchmark.py` | Timing (min of repeats), peak memory via `tracemalloc`, log–log curve fitting | Empirical growth rate ≠ proof |
| `report.py` | Merge all results, produce comparisons and plain-language summary | Keep the three evidence types separate |
| `examples.py` | Ready-made algorithm pairs for demos | Quick class demos |

## 5. Complexity analysis rules (heuristic, explainable)

* **Sequential statements** → `max` of costs. **Nested loops** → product.
* `for x in range(<non-constant>)` / `for x in arr` → `n` iterations; constant ranges → `O(1)`.
* `while` loops that halve/double a variable (`//= 2`, `*= 2`, binary-search `mid`) → `log n`.
* A loop containing `return`/`break` → **best case** may finish after one iteration.
  A `while` loop whose condition inspects data (`while j >= 0 and a[j] > key`) → best case 0 iterations.
* Known library costs: `sorted`/`.sort` = `n log n`, `x in list` = `n`, `x in set` = `1`,
  slicing = `n`, `heappush` = `log n`, `bisect` = `log n`, `sum/min/max` = `n`, …
* **Recursion**: count recursive calls `a` per invocation and how the argument shrinks:
  * halved (`n//2`, `arr[:mid]`) → Master theorem `T(n) = a·T(n/2) + f(n)`
  * decremented (`n-1`, `arr[1:]`) → `T(n) = T(n-1) + f(n)` (a=1) or exponential (a≥2)
  * split by a pivot/partition → best/avg as halving, worst as decrement (quicksort)
  * memoization (`@lru_cache`, `memo` dict) → ~`n` distinct sub-problems
* **Space** = auxiliary memory: new lists/sets/dicts, slices, growth via `append`/`add` in loops,
  and recursion-stack depth.
* Every conclusion is attached to a source line and a confidence level (high / medium / low).

## 6. Empirical benchmarking

* Input sizes double (100, 200, 400, …); each task has several **input profiles** (e.g. sorted,
  reversed, random) because best/worst cases depend on the input *shape*.
* Both algorithms receive byte-identical inputs (seeded generator).
* Time = minimum of several repeats (least noisy estimate); memory = `tracemalloc` peak of new
  allocations (the input itself is excluded).
* Growth-rate fit: compare `log T` vs `log n` (power law) and `log T` vs `n` (exponential), then pick
  the closest standard class.
* Adaptive stop: once a single run exceeds a threshold, larger sizes are skipped for that profile.

## 7. Project structure

```
algocompare/
├── run.py                     # start the server
├── requirements.txt
├── README.md
├── docs/ARCHITECTURE.md       # this file
├── backend/
│   ├── app.py                 # Flask API + serves the frontend
│   └── services/
│       ├── tasks.py  validation.py  sandbox.py  runner.py
│       ├── functional.py  bigo.py  complexity.py  benchmark.py
│       ├── report.py  examples.py
├── frontend/
│   ├── index.html
│   ├── css/style.css
│   └── js/ api.js  editor.js  charts.js  app.js
└── tests/                     # pytest unit + API tests
```

## 8. Phases

* **Phase 1 (this delivery)**: architecture, all modules working end-to-end, clean UI, examples, tests.
* **Phase 2 (ideas)**: user-defined custom tasks with their own input generator; export report to PDF/Markdown;
  step counters (count comparisons/swaps) as a hardware-independent metric; more precise recurrence solving.
* **Phase 3 (ideas)**: other languages (C++/Java) via compilers in containers; stronger sandboxing (Docker/nsjail);
  property-based testing (Hypothesis) to search for counterexamples.
