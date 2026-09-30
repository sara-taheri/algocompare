"""
Functional equivalence testing.

Both algorithms are run on exactly the same generated inputs (edge cases + seeded random inputs
for every input profile). Outputs are compared with the task's comparator.

IMPORTANT - what the verdict means:
  * "Equivalent on tested inputs": A and B agreed on every one of the N inputs we tried.
    This is evidence, NOT a proof. Deciding whether two arbitrary programs are equivalent on
    all inputs is undecidable in general (Rice's theorem).
  * "Not equivalent": we found at least one counterexample - that IS a proof they differ.
"""
from __future__ import annotations

from typing import Any, Dict, List

from .runner import _jsonable
from .sandbox import run_in_sandbox
from .tasks import Task, generate_test_inputs

DISCLAIMER = ("Agreement on a finite set of tested inputs is evidence, not a proof. Deciding whether two "
              "arbitrary programs are equivalent for all inputs is undecidable in general (Rice's theorem). "
              "A single mismatch, however, is a proof that the algorithms differ.")


def decode(value: Any) -> Any:
    """Undo the runner's JSON encoding of special values (big ints, sets, reprs)."""
    if isinstance(value, list):
        return [decode(v) for v in value]
    if isinstance(value, dict):
        if set(value) == {"__bigint__"}:
            return int(value["__bigint__"])
        if set(value) == {"__set__"}:
            return {"__set__": [decode(v) for v in value["__set__"]]}
        if set(value) == {"__repr__"}:
            return value
        return {k: decode(v) for k, v in value.items()}
    return value


def preview(value: Any, limit: int = 90) -> str:
    text = repr(value)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def run_tests_for(code: str, task: Task, inputs: List[List[Any]]) -> Dict[str, Any]:
    request = {"mode": "tests", "code": code, "task_id": task.id, "inputs": inputs, "call_timeout": 2.0}
    return run_in_sandbox(request, timeout=min(60.0, 10.0 + 2.0 * len(inputs)))


def smoke_test(code: str, task: Task) -> Dict[str, Any]:
    """Run the algorithm on a couple of tiny inputs to catch runtime errors early."""
    inputs = [list(args) for args in task.edge_cases[:3]]
    resp = run_tests_for(code, task, inputs)
    if not resp.get("ok"):
        return {"passed": False, "message": resp.get("error", "unknown error")}
    for args, res in zip(inputs, resp["results"]):
        if res["status"] != "ok":
            return {"passed": False, "message": f"solve{preview(tuple(args), 60)} -> {res['error']}"}
    return {"passed": True, "message": f"Ran successfully on {len(inputs)} tiny input(s)."}


def run_equivalence_tests(task: Task, code_a: str, code_b: str, seed: int) -> Dict[str, Any]:
    tests = generate_test_inputs(task, seed)
    inputs = [t["args"] for t in tests]

    resp_a = run_tests_for(code_a, task, inputs)
    resp_b = run_tests_for(code_b, task, inputs)
    for label, resp in (("A", resp_a), ("B", resp_b)):
        if not resp.get("ok"):
            return {"verdict": "inconclusive", "error": f"Algorithm {label} could not be run: {resp.get('error')}",
                    "total": len(tests), "cases": [], "disclaimer": DISCLAIMER}

    cases, agree, errors_a, errors_b = [], 0, 0, 0
    correct = {"A": 0, "B": 0}
    first_mismatch = None
    for i, (test, ra, rb) in enumerate(zip(tests, resp_a["results"], resp_b["results"])):
        args = tuple(test["args"])
        out_a = decode(ra.get("output")) if ra["status"] == "ok" else None
        out_b = decode(rb.get("output")) if rb["status"] == "ok" else None
        errors_a += ra["status"] != "ok"
        errors_b += rb["status"] != "ok"

        if ra["status"] == "ok" and rb["status"] == "ok":
            match = bool(task.compare(args, out_a, out_b))
        else:
            match = False  # an error on either side is never "agreement"

        expected = None
        correct_a = correct_b = None
        if task.reference is not None:
            expected = decode(_jsonable(task.reference(*[list(a) if isinstance(a, list) else a for a in args])))
            correct_a = ra["status"] == "ok" and bool(task.compare(args, out_a, expected))
            correct_b = rb["status"] == "ok" and bool(task.compare(args, out_b, expected))
            correct["A"] += correct_a
            correct["B"] += correct_b

        agree += match
        if not match and first_mismatch is None:
            first_mismatch = i
        cases.append({
            "index": i + 1,
            "kind": test["kind"],
            "profile": test["profile"],
            "input": preview(args[0] if len(args) == 1 else args),
            "output_a": preview(out_a) if ra["status"] == "ok" else ra.get("error"),
            "output_b": preview(out_b) if rb["status"] == "ok" else rb.get("error"),
            "expected": preview(expected) if task.reference is not None else None,
            "status_a": ra["status"],
            "status_b": rb["status"],
            "match": match,
            "correct_a": correct_a,
            "correct_b": correct_b,
        })

    total = len(tests)
    verdict = "equivalent_on_tested" if agree == total else "not_equivalent"
    result: Dict[str, Any] = {
        "verdict": verdict,
        "total": total,
        "agree": agree,
        "disagree": total - agree,
        "errors_a": errors_a,
        "errors_b": errors_b,
        "first_counterexample": cases[first_mismatch] if first_mismatch is not None else None,
        "cases": cases,
        "disclaimer": DISCLAIMER,
        "seed": seed,
    }
    if task.reference is not None:
        result["correctness"] = {"A": {"passed": correct["A"], "total": total},
                                 "B": {"passed": correct["B"], "total": total}}
    return result
