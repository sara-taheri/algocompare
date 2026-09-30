"""
Sandboxed runner - executed as a SEPARATE PROCESS:  python -m backend.services.runner

It reads one JSON request from stdin, executes the submitted algorithm, and writes one JSON
response to stdout. The web server never executes user code in its own process.

Modes
-----
  "tests"      run solve(*args) for every given input, return outputs (functional testing)
  "benchmark"  generate inputs of growing size per profile, measure time and peak memory

Protection (good enough for a course project, NOT a security boundary):
  * CPU-time and address-space limits (resource.setrlimit)
  * per-call wall-clock timeout (signal.setitimer)
  * restricted builtins + import whitelist
  * the parent process additionally enforces an overall timeout
"""
from __future__ import annotations

import builtins
import io
import json
import signal
import sys
import time
import tracemalloc
from typing import Any, Dict, List

from .tasks import get_task, make_rng
from .validation import ALLOWED_MODULES, FORBIDDEN_NAMES, ENTRY_POINT


_MEM_BASE = [0]


class CallTimeout(BaseException):
    """BaseException so that `except Exception` in user code cannot swallow it."""


def _on_alarm(signum, frame):
    raise CallTimeout()


def _apply_limits(memory_mb: int, cpu_seconds: int) -> None:
    try:
        import resource
        limit = memory_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 1))
    except (ImportError, ValueError, OSError):
        pass  # non-Linux platforms: rely on the parent's timeout


def _safe_import(name, globals=None, locals=None, fromlist=(), level=0):
    if name.split(".")[0] not in ALLOWED_MODULES:
        raise ImportError(f"import of '{name}' is not allowed")
    return __import__(name, globals, locals, fromlist, level)


def _make_loader(code: str):
    """Compile once; return a function that builds a FRESH module namespace and returns solve().

    A fresh namespace per call means no state leaks between calls - e.g. an @lru_cache or a
    global memo dict would otherwise make repeated benchmark runs look O(1)."""
    code_obj = compile(code, "<algorithm>", "exec")
    safe_builtins = {k: v for k, v in vars(builtins).items() if k not in FORBIDDEN_NAMES}
    safe_builtins["__import__"] = _safe_import

    def load():
        namespace: Dict[str, Any] = {"__builtins__": safe_builtins, "__name__": "algorithm"}
        exec(code_obj, namespace)
        fn = namespace.get(ENTRY_POINT)
        if not callable(fn):
            raise RuntimeError(f"'{ENTRY_POINT}' is not defined")
        return fn

    load()  # fail fast if loading itself raises
    return load


def _copy_args(args: List[Any]) -> List[Any]:
    """Fresh copies so in-place algorithms cannot affect later runs."""
    out = []
    for a in args:
        if isinstance(a, list):
            out.append([list(x) if isinstance(x, list) else x for x in a])
        else:
            out.append(a)
    return out


def _jsonable(value: Any, depth: int = 0) -> Any:
    if depth > 20:
        return repr(value)
    if value is None or isinstance(value, (bool, int, str)):
        if isinstance(value, int) and not isinstance(value, bool) and abs(value) > 2 ** 53:
            return {"__bigint__": str(value)}
        return value
    if isinstance(value, float):
        return value if value == value and abs(value) != float("inf") else repr(value)
    if isinstance(value, (list, tuple)):
        return [_jsonable(v, depth + 1) for v in value]
    if isinstance(value, (set, frozenset)):
        try:
            return {"__set__": [_jsonable(v, depth + 1) for v in sorted(value)]}
        except TypeError:
            return {"__set__": sorted(repr(v) for v in value)}
    if isinstance(value, dict):
        return {str(k): _jsonable(v, depth + 1) for k, v in value.items()}
    return {"__repr__": repr(value)[:500]}


def _call(load, args: List[Any], timeout: float, in_place_ok: bool):
    """Load a fresh solve() and run it once with a timeout. Returns (output, seconds).
    Only the call itself is timed - not loading the code or copying the input."""
    fn = load()
    if tracemalloc.is_tracing():          # memory measurement: ignore the cost of loading the code
        tracemalloc.reset_peak()
        _MEM_BASE[0] = tracemalloc.get_traced_memory()[0]
    signal.setitimer(signal.ITIMER_REAL, timeout)
    try:
        start = time.perf_counter()
        result = fn(*args)
        elapsed = time.perf_counter() - start
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
    if result is None and in_place_ok and args and isinstance(args[0], list):
        result = args[0]
    return result, elapsed


# --------------------------------------------------------------------------------------------
def run_tests(load, req: Dict[str, Any]) -> Dict[str, Any]:
    task = get_task(req["task_id"])
    timeout = float(req.get("call_timeout", 2.0))
    results, timeouts = [], 0
    for args in req["inputs"]:
        if timeouts >= 3:   # probably an infinite loop - do not waste time on the rest
            results.append({"status": "timeout", "error": "Skipped after 3 timeouts in a row"})
            continue
        try:
            out, secs = _call(load, _copy_args(args), timeout, task.in_place_ok)
            results.append({"status": "ok", "output": _jsonable(out), "seconds": secs})
            timeouts = 0
        except CallTimeout:
            timeouts += 1
            results.append({"status": "timeout", "error": f"Exceeded {timeout:.1f}s time limit"})
        except RecursionError:
            results.append({"status": "error", "error": "RecursionError: maximum recursion depth exceeded"})
        except MemoryError:
            results.append({"status": "error", "error": "MemoryError: memory limit exceeded"})
        except Exception as exc:  # noqa: BLE001 - we want to report any user error
            results.append({"status": "error", "error": f"{type(exc).__name__}: {exc}"[:300]})
    return {"ok": True, "results": results}


def run_benchmark(load, req: Dict[str, Any]) -> Dict[str, Any]:
    """For each profile, time solve() on growing n until it gets too slow or the budget ends."""
    task = get_task(req["task_id"])
    seed = int(req["seed"])
    slow_threshold = float(req.get("slow_threshold", 0.25))   # stop growing n after a run this slow
    call_timeout = float(req.get("call_timeout", 3.0))
    budget = float(req.get("budget", 10.0))                    # total seconds for this algorithm
    min_total = float(req.get("min_total", 0.02))              # repeat fast runs until this much time
    max_repeats = int(req.get("max_repeats", 25))
    measure_memory = bool(req.get("measure_memory", True))

    started = time.perf_counter()
    profiles_out: Dict[str, Any] = {}
    share = budget / len(task.profiles)          # every profile gets an equal slice of the budget
    for profile in task.profiles:
        points, note = [], None
        profile_start = time.perf_counter()
        trace_memory = measure_memory
        for n in task.bench_sizes:
            if time.perf_counter() - profile_start > share:
                note = "time budget exhausted"
                break
            base_args = list(task.generate(n, make_rng(seed, "bench", profile.id, n), profile.id))
            try:
                # --- time: minimum over repeats (least affected by OS noise) ---
                times, total = [], 0.0
                while True:
                    _, secs = _call(load, _copy_args(base_args), call_timeout, task.in_place_ok)
                    times.append(secs)
                    total += secs
                    if total >= min_total or len(times) >= max_repeats or secs > slow_threshold:
                        break
                best = min(times)
                # --- memory: peak of NEW allocations during one call ---
                peak = None
                # tracemalloc slows code down a lot (especially deep recursion), so only trace fast
                # runs, and stop tracing this profile once a traced run becomes slow.
                if trace_memory and best < 0.03:
                    args = _copy_args(base_args)
                    tracemalloc.start()
                    try:
                        _, traced_secs = _call(load, args, call_timeout, task.in_place_ok)
                        if traced_secs > 0.4:
                            trace_memory = False
                        _, peak = tracemalloc.get_traced_memory()
                        peak = max(0, peak - _MEM_BASE[0])
                    except CallTimeout:
                        trace_memory = False
                    finally:
                        tracemalloc.stop()
                points.append({"n": n, "seconds": best, "repeats": len(times), "peak_bytes": peak})
                if best > slow_threshold:
                    note = f"stopped after n={n}: a single run took {best:.2f}s"
                    break
            except CallTimeout:
                note = f"timeout at n={n} (> {call_timeout:.0f}s)"
                break
            except RecursionError:
                note = f"RecursionError at n={n}"
                break
            except MemoryError:
                note = f"MemoryError at n={n}"
                break
            except Exception as exc:  # noqa: BLE001
                note = f"{type(exc).__name__} at n={n}: {exc}"[:200]
                break
        profiles_out[profile.id] = {"points": points, "note": note}
    return {"ok": True, "profiles": profiles_out, "elapsed": time.perf_counter() - started}


# --------------------------------------------------------------------------------------------
def main() -> None:
    real_stdout = sys.stdout
    req = json.loads(sys.stdin.read())
    _apply_limits(int(req.get("memory_mb", 1024)), int(req.get("cpu_seconds", 60)))
    signal.signal(signal.SIGALRM, _on_alarm)
    sys.setrecursionlimit(20_000)
    sys.set_int_max_str_digits(0) if hasattr(sys, "set_int_max_str_digits") else None
    sys.stdout = io.StringIO()  # swallow the algorithm's print() output
    try:
        load = _make_loader(req["code"])
        if req["mode"] == "tests":
            response = run_tests(load, req)
        elif req["mode"] == "benchmark":
            response = run_benchmark(load, req)
        else:
            response = {"ok": False, "error": f"unknown mode {req['mode']}"}
    except CallTimeout:
        response = {"ok": False, "error": "Loading the code timed out"}
    except BaseException as exc:  # noqa: BLE001 - report everything, including SyntaxError
        response = {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:500]}
    sys.stdout = real_stdout
    real_stdout.write(json.dumps(response))
    real_stdout.flush()


if __name__ == "__main__":
    main()
