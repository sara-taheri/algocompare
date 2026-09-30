"""
Theoretical (static) complexity analysis.

The code is NOT executed. We walk Python's abstract syntax tree (AST) and apply the rules taught
in an Algorithm Design course:

  * sequential statements  -> max of their costs
  * a loop                 -> (number of iterations) x (cost of the body)
  * `for x in range(n)` / `for x in arr`            -> n iterations
  * a `while` loop that halves/doubles a variable    -> log n iterations
  * an early `return` / `break` inside a loop        -> best case may stop after 1 iteration
  * a `while` loop whose condition inspects the data (e.g. insertion sort's inner loop)
                                                     -> best case 0 iterations
  * known library costs (sorted = n log n, `x in list` = n, `x in set` = 1, slicing = n, ...)
  * recursion: count calls per invocation (a) and how the input shrinks:
        halved (n//2, arr[:mid])        -> Master theorem  T(n) = a T(n/2) + f(n)
        decremented (n-1, arr[1:])      -> T(n) = T(n-1) + f(n)   (a = 1)   or   O(2^n) (a >= 2)
        split around a pivot            -> best/avg like halving, worst like decrementing (quicksort)
        memoised (@lru_cache, memo dict)-> about n distinct sub-problems
  * space = auxiliary memory: new containers, slices, growth via append/add in loops,
    and recursion depth (call stack).

This is a HEURISTIC. Complexity of arbitrary code is undecidable in general, so every result
comes with the observations that produced it and a confidence level.
"""
from __future__ import annotations

import ast
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from .bigo import (C_ONE, C_ZERO, EXP, LOG, N, NLOGN, ONE, SQRT, Big, Cost, bmax)

COMPREHENSIONS = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
HASH_CONSTRUCTORS = {"set", "dict", "frozenset", "Counter", "defaultdict", "OrderedDict"}
LIST_CONSTRUCTORS = {"list", "tuple", "sorted", "deque", "bytearray"}
LINEAR_REDUCERS = {"sum", "min", "max", "any", "all"}
LIBRARY_MODULES = {"heapq", "bisect", "math", "itertools", "functools", "collections", "operator"}
CONFIDENCE_LEVELS = ["low", "medium", "high"]


# ---------------------------------------------------------------------------------------------
@dataclass
class Res:
    """Cost of a code fragment."""
    time: Cost = C_ONE
    fixed: Cost = C_ZERO      # memory allocated by the fragment (not multiplied by loops)
    growth: Cost = C_ZERO     # memory that accumulates per loop iteration (append/add/d[k]=v)
    rec: int = 0              # recursive calls per invocation (max over if/else branches)
    rec_in_loop: bool = False

    def then(self, o: "Res") -> "Res":          # sequential composition
        return Res(self.time.max(o.time), self.fixed.max(o.fixed), self.growth.max(o.growth),
                   self.rec + o.rec, self.rec_in_loop or o.rec_in_loop)

    def either(self, o: "Res") -> "Res":        # if / else: only one branch runs
        return Res(self.time.max(o.time), self.fixed.max(o.fixed), self.growth.max(o.growth),
                   max(self.rec, o.rec), self.rec_in_loop or o.rec_in_loop)


@dataclass
class FunctionReport:
    name: str
    time: Cost
    space: Cost
    notes: List[Tuple[int, str]] = field(default_factory=list)
    confidence: int = 2                  # index into CONFIDENCE_LEVELS
    recurrence: Optional[str] = None


# ---------------------------------------------------------------------------------------------
def _is_const(node: ast.AST) -> bool:
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, ast.UnaryOp):
        return _is_const(node.operand)
    if isinstance(node, ast.BinOp):
        return _is_const(node.left) and _is_const(node.right)
    return False


def _const_int(node: ast.AST) -> Optional[int]:
    try:
        value = ast.literal_eval(node)
        return value if isinstance(value, int) else None
    except (ValueError, SyntaxError, TypeError):
        return None


def _call_name(node: ast.AST) -> Optional[str]:
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name):
            return node.func.id
        if isinstance(node.func, ast.Attribute):
            return node.func.attr
    return None


def _walk_no_nested(nodes) -> List[ast.AST]:
    """ast.walk over statements, but do not descend into nested functions/lambdas/classes."""
    out, stack = [], list(nodes)
    while stack:
        node = stack.pop()
        out.append(node)
        for child in ast.iter_child_nodes(node):
            if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
                stack.append(child)
    return out


def _has_exit(body: List[ast.stmt]) -> bool:
    """True if the loop body contains a `return`, or a `break` belonging to THIS loop."""
    def visit(stmts, in_inner_loop):
        for s in stmts:
            if isinstance(s, ast.Return):
                return True
            if isinstance(s, ast.Break) and not in_inner_loop:
                return True
            if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            inner = in_inner_loop or isinstance(s, (ast.For, ast.While, ast.AsyncFor))
            for fld in ("body", "orelse", "finalbody"):
                if visit(getattr(s, fld, []) or [], inner):
                    return True
            for h in getattr(s, "handlers", []) or []:
                if visit(h.body, inner):
                    return True
        return False
    return visit(body, False)


def _src(node: ast.AST, limit: int = 40) -> str:
    try:
        text = ast.unparse(node)
    except Exception:  # noqa: BLE001
        return "…"
    return text if len(text) <= limit else text[: limit - 1] + "…"


# ---------------------------------------------------------------------------------------------
class FunctionAnalyzer:
    def __init__(self, module: "ModuleAnalyzer", fdef: ast.FunctionDef):
        self.module = module
        self.fdef = fdef
        self.name = fdef.name
        args = fdef.args
        self.params = [a.arg for a in args.posonlyargs + args.args]
        self.seq_vars: Set[str] = self._infer_sequence_params()
        self.hash_vars: Set[str] = set()
        self.var_kind: Dict[str, str] = {}
        self.notes: List[Tuple[int, str]] = []
        self.confidence = 2
        self.rec_sites: List[Tuple[int, str]] = []
        self.rec_args: List[str] = []
        self.while_test_vars: List[Set[str]] = []   # stack: variables tested by enclosing while loops
        # parameters with a {} default are dict memo tables
        positional = args.posonlyargs + args.args
        for a, d in zip(reversed(positional), reversed(args.defaults)):
            if isinstance(d, (ast.Dict, ast.Set)) or _call_name(d) in HASH_CONSTRUCTORS:
                self.hash_vars.add(a.arg)
        self.memoized = self._detect_memo()

    # ---- helpers -----------------------------------------------------------------------
    def note(self, node: ast.AST, text: str) -> None:
        self.notes.append((getattr(node, "lineno", 0), text))

    def lower_confidence(self, to: int) -> None:
        self.confidence = min(self.confidence, to)

    def _infer_sequence_params(self) -> Set[str]:
        """A parameter is a sequence if it is used like one: len(p), p[i], `for x in p`, p.append."""
        params, seqs = set(self.params), set()
        for node in _walk_no_nested(self.fdef.body):
            if isinstance(node, ast.Call) and _call_name(node) == "len" and node.args \
                    and isinstance(node.args[0], ast.Name) and node.args[0].id in params:
                seqs.add(node.args[0].id)
            elif isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id in params:
                seqs.add(node.value.id)
            elif isinstance(node, (ast.For, ast.comprehension)) and isinstance(node.iter, ast.Name) \
                    and node.iter.id in params:
                seqs.add(node.iter.id)
            elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id in params \
                    and node.attr in {"append", "pop", "sort", "index", "count", "insert", "remove", "extend"}:
                seqs.add(node.value.id)
        return seqs

    def _detect_memo(self) -> bool:
        for dec in self.fdef.decorator_list:
            target = dec.func if isinstance(dec, ast.Call) else dec
            name = target.attr if isinstance(target, ast.Attribute) else getattr(target, "id", "")
            if name in {"lru_cache", "cache", "memoize"}:
                return True
        stored, checked = set(), set()
        for node in _walk_no_nested(self.fdef.body):
            if isinstance(node, (ast.Assign, ast.AugAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for t in targets:
                    if isinstance(t, ast.Subscript) and isinstance(t.value, ast.Name):
                        stored.add(t.value.id)
            if isinstance(node, ast.Compare) and any(isinstance(op, (ast.In, ast.NotIn)) for op in node.ops):
                for c in node.comparators:
                    if isinstance(c, ast.Name):
                        checked.add(c.id)
        return bool(stored & checked)

    def is_hash(self, e: ast.AST) -> bool:
        return (isinstance(e, ast.Name) and e.id in self.hash_vars) or isinstance(
            e, (ast.Set, ast.Dict, ast.SetComp, ast.DictComp)) or _call_name(e) in HASH_CONSTRUCTORS

    def is_listy(self, e: ast.AST) -> bool:
        if isinstance(e, ast.Name):
            return e.id in self.seq_vars
        if isinstance(e, (ast.ListComp,)):
            return True
        if isinstance(e, ast.List):
            return True
        if isinstance(e, ast.Subscript) and isinstance(e.slice, ast.Slice):
            return True
        if isinstance(e, ast.BinOp) and isinstance(e.op, (ast.Add, ast.Mult)):
            return self.is_listy(e.left) or self.is_listy(e.right)
        return _call_name(e) in LIST_CONSTRUCTORS

    # ---- loop iteration counts ----------------------------------------------------------
    def _range_iters(self, call: ast.Call) -> Tuple[Big, str]:
        if all(_is_const(a) for a in call.args):
            return ONE, "a constant number of"
        text = ast.unparse(call)
        if "** 0.5" in text or "sqrt" in text or "isqrt" in text:
            return SQRT, "about √n"
        return N, "about n"

    def for_iters(self, iter_node: ast.AST) -> Tuple[Big, str]:
        if isinstance(iter_node, ast.Call):
            name = _call_name(iter_node)
            if name == "range":
                return self._range_iters(iter_node)
            if name in {"enumerate", "reversed", "sorted", "list", "zip", "set", "tuple", "iter"} and iter_node.args:
                return self.for_iters(iter_node.args[0])
            if name in {"items", "keys", "values"}:
                return N, "about n"
        if isinstance(iter_node, (ast.List, ast.Tuple, ast.Set)) or (
                isinstance(iter_node, ast.Constant) and isinstance(iter_node.value, str)):
            return ONE, "a constant number of"
        return N, "about n"

    def while_iters(self, node: ast.While) -> Tuple[Big, str]:
        body_nodes = _walk_no_nested(node.body)
        test_names = {n.id for n in ast.walk(node.test) if isinstance(n, ast.Name)}
        # 1) x //= 2, x >>= 1, x *= 2, x = x // 2
        for n in body_nodes:
            if isinstance(n, ast.AugAssign) and isinstance(n.target, ast.Name):
                if isinstance(n.op, (ast.FloorDiv, ast.Div, ast.RShift)):
                    return LOG, f"about log n (variable '{n.target.id}' is divided each iteration)"
                if isinstance(n.op, (ast.Mult, ast.LShift)) and _is_const(n.value):
                    return LOG, f"about log n (variable '{n.target.id}' is multiplied each iteration)"
            if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name) \
                    and isinstance(n.value, ast.BinOp) and isinstance(n.value.op, (ast.FloorDiv, ast.Div, ast.RShift)):
                var = n.targets[0].id
                if var in {x.id for x in ast.walk(n.value.left) if isinstance(x, ast.Name)}:
                    return LOG, f"about log n (variable '{var}' is halved each iteration)"
        # 2) binary-search pattern: mid = (lo + hi) // 2 ; lo = mid + 1 / hi = mid - 1
        mids = set()
        for n in body_nodes:
            if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name) and any(
                    isinstance(b, ast.BinOp) and isinstance(b.op, (ast.FloorDiv, ast.RShift)) for b in ast.walk(n.value)):
                mids.add(n.targets[0].id)
        if mids:
            for n in body_nodes:
                if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name) and n.targets[0].id in test_names \
                        and mids & {x.id for x in ast.walk(n.value) if isinstance(x, ast.Name)}:
                    return LOG, "about log n (search interval halves around a midpoint)"
        # 3) i * i <= n  ->  sqrt(n)
        for b in ast.walk(node.test):
            if isinstance(b, ast.BinOp) and ((isinstance(b.op, ast.Mult) and ast.dump(b.left) == ast.dump(b.right))
                                             or (isinstance(b.op, ast.Pow) and _const_int(b.right) == 2)):
                return SQRT, "about √n (loop condition compares a square)"
        if isinstance(node.test, ast.Constant):
            self.lower_confidence(1)
            return N, "an unknown number of (assumed ~n)"
        return N, "about n (assumed: the loop variable moves by a constant step)"

    @staticmethod
    def _data_dependent(test: ast.AST) -> bool:
        """`while j >= 0 and arr[j] > key` - may stop immediately depending on the data."""
        reads_data = lambda v: isinstance(v, ast.Compare) and any(isinstance(x, ast.Subscript) for x in ast.walk(v))
        if isinstance(test, ast.BoolOp) and isinstance(test.op, ast.And):
            return any(reads_data(v) for v in test.values)
        return reads_data(test)

    @staticmethod
    def _stepped_vars(body: List[ast.stmt]) -> Set[str]:
        """Variables changed by a constant step (i += 1, j -= 1) directly in this loop body."""
        return {n.target.id for n in _walk_no_nested(body)
                if isinstance(n, ast.AugAssign) and isinstance(n.target, ast.Name)
                and isinstance(n.op, (ast.Add, ast.Sub)) and _is_const(n.value)}

    @staticmethod
    def _flag_loop(node: ast.While) -> bool:
        """`while swapped:` where the body sets the flag to True/False (bubble sort with a flag)."""
        test = node.test.operand if isinstance(node.test, ast.UnaryOp) and isinstance(node.test.op, ast.Not) else node.test
        if not isinstance(test, ast.Name):
            return False
        return any(isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == test.id for t in n.targets)
                   and isinstance(n.value, ast.Constant) and isinstance(n.value.value, bool)
                   for n in _walk_no_nested(node.body))

    # ---- statements ---------------------------------------------------------------------
    def block(self, stmts: List[ast.stmt]) -> Res:
        res = Res()
        for i, s in enumerate(stmts):
            # `if c: ... return` followed by more code: the rest is effectively the else-branch,
            # so only ONE of the two paths runs (important when counting recursive calls).
            if isinstance(s, ast.If) and s.body and isinstance(s.body[-1], (ast.Return, ast.Raise)) \
                    and i + 1 < len(stmts):
                branch = self.block(s.body).either(self.block(list(s.orelse) + list(stmts[i + 1:])))
                return res.then(self.expr(s.test)).then(branch)
            res = res.then(self.stmt(s))
        return res

    def stmt(self, s: ast.stmt) -> Res:
        if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Import, ast.ImportFrom)):
            return Res()
        if isinstance(s, ast.For):
            return self.loop(s, *self.for_iters(s.iter), header=self.expr(s.iter), early=_has_exit(s.body),
                             kind="for")
        if isinstance(s, ast.While):
            iters, why = self.while_iters(s)
            early = _has_exit(s.body) or self._data_dependent(s.test) or self._flag_loop(s)
            if self._flag_loop(s):
                why += "; it is controlled by a flag, so in the best case it stops after one pass"
            # Two-pointer amortisation: an inner while loop that only moves a pointer which the
            # enclosing while loop also tests (Hoare partition, two pointers) cannot run more than
            # n times in total, so it costs O(1) amortised per outer iteration.
            stepped = self._stepped_vars(s.body)
            if iters.same_as(N) and any(stepped & outer for outer in self.while_test_vars):
                iters, why = ONE, ("O(1) amortised (it moves a pointer that the enclosing while loop also "
                                   "tests, so all its iterations together are at most n)")
            self.while_test_vars.append({n.id for n in ast.walk(s.test) if isinstance(n, ast.Name)})
            try:
                return self.loop(s, iters, why, header=self.expr(s.test), early=early, kind="while")
            finally:
                self.while_test_vars.pop()
        if isinstance(s, ast.If):
            branch = self.block(s.body).either(self.block(s.orelse) if s.orelse else Res())
            return self.expr(s.test).then(branch)
        if isinstance(s, ast.Return):
            return self.expr(s.value)
        if isinstance(s, (ast.Assign, ast.AnnAssign)):
            value = s.value
            targets = s.targets if isinstance(s, ast.Assign) else [s.target]
            res = self.expr(value) if value is not None else Res()
            for t in targets:
                if isinstance(t, ast.Subscript):
                    res = res.then(self.expr(t.slice))
                    if isinstance(t.value, ast.Name) and t.value.id in self.hash_vars:
                        res = res.then(Res(growth=C_ONE))   # d[key] = value adds an entry
            if value is not None:
                self.track_assign(targets, value)
            return res
        if isinstance(s, ast.AugAssign):
            res = self.expr(s.value)
            if isinstance(s.target, ast.Name) and s.target.id in self.seq_vars and isinstance(s.op, ast.Add):
                if isinstance(s.value, ast.List) and len(s.value.elts) <= 3:
                    res = res.then(Res(growth=C_ONE))
                else:
                    res = res.then(Res(time=Cost.of(N), growth=Cost.of(N)))
            return res
        if isinstance(s, ast.Expr):
            return self.expr(s.value)
        if isinstance(s, ast.Try):
            res = self.block(s.body)
            for h in s.handlers:
                res = res.either(self.block(h.body))
            return res.then(self.block(s.orelse)).then(self.block(s.finalbody))
        if isinstance(s, ast.With):
            return self.block(s.body)
        return Res()

    def loop(self, s, iters: Big, why: str, header: Res, early: bool, kind: str) -> Res:
        body = self.block(s.body).then(self.block(getattr(s, "orelse", []) or []))
        best_iters = ONE if early else iters
        it = Cost(best_iters, iters, iters)
        res = Res(time=(it * body.time).max(header.time),
                  fixed=body.fixed.max(header.fixed),
                  growth=(it * body.growth).max(header.growth),
                  rec=body.rec, rec_in_loop=body.rec_in_loop)
        if body.rec:
            if iters.same_as(ONE):
                count = 2
                if isinstance(s, ast.For) and _call_name(s.iter) == "range":
                    count = max(1, _const_int(s.iter.args[-1] if len(s.iter.args) == 1 else s.iter.args[1]) or 2)
                res.rec = body.rec * count
            else:
                res.rec_in_loop = True
        text = f"`{kind}` loop runs {why} iterations"
        if early:
            text += "; it can exit early (return/break or data-dependent condition), so the best case may stop almost immediately"
        self.note(s, text + f" → contributes {(iters * body.time.worst).label()} in the worst case.")
        return res

    # ---- assignments: remember what variables hold ---------------------------------------
    def track_assign(self, targets: List[ast.AST], value: ast.AST) -> None:
        names: List[str] = []
        for t in targets:
            if isinstance(t, ast.Name):
                names.append(t.id)
            elif isinstance(t, (ast.Tuple, ast.List)):
                if isinstance(value, (ast.Tuple, ast.List)) and len(value.elts) == len(t.elts):
                    for sub_t, sub_v in zip(t.elts, value.elts):
                        self.track_assign([sub_t], sub_v)
                    continue
                names.extend(e.id for e in t.elts if isinstance(e, ast.Name))
        if not names:
            return
        kind = None
        if (isinstance(value, ast.ListComp) and any(g.ifs for g in value.generators)) or _call_name(value) == "filter":
            kind = "partition"
        elif isinstance(value, ast.Call) and isinstance(value.func, ast.Name) \
                and value.func.id in self.module.functions and value.func.id != self.name:
            kind = "partition"
        elif any(isinstance(b, ast.BinOp) and isinstance(b.op, (ast.FloorDiv, ast.Div, ast.RShift))
                 for b in ast.walk(value)):
            kind = "half"
        else:
            refs = {self.var_kind.get(x.id) for x in ast.walk(value) if isinstance(x, ast.Name)}
            kind = "half" if "half" in refs else "partition" if "partition" in refs else None
        for name in names:
            if kind:
                self.var_kind[name] = kind
            else:
                self.var_kind.pop(name, None)
            if self.is_hash(value):
                self.hash_vars.add(name)
                self.seq_vars.discard(name)
            elif self.is_listy(value):
                self.seq_vars.add(name)
                self.hash_vars.discard(name)

    # ---- expressions --------------------------------------------------------------------
    def expr(self, node: Optional[ast.AST]) -> Res:
        if node is None:
            return Res()
        if isinstance(node, ast.Call):
            return self.call(node)
        if isinstance(node, COMPREHENSIONS):
            return self.comprehension(node)
        if isinstance(node, ast.Lambda):
            return Res()
        res = Res()
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.expr):
                res = res.then(self.expr(child))
        return res.then(self.own_cost(node))

    def own_cost(self, node: ast.AST) -> Res:
        if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Slice):
            sl = node.slice
            if sl.lower is not None and sl.upper is not None and _is_const(sl.lower) and _is_const(sl.upper):
                return Res()
            self.note(node, f"slice `{_src(node)}` copies up to n elements → O(n) time and extra space.")
            return Res(time=Cost.of(N), fixed=Cost.of(N))
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult):
            for lst, other in ((node.left, node.right), (node.right, node.left)):
                if isinstance(lst, (ast.List, ast.ListComp)) and not _is_const(other):
                    self.note(node, f"`{_src(node)}` builds a list of size n → O(n) time and space.")
                    return Res(time=Cost.of(N), fixed=Cost.of(N))
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add) \
                and (self.is_listy(node.left) or self.is_listy(node.right)):
            self.note(node, f"list concatenation `{_src(node)}` creates a new list → O(n).")
            return Res(time=Cost.of(N), fixed=Cost.of(N))
        if isinstance(node, ast.Compare) and any(isinstance(op, (ast.In, ast.NotIn)) for op in node.ops):
            for comp in node.comparators:
                if self.is_hash(comp):
                    self.note(node, f"`{_src(node)}` is a hash-table lookup → O(1) on average.")
                elif self.is_listy(comp) and not (isinstance(comp, (ast.List, ast.Tuple)) and len(comp.elts) < 8):
                    self.note(node, f"`{_src(node)}` scans a list → O(n).")
                    return Res(time=Cost.of(N))
        return Res()

    def comprehension(self, node) -> Res:
        factor = ONE
        once = Res()        # the first iterable is evaluated once (e.g. `arr[1:]`, `sorted(arr)`)
        per_item = Res()    # conditions, nested iterables and the element run for every item
        for k, gen in enumerate(node.generators):
            iters, _ = self.for_iters(gen.iter)
            if k == 0:
                once = once.then(self.expr(gen.iter))
            else:
                per_item = per_item.then(self.expr(gen.iter))
            for cond in gen.ifs:
                per_item = per_item.then(self.expr(cond))
            factor = factor * iters
        elts = [node.key, node.value] if isinstance(node, ast.DictComp) else [node.elt]
        for e in elts:
            per_item = per_item.then(self.expr(e))
        f = Cost.of(factor)
        time = (f * per_item.time).max(once.time)
        fixed = per_item.fixed if isinstance(node, ast.GeneratorExp) else f * per_item.fixed.at_least_one()
        return Res(time=time, fixed=fixed.max(once.fixed), rec=per_item.rec,
                   rec_in_loop=bool(per_item.rec) and not factor.same_as(ONE))

    def call(self, node: ast.Call) -> Res:
        res = Res()
        for a in node.args:
            res = res.then(self.expr(a))
        for kw in node.keywords:
            res = res.then(self.expr(kw.value))
        func = node.func
        has_arg = bool(node.args) and not all(_is_const(a) for a in node.args)

        if isinstance(func, ast.Name):
            name = func.id
            if name == self.name:                                       # recursion
                kind = self.reduction(node)
                self.rec_sites.append((node.lineno, kind))
                self.rec_args.append(next((ast.unparse(a) for a in node.args if not _is_const(a)
                                           and not (isinstance(a, ast.Name) and a.id not in self.params)), "…"))
                return res.then(Res(rec=1))
            if name in self.module.functions:                          # helper function
                callee = self.module.analyze_function(name)
                if callee is not None:
                    self.note(node, f"calls helper `{name}()` which costs {callee.time.worst.label()} time, "
                                    f"{callee.space.worst.label()} space (worst case).")
                    self.lower_confidence(callee.confidence)
                    return res.then(Res(time=callee.time, fixed=callee.space))
            return res.then(self.library_call(node, name, has_arg))

        if isinstance(func, ast.Attribute):
            obj, attr = func.value, func.attr
            res = res.then(self.expr(obj))
            if isinstance(obj, ast.Name) and obj.id in LIBRARY_MODULES:
                return res.then(self.library_call(node, attr, has_arg))
            return res.then(self.method_call(node, obj, attr))
        return res

    def library_call(self, node: ast.Call, name: str, has_arg: bool) -> Res:
        if name == "sorted":
            self.note(node, "`sorted()` (Timsort) costs O(n log n) time and O(n) extra space.")
            return Res(time=Cost(N, NLOGN, NLOGN), fixed=Cost.of(N))
        if name in LIST_CONSTRUCTORS | HASH_CONSTRUCTORS:
            if has_arg:
                self.note(node, f"`{name}(...)` copies its input → O(n) time and space.")
                return Res(time=Cost.of(N), fixed=Cost.of(N))
            return Res()
        if name in LINEAR_REDUCERS and len(node.args) == 1 and has_arg:
            self.note(node, f"`{name}()` over a collection scans every element → O(n).")
            return Res(time=Cost.of(N))
        if name in {"heappush", "heappop", "heappushpop", "heapreplace"}:
            self.note(node, f"`{name}` on a binary heap → O(log n).")
            return Res(time=Cost.of(LOG), growth=C_ONE if name == "heappush" else C_ZERO)
        if name == "heapify":
            return Res(time=Cost.of(N))
        if name in {"bisect", "bisect_left", "bisect_right"}:
            self.note(node, f"`{name}` is a binary search → O(log n).")
            return Res(time=Cost.of(LOG))
        if name in {"insort", "insort_left", "insort_right"}:
            return Res(time=Cost.of(N), growth=C_ONE)
        if name in {"nlargest", "nsmallest"}:
            return Res(time=Cost.of(NLOGN), fixed=Cost.of(N))
        return Res()

    def method_call(self, node: ast.Call, obj: ast.AST, attr: str) -> Res:
        if attr == "sort":
            self.note(node, "`.sort()` (Timsort) costs O(n log n) time (O(n) on already-sorted data) "
                            "and up to O(n) temporary space.")
            return Res(time=Cost(N, NLOGN, NLOGN), fixed=Cost.of(N))
        if attr in {"append", "add", "appendleft", "setdefault"}:
            return Res(growth=C_ONE)
        if attr == "pop":
            if node.args and not (isinstance(node.args[0], ast.UnaryOp)):
                self.note(node, f"`{_src(node)}` shifts the remaining elements → O(n).")
                return Res(time=Cost.of(N))
            return Res()
        if attr == "insert":
            self.note(node, f"`{_src(node)}` shifts elements → O(n).")
            return Res(time=Cost.of(N), growth=C_ONE)
        if attr in {"remove", "index", "count"}:
            self.note(node, f"`.{attr}()` scans the list → O(n).")
            return Res(time=Cost.of(N))
        if attr == "extend":
            return Res(time=Cost.of(N), growth=Cost.of(N))
        if attr in {"copy", "join", "split"}:
            return Res(time=Cost.of(N), fixed=Cost.of(N))
        if attr in {"reverse", "update"}:
            return Res(time=Cost.of(N))
        return Res()

    # ---- recursion ----------------------------------------------------------------------
    def reduction(self, call: ast.Call) -> str:
        """How much smaller is the input of this recursive call? half / partition / sub / unknown."""
        kinds = set()
        for arg in list(call.args) + [k.value for k in call.keywords]:
            for sub in ast.walk(arg):
                if isinstance(sub, ast.BinOp) and isinstance(sub.op, (ast.FloorDiv, ast.Div, ast.RShift)):
                    kinds.add("half")
                elif isinstance(sub, ast.Name) and sub.id in self.var_kind:
                    kinds.add(self.var_kind[sub.id])
                elif isinstance(sub, ast.ListComp) and any(g.ifs for g in sub.generators) \
                        or _call_name(sub) == "filter":
                    kinds.add("partition")      # e.g. solve([x for x in arr if x < pivot]) - quicksort
                elif isinstance(sub, ast.Slice):
                    kinds.add("sub")
                elif isinstance(sub, ast.BinOp) and isinstance(sub.op, (ast.Sub, ast.Add)):
                    names = [x.id for x in (sub.left, sub.right) if isinstance(x, ast.Name)]
                    if any(_is_const(x) for x in (sub.left, sub.right)) and names:
                        kinds.add("sub" if names[0] in self.params else "unknown")
                elif isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name) \
                        and sub.func.id in self.module.functions and sub.func.id != self.name:
                    kinds.add("partition")
        for k in ("half", "partition", "sub", "unknown"):
            if k in kinds:
                return k
        return "unknown"

    def _data_dependent_return(self) -> bool:
        """e.g. `if arr[mid] == target: return mid` - the recursion can stop early for lucky inputs."""
        for node in _walk_no_nested(self.fdef.body):
            if isinstance(node, ast.If) and any(isinstance(x, ast.Subscript) for x in ast.walk(node.test)):
                for s in node.body:
                    if isinstance(s, ast.Return) and not any(
                            isinstance(c, ast.Call) and _call_name(c) == self.name for c in ast.walk(s)):
                        return True
        return False

    @staticmethod
    def master(a: int, f: Big) -> Big:
        """T(n) = a·T(n/2) + f(n) with f(n) = n^k log^j n  (Master theorem, b = 2)."""
        crit = math.log2(a) if a > 0 else 0.0
        f = f.at_least_one()
        if f.exp:
            return f
        if abs(f.poly - crit) < 1e-9:
            return Big(f.poly, f.log + 1)
        if f.poly > crit:
            return f
        return Big(round(crit, 2), 0)

    def run(self) -> FunctionReport:
        res = self.block(self.fdef.body)
        f_time = res.time
        f_space = res.fixed.max(res.growth)
        time, space, recurrence = f_time, f_space, None
        a = res.rec

        if a > 0 or res.rec_in_loop:
            kinds = {k for _, k in self.rec_sites}
            if kinds == {"half"}:
                kind = "half"
            elif kinds & {"partition", "unknown"} and a >= 2:
                kind = "partition"
            elif "sub" in kinds or "unknown" in kinds:
                kind = "sub"
            elif "half" in kinds:
                kind = "half"
            else:
                kind = "partition"
            line = self.rec_sites[0][0] if self.rec_sites else self.fdef.lineno
            fw = f_time.worst.at_least_one().label()
            s1 = f_space.at_least_one()

            if self.memoized:
                time = Cost.of(N) * f_time.at_least_one()
                space = Cost.of(N).max(f_space)
                recurrence = f"memoised: ≈ n distinct sub-problems × {fw} each"
                self.notes.append((line, f"`{self.name}()` is recursive but memoised (cache/memo table): each "
                                         f"sub-problem is solved once → about n sub-problems × {fw}."))
                self.lower_confidence(1)
            elif res.rec_in_loop:
                time = Cost.of(EXP)
                space = Cost.of(N) * s1
                recurrence = "recursive call inside a loop (branching grows with n)"
                self.notes.append((line, f"`{self.name}()` calls itself inside a loop → branching factor grows "
                                         "with n (backtracking/brute force) → at least exponential time."))
                self.lower_confidence(0)
            elif kind == "half":
                time = Cost(self.master(a, f_time.best), self.master(a, f_time.avg), self.master(a, f_time.worst))
                if self._data_dependent_return():
                    time = Cost(f_time.best.at_least_one(), time.avg, time.worst)
                space = f_space.max(Cost.of(LOG))
                recurrence = f"T(n) = {a if a > 1 else ''}T(n/2) + {fw}"
                self.notes.append((line, f"`{self.name}()` makes {a} recursive call(s) per invocation on a halved "
                                         f"input: {recurrence} → {time.worst.label()} by the Master theorem. "
                                         "Recursion depth is O(log n)."))
            elif kind == "partition":
                balanced = self.master(a, f_time.avg)
                worst = N * f_time.worst.at_least_one()
                time = Cost(self.master(a, f_time.best), balanced, worst)
                space = Cost(bmax(f_space.best, LOG),
                             bmax(f_space.avg, LOG), N * s1.worst)
                recurrence = f"balanced: T(n) = {a}T(n/2) + {fw};  unbalanced: T(n) = T(n-1) + {fw}"
                self.notes.append((line, f"`{self.name}()` splits its input around a pivot/partition point into {a} "
                                         f"parts. Balanced splits give {balanced.label()} (best/average); a split "
                                         f"that removes only one element each time gives {worst.label()} (worst). "
                                         "Recursion depth: O(log n) balanced, O(n) worst."))
                self.lower_confidence(1)
            else:  # "sub"
                if a == 1:
                    time = Cost.of(N) * f_time.at_least_one()
                    if self._data_dependent_return():
                        time = Cost(f_time.best.at_least_one(), time.avg, time.worst)
                    recurrence = f"T(n) = T(n-1) + {fw}"
                    self.notes.append((line, f"`{self.name}()` calls itself once on an input one step smaller: "
                                             f"{recurrence} → {time.worst.label()}. Recursion depth is O(n)."))
                else:
                    time = Cost.of(EXP)
                    terms = list(dict.fromkeys(self.rec_args))[:a]
                    recurrence = "T(n) = " + " + ".join(f"T({t})" for t in terms) + f" + {fw}"
                    self.notes.append((line, f"`{self.name}()` calls itself {a} times on inputs only a constant "
                                             "smaller → the recursion tree grows exponentially (≈ O(2ⁿ); "
                                             "Fibonacci-style recursion is Θ(φⁿ) ≈ Θ(1.618ⁿ))."))
                space = Cost.of(N) * s1
                if "unknown" in kinds:
                    self.lower_confidence(0)
        return FunctionReport(self.name, time.at_least_one(), space, self.notes, self.confidence, recurrence)


# ---------------------------------------------------------------------------------------------
class ModuleAnalyzer:
    def __init__(self, tree: ast.Module):
        self.functions: Dict[str, ast.FunctionDef] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name not in self.functions:
                self.functions[node.name] = node
        self.reports: Dict[str, FunctionReport] = {}
        self.in_progress: Set[str] = set()
        self.order: List[str] = []

    def analyze_function(self, name: str) -> Optional[FunctionReport]:
        if name in self.reports:
            return self.reports[name]
        if name in self.in_progress:   # mutual recursion - give up gracefully
            return FunctionReport(name, C_ONE, C_ZERO,
                                  [(self.functions[name].lineno, f"mutual recursion involving `{name}()` "
                                                                 "is not analysed")], 0)
        self.in_progress.add(name)
        report = FunctionAnalyzer(self, self.functions[name]).run()
        self.in_progress.discard(name)
        self.reports[name] = report
        self.order.append(name)
        return report


def analyze_complexity(code: str, entry: str = "solve") -> Dict:
    """Public entry point. Returns a JSON-friendly dict."""
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return {"ok": False, "error": f"Syntax error: {exc}"}
    module = ModuleAnalyzer(tree)
    if entry not in module.functions:
        return {"ok": False, "error": f"No function '{entry}'"}
    report = module.analyze_function(entry)

    observations, confidence = [], report.confidence
    for fname in module.order:
        r = module.reports[fname]
        confidence = min(confidence, r.confidence)
        seen = set()
        for line, text in sorted(r.notes, key=lambda x: x[0]):
            if (line, text) in seen:
                continue
            seen.add((line, text))
            observations.append({"line": line, "function": fname, "text": text})

    space = Cost(report.space.best.at_least_one(), report.space.avg.at_least_one(), report.space.worst.at_least_one())
    summary = []
    if not report.time.best.same_as(report.time.worst):
        summary.append(f"Best case {report.time.best.label()} differs from worst case {report.time.worst.label()}: "
                       "the running time depends on the input's shape, not just its size.")
    else:
        summary.append(f"Best, average and worst case are all {report.time.worst.label()}: the running time "
                       "depends mainly on the input size.")
    if space.worst.same_as(ONE):
        summary.append("Uses only O(1) auxiliary memory (in-place / constant extra variables).")
    else:
        summary.append(f"Needs {space.worst.label()} auxiliary memory in the worst case.")

    return {
        "ok": True,
        "time": report.time.to_dict(),
        "space": space.to_dict(),
        "recurrence": next((f"{f}(): {module.reports[f].recurrence}" for f in module.order
                            if module.reports[f].recurrence), None),
        "confidence": CONFIDENCE_LEVELS[confidence],
        "observations": observations,
        "summary": summary,
        "functions_analysed": module.order,
        "method": "Static analysis of the abstract syntax tree (heuristic; the code is not executed).",
    }
