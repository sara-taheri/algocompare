"""Validation, functional equivalence, benchmark fitting and the HTTP API."""
import pytest

from backend.app import create_app
from backend.services import examples as ex
from backend.services.benchmark import fit_growth
from backend.services.functional import run_equivalence_tests
from backend.services.tasks import TASKS, generate_test_inputs, get_task
from backend.services.validation import validate_code

SORT = get_task("sorting")


# ---------------- validation ----------------
def test_valid_code_passes():
    assert validate_code(ex.MERGE_SORT, SORT)["valid"]


@pytest.mark.parametrize("code, fragment", [
    ("", "empty"),
    ("def solve(arr)\n    return arr", "Syntax error"),
    ("def sort(arr):\n    return arr", "No top-level function"),
    ("def solve(a, b):\n    return a", "parameter"),
    ("import os\ndef solve(arr):\n    return arr", "not allowed"),
    ("def solve(arr):\n    return open('x')", "not allowed"),
    ("def solve(arr):\n    return arr.__class__", "dunder"),
])
def test_invalid_code_is_rejected(code, fragment):
    result = validate_code(code, SORT)
    assert not result["valid"]
    assert any(fragment in e["message"] for e in result["errors"])


def test_in_place_without_return_is_a_warning_for_sorting():
    code = "def solve(arr):\n    arr.sort()\n"
    result = validate_code(code, SORT)
    assert result["valid"] and result["warnings"]


# ---------------- tasks ----------------
def test_generated_inputs_are_deterministic():
    for task in TASKS.values():
        assert generate_test_inputs(task, 7) == generate_test_inputs(task, 7)


# ---------------- functional ----------------
def test_equivalent_algorithms():
    r = run_equivalence_tests(SORT, ex.BUBBLE_SORT, ex.MERGE_SORT, seed=1)
    assert r["verdict"] == "equivalent_on_tested"
    assert r["agree"] == r["total"] and "not a proof" in r["disclaimer"]


def test_counterexample_is_found():
    r = run_equivalence_tests(SORT, ex.BUBBLE_SORT, ex.BUGGY_SORT, seed=1)
    assert r["verdict"] == "not_equivalent"
    assert r["first_counterexample"] is not None
    assert r["correctness"]["B"]["passed"] < r["total"]


def test_runtime_errors_and_infinite_loops_are_contained():
    crash = "def solve(arr):\n    return arr[len(arr) + 5]\n"
    loop = "def solve(arr):\n    while True:\n        pass\n"
    r = run_equivalence_tests(SORT, crash, loop, seed=1)
    assert r["verdict"] == "not_equivalent"
    assert r["errors_a"] > 0
    assert all(c["status_b"] == "timeout" for c in r["cases"][:2])


# ---------------- fitting ----------------
@pytest.mark.parametrize("f, label", [
    (lambda n: 1e-6 * n, "O(n)"),
    (lambda n: 1e-7 * n * n, "O(n²)"),
    (lambda n: 3e-7 * n * __import__("math").log2(n), "O(n log n)"),
    (lambda n: 5e-3, "O(1)"),
])
def test_fit_growth(f, label):
    pts = [(n, f(n)) for n in (100, 200, 400, 800, 1600, 3200)]
    assert fit_growth(pts)["label"] == label


def test_fit_exponential():
    pts = [(n, 1e-7 * 1.618 ** n) for n in (5, 10, 15, 20, 25, 30)]
    assert "ⁿ" in fit_growth(pts)["label"]


# ---------------- API ----------------
@pytest.fixture()
def client():
    return create_app().test_client()


def test_api_tasks(client):
    data = client.get("/api/tasks").get_json()
    assert {t["id"] for t in data["tasks"]} >= {"sorting", "search_sorted", "custom"}
    assert data["examples"]


def test_api_validate(client):
    data = client.post("/api/validate", json={"task_id": "sorting", "code_a": ex.MERGE_SORT,
                                              "code_b": "def solve(arr):\n    return arr[99]\n"}).get_json()
    assert data["A"]["valid"] and data["A"]["smoke"]["passed"]
    assert not data["B"]["valid"]


def test_api_compare_without_benchmark(client):
    resp = client.post("/api/compare", json={"task_id": "search_sorted", "code_a": ex.LINEAR_SEARCH,
                                             "code_b": ex.BINARY_SEARCH, "benchmark": False, "seed": 3})
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["functional"]["verdict"] == "equivalent_on_tested"
    assert data["theory"]["A"]["time"]["worst"]["label"] == "O(n)"
    assert data["theory"]["B"]["time"]["worst"]["label"] == "O(log n)"
    assert data["empirical"] is None
    assert {s["kind"] for s in data["summary"]} == {"tested", "theory"}


def test_api_compare_rejects_invalid(client):
    resp = client.post("/api/compare", json={"task_id": "sorting", "code_a": "x =", "code_b": ex.MERGE_SORT})
    assert resp.status_code == 422


def test_api_unknown_task(client):
    assert client.post("/api/compare", json={"task_id": "nope"}).status_code == 400
