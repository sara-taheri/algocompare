"""
Task definitions.

A *task* describes the computational problem both algorithms must solve:
  * the signature of the required `solve(...)` function,
  * how to generate inputs of size n (for testing and benchmarking),
  * which *input profiles* exist (e.g. sorted / reversed / random) - these matter because
    best-case and worst-case behaviour depends on the shape of the input,
  * hand-picked edge cases,
  * how two outputs are compared ("what does *same result* mean?"),
  * an optional trusted reference solution (used to say whether A / B are *correct* on the tests).

This module is imported both by the web server and by the sandboxed runner process, so it must
not import anything heavy.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

Args = Tuple[Any, ...]


@dataclass
class Profile:
    id: str
    label: str
    description: str


@dataclass
class Task:
    id: str
    name: str
    description: str
    signature: str                   # shown to the user, e.g. "solve(arr: list[int]) -> list[int]"
    param_count: int
    size_meaning: str                # what "n" means for this task
    profiles: List[Profile]
    generate: Callable[[int, random.Random, str], Args]   # (n, rng, profile_id) -> args
    edge_cases: List[Args]
    test_sizes: List[int]            # sizes used for random functional tests
    bench_sizes: List[int]           # sizes used for benchmarking (adaptive stop applies)
    reference: Optional[Callable[..., Any]] = None
    in_place_ok: bool = False        # if solve() returns None, use the mutated first argument
    compare: Callable[[Args, Any, Any], bool] = field(default=lambda args, a, b: outputs_equal(a, b))

    def to_public_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "signature": self.signature,
            "size_meaning": self.size_meaning,
            "profiles": [p.__dict__ for p in self.profiles],
            "in_place_ok": self.in_place_ok,
            "has_reference": self.reference is not None,
        }


# --------------------------------------------------------------------------------------------
# Output comparison helpers
# --------------------------------------------------------------------------------------------
def outputs_equal(a: Any, b: Any) -> bool:
    """Structural equality that treats tuples like lists and tolerates float rounding."""
    if isinstance(a, float) or isinstance(b, float):
        try:
            return abs(float(a) - float(b)) <= 1e-9 * max(1.0, abs(float(a)), abs(float(b)))
        except (TypeError, ValueError):
            return False
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(outputs_equal(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(outputs_equal(a[k], b[k]) for k in a)
    if isinstance(a, bool) != isinstance(b, bool):
        return False  # do not treat True == 1 as equal answers
    return a == b


# --------------------------------------------------------------------------------------------
# Generators (all deterministic given the rng)
# --------------------------------------------------------------------------------------------
def _gen_int_list(n: int, rng: random.Random, profile: str) -> Args:
    if profile == "sorted":
        arr = sorted(rng.randint(-n * 4, n * 4) for _ in range(n))
    elif profile == "reversed":
        arr = sorted((rng.randint(-n * 4, n * 4) for _ in range(n)), reverse=True)
    elif profile == "few_unique":
        arr = [rng.randint(0, 4) for _ in range(n)]
    else:  # random
        arr = [rng.randint(-n * 4, n * 4) for _ in range(n)]
    return (arr,)


def _gen_search(n: int, rng: random.Random, profile: str) -> Args:
    arr, value = [], -n
    for _ in range(n):              # strictly increasing -> sorted and distinct
        value += rng.randint(1, 5)
        arr.append(value)
    if n == 0:
        return (arr, rng.randint(-5, 5))
    if profile == "front":
        target = arr[0]
    elif profile == "absent":
        target = arr[-1] + 1          # larger than everything -> not present
    else:  # random present element
        target = arr[rng.randrange(n)]
    return (arr, target)


def _gen_max_subarray(n: int, rng: random.Random, profile: str) -> Args:
    n = max(n, 1)  # task requires a non-empty array
    if profile == "positive":
        arr = [rng.randint(1, 100) for _ in range(n)]
    elif profile == "negative":
        arr = [rng.randint(-100, -1) for _ in range(n)]
    else:
        arr = [rng.randint(-100, 100) for _ in range(n)]
    return (arr,)


def _gen_fib(n: int, rng: random.Random, profile: str) -> Args:
    return (n,)


def _gen_duplicates(n: int, rng: random.Random, profile: str) -> Args:
    if n <= 1:
        return ([rng.randint(0, 9) for _ in range(n)],)
    if profile == "front_dup":
        arr = rng.sample(range(n * 10), n)
        arr[1] = arr[0]                   # duplicate discovered immediately
    elif profile == "no_dup":
        arr = rng.sample(range(n * 10), n)  # all distinct -> worst case for most algorithms
    else:  # random values; duplicates likely but position random
        arr = [rng.randint(0, n * 2) for _ in range(n)]
    return (arr,)


# --------------------------------------------------------------------------------------------
# Reference (trusted) solutions
# --------------------------------------------------------------------------------------------
def _ref_search(arr, target):
    import bisect
    i = bisect.bisect_left(arr, target)
    return i if i < len(arr) and arr[i] == target else -1


def _ref_max_subarray(arr):
    best = cur = arr[0]
    for x in arr[1:]:
        cur = max(x, cur + x)
        best = max(best, cur)
    return best


def _ref_fib(n):
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a


# --------------------------------------------------------------------------------------------
# Registry
# --------------------------------------------------------------------------------------------
_DOUBLING = [100, 200, 400, 800, 1600, 3200, 6400, 12800]

TASKS: Dict[str, Task] = {}


def _register(task: Task) -> None:
    TASKS[task.id] = task


_register(Task(
    id="sorting",
    name="Sorting",
    description="Return the elements of the integer list in non-decreasing order. "
                "In-place algorithms may return None; the mutated list is then used as the output.",
    signature="solve(arr: list[int]) -> list[int]",
    param_count=1,
    size_meaning="n = len(arr)",
    profiles=[
        Profile("random", "Random", "Uniformly random integers (typical/average case)"),
        Profile("sorted", "Already sorted", "Best case for adaptive sorts, worst for naive quicksort"),
        Profile("reversed", "Reverse sorted", "Worst case for insertion/bubble sort"),
        Profile("few_unique", "Few unique values", "Many duplicates (values 0..4)"),
    ],
    generate=_gen_int_list,
    edge_cases=[([],), ([1],), ([2, 1],), ([1, 2],), ([3, 3, 3],), ([5, -1, 0, -1, 5],),
                ([10, 9, 8, 7, 6, 5, 4, 3, 2, 1],), ([0, -2147483648, 2147483647],)],
    test_sizes=[2, 3, 5, 8, 13, 21, 50, 100],
    bench_sizes=_DOUBLING,
    reference=lambda arr: sorted(arr),
    in_place_ok=True,
))

_register(Task(
    id="search_sorted",
    name="Search in a sorted array",
    description="Given a sorted list of DISTINCT integers and a target, return the index of the target, "
                "or -1 if it is not present.",
    signature="solve(arr: list[int], target: int) -> int",
    param_count=2,
    size_meaning="n = len(arr)",
    profiles=[
        Profile("front", "Target at front", "Target is the first element (best case for linear search)"),
        Profile("random", "Random present target", "Target is a random element (average case)"),
        Profile("absent", "Target absent", "Target larger than every element (worst case for linear search)"),
    ],
    generate=_gen_search,
    edge_cases=[([], 5), ([5], 5), ([5], 3), ([1, 3, 5, 7], 1), ([1, 3, 5, 7], 7),
                ([1, 3, 5, 7], 4), ([1, 3, 5, 7], 8), ([1, 3, 5, 7], 0), ([-9, -4, 0, 2], -4)],
    test_sizes=[1, 2, 3, 7, 16, 31, 64, 200],
    bench_sizes=[1000, 4000, 16000, 64000, 256000],
    reference=_ref_search,
))

_register(Task(
    id="max_subarray",
    name="Maximum subarray sum",
    description="Return the largest sum of a non-empty contiguous subarray of the (non-empty) integer list.",
    signature="solve(arr: list[int]) -> int",
    param_count=1,
    size_meaning="n = len(arr)",
    profiles=[
        Profile("random", "Random (-100..100)", "Mixed positive and negative values"),
        Profile("positive", "All positive", "Answer is the sum of the whole array"),
        Profile("negative", "All negative", "Answer is the largest single element"),
    ],
    generate=_gen_max_subarray,
    edge_cases=[([5],), ([-3],), ([-2, -1],), ([1, -1, 1],), ([-2, 1, -3, 4, -1, 2, 1, -5, 4],),
                ([0, 0, 0],), ([100, -1000, 100],)],
    test_sizes=[1, 2, 3, 5, 8, 13, 40, 100],
    bench_sizes=_DOUBLING,
    reference=_ref_max_subarray,
))

_register(Task(
    id="fibonacci",
    name="n-th Fibonacci number",
    description="Return F(n) where F(0) = 0, F(1) = 1 and F(n) = F(n-1) + F(n-2).",
    signature="solve(n: int) -> int",
    param_count=1,
    size_meaning="n = the input value itself",
    profiles=[Profile("value", "n", "The input is just the number n")],
    generate=_gen_fib,
    edge_cases=[(0,), (1,), (2,), (3,), (10,)],
    test_sizes=[4, 5, 6, 7, 8, 9, 11, 12, 15, 18, 20, 22],
    bench_sizes=[5, 10, 15, 20, 25, 30, 35, 50, 100, 200, 400, 800],
    reference=_ref_fib,
))

_register(Task(
    id="contains_duplicate",
    name="Contains duplicate",
    description="Return True if any value appears at least twice in the list, otherwise False.",
    signature="solve(arr: list[int]) -> bool",
    param_count=1,
    size_meaning="n = len(arr)",
    profiles=[
        Profile("front_dup", "Duplicate at front", "arr[0] == arr[1] (best case for early exit)"),
        Profile("random", "Random values", "Values in 0..2n, duplicates likely somewhere"),
        Profile("no_dup", "All distinct", "No duplicates - every pair must be ruled out (worst case)"),
    ],
    generate=_gen_duplicates,
    edge_cases=[([],), ([1],), ([1, 1],), ([1, 2],), ([1, 2, 3, 1],), ([-1, 1],), ([0, 0, 0],)],
    test_sizes=[2, 3, 5, 8, 13, 40, 100],
    bench_sizes=_DOUBLING,
    reference=lambda arr: len(set(arr)) != len(arr),
))

_register(Task(
    id="custom",
    name="Custom task (integer list → any result)",
    description="Generic task: both algorithms receive the same list of integers and their return values "
                "are compared for exact equality. There is no reference solution, so only A-vs-B agreement "
                "is reported. Describe the intended problem in the task notes.",
    signature="solve(arr: list[int]) -> Any",
    param_count=1,
    size_meaning="n = len(arr)",
    profiles=[
        Profile("random", "Random", "Uniformly random integers"),
        Profile("sorted", "Sorted", "Non-decreasing integers"),
        Profile("reversed", "Reverse sorted", "Non-increasing integers"),
    ],
    generate=_gen_int_list,
    edge_cases=[([],), ([1],), ([2, 1],), ([1, 2, 3],), ([3, 3, 3],), ([5, -1, 0, -1, 5],)],
    test_sizes=[2, 3, 5, 8, 13, 21, 50, 100],
    bench_sizes=_DOUBLING,
    reference=None,
    in_place_ok=True,
))


def get_task(task_id: str) -> Task:
    if task_id not in TASKS:
        raise KeyError(f"Unknown task '{task_id}'")
    return TASKS[task_id]


def make_rng(seed: int, *parts: Any) -> random.Random:
    """Deterministic RNG: the same (seed, parts) always produces the same inputs,
    in any process. This is how A and B are guaranteed to see identical inputs."""
    return random.Random("|".join([str(seed), *map(str, parts)]))


def generate_test_inputs(task: Task, seed: int) -> List[Dict[str, Any]]:
    """Edge cases + random inputs across all profiles and several small sizes."""
    tests: List[Dict[str, Any]] = []
    for args in task.edge_cases:
        tests.append({"kind": "edge case", "profile": "-", "args": list(args)})
    for profile in task.profiles:
        for n in task.test_sizes:
            rng = make_rng(seed, "test", profile.id, n)
            args = task.generate(n, rng, profile.id)
            tests.append({"kind": "random", "profile": profile.id, "args": list(args)})
    # de-duplicate identical inputs (e.g. Fibonacci has only one profile)
    seen, unique = set(), []
    for t in tests:
        key = repr(t["args"])
        if key not in seen:
            seen.add(key)
            unique.append(t)
    return unique
