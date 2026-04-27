"""JARVIS Expert: Mathematics (symbolic + numeric reasoning)."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any


@dataclass
class MathematicsQuery:
    query: str
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class MathematicsResult:
    answer: str
    confidence: float
    domain: str
    sources: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


_KEYWORDS = (
    "solve", "equation", "integral", "derivative", "limit", "matrix",
    "vector", "proof", "theorem", "lemma", "polynomial", "factor",
    "expand", "simplify", "differentiate", "integrate", "calculate",
    "compute", "math", "algebra", "calculus", "geometry", "trigonometry",
    "probability", "statistics", "logarithm", "exponent",
)


class MathematicsExpert:
    """JARVIS expert for mathematical reasoning."""

    DOMAIN = "mathematics"
    VERSION = "1.0.0"

    def analyze(self, query: str, context: dict[str, Any] | None = None) -> MathematicsResult:
        confidence = self.can_handle(query)
        sources: list[str] = []
        meta: dict[str, Any] = {}
        parts: list[str] = []

        # Try linear equation
        sol = self.solve_linear(query)
        if sol is not None:
            meta["solution"] = sol
            parts.append(f"Linear equation solution: x = {sol}.")
            sources.append("symbolic-solver")

        # Try arithmetic eval
        if sol is None:
            arith = self.evaluate_arithmetic(query)
            if arith is not None:
                meta["arithmetic"] = arith
                parts.append(f"Arithmetic result: {arith}.")
                sources.append("arithmetic-evaluator")

        # Try quadratic
        quad = self.solve_quadratic(query)
        if quad is not None:
            meta["quadratic_roots"] = quad
            parts.append(f"Quadratic roots: {quad}.")
            sources.append("quadratic-formula")

        # Derivative pattern
        deriv = self.derivative(query)
        if deriv:
            meta["derivative"] = deriv
            parts.append(f"Derivative: {deriv}.")
            sources.append("symbolic-differentiation")

        # LaTeX detection
        latex = self.parse_latex(query)
        if latex:
            meta["latex"] = latex
            sources.append("latex-parser")

        if not parts:
            parts.append("Mathematics query received. No solver pattern matched. "
                         "Try forms like '2x + 3 = 7', '3 + 4 * 5', 'd/dx x^2'.")
            confidence = min(confidence, 0.3)

        return MathematicsResult(
            answer=" ".join(parts),
            confidence=confidence,
            domain=self.DOMAIN,
            sources=sources,
            metadata=meta,
        )

    def can_handle(self, query: str) -> float:
        q = query.lower()
        hits = sum(1 for kw in _KEYWORDS if kw in q)
        # Equation-like: digit op digit, or 'x =', or '=' between expressions
        if re.search(r"\d\s*[\+\-\*/\^]\s*\d", query) or re.search(r"\bx\b\s*=", query):
            hits += 2
        elif "=" in query and re.search(r"\d", query):
            hits += 1
        # Formula tokens like 'd/dx' or '\\int' boost confidence
        if re.search(r"d\s*/\s*dx", query, re.IGNORECASE) or re.search(r"\\(int|sum|frac)", query):
            hits += 2
        if hits == 0:
            return 0.0
        return min(1.0, 0.25 + 0.15 * hits)

    def solve_linear(self, query: str) -> Fraction | None:
        # match a*x + b = c style
        m = re.search(r"(-?\d+(?:\.\d+)?)\s*\*?\s*x\s*([+\-]\s*-?\d+(?:\.\d+)?)?\s*=\s*(-?\d+(?:\.\d+)?)", query)
        if not m:
            return None
        try:
            a = Fraction(m.group(1))
            b = Fraction(m.group(2).replace(" ", "")) if m.group(2) else Fraction(0)
            c = Fraction(m.group(3))
            if a == 0:
                return None
            return (c - b) / a
        except Exception:
            return None

    def evaluate_arithmetic(self, query: str) -> float | None:
        m = re.search(r"([\d\.\s\+\-\*/\(\)]+)$", query.strip())
        candidate = m.group(1).strip() if m else query.strip()
        if not re.fullmatch(r"[\d\.\s\+\-\*/\(\)]+", candidate):
            return None
        if not any(op in candidate for op in "+-*/"):
            return None
        try:
            # safe-ish: only digits and ops
            result = eval(candidate, {"__builtins__": {}}, {})
            if isinstance(result, (int, float)):
                return float(result)
        except Exception:
            return None
        return None

    def solve_quadratic(self, query: str) -> list[float] | None:
        # ax^2 + bx + c = 0
        m = re.search(
            r"(-?\d+(?:\.\d+)?)\s*\*?\s*x\s*\^?\s*2\s*([+\-]\s*\d+(?:\.\d+)?)\s*\*?\s*x\s*([+\-]\s*\d+(?:\.\d+)?)\s*=\s*0",
            query,
        )
        if not m:
            return None
        try:
            a = float(m.group(1))
            b = float(m.group(2).replace(" ", ""))
            c = float(m.group(3).replace(" ", ""))
        except Exception:
            return None
        disc = b * b - 4 * a * c
        if disc < 0:
            return []
        sq = math.sqrt(disc)
        return [(-b + sq) / (2 * a), (-b - sq) / (2 * a)]

    def derivative(self, query: str) -> str | None:
        # d/dx x^n -> n*x^(n-1); d/dx c -> 0; d/dx c*x -> c
        m = re.search(r"d\s*/\s*dx\s+(.+)", query)
        if not m:
            return None
        expr = m.group(1).strip()
        # x^n
        mp = re.fullmatch(r"x\s*\^\s*(-?\d+)", expr)
        if mp:
            n = int(mp.group(1))
            if n == 0:
                return "0"
            return f"{n}*x^{n - 1}"
        # c*x^n
        mp = re.fullmatch(r"(-?\d+)\s*\*?\s*x\s*\^\s*(-?\d+)", expr)
        if mp:
            c = int(mp.group(1)); n = int(mp.group(2))
            return f"{c * n}*x^{n - 1}"
        # c*x
        mp = re.fullmatch(r"(-?\d+)\s*\*?\s*x", expr)
        if mp:
            return mp.group(1)
        # x
        if expr == "x":
            return "1"
        # constant
        if re.fullmatch(r"-?\d+", expr):
            return "0"
        return None

    def integrate_polynomial(self, coefficients: list[float]) -> list[float]:
        """Integrate polynomial given by coefficients [a0, a1, ...] for a0 + a1*x + ..."""
        out: list[float] = [0.0]
        for i, c in enumerate(coefficients):
            out.append(c / (i + 1))
        return out

    def parse_latex(self, query: str) -> str | None:
        m = re.search(r"\$([^$]+)\$", query)
        if m:
            return m.group(1)
        m = re.search(r"\\\(([^)]+)\\\)", query)
        if m:
            return m.group(1)
        return None

    def factor_integer(self, n: int) -> list[int]:
        if n < 2:
            return []
        factors: list[int] = []
        d = 2
        while d * d <= n:
            while n % d == 0:
                factors.append(d)
                n //= d
            d += 1
        if n > 1:
            factors.append(n)
        return factors

    def gcd(self, a: int, b: int) -> int:
        return math.gcd(a, b)

    def lcm(self, a: int, b: int) -> int:
        if a == 0 or b == 0:
            return 0
        return abs(a * b) // math.gcd(a, b)

    def is_prime(self, n: int) -> bool:
        if n < 2:
            return False
        if n < 4:
            return True
        if n % 2 == 0:
            return False
        for d in range(3, int(math.isqrt(n)) + 1, 2):
            if n % d == 0:
                return False
        return True

    def matrix_determinant_2x2(self, m: list[list[float]]) -> float:
        return m[0][0] * m[1][1] - m[0][1] * m[1][0]

    def status(self) -> dict[str, Any]:
        return {
            "domain": self.DOMAIN,
            "version": self.VERSION,
            "ok": True,
            "capabilities": ["linear", "quadratic", "arithmetic", "derivative",
                             "factorization", "gcd/lcm", "prime", "latex"],
        }


_singleton: MathematicsExpert | None = None


def get_expert() -> MathematicsExpert:
    global _singleton
    if _singleton is None:
        _singleton = MathematicsExpert()
    return _singleton
