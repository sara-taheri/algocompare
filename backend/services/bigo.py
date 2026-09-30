"""
A tiny symbolic Big-O algebra.

Every growth rate we care about in an Algorithm Design course can be written as

        n^k · (log n)^j          (polynomial × polylog)       or        c^n  (exponential)

so a complexity class is just the triple (poly=k, log=j, exp=True/False).

Two rules are enough to combine costs of code fragments:
  * sequential code  ->  max(cost1, cost2)       (the larger term dominates)
  * nested code      ->  cost1 * cost2           (exponents add)

ZERO is a special "nothing at all" value (used for "no memory growth"); it is absorbing under
multiplication and neutral under max.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

_SUPERSCRIPT = str.maketrans("0123456789.", "⁰¹²³⁴⁵⁶⁷⁸⁹·")


@dataclass(frozen=True)
class Big:
    poly: float = 0.0
    log: int = 0
    exp: bool = False
    zero: bool = False

    # ---- ordering -----------------------------------------------------------------------
    def key(self):
        if self.zero:
            return (-1, 0, 0)
        return (1 if self.exp else 0, round(self.poly, 3), self.log)

    def __lt__(self, other: "Big") -> bool:
        return self.key() < other.key()

    def __le__(self, other: "Big") -> bool:
        return self.key() <= other.key()

    def same_as(self, other: "Big") -> bool:
        return self.key() == other.key()

    # ---- algebra ------------------------------------------------------------------------
    def __mul__(self, other: "Big") -> "Big":
        if self.zero or other.zero:
            return ZERO
        return Big(self.poly + other.poly, self.log + other.log, self.exp or other.exp)

    def at_least_one(self) -> "Big":
        return ONE if self.zero else self

    # ---- presentation -------------------------------------------------------------------
    def label(self) -> str:
        if self.zero:
            return "O(1)"
        if self.exp:
            return "O(2ⁿ)"
        parts = []
        p = round(self.poly, 2)
        if p == 0.5:
            parts.append("√n")
        elif p == 1:
            parts.append("n")
        elif p > 0:
            txt = str(int(p)) if float(p).is_integer() else f"{p:g}"
            parts.append("n" + txt.translate(_SUPERSCRIPT))
        if self.log == 1:
            parts.append("log n")
        elif self.log > 1:
            parts.append("log" + str(self.log).translate(_SUPERSCRIPT) + " n")
        return "O(" + (" ".join(parts) if parts else "1") + ")"

    def evaluate(self, n: float) -> float:
        """Numeric value of the growth function (used to draw theoretical curves)."""
        if self.zero:
            return 1.0
        if self.exp:
            return 2.0 ** min(n, 1000)
        return (n ** self.poly) * (max(math.log2(max(n, 2)), 1.0) ** self.log)

    def to_dict(self) -> dict:
        return {"label": self.label(), "key": list(self.key())}

    def __str__(self) -> str:
        return self.label()


ZERO = Big(zero=True)
ONE = Big()
LOG = Big(0, 1)
SQRT = Big(0.5)
N = Big(1)
NLOGN = Big(1, 1)
N2 = Big(2)
EXP = Big(0, 0, True)


def bmax(*items: Big) -> Big:
    result = ZERO
    for item in items:
        if result < item:
            result = item
    return result


def compare(a: Big, b: Big) -> str:
    """'A' if a grows strictly slower (better), 'B' if b is better, '=' if the same class."""
    if a.same_as(b):
        return "="
    return "A" if a < b else "B"


@dataclass(frozen=True)
class Cost:
    """Best / average / worst case, each a Big-O class."""
    best: Big
    avg: Big
    worst: Big

    @staticmethod
    def of(b: Big) -> "Cost":
        return Cost(b, b, b)

    def __mul__(self, other: "Cost") -> "Cost":
        return Cost(self.best * other.best, self.avg * other.avg, self.worst * other.worst)

    def max(self, other: "Cost") -> "Cost":
        return Cost(bmax(self.best, other.best), bmax(self.avg, other.avg), bmax(self.worst, other.worst))

    def at_least_one(self) -> "Cost":
        return Cost(self.best.at_least_one(), self.avg.at_least_one(), self.worst.at_least_one())

    def to_dict(self) -> dict:
        return {"best": self.best.to_dict(), "average": self.avg.to_dict(), "worst": self.worst.to_dict()}


C_ZERO = Cost.of(ZERO)
C_ONE = Cost.of(ONE)
