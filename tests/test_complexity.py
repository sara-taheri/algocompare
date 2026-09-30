"""Static complexity analysis should reproduce the textbook results for classic algorithms."""
import pytest

from backend.services import examples as ex
from backend.services.bigo import EXP, LOG, N, N2, NLOGN, ONE, Big, Cost, bmax
from backend.services.complexity import analyze_complexity


def labels(code):
    r = analyze_complexity(code)
    assert r["ok"], r
    t, s = r["time"], r["space"]
    return (t["best"]["label"], t["average"]["label"], t["worst"]["label"]), s["worst"]["label"]


@pytest.mark.parametrize("code, time, space", [
    (ex.BUBBLE_SORT, ("O(n)", "O(n²)", "O(n²)"), "O(1)"),
    (ex.INSERTION_SORT, ("O(n)", "O(n²)", "O(n²)"), "O(1)"),
    (ex.MERGE_SORT, ("O(n log n)",) * 3, "O(n)"),
    (ex.QUICK_SORT, ("O(n log n)", "O(n log n)", "O(n²)"), "O(n)"),
    (ex.LINEAR_SEARCH, ("O(1)", "O(n)", "O(n)"), "O(1)"),
    (ex.BINARY_SEARCH, ("O(1)", "O(log n)", "O(log n)"), "O(1)"),
    (ex.BINARY_SEARCH_REC, ("O(1)", "O(log n)", "O(log n)"), "O(log n)"),
    (ex.MAX_SUB_BRUTE, ("O(n²)",) * 3, "O(1)"),
    (ex.MAX_SUB_DC, ("O(n log n)",) * 3, "O(log n)"),
    (ex.FIB_NAIVE, ("O(2ⁿ)",) * 3, "O(n)"),
    (ex.FIB_ITER, ("O(n)",) * 3, "O(1)"),
    (ex.FIB_MEMO, ("O(n)",) * 3, "O(n)"),
    (ex.FIB_DOUBLING, ("O(log n)",) * 3, "O(log n)"),
    (ex.DUP_BRUTE, ("O(1)", "O(n²)", "O(n²)"), "O(1)"),
    (ex.DUP_SET, ("O(1)", "O(n)", "O(n)"), "O(n)"),
    (ex.INV_MERGE, ("O(n log n)",) * 3, "O(n)"),
])
def test_classic_algorithms(code, time, space):
    assert labels(code) == (time, space)


def test_triple_loop_is_cubic():
    code = "def solve(arr):\n    c = 0\n    for i in arr:\n        for j in arr:\n            for k in arr:\n                c += 1\n    return c\n"
    assert labels(code)[0][2] == "O(n³)"


def test_constant_range_is_constant():
    code = "def solve(arr):\n    s = 0\n    for i in range(10):\n        s += i\n    return s\n"
    assert labels(code) == (("O(1)",) * 3, "O(1)")


def test_membership_in_list_vs_set():
    lst = "def solve(arr):\n    c = 0\n    for x in arr:\n        if x in arr:\n            c += 1\n    return c\n"
    st = "def solve(arr):\n    s = set(arr)\n    c = 0\n    for x in arr:\n        if x in s:\n            c += 1\n    return c\n"
    assert labels(lst)[0][2] == "O(n²)"
    assert labels(st)[0][2] == "O(n)"


def test_observations_have_line_numbers():
    r = analyze_complexity(ex.MERGE_SORT)
    assert r["observations"] and all(o["line"] > 0 for o in r["observations"])
    assert "2T(n/2)" in r["recurrence"]


def test_bigo_algebra():
    assert (N * N).same_as(N2)
    assert (N * LOG).same_as(NLOGN)
    assert bmax(N, NLOGN, ONE).same_as(NLOGN)
    assert bmax(N2, EXP).same_as(EXP)
    assert Big(3).label() == "O(n³)"
    c = Cost(ONE, N, N2) * Cost.of(N)
    assert (c.best.label(), c.worst.label()) == ("O(n)", "O(n³)")


# ---- regression tests from the final audit: student-style variants ----------------------
QUICK_COMPREHENSION = """
def solve(arr):
    if len(arr) < 2:
        return arr
    p = arr[0]
    return solve([x for x in arr[1:] if x < p]) + [p] + solve([x for x in arr[1:] if x >= p])
"""

QUICK_HOARE = """
def solve(arr):
    qs(arr, 0, len(arr) - 1)
    return arr
def qs(a, lo, hi):
    if lo >= hi:
        return
    pivot = a[(lo + hi) // 2]
    i, j = lo, hi
    while i <= j:
        while a[i] < pivot:
            i += 1
        while a[j] > pivot:
            j -= 1
        if i <= j:
            a[i], a[j] = a[j], a[i]
            i += 1
            j -= 1
    qs(a, lo, j)
    qs(a, i, hi)
"""

BUBBLE_FLAG = """
def solve(arr):
    swapped = True
    while swapped:
        swapped = False
        for i in range(len(arr) - 1):
            if arr[i] > arr[i + 1]:
                arr[i], arr[i + 1] = arr[i + 1], arr[i]
                swapped = True
    return arr
"""

NESTED_INDEPENDENT_WHILES = """
def solve(arr):
    i = 0
    while i < len(arr):
        k = 0
        while k < len(arr):
            k += 1
        i += 1
    return i
"""


@pytest.mark.parametrize("code, time", [
    (QUICK_COMPREHENSION, ("O(n log n)", "O(n log n)", "O(n²)")),
    (QUICK_HOARE, ("O(n log n)", "O(n log n)", "O(n²)")),
    (BUBBLE_FLAG, ("O(n)", "O(n²)", "O(n²)")),
    (NESTED_INDEPENDENT_WHILES, ("O(n²)",) * 3),          # must NOT be treated as amortised
    ("def solve(arr):\n    return [x for x in sorted(arr)]\n", ("O(n)", "O(n log n)", "O(n log n)")),
])
def test_student_style_variants(code, time):
    assert labels(code)[0] == time
