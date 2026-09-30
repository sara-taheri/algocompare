"""
Empirical runtime / memory benchmarking.

The sandboxed runner measures, for every input profile and growing sizes n:
  * time  = minimum over several repeats (the minimum is the least noisy estimate),
  * memory = tracemalloc peak of NEW allocations during one call (input excluded).

Here we fit the measurements to standard growth classes. This gives an *empirical* estimate
("the measurements grow like n²") - valid only for the tested sizes, on this machine, with
this interpreter. It is NOT a proof of asymptotic complexity.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from .sandbox import run_in_sandbox
from .tasks import Task

CANDIDATES: List[Tuple[str, Any]] = [
    ("O(1)", lambda n: 1.0),
    ("O(log n)", lambda n: math.log2(n)),
    ("O(√n)", lambda n: math.sqrt(n)),
    ("O(n)", lambda n: float(n)),
    ("O(n log n)", lambda n: n * math.log2(n)),
    ("O(n²)", lambda n: float(n) ** 2),
    ("O(n³)", lambda n: float(n) ** 3),
]


def _linreg(xs: List[float], ys: List[float]) -> Tuple[float, float, float]:
    """Least squares y = a + b x. Returns (a, b, r²)."""
    k = len(xs)
    mx, my = sum(xs) / k, sum(ys) / k
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    syy = sum((y - my) ** 2 for y in ys)
    b = sxy / sxx if sxx else 0.0
    a = my - b * mx
    r2 = (sxy * sxy) / (sxx * syy) if sxx and syy else 1.0
    return a, b, r2


def fit_growth(points: List[Tuple[float, float]], kind: str = "time") -> Optional[Dict[str, Any]]:
    """Choose the standard class that best explains y(n). Needs at least 3 points."""
    pts = [(n, y) for n, y in points if n and n > 1 and y is not None and y > 0]
    if len(pts) < 3:
        return None
    ns = [p[0] for p in pts]
    ys = [p[1] for p in pts]

    # Absolute noise level: timer/interpreter jitter (~2 µs) or allocator granularity (~1 KB).
    noise = 1024.0 if kind == "memory" else 2e-6
    # Barely changing measurements -> constant (e.g. memory of an in-place algorithm).
    flat_ratio = 1.6 if kind == "memory" else 1.25
    if (max(ys) / min(ys) < flat_ratio or max(ys) - min(ys) < noise) and max(ns) / min(ns) >= 4:
        return {"label": "O(1)", "slope": 0.0, "detail": "measurements stay roughly constant as n grows"}
    if kind == "memory" and max(ys) < 2048:
        return {"label": "O(1)", "slope": 0.0, "detail": "only a few hundred bytes of new allocations"}
    if kind == "memory" and sum(1 for y in ys if y >= noise) < 3:
        return None   # too few meaningful measurements to say anything

    log_n = [math.log(n) for n in ns]
    log_y = [math.log(y) for y in ys]
    _, slope, r2_power = _linreg(log_n, log_y)
    _, exp_rate, r2_exp = _linreg(ns, log_y)

    # Exponential: log y is linear in n (not in log n), and the power-law slope is huge.
    if slope > 2.5 and r2_exp > r2_power and exp_rate > 0:
        base = math.exp(exp_rate)
        return {"label": f"O({base:.2f}ⁿ)", "slope": round(slope, 2), "exponential_base": round(base, 3),
                "detail": f"log(y) grows linearly with n (base ≈ {base:.2f})"}

    # Otherwise fit y ≈ a + b·g(n) for every candidate g. The intercept a >= 0 absorbs the fixed
    # per-call overhead (function call, interpreter), which dominates for very fast algorithms.
    scores = []
    for label, g in CANDIDATES:
        err = _fit_error(ns, ys, g, noise)
        scores.append((err, label))
    min_err = min(err for err, _ in scores)
    # Occam's razor: take the SIMPLEST class whose error is close to the best one.
    for err, label in scores:                       # CANDIDATES are ordered by growth rate
        if err <= min_err * 1.3 + 0.002:
            result = {"label": label, "slope": round(slope, 2), "fit_error": round(err, 4),
                      "detail": f"log-log slope ≈ {slope:.2f} (1 ≈ linear, 2 ≈ quadratic)"}
            if kind == "time" and max(ys) < 50e-6:
                result["unreliable"] = True
                result["detail"] += "; every run took < 50 µs, so interpreter overhead and CPU-cache " \
                                    "effects dominate - treat this class with caution"
            return result
    return None


def _fit_error(ns: List[float], ys: List[float], g, noise: float) -> float:
    """Weighted least squares y = a + b·g(n) with weights 1/y² (i.e. relative error), a, b >= 0.
    Returns the mean squared relative error."""
    gs = [g(n) for n in ns]
    floor = max(0.02 * max(ys), noise)     # measurements below the noise level get less weight
    w = [1.0 / max(y, floor) ** 2 for y in ys]
    sw = sum(w)
    swg = sum(wi * gi for wi, gi in zip(w, gs))
    swgg = sum(wi * gi * gi for wi, gi in zip(w, gs))
    swy = sum(wi * yi for wi, yi in zip(w, ys))
    swgy = sum(wi * gi * yi for wi, gi, yi in zip(w, gs, ys))
    det = sw * swgg - swg * swg
    a, b = (0.0, 0.0)
    if abs(det) > 1e-300:
        a = (swy * swgg - swg * swgy) / det
        b = (sw * swgy - swg * swy) / det
    if abs(det) <= 1e-300 or a < 0 or b < 0:
        # fall back to the best one-parameter model (pure constant or pure c·g(n))
        options = []
        if swgg:
            options.append((0.0, max(swgy / swgg, 0.0)))
        options.append((swy / sw, 0.0))
        a, b = min(options, key=lambda ab: sum(wi * (yi - ab[0] - ab[1] * gi) ** 2
                                               for wi, yi, gi in zip(w, ys, gs)))
    return sum(wi * (yi - a - b * gi) ** 2 for wi, yi, gi in zip(w, ys, gs)) / len(ys)


def run_benchmark(task: Task, code: str, seed: int, quick: bool = False) -> Dict[str, Any]:
    request = {
        "mode": "benchmark",
        "code": code,
        "task_id": task.id,
        "seed": seed,
        "slow_threshold": 0.08 if quick else 0.15,
        "budget": 5.0 if quick else 10.0,
        "call_timeout": 3.0,
        "cpu_seconds": 60,
    }
    resp = run_in_sandbox(request, timeout=45)
    if not resp.get("ok"):
        return {"ok": False, "error": resp.get("error", "benchmark failed")}

    profiles = {}
    for pid, data in resp["profiles"].items():
        pts = data["points"]
        profiles[pid] = {
            "points": pts,
            "note": data.get("note"),
            "time_fit": fit_growth([(p["n"], p["seconds"]) for p in pts], "time"),
            "memory_fit": fit_growth([(p["n"], p["peak_bytes"]) for p in pts], "memory"),
        }
    return {"ok": True, "profiles": profiles, "elapsed": resp.get("elapsed")}


def compare_benchmarks(task: Task, bench_a: Dict[str, Any], bench_b: Dict[str, Any]) -> Dict[str, Any]:
    """Per profile: speed ratio at the largest n both algorithms completed."""
    rows = []
    if not (bench_a.get("ok") and bench_b.get("ok")):
        return {"rows": rows}
    for profile in task.profiles:
        pa = {p["n"]: p for p in bench_a["profiles"].get(profile.id, {}).get("points", [])}
        pb = {p["n"]: p for p in bench_b["profiles"].get(profile.id, {}).get("points", [])}
        common = sorted(set(pa) & set(pb))
        row: Dict[str, Any] = {"profile": profile.id, "label": profile.label,
                               "max_n_a": max(pa) if pa else None, "max_n_b": max(pb) if pb else None}
        if common:
            n = common[-1]
            ta, tb = pa[n]["seconds"], pb[n]["seconds"]
            row.update({"n": n, "time_a": ta, "time_b": tb,
                        "faster": "A" if ta < tb else "B", "ratio": (max(ta, tb) / min(ta, tb)) if min(ta, tb) > 0 else None,
                        "mem_a": pa[n].get("peak_bytes"), "mem_b": pb[n].get("peak_bytes")})
        rows.append(row)
    return {"rows": rows}
