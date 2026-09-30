"""
Result generation: merges functional, theoretical and empirical results into one report.

The three kinds of evidence are deliberately kept in separate sections and every summary
sentence is tagged with the kind of evidence it is based on.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .tasks import Task

CASES = [("best", "Best case"), ("average", "Average case"), ("worst", "Worst case")]


def _cmp_keys(a: List[float], b: List[float]) -> str:
    if a == b:
        return "="
    return "A" if a < b else "B"


def compare_theory(theory_a: Dict[str, Any], theory_b: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = []
    if not (theory_a.get("ok") and theory_b.get("ok")):
        return rows
    for resource in ("time", "space"):
        for case, label in CASES:
            a, b = theory_a[resource][case], theory_b[resource][case]
            rows.append({"resource": resource, "case": case, "label": f"{label} {resource}",
                         "a": a["label"], "b": b["label"], "better": _cmp_keys(a["key"], b["key"])})
    return rows


def _empirical_cases(bench: Dict[str, Any], task: Task) -> Optional[Dict[str, Any]]:
    """Which input profile was fastest / slowest (at the largest n that all profiles reached)?"""
    if not bench.get("ok") or len(task.profiles) < 2:
        return None
    per_profile = {pid: {p["n"]: p["seconds"] for p in d["points"]} for pid, d in bench["profiles"].items()}
    common = set.intersection(*(set(v) for v in per_profile.values())) if per_profile else set()
    if not common:
        return None
    n = max(common)
    times = {pid: v[n] for pid, v in per_profile.items()}
    fastest = min(times, key=times.get)
    slowest = max(times, key=times.get)
    labels = {p.id: p.label for p in task.profiles}
    return {"n": n, "fastest": labels[fastest], "slowest": labels[slowest],
            "fastest_time": times[fastest], "slowest_time": times[slowest],
            "spread": times[slowest] / times[fastest] if times[fastest] > 0 else None}


def _consistency(theory: Dict[str, Any], bench: Dict[str, Any]) -> List[Dict[str, str]]:
    """Does the empirical growth on each profile match one of the theoretical cases?"""
    out = []
    if not (theory.get("ok") and bench.get("ok")):
        return out
    labels = {case: theory["time"][case]["label"] for case, _ in CASES}
    for pid, data in bench["profiles"].items():
        fit = data.get("time_fit")
        if not fit:
            continue
        emp = fit["label"]
        matches = [case for case, lab in labels.items()
                   if lab == emp or ("ⁿ" in lab and "ⁿ" in emp)]
        strip = lambda s: s.replace(" log n", "").replace("O(log n)", "O(1)")
        close = [case for case, lab in labels.items() if strip(lab) == strip(emp)] if not matches else []
        out.append({"profile": pid, "empirical": emp,
                    "matches": ", ".join(matches) if matches else None,
                    "close_to": ", ".join(close) if close else None})
    return out


def build_summary(task: Task, names: Dict[str, str], functional: Dict[str, Any], theory_rows: List[Dict[str, Any]],
                  bench_cmp: Dict[str, Any]) -> List[Dict[str, str]]:
    a, b = names["A"], names["B"]
    lines: List[Dict[str, str]] = []

    # --- functional -------------------------------------------------------------------------
    v = functional.get("verdict")
    if v == "equivalent_on_tested":
        lines.append({"kind": "tested", "text": f"{a} and {b} produced equivalent outputs on all "
                                                f"{functional['total']} tested inputs. This is evidence, not a proof "
                                                "of equivalence for every possible input."})
    elif v == "not_equivalent":
        ce = functional.get("first_counterexample") or {}
        lines.append({"kind": "tested", "text": f"{a} and {b} are NOT equivalent: they disagreed on "
                                                f"{functional['disagree']} of {functional['total']} inputs "
                                                f"(first counterexample: input {ce.get('input')})."})
        lines.append({"kind": "tested", "text": "Because the outputs differ, the performance comparison below compares "
                                                "algorithms that solve DIFFERENT problems - interpret it with care."})
    else:
        lines.append({"kind": "tested", "text": "Functional equivalence could not be determined: "
                                                f"{functional.get('error', 'unknown error')}"})
    corr = functional.get("correctness")
    if corr:
        for key, nm in (("A", a), ("B", b)):
            c = corr[key]
            state = "matched" if c["passed"] == c["total"] else "did NOT match"
            lines.append({"kind": "tested", "text": f"{nm} {state} the reference solution on "
                                                    f"{c['passed']}/{c['total']} tested inputs."})

    # --- theory -----------------------------------------------------------------------------
    worst = next((r for r in theory_rows if r["resource"] == "time" and r["case"] == "worst"), None)
    if worst:
        if worst["better"] == "=":
            lines.append({"kind": "theory", "text": f"Both have the same worst-case time class {worst['a']} "
                                                    "(heuristic static analysis)."})
        else:
            win = a if worst["better"] == "A" else b
            lines.append({"kind": "theory", "text": f"Worst-case time: {a} {worst['a']} vs {b} {worst['b']} → "
                                                    f"{win} scales better asymptotically (heuristic static analysis)."})
    sp = next((r for r in theory_rows if r["resource"] == "space" and r["case"] == "worst"), None)
    if sp:
        if sp["better"] == "=":
            lines.append({"kind": "theory", "text": f"Both need {sp['a']} auxiliary space in the worst case."})
        else:
            win = a if sp["better"] == "A" else b
            lines.append({"kind": "theory", "text": f"Worst-case auxiliary space: {a} {sp['a']} vs {b} {sp['b']} → "
                                                    f"{win} uses asymptotically less memory."})

    # --- empirical --------------------------------------------------------------------------
    rows = [r for r in bench_cmp.get("rows", []) if r.get("n")]
    if rows:
        biggest = max(rows, key=lambda r: (r["ratio"] or 0))
        win = a if biggest["faster"] == "A" else b
        ratio = biggest["ratio"]
        lines.append({"kind": "empirical", "text": f"Measured: on '{biggest['label']}' inputs of size n = {biggest['n']}, "
                                                   f"{win} was {ratio:.1f}× faster (this machine, this interpreter)."})
        wins = {r["faster"] for r in rows}
        if len(wins) == 2:
            lines.append({"kind": "empirical", "text": "Which algorithm is faster depends on the input profile - "
                                                       "see the per-profile table."})
    return lines


def build_report(task: Task, names: Dict[str, str], validation: Dict[str, Any], functional: Dict[str, Any],
                 theory_a: Dict[str, Any], theory_b: Dict[str, Any], bench_a: Optional[Dict[str, Any]],
                 bench_b: Optional[Dict[str, Any]], bench_cmp: Dict[str, Any], seed: int,
                 notes: str = "") -> Dict[str, Any]:
    theory_rows = compare_theory(theory_a, theory_b)
    return {
        "task": task.to_public_dict(),
        "task_notes": notes,
        "names": names,
        "seed": seed,
        "validation": validation,
        "functional": functional,
        "theory": {
            "A": theory_a, "B": theory_b, "comparison": theory_rows,
            "model_note": "Unit-cost RAM model: arithmetic, comparisons and list indexing are assumed O(1). "
                          "Python big integers (e.g. large Fibonacci numbers) actually cost more.",
        },
        "empirical": {
            "A": bench_a, "B": bench_b, "comparison": bench_cmp,
            "cases": {"A": _empirical_cases(bench_a or {}, task), "B": _empirical_cases(bench_b or {}, task)},
            "consistency": {"A": _consistency(theory_a, bench_a or {}), "B": _consistency(theory_b, bench_b or {})},
        } if bench_a is not None else None,
        "summary": build_summary(task, names, functional, theory_rows, bench_cmp),
    }
