"""
Algorithm input validation (static - nothing is executed here).

Checks, in order:
  1. The code is non-empty and not too long.
  2. It is syntactically valid Python (ast.parse).
  3. It only imports whitelisted, side-effect-free modules and avoids dangerous builtins
     (open, eval, exec, __import__, ...) and dunder attributes (a classic sandbox-escape route).
  4. It defines a top-level function `solve` with the number of parameters the task requires.
  5. Soft warnings (print calls, randomness, missing return, `while True`, ...).

A smoke test (actually running the code once) is done separately by the API using the sandbox.
"""
from __future__ import annotations

import ast
from typing import Any, Dict, List

from .tasks import Task

MAX_CODE_LENGTH = 20_000
ENTRY_POINT = "solve"

ALLOWED_MODULES = {
    "math", "heapq", "bisect", "collections", "functools", "itertools",
    "random", "typing", "operator", "array", "string", "copy",
}
FORBIDDEN_NAMES = {
    "open", "eval", "exec", "compile", "__import__", "input", "globals", "locals", "vars",
    "breakpoint", "exit", "quit", "getattr", "setattr", "delattr", "memoryview", "help",
}


def _issue(line: int | None, message: str) -> Dict[str, Any]:
    return {"line": line, "message": message}


def validate_code(code: str, task: Task) -> Dict[str, Any]:
    """Return {"valid": bool, "errors": [...], "warnings": [...], "info": {...}}."""
    errors: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []
    info: Dict[str, Any] = {"functions": [], "lines": 0}

    if code is None or not code.strip():
        return {"valid": False, "errors": [_issue(None, "The code is empty.")], "warnings": [], "info": info}
    if len(code) > MAX_CODE_LENGTH:
        errors.append(_issue(None, f"Code is too long ({len(code)} characters, max {MAX_CODE_LENGTH})."))
        return {"valid": False, "errors": errors, "warnings": warnings, "info": info}

    info["lines"] = code.count("\n") + 1

    # ---- 2. syntax ------------------------------------------------------------------------
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        errors.append(_issue(exc.lineno, f"Syntax error: {exc.msg} (line {exc.lineno}, column {exc.offset})"))
        return {"valid": False, "errors": errors, "warnings": warnings, "info": info}

    # ---- 3. safety ------------------------------------------------------------------------
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root not in ALLOWED_MODULES:
                    errors.append(_issue(node.lineno, f"Import of '{alias.name}' is not allowed. "
                                                      f"Allowed: {', '.join(sorted(ALLOWED_MODULES))}."))
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root not in ALLOWED_MODULES:
                errors.append(_issue(node.lineno, f"Import from '{node.module}' is not allowed."))
        elif isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            errors.append(_issue(node.lineno, f"Use of '{node.id}' is not allowed in submitted algorithms."))
        elif isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            errors.append(_issue(node.lineno, f"Access to dunder attribute '{node.attr}' is not allowed."))
        elif isinstance(node, ast.Global):
            warnings.append(_issue(node.lineno, "Uses 'global' state - results may depend on previous calls."))

    # ---- 4. entry point -------------------------------------------------------------------
    top_funcs = {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    info["functions"] = sorted(top_funcs)
    entry = top_funcs.get(ENTRY_POINT)
    if entry is None:
        errors.append(_issue(None, f"No top-level function named '{ENTRY_POINT}' was found. "
                                   f"Expected signature: {task.signature}"))
    else:
        if isinstance(entry, ast.AsyncFunctionDef):
            errors.append(_issue(entry.lineno, f"'{ENTRY_POINT}' must be a normal (non-async) function."))
        args = entry.args
        positional = len(args.posonlyargs) + len(args.args)
        required = positional - len(args.defaults)
        if args.vararg is None and not (required <= task.param_count <= positional):
            errors.append(_issue(entry.lineno,
                                 f"'{ENTRY_POINT}' takes {required} required parameter(s) but the task "
                                 f"passes {task.param_count}. Expected: {task.signature}"))
        has_return_value = any(isinstance(n, ast.Return) and n.value is not None for n in ast.walk(entry))
        if not has_return_value:
            if task.in_place_ok:
                warnings.append(_issue(entry.lineno, f"'{ENTRY_POINT}' never returns a value - the mutated "
                                                     "input list will be used as its output (in-place algorithm)."))
            else:
                errors.append(_issue(entry.lineno, f"'{ENTRY_POINT}' never returns a value."))

    # ---- 5. soft warnings -----------------------------------------------------------------
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print":
            warnings.append(_issue(node.lineno, "print() output is ignored and slows down benchmarks."))
        if isinstance(node, ast.While) and isinstance(node.test, ast.Constant) and node.test.value is True:
            warnings.append(_issue(node.lineno, "'while True' loop - make sure it always terminates."))
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [a.name for a in node.names] + [getattr(node, "module", None) or ""]
            if "random" in names:
                warnings.append(_issue(node.lineno, "Uses randomness - outputs/timings may vary between runs."))
    top_level_code = [n for n in tree.body if not isinstance(
        n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Import, ast.ImportFrom, ast.ClassDef, ast.Assign, ast.Expr))]
    if top_level_code:
        warnings.append(_issue(top_level_code[0].lineno, "Top-level statements run once when the code is loaded."))

    return {"valid": not errors, "errors": errors, "warnings": _dedupe(warnings), "info": info}


def _dedupe(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen, out = set(), []
    for it in items:
        key = (it["line"], it["message"])
        if key not in seen:
            seen.add(key)
            out.append(it)
    return out
