"""A formula as something that can be worked out: read it, solve it, and write it for a sheet, a page, or Python.

An expression is a tree of tuples:

    ("num", 2.0)            ("sym", r"\\sigma")        ("const", "pi")
    ("add", a, b)  ("sub", a, b)  ("mul", a, b)  ("div", a, b)  ("pow", a, b)
    ("neg", a)              ("call", "sqrt", a)

A symbol is known by its TeX as written, the same key the ledger uses. Only
real, closed-form formulas are read: one that needs a derivative, an integral,
a sum, a vector product, or a bra-ket is refused, never guessed at.

``from_tex`` reads TeX. ``from_text`` reads what a person or a model types,
such as ``f = exp(-(x-mu)**2/(2*sigma**2))``. Neither one runs any code.
"""

from __future__ import annotations

import ast as pyast
import keyword
import math
import re

from eqlens.engine import FormulaError

__all__ = [
    "Unreadable",
    "from_tex",
    "from_text",
    "isolate",
    "slug",
    "symbols_in",
    "to_excel",
    "to_js",
    "to_python",
    "to_tex",
    "to_text",
    "value",
]


class Unreadable(FormulaError):
    """The formula cannot be worked out as it is written."""


# name: (arity is always 1) how it is worked out
_FUNCS = {
    "sqrt": math.sqrt,
    "exp": math.exp,
    "ln": math.log,
    "log10": math.log10,
    "log2": math.log2,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "asin": math.asin,
    "acos": math.acos,
    "atan": math.atan,
    "sinh": math.sinh,
    "cosh": math.cosh,
    "tanh": math.tanh,
    "abs": abs,
}
_TEX_FUNCS = {
    "exp": "exp", "ln": "ln", "log": "log10", "lg": "log10", "sin": "sin", "cos": "cos", "tan": "tan",
    "arcsin": "asin", "arccos": "acos", "arctan": "atan", "sinh": "sinh", "cosh": "cosh", "tanh": "tanh",
}
_ACCENTS = {"hat", "widehat", "bar", "overline", "tilde", "widetilde", "vec", "dot", "ddot", "mathbf", "boldsymbol"}
_NAMES = {"mathrm", "text", "mathit", "mathsf", "operatorname", "mathcal", "mathbb", "mathtt"}
_LETTERS = {
    "alpha", "beta", "gamma", "delta", "epsilon", "varepsilon", "zeta", "eta", "theta", "vartheta", "iota",
    "kappa", "lambda", "mu", "nu", "xi", "varpi", "rho", "varrho", "sigma", "varsigma", "tau", "upsilon",
    "phi", "varphi", "chi", "psi", "omega", "Gamma", "Delta", "Theta", "Lambda", "Xi", "Pi", "Sigma",
    "Upsilon", "Phi", "Psi", "Omega", "hbar", "ell",
}
_SPACES = {",", ";", ":", "!", " ", "quad", "qquad", "displaystyle", "textstyle", "left", "right", "big", "Big",
           "bigl", "bigr", "Bigl", "Bigr", "limits", "nolimits"}
# What each of these would need, so the refusal can say it.
_BEYOND = {
    "partial": "a derivative", "nabla": "a derivative", "int": "an integral", "oint": "an integral",
    "iint": "an integral", "iiint": "an integral", "sum": "a sum", "prod": "a product over an index",
    "lim": "a limit", "langle": "a bra-ket", "rangle": "a bra-ket", "geq": "an inequality", "leq": "an inequality",
    "ge": "an inequality", "le": "an inequality", "neq": "an inequality", "approx": "an approximation",
    "sim": "a distribution", "propto": "a proportion", "to": "a limit", "infty": "infinity", "top": "a matrix",
    "dagger": "a matrix", "otimes": "a tensor product", "oplus": "a direct sum", "pm": "two answers at once",
    "mp": "two answers at once", "in": "a set", "max": "a maximum", "min": "a minimum", "det": "a matrix",
    "odot": "a product of arrays", "circ": "a composition", "mid": "a conditional",
}
_MARKS = {"star": r"\star", "ast": r"\ast", "prime": r"\prime", "*": "*"}

_TOKEN = re.compile(r"\s*(?:(\d+(?:\.\d+)?|\.\d+)|\\([A-Za-z]+)|\\(.)|(.))", re.S)


def slug(key: str) -> str:
    """A plain name for a symbol, safe in a cell formula, in JavaScript, and in Python: ``\\bar{\\alpha}_t`` is ``alpha_bar_t``."""
    text = key
    for accent in _ACCENTS:
        short = {"widehat": "hat", "widetilde": "tilde", "overline": "bar", "mathbf": "", "boldsymbol": ""}.get(accent, accent)
        text = re.sub(r"\\" + accent + r"\s*\{([^{}]*)\}", (r"\1_" + short) if short else r"\1", text)
    text = re.sub(r"\\(?:" + "|".join(_NAMES) + r")\s*\{([^{}]*)\}", r"\1", text)
    text = text.replace(r"\star", "_star").replace(r"\ast", "_star").replace(r"\prime", "_prime").replace("'", "_prime")
    text = text.replace("*", "_star").replace("^", "_")
    text = re.sub(r"\\([A-Za-z]+)", r"_\1_", text)
    text = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")
    text = re.sub(r"_+", "_", text) or "s"
    if text[0].isdigit():
        text = "s_" + text
    return text


# ---------------------------------------------------------------- reading TeX


class _Tex:
    def __init__(self, tex: str, args: tuple[str, ...] = ()):
        self.src = tex
        self.args = set(args)
        self.toks: list[tuple[str, str]] = []
        for match in _TOKEN.finditer(tex):
            number, command, escaped, char = match.groups()
            if number:
                self.toks.append(("num", number))
            elif command:
                if command in _SPACES:
                    continue
                self.toks.append(("cmd", command))
            elif escaped:
                if escaped in _SPACES:
                    continue
                self.toks.append(("chr", "|" if escaped == "|" else "\\" + escaped))
            elif char and not char.isspace():
                self.toks.append(("chr", char))
        self.at = 0
        self.bars = 0

    def peek(self, ahead: int = 0) -> tuple[str, str]:
        index = self.at + ahead
        return self.toks[index] if index < len(self.toks) else ("end", "")

    def take(self) -> tuple[str, str]:
        tok = self.peek()
        self.at += 1
        return tok

    def want(self, char: str) -> None:
        if self.peek() != ("chr", char):
            raise Unreadable(f"the formula is missing a {char}")
        self.at += 1

    def is_chr(self, char: str, ahead: int = 0) -> bool:
        return self.peek(ahead) == ("chr", char)

    # expr := term (('+'|'-') term)*
    def expr(self):
        node = self.term()
        while self.is_chr("+") or self.is_chr("-"):
            op = self.take()[1]
            node = ("add" if op == "+" else "sub", node, self.term())
        return node

    def starts_factor(self) -> bool:
        kind, text = self.peek()
        if kind == "num":
            return True
        if kind == "cmd":
            return text not in ("cdot", "times", "div") and text not in _BEYOND
        if kind == "chr":
            if text == "|":
                return self.bars == 0
            return text.isalpha() or text in "({[" or text == "\\{"
        return False

    # term := unary (('*'|'/'|nothing) unary)*, where a/bc is a over bc, as it is in print.
    def term(self):
        node = self.unary()
        while True:
            kind, text = self.peek()
            if (kind, text) in (("cmd", "cdot"), ("cmd", "times"), ("chr", "*")):
                self.take()
                node = ("mul", node, self.unary())
            elif (kind, text) in (("chr", "/"), ("cmd", "div")):
                self.take()
                node = ("div", node, self.run())
            elif self.starts_factor():
                node = ("mul", node, self.power())
            else:
                return node

    def run(self):
        """Factors written side by side with nothing between them: what a slash divides by."""
        node = self.unary()
        while self.starts_factor():
            node = ("mul", node, self.power())
        return node

    def unary(self):
        if self.is_chr("-"):
            self.take()
            return ("neg", self.unary())
        if self.is_chr("+"):
            self.take()
            return self.unary()
        return self.power()

    def power(self):
        node = self.atom()
        while self.is_chr("^"):
            self.take()
            if self.peek() == ("chr", "T") or (self.is_chr("{") and self.peek(1) == ("chr", "T") and self.is_chr("}", 2)):
                raise Unreadable("the formula needs a matrix (^T reads as a transpose)")
            exponent = self.arg()
            node = ("call", "exp", exponent) if node == ("const", "e") else ("pow", node, exponent)
        return node

    def arg(self):
        """What follows ^ or _: a braced group, or one thing."""
        if self.is_chr("{"):
            self.take()
            node = self.expr()
            self.want("}")
            return node
        if self.is_chr("-"):
            self.take()
            return ("neg", self.arg())
        kind, text = self.peek()
        if kind == "num" and len(text) > 1 and "." not in text:
            # x^23 is x cubed... no: TeX takes one digit, and the rest multiplies.
            self.toks[self.at : self.at + 1] = [("num", text[0]), ("num", text[1:])]
        return self.atom(bare=True)

    def raw_arg(self) -> str:
        """The TeX of what follows _ exactly as written."""
        if self.is_chr("{"):
            depth, parts = 0, []
            while True:
                kind, text = self.take()
                if kind == "end":
                    raise Unreadable("the formula is missing a }")
                parts.append(_show(kind, text))
                if (kind, text) == ("chr", "{"):
                    depth += 1
                elif (kind, text) == ("chr", "}"):
                    depth -= 1
                    if depth == 0:
                        return _join(parts)
        kind, text = self.take()
        if kind == "end":
            raise Unreadable("the formula ends at a _")
        return _show(kind, text)

    def group(self, close: str):
        node = self.expr()
        self.want(close)
        return node

    def atom(self, bare: bool = False):
        kind, text = self.take()
        if kind == "num":
            return ("num", float(text))
        if kind == "chr":
            if text == "(":
                return self.group(")")
            if text == "[":
                return self.group("]")
            if text == "{":
                return self.group("}")
            if text == "\\{":
                return self.group("\\}")
            if text == "|":
                self.bars += 1
                node = self.expr()
                self.want("|")
                self.bars -= 1
                return ("call", "abs", node)
            if text.isalpha():
                if text == "e" and self.is_chr("^"):
                    return ("const", "e")
                return self.symbol(text, bare)
            if text == ",":
                raise Unreadable("there is more than one formula here, or a list")
            if text == "=":
                raise Unreadable("the formula has more than one equals sign")
            if text == "!":
                raise Unreadable("the formula needs a factorial")
            raise Unreadable(f"cannot work out the {text} in this formula")
        if kind == "cmd":
            if text in _BEYOND:
                raise Unreadable(f"the formula needs {_BEYOND[text]} (\\{text})")
            if text == "pi":
                return ("const", "pi")
            if text in ("frac", "dfrac", "tfrac"):
                return self.frac()
            if text == "sqrt":
                return self.sqrt()
            if text in _TEX_FUNCS:
                return self.func(text)
            if text in _LETTERS:
                return self.symbol("\\" + text, bare)
            if text in _ACCENTS or text in _NAMES:
                return self.symbol(self.wrapped(text), bare)
            raise Unreadable(f"cannot work out \\{text}")
        raise Unreadable("the formula stops short")

    def wrapped(self, command: str) -> str:
        """An accent or a font and what it covers, as written: ``\\hat{x}``."""
        if not self.is_chr("{"):
            kind, text = self.take()
            if kind == "end":
                raise Unreadable(f"\\{command} covers nothing")
            return f"\\{command}{{{_show(kind, text)}}}"
        inside = self.raw_arg()
        if command in ("mathrm", "text", "operatorname") and inside in ("{e}", "{d}"):
            return inside[1:-1] if inside == "{e}" else self.refuse_d()
        return f"\\{command}{inside}"

    def refuse_d(self):
        raise Unreadable("the formula needs a derivative or an integral (d)")

    def symbol(self, base: str, bare: bool = False):
        if base == "\\Delta" and not bare:
            kind, text = self.peek()
            if (kind == "chr" and text.isalpha()) or (kind == "cmd" and text in _LETTERS):
                self.take()
                base = "\\Delta " + _show(kind, text)
        key = base
        if bare:
            return ("sym", key)
        sub = sup = False
        while True:
            if self.is_chr("_") and not sub:
                self.take()
                key += "_" + self.raw_arg()
                sub = True
            elif self.is_chr("'") and not sup:
                self.take()
                key += "'"
                sup = True
            elif self.is_chr("^") and not sup:
                mark = self.mark_after_caret()
                if mark is None:
                    break
                key += "^" + mark
                sup = True
            else:
                break
        name = base.startswith(("\\mathrm{", "\\text{", "\\operatorname{")) and len(base.split("{", 1)[1]) > 2
        if self.is_chr("("):
            inner, at = [], 1
            while self.peek(at)[0] != "end" and self.peek(at) != ("chr", ")"):
                inner.append(self.peek(at))
                at += 1
            names = {_show(kind, text) for kind, text in inner if (kind, text) != ("chr", ",")}
            if name or (self.args and names and names <= self.args):
                raise Unreadable(f"{key} is a function this formula uses and does not define")
        return ("sym", key)

    def mark_after_caret(self) -> str | None:
        """``^\\star`` and ``^*`` name a symbol; any other ``^`` is a power."""
        kind, text = self.peek(1)
        if (kind, text) == ("chr", "{") and self.peek(3) == ("chr", "}"):
            kind, text = self.peek(2)
            if text in _MARKS and (kind == "cmd" or text == "*"):
                self.at += 4
                return _MARKS[text]
            return None
        if text in _MARKS and (kind == "cmd" or text == "*"):
            self.at += 2
            return _MARKS[text]
        return None

    def frac(self):
        if self.is_chr("{") and self.peek(1) == ("chr", "d") and self.peek(2)[1] != "}":
            self.refuse_d()
        if self.is_chr("{") and self.peek(1) == ("chr", "d"):
            # \frac{d}{dt}
            depth, at = 0, 0
            while True:
                tok = self.peek(at)
                if tok == ("chr", "{"):
                    depth += 1
                elif tok == ("chr", "}"):
                    depth -= 1
                    if depth == 0:
                        break
                at += 1
            if self.peek(at + 1) == ("chr", "{") and self.peek(at + 2) == ("chr", "d"):
                self.refuse_d()
        self.want("{")
        top = self.group("}")
        self.want("{")
        bottom = self.group("}")
        return ("div", top, bottom)

    def sqrt(self):
        if self.is_chr("["):
            self.take()
            degree = self.group("]")
            self.want("{")
            inside = self.group("}")
            return ("pow", inside, ("div", ("num", 1.0), degree))
        if self.is_chr("{"):
            self.take()
            return ("call", "sqrt", self.group("}"))
        return ("call", "sqrt", self.atom(bare=True))

    def func(self, name: str):
        fn = _TEX_FUNCS[name]
        base = None
        if name == "log" and self.is_chr("_"):
            self.take()
            base = self.arg()
        elif name == "log":
            raise Unreadable("\\log could be base 10 or the natural log: write \\ln or \\log_{10}")
        power = None
        if self.is_chr("^"):
            self.take()
            power = self.arg()
            if power == ("neg", ("num", 1.0)):
                raise Unreadable(f"\\{name}^{{-1}} could be an inverse or a reciprocal: write which")
        if self.peek() in (("chr", "("), ("chr", "["), ("chr", "{")):
            inside = self.atom()
        else:
            inside = self.run_plain()
        node = ("call", fn, inside)
        if base is not None:
            node = ("div", ("call", "ln", inside), ("call", "ln", base))
        return ("pow", node, power) if power is not None else node

    def run_plain(self):
        """What a function with no brackets takes: the factors up to the next sign."""
        if not self.starts_factor():
            raise Unreadable("a function in the formula is given nothing")
        node = self.power()
        while self.starts_factor() and self.peek()[0] != "cmd" or (
            self.peek()[0] == "cmd" and (self.peek()[1] in _LETTERS or self.peek()[1] == "pi")
        ):
            node = ("mul", node, self.power())
        return node


def _show(kind: str, text: str) -> str:
    return "\\" + text if kind == "cmd" else text


def _join(parts: list[str]) -> str:
    """Tokens back into TeX: a command needs a space before a letter."""
    out = ""
    for part in parts:
        if out and re.search(r"\\[A-Za-z]+$", out) and part[:1].isalpha():
            out += " "
        out += part
    return out


def _split(tex: str) -> list[str]:
    """The sides of the formula: cut at each ``=`` that is not inside braces."""
    sides, depth, start = [], 0, 0
    i = 0
    while i < len(tex):
        char = tex[i]
        if char == "\\":
            i += 2
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        elif char == "=" and depth == 0:
            sides.append(tex[start:i])
            start = i + 1
        i += 1
    sides.append(tex[start:])
    return sides


def _head(tex: str) -> tuple[str, tuple[str, ...]] | None:
    """``f(x)`` or ``B_\\nu(T)`` or ``E_k`` on the left: its symbol and what it is a function of."""
    reader = _Tex(tex)
    kind, text = reader.peek()
    if kind == "num" or (kind == "cmd" and text not in _LETTERS | _ACCENTS | _NAMES) or (kind == "chr" and not text.isalpha()):
        return None
    try:
        node = reader.atom()
    except Unreadable:
        return None
    if node[0] != "sym":
        return None
    if reader.peek()[0] == "end":
        return node[1], ()
    if not reader.is_chr("("):
        return None
    reader.take()
    args: list[str] = []
    while True:
        try:
            arg = reader.atom()
        except Unreadable:
            return None
        if arg[0] != "sym":
            return None
        args.append(arg[1])
        if reader.is_chr(","):
            reader.take()
            continue
        break
    if not reader.is_chr(")"):
        return None
    reader.take()
    return (node[1], tuple(args)) if reader.peek()[0] == "end" else None


def from_tex(tex: str, solve: str | None = None) -> tuple[str | None, tuple[str, ...], tuple]:
    """Read a formula. Return what it gives (a symbol, or None), what that is a function of, and the expression.

    ``y = ...`` gives ``y``. ``f(x) = ...`` gives ``f``, a function of ``x``.
    With no equals sign there is nothing on the left and the result has no
    symbol. When neither side is one symbol, as in ``PV=nRT``, the formula is
    solved for ``solve``, or for the first symbol on the left that can be got
    alone. ``solve`` also turns a formula round: ``\\lambda=h/p`` for ``p``.
    """
    text = tex.strip().strip("$").strip()
    sides = _split(text)
    if len(sides) > 2:
        raise Unreadable("the formula has more than one equals sign")
    if len(sides) == 1:
        if solve:
            raise Unreadable("there is no equals sign, so nothing to solve")
        return None, (), _parse(sides[0])
    left, right = sides
    head = _head(left)
    if head and not solve:
        return head[0], head[1], _parse(right, head[1])
    back = _head(right)
    if back and not head and not solve:
        return back[0], back[1], _parse(left, back[1])
    lhs = ("sym", head[0]) if head else _parse(left)
    rhs = _parse(right, head[1] if head else ())
    if solve:
        target = _match(solve, symbols_in(("sub", lhs, rhs)))
        return target, (), isolate(lhs, rhs, target)
    for key in symbols_in(lhs) + symbols_in(rhs):
        try:
            return key, (), isolate(lhs, rhs, key)
        except Unreadable:
            continue
    raise Unreadable("neither side is one symbol: say which symbol to solve for")


def _parse(tex: str, args: tuple[str, ...] = ()) -> tuple:
    reader = _Tex(tex, args)
    if reader.peek()[0] == "end":
        raise Unreadable("one side of the formula is empty")
    node = reader.expr()
    kind, text = reader.peek()
    if kind != "end":
        if (kind, text) == ("chr", ","):
            raise Unreadable("there is more than one formula here, or a list")
        if kind == "cmd" and text in _BEYOND:
            raise Unreadable(f"the formula needs {_BEYOND[text]} (\\{text})")
        raise Unreadable(f"cannot work out the {_show(kind, text)} in this formula")
    return node


def _match(name: str, keys: list[str]) -> str:
    """The symbol a caller means by ``name``: its TeX, or its plain name."""
    want = name.strip().strip("$").strip()
    for key in keys:
        if key == want or key.replace(" ", "") == want.replace(" ", ""):
            return key
    for key in keys:
        if slug(key) == want or slug(key) == slug(want):
            return key
    raise Unreadable(f"{name} is not a symbol in this formula. It has: " + ", ".join(slug(key) for key in keys))


# ------------------------------------------------------------------ solving


def _count(node: tuple, key: str) -> int:
    if node[0] == "sym":
        return int(node[1] == key)
    if node[0] in ("num", "const"):
        return 0
    return sum(_count(child, key) for child in node[1:] if isinstance(child, tuple))


def isolate(lhs: tuple, rhs: tuple, key: str) -> tuple:
    """Solve ``lhs = rhs`` for ``key``, which must appear once. Roots and logs take the principal value."""
    left, right = _count(lhs, key), _count(rhs, key)
    if left + right == 0:
        raise Unreadable(f"{slug(key)} is not in the formula")
    if left + right > 1:
        raise Unreadable(f"{slug(key)} appears more than once, so it cannot be got alone by undoing one step at a time")
    side, other = (lhs, rhs) if left else (rhs, lhs)
    while side != ("sym", key):
        kind = side[0]
        if kind == "neg":
            side, other = side[1], ("neg", other)
            continue
        if kind == "call":
            name, inner = side[1], side[2]
            undo = {
                "sqrt": lambda o: ("pow", o, ("num", 2.0)),
                "exp": lambda o: ("call", "ln", o),
                "ln": lambda o: ("call", "exp", o),
                "log10": lambda o: ("pow", ("num", 10.0), o),
                "log2": lambda o: ("pow", ("num", 2.0), o),
                "sin": lambda o: ("call", "asin", o),
                "cos": lambda o: ("call", "acos", o),
                "tan": lambda o: ("call", "atan", o),
                "asin": lambda o: ("call", "sin", o),
                "acos": lambda o: ("call", "cos", o),
                "atan": lambda o: ("call", "tan", o),
            }.get(name)
            if undo is None:
                raise Unreadable(f"cannot undo {name} to get {slug(key)} alone")
            side, other = inner, undo(other)
            continue
        a, b = side[1], side[2]
        in_a = bool(_count(a, key))
        if kind == "add":
            side, other = (a, ("sub", other, b)) if in_a else (b, ("sub", other, a))
        elif kind == "sub":
            side, other = (a, ("add", other, b)) if in_a else (b, ("sub", a, other))
        elif kind == "mul":
            side, other = (a, ("div", other, b)) if in_a else (b, ("div", other, a))
        elif kind == "div":
            side, other = (a, ("mul", other, b)) if in_a else (b, ("div", a, other))
        elif kind == "pow":
            if in_a:
                side, other = a, (("call", "sqrt", other) if b == ("num", 2.0) else ("pow", other, ("div", ("num", 1.0), b)))
            else:
                side, other = b, ("div", ("call", "ln", other), ("call", "ln", a))
        else:
            raise Unreadable(f"cannot get {slug(key)} alone")
    return other


# ----------------------------------------------------------- reading plain text


def from_text(text: str, names: dict[str, str]) -> tuple[str | None, tuple]:
    """Read ``out = expression`` or a bare expression, in the plain form ``to_text`` writes.

    ``names`` maps each plain name to its symbol. ``**`` and ``^`` are both
    powers. Nothing here is run: the text is parsed, and anything that is not
    arithmetic, a known function, a number, or a known name is refused.
    """
    source = (text or "").strip()
    if not source:
        raise Unreadable("the expression is empty")
    out = None
    match = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=(?!=)(.*)$", source, re.S)
    if match:
        out, source = match.group(1), match.group(2).strip()
    # Python words that are also symbol names: lambda, in, is.
    source = source.replace("^", "**")
    source = re.sub(r"\b(" + "|".join(keyword.kwlist) + r")\b(?!_)", r"\1_", source)
    try:
        tree = pyast.parse(source, mode="eval")
    except SyntaxError as exc:
        raise Unreadable(f"cannot read the expression: {exc.msg}") from exc
    known = dict(names)
    for plain, key in names.items():
        if keyword.iskeyword(plain):
            known[plain + "_"] = key

    def walk(node) -> tuple:
        if isinstance(node, pyast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return ("num", float(node.value))
        if isinstance(node, pyast.Name):
            if node.id in known:
                return ("sym", known[node.id])
            if node.id == "pi":
                return ("const", "pi")
            if node.id in ("e", "E"):
                return ("const", "e")
            raise Unreadable(f"{node.id} is not a symbol in this formula. It has: " + ", ".join(sorted(names)))
        if isinstance(node, pyast.UnaryOp) and isinstance(node.op, (pyast.USub, pyast.UAdd)):
            inner = walk(node.operand)
            return ("neg", inner) if isinstance(node.op, pyast.USub) else inner
        if isinstance(node, pyast.BinOp):
            kind = {pyast.Add: "add", pyast.Sub: "sub", pyast.Mult: "mul", pyast.Div: "div", pyast.Pow: "pow"}.get(type(node.op))
            if kind:
                return (kind, walk(node.left), walk(node.right))
        if isinstance(node, pyast.Call) and isinstance(node.func, pyast.Name) and not node.keywords:
            name = {"log": "ln", "arcsin": "asin", "arccos": "acos", "arctan": "atan", "fabs": "abs"}.get(node.func.id, node.func.id)
            if name in _FUNCS and len(node.args) == 1:
                return ("call", name, walk(node.args[0]))
            if name == "ln" and len(node.args) == 2:
                return ("div", ("call", "ln", walk(node.args[0])), ("call", "ln", walk(node.args[1])))
            if name == "pow" and len(node.args) == 2:
                return ("pow", walk(node.args[0]), walk(node.args[1]))
            raise Unreadable(f"{node.func.id} is not a function the bench knows. It knows: " + ", ".join(_FUNCS))
        raise Unreadable("the expression may hold only numbers, symbols, + - * / **, and functions such as sqrt and exp")

    return out, walk(tree.body)


# ---------------------------------------------------------------- working out


def symbols_in(node: tuple) -> list[str]:
    """The symbols in an expression, each once, in the order they are met."""
    found: list[str] = []

    def walk(part: tuple) -> None:
        if part[0] == "sym":
            if part[1] not in found:
                found.append(part[1])
        elif part[0] not in ("num", "const"):
            for child in part[1:]:
                if isinstance(child, tuple):
                    walk(child)

    walk(node)
    return found


def value(node: tuple, env: dict[str, float]) -> float:
    """Work the expression out with ``env`` giving each symbol a number. ``nan`` where it has no real value."""
    try:
        result = _value(node, env)
    except (ZeroDivisionError, ValueError, OverflowError, TypeError):
        return math.nan
    if isinstance(result, complex) or math.isinf(result):
        return math.nan
    return float(result)


def _value(node: tuple, env: dict[str, float]):
    kind = node[0]
    if kind == "num":
        return node[1]
    if kind == "sym":
        return env[node[1]]
    if kind == "const":
        return math.pi if node[1] == "pi" else math.e
    if kind == "neg":
        return -_value(node[1], env)
    if kind == "call":
        return _FUNCS[node[1]](_value(node[2], env))
    a, b = _value(node[1], env), _value(node[2], env)
    if kind == "add":
        return a + b
    if kind == "sub":
        return a - b
    if kind == "mul":
        return a * b
    if kind == "div":
        return a / b
    result = a**b
    if isinstance(result, complex):
        raise ValueError("no real value")
    return result


# -------------------------------------------------------------------- writing

_RANK = {"add": 1, "sub": 1, "mul": 2, "div": 2, "neg": 3, "pow": 4}
_SIGN = {"add": "+", "sub": "-", "mul": "*", "div": "/"}


def _number(x: float) -> str:
    if x == int(x) and abs(x) < 1e15:
        return str(int(x))
    return repr(x)


def _infix(node: tuple, name, func, const, power) -> str:
    """Write with every power and every minus sign bracketed, so no dialect can read it another way."""

    def atom(part: tuple) -> str:
        text = walk(part)
        return text if part[0] in ("sym", "const", "call") or (part[0] == "num" and part[1] >= 0) else f"({text})"

    def walk(part: tuple) -> str:
        kind = part[0]
        if kind == "num":
            return _number(part[1])
        if kind == "sym":
            return name(part[1])
        if kind == "const":
            return const(part[1])
        if kind == "call":
            return func(part[1], walk(part[2]))
        if kind == "neg":
            return "-" + atom(part[1])
        if kind == "pow":
            return power(atom(part[1]), atom(part[2]))
        a, b = part[1], part[2]
        left = walk(a) if _RANK.get(a[0], 9) >= _RANK[kind] and a[0] != "neg" else atom(a)
        right = walk(b) if _RANK.get(b[0], 9) > _RANK[kind] and b[0] != "neg" else atom(b)
        return f"{left}{_SIGN[kind]}{right}"

    return walk(node)


def to_text(node: tuple, name=slug) -> str:
    """The plain form: ``1/(sigma*sqrt(2*pi))*exp(-((x-mu)**2)/(2*sigma**2))``. ``from_text`` reads it back."""
    return _infix(node, name, lambda fn, arg: f"{fn}({arg})", lambda c: c, lambda a, b: f"{a}**{b}")


def to_python(node: tuple, name=slug) -> str:
    """Python source that needs ``import math``."""
    funcs = {"ln": "math.log", "abs": "abs"}
    safe = lambda key: name(key) + ("_" if keyword.iskeyword(name(key)) else "")  # noqa: E731
    return _infix(
        node,
        safe,
        lambda fn, arg: f"{funcs.get(fn, 'math.' + fn)}({arg})",
        lambda c: f"math.{c}",
        lambda a, b: f"{a}**{b}",
    )


def to_js(node: tuple, name=slug) -> str:
    """A JavaScript expression."""
    funcs = {"ln": "Math.log", "log10": "Math.log10", "log2": "Math.log2"}
    return _infix(
        node,
        name,
        lambda fn, arg: f"{funcs.get(fn, 'Math.' + fn)}({arg})",
        lambda c: "Math.PI" if c == "pi" else "Math.E",
        lambda a, b: f"Math.pow({a},{b})",
    )


def to_excel(node: tuple, name) -> str:
    """A cell formula, without the leading ``=``. ``name`` gives each symbol its cell or its defined name."""
    funcs = {"ln": "LN", "log10": "LOG10", "log2": "LOG", "asin": "ASIN", "acos": "ACOS", "atan": "ATAN"}

    def func(fn: str, arg: str) -> str:
        if fn == "log2":
            return f"LOG({arg},2)"
        return f"{funcs.get(fn, fn.upper())}({arg})"

    return _infix(node, name, func, lambda c: "PI()" if c == "pi" else "EXP(1)", lambda a, b: f"{a}^{b}")


_TEX_NAMES = {"ln": r"\ln", "exp": r"\exp", "sin": r"\sin", "cos": r"\cos", "tan": r"\tan", "asin": r"\arcsin",
              "acos": r"\arccos", "atan": r"\arctan", "sinh": r"\sinh", "cosh": r"\cosh", "tanh": r"\tanh",
              "log10": r"\log_{10}", "log2": r"\log_{2}"}


def to_tex(node: tuple) -> str:
    """The expression set as TeX again, so a reader can see what is being worked out."""

    def paren(part: tuple, rank: int) -> str:
        text = walk(part)
        return rf"\left({text}\right)" if _RANK.get(part[0], 9) < rank else text

    def walk(part: tuple) -> str:
        kind = part[0]
        if kind == "num":
            return _number(part[1])
        if kind == "sym":
            return part[1]
        if kind == "const":
            return r"\pi" if part[1] == "pi" else "e"
        if kind == "call":
            if part[1] == "sqrt":
                return rf"\sqrt{{{walk(part[2])}}}"
            if part[1] == "abs":
                return rf"\left|{walk(part[2])}\right|"
            return rf"{_TEX_NAMES[part[1]]}\left({walk(part[2])}\right)"
        if kind == "neg":
            return "-" + paren(part[1], 2)
        if kind == "pow":
            base = part[1]
            inner = walk(base)
            if base[0] not in ("sym", "const") and base[1:2] != ("abs",) and not (base[0] == "num" and base[1] >= 0):
                inner = rf"\left({inner}\right)"
            elif base[0] == "sym" and ("^" in base[1] or "'" in base[1]):
                inner = rf"\left({inner}\right)"
            return rf"{inner}^{{{walk(part[2])}}}"
        if kind == "div":
            return rf"\frac{{{walk(part[1])}}}{{{walk(part[2])}}}"
        if kind == "mul":
            left, right = paren(part[1], 2), paren(part[2], 2)
            if part[2][0] == "neg":
                right = rf"\left({right}\right)"
            first = part[2]
            while first[0] in ("mul", "pow"):
                first = first[1]
            gap = r"\cdot " if first[0] == "num" else r"\,"
            return f"{left}{gap}{right}"
        left = walk(part[1])
        right = paren(part[2], 2 if kind == "sub" else 1)
        if part[2][0] == "neg":
            right = rf"\left({right}\right)"
        return f"{left}{'+' if kind == 'add' else '-'}{right}"

    return walk(node)
