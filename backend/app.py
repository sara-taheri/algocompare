"""
AlgoCompare - Backend API (Flask).

Routes
------
  GET  /                  -> the single-page frontend
  GET  /api/tasks         -> task definitions + example algorithm pairs
  POST /api/validate      -> static validation + smoke test of both algorithms
  POST /api/compare       -> full pipeline: validate → functional tests → complexity → benchmark → report

The route handlers are intentionally thin: all logic lives in backend/services/.
"""
from __future__ import annotations

import os
import random
import time
from typing import Any, Dict, Tuple

from flask import Flask, jsonify, request, send_from_directory

from .services.benchmark import compare_benchmarks, run_benchmark
from .services.complexity import analyze_complexity
from .services.examples import EXAMPLES
from .services.functional import run_equivalence_tests, smoke_test
from .services.report import build_report
from .services.tasks import TASKS, get_task
from .services.validation import validate_code

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")


def _read_request() -> Tuple[Dict[str, Any], Any]:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return {}, (jsonify({"error": "Request body must be a JSON object"}), 400)
    try:
        task = get_task(data.get("task_id", ""))
    except KeyError as exc:
        return data, (jsonify({"error": str(exc)}), 400)
    return data, task


def _validate_both(data: Dict[str, Any], task, with_smoke: bool) -> Dict[str, Any]:
    result = {}
    for key in ("A", "B"):
        code = data.get(f"code_{key.lower()}", "")
        v = validate_code(code, task)
        if v["valid"] and with_smoke:
            v["smoke"] = smoke_test(code, task)
            if not v["smoke"]["passed"]:
                v["valid"] = False
                v["errors"].append({"line": None, "message": f"Smoke test failed: {v['smoke']['message']}"})
        result[key] = v
    return result


def create_app() -> Flask:
    app = Flask(__name__, static_folder=None)

    @app.get("/")
    def index():
        return send_from_directory(FRONTEND_DIR, "index.html")

    @app.get("/<path:path>")
    def static_files(path):
        return send_from_directory(FRONTEND_DIR, path)

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok"})

    @app.get("/api/tasks")
    def tasks():
        return jsonify({"tasks": [t.to_public_dict() for t in TASKS.values()], "examples": EXAMPLES})

    @app.post("/api/validate")
    def validate():
        data, task = _read_request()
        if isinstance(task, tuple):
            return task
        return jsonify(_validate_both(data, task, with_smoke=True))

    @app.post("/api/compare")
    def compare():
        data, task = _read_request()
        if isinstance(task, tuple):
            return task
        started = time.perf_counter()
        names = {"A": (data.get("name_a") or "Algorithm A").strip()[:60],
                 "B": (data.get("name_b") or "Algorithm B").strip()[:60]}
        try:
            seed = int(data.get("seed") or random.randint(1, 10 ** 6))
        except (TypeError, ValueError):
            return jsonify({"error": "seed must be an integer"}), 400
        code_a, code_b = data.get("code_a", ""), data.get("code_b", "")

        # 1. validation (stop early if invalid)
        validation = _validate_both(data, task, with_smoke=False)
        if not (validation["A"]["valid"] and validation["B"]["valid"]):
            return jsonify({"error": "validation failed", "validation": validation}), 422

        # 2. functional equivalence on identical generated inputs
        functional = run_equivalence_tests(task, code_a, code_b, seed)

        # 3. theoretical complexity (static - no execution)
        theory_a, theory_b = analyze_complexity(code_a), analyze_complexity(code_b)

        # 4. empirical benchmark (sequential, so A and B do not compete for the CPU)
        bench_a = bench_b = None
        bench_cmp: Dict[str, Any] = {"rows": []}
        if data.get("benchmark", True):
            quick = bool(data.get("quick", False))
            bench_a = run_benchmark(task, code_a, seed, quick)
            bench_b = run_benchmark(task, code_b, seed, quick)
            bench_cmp = compare_benchmarks(task, bench_a, bench_b)

        # 5. report
        report = build_report(task, names, validation, functional, theory_a, theory_b,
                              bench_a, bench_b, bench_cmp, seed, notes=(data.get("notes") or "")[:1000])
        report["elapsed_seconds"] = round(time.perf_counter() - started, 2)
        return jsonify(report)

    return app


app = create_app()
