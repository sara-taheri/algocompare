# AlgoCompare

A web platform for an **Algorithm Design** course that compares two algorithms intended to solve the same task.

It reports three kinds of evidence and **keeps them separate on purpose**:

| | Meaning | Strength |
|---|---|---|
| 🟢 **Equivalent on tested inputs** | A and B returned the same outputs on every generated input | Evidence, *not* proof (program equivalence is undecidable in general — Rice's theorem). A single mismatch *is* proof they differ. |
| 🟣 **Theoretical complexity analysis** | Best / average / worst-case time & space, derived from the source code's syntax tree | Heuristic estimate, with the reasoning shown line by line and a confidence level |
| 🔵 **Empirical runtime measurements** | Measured time & memory on growing inputs and several input profiles, with curve fitting | Real measurements, only valid for this machine, this interpreter and the tested sizes |

## Quick start

```bash
pip install -r requirements.txt
python run.py            # → http://localhost:8000
python -m pytest -q      # 49 tests
```

1. Pick a **task** (or load an **example pair** such as *Bubble sort vs Merge sort*).
2. Write/paste Algorithm A and B. Each must define `solve(...)` with the task's signature (helper functions are fine).
3. **Validate both** → syntax, safety, signature, smoke test.
4. **Run full comparison** → the report with three tabs.

## Architecture

```
Frontend (HTML/CSS/vanilla JS)
   │  fetch /api/...
   ▼
Backend API (Flask, backend/app.py)
   │
   ▼
Algorithm Analysis Service (backend/services/)
   ├── validation.py   static checks: syntax, allowed imports, solve() signature, warnings
   ├── tasks.py        task registry: input generators, profiles, edge cases, comparators, reference solutions
   ├── functional.py   same seeded inputs → run A and B → compare → counterexamples
   ├── bigo.py         tiny Big-O algebra (n^k · log^j n, 2^n) with max / multiply
   ├── complexity.py   static AST analysis → best/avg/worst time & space + explanations
   ├── benchmark.py    timing & tracemalloc measurements → curve fitting
   ├── report.py       merges everything; every summary line is tagged tested/theory/measured
   ├── sandbox.py      runs runner.py in a separate process (timeouts)
   └── runner.py       child process: restricted builtins, import whitelist, CPU/memory limits
```

See **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** for the data flow, the complexity rules and the roadmap.

### API

| Method | Route | Body | Returns |
|---|---|---|---|
| GET | `/api/tasks` | – | tasks + example pairs |
| POST | `/api/validate` | `{task_id, code_a, code_b}` | per-algorithm errors / warnings / smoke test |
| POST | `/api/compare` | `{task_id, code_a, code_b, name_a?, name_b?, seed?, benchmark?, quick?, notes?}` | full report |

## Built-in tasks

Sorting · Search in a sorted array · Maximum subarray sum · n-th Fibonacci · Contains duplicate · Custom (integer list → any result).

Each task defines **input profiles** (e.g. *random, already sorted, reverse sorted, few unique values*). They matter because best-case and worst-case behaviour depends on the *shape* of the input, not only its size.

## How the static complexity analysis works (short version)

* sequential code → **max**; nested loops → **product**
* `for x in range(n)` / `for x in arr` → n iterations; constant ranges → O(1)
* `while` loops that halve/double a variable or follow the binary-search pattern → log n
* `return`/`break` inside a loop, or a data-dependent `while` condition → the best case can stop early
* library costs: `sorted` n log n, `x in list` n, `x in set` 1, slicing n, `heappush` log n, …
* recursion: count calls per invocation and how the input shrinks → Master theorem (halving), T(n-1) unrolling (decrement),
  pivot split (quicksort: balanced vs. unbalanced), memoisation (≈ n sub-problems)
* space: new containers, slices, `append` in loops, recursion depth

## Honest limitations (good discussion points for the presentation)

* Static analysis is heuristic; complexity of arbitrary code is undecidable. Confidence levels and observations make the reasoning auditable.
* The unit-cost RAM model assumes O(1) arithmetic; Python big integers (large Fibonacci numbers) break this assumption, and the measurements show it.
* Operations that take microseconds are dominated by interpreter overhead and CPU caches. Their empirical classes are flagged as *unreliable*.
* The sandbox (separate process, rlimits, restricted builtins, import whitelist) is fine for a course project but is **not** a security boundary for hostile code.

## Project structure

```
algocompare/
├── run.py  requirements.txt  README.md
├── docs/ARCHITECTURE.md
├── backend/app.py
├── backend/services/*.py
├── frontend/index.html  css/style.css  js/{app,api,editor,render,charts}.js
└── tests/test_complexity.py  tests/test_validation_and_api.py
```

All code in this repository was written for this project.
