"""Ready-made algorithm pairs for demonstrations (all written for this project)."""
from __future__ import annotations

from typing import Dict, List

BUBBLE_SORT = '''def solve(arr):
    """Bubble sort with early exit (in-place)."""
    n = len(arr)
    for i in range(n):
        swapped = False
        for j in range(0, n - i - 1):
            if arr[j] > arr[j + 1]:
                arr[j], arr[j + 1] = arr[j + 1], arr[j]
                swapped = True
        if not swapped:          # no swaps -> already sorted
            break
    return arr
'''

MERGE_SORT = '''def solve(arr):
    """Top-down merge sort (returns a new list)."""
    if len(arr) <= 1:
        return arr
    mid = len(arr) // 2
    left = solve(arr[:mid])
    right = solve(arr[mid:])
    return merge(left, right)


def merge(left, right):
    result = []
    i = j = 0
    while i < len(left) and j < len(right):
        if left[i] <= right[j]:
            result.append(left[i])
            i += 1
        else:
            result.append(right[j])
            j += 1
    result.extend(left[i:])
    result.extend(right[j:])
    return result
'''

INSERTION_SORT = '''def solve(arr):
    """Insertion sort (in-place)."""
    for i in range(1, len(arr)):
        key = arr[i]
        j = i - 1
        while j >= 0 and arr[j] > key:
            arr[j + 1] = arr[j]
            j -= 1
        arr[j + 1] = key
    return arr
'''

QUICK_SORT = '''def solve(arr):
    """Quicksort, Lomuto partition, LAST element as pivot (in-place)."""
    quick_sort(arr, 0, len(arr) - 1)
    return arr


def quick_sort(arr, lo, hi):
    if lo < hi:
        p = partition(arr, lo, hi)
        quick_sort(arr, lo, p - 1)
        quick_sort(arr, p + 1, hi)


def partition(arr, lo, hi):
    pivot = arr[hi]
    i = lo - 1
    for j in range(lo, hi):
        if arr[j] <= pivot:
            i += 1
            arr[i], arr[j] = arr[j], arr[i]
    arr[i + 1], arr[hi] = arr[hi], arr[i + 1]
    return i + 1
'''

QUICK_SORT_SIMPLE = '''def solve(arr):
    """Functional quicksort (middle element as pivot)."""
    if len(arr) <= 1:
        return arr
    pivot = arr[len(arr) // 2]
    less = [x for x in arr if x < pivot]
    equal = [x for x in arr if x == pivot]
    greater = [x for x in arr if x > pivot]
    return solve(less) + equal + solve(greater)
'''

BUGGY_SORT = '''def solve(arr):
    """Looks like a sort... but a set silently removes duplicates!"""
    return sorted(set(arr))
'''

LINEAR_SEARCH = '''def solve(arr, target):
    """Linear search."""
    for i in range(len(arr)):
        if arr[i] == target:
            return i
    return -1
'''

BINARY_SEARCH = '''def solve(arr, target):
    """Iterative binary search."""
    lo, hi = 0, len(arr) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            lo = mid + 1
        else:
            hi = mid - 1
    return -1
'''

BINARY_SEARCH_REC = '''def solve(arr, target):
    return search(arr, target, 0, len(arr) - 1)


def search(arr, target, lo, hi):
    """Recursive binary search."""
    if lo > hi:
        return -1
    mid = (lo + hi) // 2
    if arr[mid] == target:
        return mid
    if arr[mid] < target:
        return search(arr, target, mid + 1, hi)
    return search(arr, target, lo, mid - 1)
'''

MAX_SUB_BRUTE = '''def solve(arr):
    """Brute force: try every start index, extend to the right."""
    best = arr[0]
    for i in range(len(arr)):
        current = 0
        for j in range(i, len(arr)):
            current += arr[j]
            if current > best:
                best = current
    return best
'''

MAX_SUB_KADANE = '''def solve(arr):
    """Kadane's algorithm (dynamic programming)."""
    best = current = arr[0]
    for x in arr[1:]:
        current = max(x, current + x)
        best = max(best, current)
    return best
'''

MAX_SUB_DC = '''def solve(arr):
    """Divide and conquer (CLRS style)."""
    return best_in(arr, 0, len(arr) - 1)


def best_in(arr, lo, hi):
    if lo == hi:
        return arr[lo]
    mid = (lo + hi) // 2
    left_best = best_in(arr, lo, mid)
    right_best = best_in(arr, mid + 1, hi)
    total, left_cross = 0, arr[mid]
    for i in range(mid, lo - 1, -1):
        total += arr[i]
        left_cross = max(left_cross, total)
    total, right_cross = 0, arr[mid + 1]
    for i in range(mid + 1, hi + 1):
        total += arr[i]
        right_cross = max(right_cross, total)
    return max(left_best, right_best, left_cross + right_cross)
'''

FIB_NAIVE = '''def solve(n):
    """Naive recursion straight from the definition."""
    if n < 2:
        return n
    return solve(n - 1) + solve(n - 2)
'''

FIB_ITER = '''def solve(n):
    """Bottom-up iteration with two variables."""
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a
'''

FIB_MEMO = '''from functools import lru_cache


def solve(n):
    return fib(n)


@lru_cache(maxsize=None)
def fib(n):
    """Top-down recursion with memoisation."""
    if n < 2:
        return n
    return fib(n - 1) + fib(n - 2)
'''

FIB_DOUBLING = '''def solve(n):
    return pair(n)[0]


def pair(n):
    """Fast doubling: returns (F(n), F(n+1))."""
    if n == 0:
        return (0, 1)
    a, b = pair(n // 2)
    c = a * (2 * b - a)
    d = a * a + b * b
    if n % 2 == 0:
        return (c, d)
    return (d, c + d)
'''

DUP_BRUTE = '''def solve(arr):
    """Compare every pair."""
    n = len(arr)
    for i in range(n):
        for j in range(i + 1, n):
            if arr[i] == arr[j]:
                return True
    return False
'''

DUP_SET = '''def solve(arr):
    """Hash set of values seen so far."""
    seen = set()
    for x in arr:
        if x in seen:
            return True
        seen.add(x)
    return False
'''

DUP_SORT = '''def solve(arr):
    """Sort a copy, then check neighbours."""
    s = sorted(arr)
    for i in range(1, len(s)):
        if s[i] == s[i - 1]:
            return True
    return False
'''

INV_BRUTE = '''def solve(arr):
    """Count inversions: pairs i < j with arr[i] > arr[j] (brute force)."""
    count = 0
    for i in range(len(arr)):
        for j in range(i + 1, len(arr)):
            if arr[i] > arr[j]:
                count += 1
    return count
'''

INV_MERGE = '''def solve(arr):
    """Count inversions with a modified merge sort."""
    return sort_count(arr)[1]


def sort_count(arr):
    if len(arr) <= 1:
        return arr, 0
    mid = len(arr) // 2
    left, a = sort_count(arr[:mid])
    right, b = sort_count(arr[mid:])
    merged, i, j, c = [], 0, 0, 0
    while i < len(left) and j < len(right):
        if left[i] <= right[j]:
            merged.append(left[i])
            i += 1
        else:
            merged.append(right[j])
            c += len(left) - i       # every remaining left element is an inversion
            j += 1
    merged.extend(left[i:])
    merged.extend(right[j:])
    return merged, a + b + c
'''

EXAMPLES: List[Dict[str, str]] = [
    {"id": "bubble_vs_merge", "task_id": "sorting", "title": "Bubble sort vs Merge sort",
     "a_name": "Bubble sort", "a_code": BUBBLE_SORT, "b_name": "Merge sort", "b_code": MERGE_SORT},
    {"id": "insertion_vs_quick", "task_id": "sorting", "title": "Insertion sort vs Quicksort (last-element pivot)",
     "a_name": "Insertion sort", "a_code": INSERTION_SORT, "b_name": "Quicksort", "b_code": QUICK_SORT},
    {"id": "merge_vs_functional_quick", "task_id": "sorting", "title": "Merge sort vs Functional quicksort",
     "a_name": "Merge sort", "a_code": MERGE_SORT, "b_name": "Functional quicksort", "b_code": QUICK_SORT_SIMPLE},
    {"id": "bubble_vs_buggy", "task_id": "sorting", "title": "Bubble sort vs Buggy sort (finds a counterexample)",
     "a_name": "Bubble sort", "a_code": BUBBLE_SORT, "b_name": "Buggy set-sort", "b_code": BUGGY_SORT},
    {"id": "linear_vs_binary", "task_id": "search_sorted", "title": "Linear search vs Binary search",
     "a_name": "Linear search", "a_code": LINEAR_SEARCH, "b_name": "Binary search", "b_code": BINARY_SEARCH},
    {"id": "binary_iter_vs_rec", "task_id": "search_sorted", "title": "Iterative vs Recursive binary search",
     "a_name": "Iterative binary search", "a_code": BINARY_SEARCH,
     "b_name": "Recursive binary search", "b_code": BINARY_SEARCH_REC},
    {"id": "brute_vs_kadane", "task_id": "max_subarray", "title": "Brute force vs Kadane",
     "a_name": "Brute force", "a_code": MAX_SUB_BRUTE, "b_name": "Kadane", "b_code": MAX_SUB_KADANE},
    {"id": "dc_vs_kadane", "task_id": "max_subarray", "title": "Divide & conquer vs Kadane",
     "a_name": "Divide & conquer", "a_code": MAX_SUB_DC, "b_name": "Kadane", "b_code": MAX_SUB_KADANE},
    {"id": "fib_naive_vs_iter", "task_id": "fibonacci", "title": "Naive recursion vs Iteration",
     "a_name": "Naive recursive", "a_code": FIB_NAIVE, "b_name": "Iterative", "b_code": FIB_ITER},
    {"id": "fib_memo_vs_doubling", "task_id": "fibonacci", "title": "Memoisation vs Fast doubling",
     "a_name": "Memoised recursion", "a_code": FIB_MEMO, "b_name": "Fast doubling", "b_code": FIB_DOUBLING},
    {"id": "dup_brute_vs_set", "task_id": "contains_duplicate", "title": "All pairs vs Hash set",
     "a_name": "All pairs", "a_code": DUP_BRUTE, "b_name": "Hash set", "b_code": DUP_SET},
    {"id": "dup_sort_vs_set", "task_id": "contains_duplicate", "title": "Sort first vs Hash set",
     "a_name": "Sort + scan", "a_code": DUP_SORT, "b_name": "Hash set", "b_code": DUP_SET},
    {"id": "inversions", "task_id": "custom", "title": "Count inversions: brute force vs merge-based",
     "a_name": "Brute force", "a_code": INV_BRUTE, "b_name": "Merge-based", "b_code": INV_MERGE},
]
