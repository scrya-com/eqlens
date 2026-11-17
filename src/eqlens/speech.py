"""Read a whole formula aloud, the way people say it.

``\\frac{a}{b}`` is "a over b", ``\\|x\\|_1`` is "the L1 norm of x", ``x^2`` is
"x squared", ``\\sum_{i=1}^{n}`` is "the sum from i equals 1 to n of". Brackets
stay in the text, so "(1 minus M) elementwise times (v hat l minus v l)" keeps
its grouping on the page; a voice reads past them. A part of a fraction or a
root that is more than one term gets brackets of its own for the same reason.

``read(tex)`` puts a line break after each top-level relation, around each
top-level plus and minus, and before a top-level "over", so a long formula reads
in phrases. ``say(tex)`` is the same words on one line, for a voice or an
``aria`` label.
"""

from __future__ import annotations

import re

from eqlens.legend import _ACCENTS, _BY_COMMAND, _NAMED, _POWERS

__all__ = ["read", "say"]

_BREAK = "\n"
_RELATIONS = {
    "=": "equals", "<": "is less than", ">": "is greater than", "leq": "is less than or equal to",
    "le": "is less than or equal to", "geq": "is greater than or equal to", "ge": "is greater than or equal to",
    "neq": "is not equal to", "ne": "is not equal to", "approx": "is approximately", "sim": "is distributed as",
    "simeq": "is approximately", "equiv": "is equivalent to", "propto": "is proportional to",
    "coloneqq": "is defined as", "triangleq": "is defined as", "ll": "is much less than", "gg": "is much greater than",
    "to": "goes to", "rightarrow": "goes to", "mapsto": "maps to", "Rightarrow": "implies", "implies": "implies",
    "iff": "if and only if", "Leftrightarrow": "if and only if",
}
_INFIX = {
    "+": "plus", "-": "minus", "pm": "plus or minus", "mp": "minus or plus", "times": "times", "cdot": "times",
    "odot": "elementwise times", "otimes": "tensor", "oplus": "direct sum", "circ": "composed with",
    "ast": "convolved with", "/": "over", "div": "divided by", "in": "in", "notin": "not in", "subset": "a subset of",
    "subseteq": "a subset of", "cup": "union", "cap": "intersection", "setminus": "minus", "wedge": "and",
    "vee": "or", "land": "and", "lor": "or", "mid": "given",
}
_SYMBOLS = {
    "infty": "infinity", "partial": "partial", "nabla": "del", "hbar": "h bar", "ell": "ell", "emptyset": "the empty set",
    "forall": "for all", "exists": "there exists", "neg": "not", "prime": "prime", "dagger": "dagger", "star": "star",
    "top": "transpose", "intercal": "transpose", "cdots": "dot dot dot", "ldots": "dot dot dot", "dots": "dot dot dot",
    "uparrow": "up arrow", "downarrow": "down arrow", "leftarrow": "left arrow", "degree": "degrees", "%": "percent",
    "!": "factorial", "Re": "the real part of", "Im": "the imaginary part of",
}
_FUNCTIONS = {
    "exp": "exp", "log": "log", "ln": "natural log", "sin": "sine", "cos": "cosine", "tan": "tangent",
    "sinh": "hyperbolic sine", "cosh": "hyperbolic cosine", "tanh": "tanh", "arcsin": "arcsine", "arccos": "arccosine",
    "arctan": "arctangent", "det": "the determinant", "tr": "the trace", "Tr": "the trace", "dim": "the dimension",
    "ker": "the kernel", "deg": "the degree", "arg": "the argument", "sgn": "the sign", "Pr": "the probability",
    "gcd": "the gcd",
}
# Big operators: the spoken name, and the word before a lower limit.
_BIG = {
    "sum": ("the sum", "from"), "prod": ("the product", "from"), "coprod": ("the coproduct", "from"),
    "int": ("the integral", "from"), "iint": ("the double integral", "over"), "iiint": ("the triple integral", "over"),
    "oint": ("the closed integral", "over"), "bigcup": ("the union", "over"), "bigcap": ("the intersection", "over"),
    "bigoplus": ("the direct sum", "over"), "bigotimes": ("the tensor product", "over"),
    "lim": ("the limit", "as"), "max": ("the max", "over"), "min": ("the min", "over"), "sup": ("the supremum", "over"),
    "inf": ("the infimum", "over"), "argmax": ("the arg max", "over"), "argmin": ("the arg min", "over"),
    "limsup": ("the lim sup", "as"), "liminf": ("the lim inf", "as"),
}
_EXPECT = ("the expectation", "over")
_FONTS = {"mathrm", "text", "mathit", "mathsf", "mathbf", "mathtt", "operatorname", "textrm", "textit", "textbf",
          "boldsymbol", "bm", "mathnormal"}
_SIZING = {"left", "right", "big", "Big", "bigg", "Bigg", "bigl", "bigr", "Bigl", "Bigr", "biggl", "biggr",
           "displaystyle", "textstyle", "scriptstyle", "limits", "nolimits", "!", ",", ":", ";", " ", "mathstrut"}
_PAUSE = {"quad", "qquad"}
_OPEN = {"(": ")", "[": "]", "\\{": "\\}", "\\lfloor": "\\rfloor", "\\lceil": "\\rceil"}
_CLOSERS = {")", "]", "}", "\\}", "\\rangle", "\\rfloor", "\\rceil"}
_NORM = {"\\|", "\\Vert", "\\lVert", "\\rVert"}
_BAR = {"|", "\\vert", "\\lvert", "\\rvert", "\\mid"}
# Letters that are usually a function when a bracket follows them: f(x) is "f of x".
_FUNCTION_LETTERS = set("fghpqFGHPQ") | {"psi", "Psi", "phi", "varphi", "Phi", "sigma"}
# A one-letter superscript that is a label and not a power: v^l is "v l", the layer, not "v to the l".
_LABEL_LETTERS = set("lhLHcfsuo")
# Subscripts said without "sub": M_\uparrow is "M up arrow".
_SUB_PLAIN = {r"\uparrow", r"\downarrow", r"\star", r"\ast", "*", r"\prime"}
_FRACTIONS = {("1", "2"): "one half", ("1", "3"): "one third", ("2", "3"): "two thirds", ("1", "4"): "one quarter",
              ("3", "4"): "three quarters"}
_TOKEN = re.compile(r"\\[A-Za-z]+|\\.|[0-9]+(?:\.[0-9]+)?|\s+|.", re.S)
_COMPOUND = re.compile(r"\b(plus|minus|plus or minus|equals)\b")


def read(tex: str) -> str:
    """The formula in words, broken into phrases with newlines."""
    text = _Reader(_strip(tex)).sentence()
    lines = [_tidy(line).lstrip(", ") for line in text.split(_BREAK)]
    return "\n".join(line for line in lines if line).rstrip(",")


def say(tex: str) -> str:
    """The formula in words, on one line."""
    return _tidy(read(tex).replace("\n", " ")).rstrip(",")


def _strip(tex: str) -> str:
    text = (tex or "").strip()
    while text.startswith("$") and text.endswith("$") and len(text) > 1:
        text = text[1:-1].strip()
    return text


def _tidy(text: str) -> str:
    text = " ".join(text.split())
    text = re.sub(r"\s+([,)\]}])", r"\1", text)
    text = re.sub(r"([(\[{])\s+", r"\1", text)
    text = re.sub(r",(\s*,)+", ",", text)
    text = re.sub(r",\s*([)\]}])", r"\1", text)
    return text.strip(" ")


def _compound(text: str) -> bool:
    """More than one term at its own level: brackets are needed to say where it ends."""
    level, flat = 0, []
    for c in text:
        level += c in "([{"
        level -= c in ")]}"
        flat.append(c if level == 0 else " ")
    return bool(_COMPOUND.search("".join(flat))) and not (text.startswith("(") and text.endswith(")"))


def _wrap(text: str) -> str:
    text = _tidy(text)
    return f"({text})" if _compound(text) else text


class _Reader:
    def __init__(self, tex: str) -> None:
        self.tokens = [t for t in _TOKEN.findall(tex) if not t.isspace()]
        self.i = 0
        self.bare = False
        self.called = False

    def peek(self, offset: int = 0) -> str | None:
        j = self.i + offset
        return self.tokens[j] if j < len(self.tokens) else None

    def take(self) -> str | None:
        token = self.peek()
        self.i += token is not None
        return token

    def skip_sizing(self) -> None:
        while (token := self.peek()) is not None and token.startswith("\\") and token[1:] in _SIZING:
            self.take()

    def ahead(self, wanted: set[str], before: set[str] = frozenset()) -> str | None:
        """The first token in ``wanted`` or ``before`` at this level, looking ahead, or None at the level's end."""
        depth = 0
        for token in self.tokens[self.i :]:
            if depth == 0 and (token in wanted or token in before):
                return token
            if token in ("{", "(", "[", "\\{", "\\langle"):
                depth += 1
            elif token in _CLOSERS:
                depth -= 1
                if depth < 0:
                    return None
        return None

    # ---- grammar

    def sentence(self) -> str:
        return self.sequence(stop=set(), top=True)

    def sequence(self, stop: set[str], top: bool = False, term: bool = False) -> str:
        """Atoms and the words between them, up to a token in ``stop``.

        ``term`` stops before a top-level plus, minus, or relation: the body of a
        sum or an integral is one term.
        """
        words: list[str] = []
        last: tuple[str, str, bool] | None = None
        while True:
            self.skip_sizing()
            token = self.peek()
            if token is None or token in stop:
                break
            command = token.startswith("\\")
            name = token[1:] if command else token
            if token == "}" or (token in _CLOSERS and token not in stop and not command and not stop):
                self.take()
                continue
            if token in ("&", "\\\\"):
                self.take()
                words.append(", ")
                last = None
                continue
            relation = _RELATIONS.get(name) if (command or token in "=<>") else None
            infix = _INFIX.get(name) if (command or token in "+-/") else None
            if term and words and (relation or token in ("+", "-") or name in ("pm", "mp")):
                break
            if relation:
                self.take()
                words.append(f" {relation} " + (_BREAK if top else ""))
                last = None
                continue
            if infix:
                self.take()
                if last and last[0] == "del" and name in ("cdot", "times"):
                    words[-1] = "del " + ("dot" if name == "cdot" else "cross")
                    last = None
                    continue
                words.append(f"{_BREAK}{infix}{_BREAK}" if top and token in ("+", "-") and words else f" {infix} ")
                last = None
                continue
            if command and name in _PAUSE:
                self.take()
                words.append(", " + (_BREAK if top else ""))
                last = None
                continue
            if token in (",", ";", ":"):
                self.take()
                words.append(f"{token} ")
                last = None
                continue
            if token == ".":
                self.take()
                continue
            if token in _BAR and not self.closes(_BAR | {"\\rangle"}):
                # A bar with no partner, as in P(A|B), reads "given".
                self.take()
                words.append(" given ")
                last = None
                continue
            if token in _NORM and not self.closes(_NORM):
                self.take()
                words.append(" parallel ")
                last = None
                continue
            atom, kind = self.atom(top)
            if atom is None:
                continue
            called = self.called
            if kind in ("operator", "derivative"):
                body = self.sequence(stop | _CLOSERS, term=True)
                atom = f"{atom} of {_tidy(body)}" if _tidy(body) else atom
            elif kind == "function":
                self.skip_sizing()
                nxt = self.peek()
                if nxt is not None and nxt not in stop and nxt not in _CLOSERS and _RELATIONS.get(nxt.lstrip("\\")) is None:
                    if nxt not in ("+", "-"):
                        arg, _ = self.atom(top=False)
                        atom = f"{atom} of {_unwrap(arg)}" if arg else atom
            elif kind == "bracket" and last is not None and last[1] in ("letter", "named") and words:
                if last[2] or "," in _unwrap(atom):
                    words[-1] = f"{last[0]} of {_unwrap(atom)}"
                    last = (words[-1], "applied", False)
                    continue
            words.append(atom)
            last = (atom, kind, called)
        out = ""
        for w in words:
            out += w if w.startswith((" ", ",", _BREAK)) or w.endswith((" ", _BREAK)) else f" {w} "
        return out

    def closes(self, partners: set[str]) -> bool:
        """Whether the bar here opens a pair: |x|, a ket |n>, or a norm."""
        self.i += 1
        try:
            return self.ahead(partners) is not None
        finally:
            self.i -= 1

    def group(self, script: bool = False) -> str:
        """A braced group, or the one token that stands for it. A script's one token takes no scripts."""
        self.skip_sizing()
        if self.peek() == "{":
            self.take()
            text = self.sequence(stop={"}"})
            if self.peek() == "}":
                self.take()
            return text
        self.bare = script
        atom, _ = self.atom(top=False)
        self.bare = False
        return atom or ""

    def raw_group(self) -> str:
        """The text inside a braced group, unread: for \\mathrm{softmax} and \\text{if}."""
        self.skip_sizing()
        if self.peek() != "{":
            token = self.take() or ""
            return token[1:] if token.startswith("\\") else token
        self.take()
        depth, parts = 1, []
        while self.peek() is not None:
            token = self.take()
            if token == "{":
                depth += 1
            elif token == "}":
                depth -= 1
                if depth == 0:
                    break
            parts.append(token)
        return "".join(" " if p.startswith("\\") and p[1:] in _SIZING else p for p in parts).strip()

    def atom(self, top: bool) -> tuple[str | None, str]:
        """One thing and its scripts. The kind says how it joins what follows."""
        self.called = False
        self.skip_sizing()
        token = self.take()
        if token is None:
            return None, ""
        name = token[1:] if token.startswith("\\") else None

        if token == "{":
            text = self.sequence(stop={"}"})
            if self.peek() == "}":
                self.take()
            return self.scripts(text, "group")
        if name in ("frac", "dfrac", "tfrac"):
            return self.fraction(top)
        if name == "sqrt":
            index = ""
            if self.peek() == "[":
                self.take()
                index = _tidy(self.sequence(stop={"]"}))
                self.take()
            inside = _wrap(self.group())
            root = {"": "square", "2": "square", "3": "cube"}.get(index)
            text = f"the {root} root of {inside}" if root else f"the {_ordinal(index)} root of {inside}"
            return self.scripts(text, "group")
        if name in _ACCENTS:
            inside = _tidy(self.group())
            return self.scripts(f"{inside} {_ACCENTS[name][0]}", "named")
        if name in ("mathbb", "mathcal", "mathfrak", "mathscr"):
            letter = self.raw_group()
            if name == "mathbb" and letter == "E":
                return self.big(_EXPECT)
            spoken = {key: said for key, said, _hint in _NAMED}.get(f"{name}{{{letter}}}")
            if spoken is None:
                spoken = {"mathbb": f"blackboard {letter}", "mathfrak": f"fraktur {letter}"}.get(name, f"script {letter}")
            return self.scripts(spoken, "named")
        if name in _FONTS:
            word = self.raw_group()
            if name == "operatorname" or word.lower() in _FUNCTIONS:
                return self.scripts(_FUNCTIONS.get(word.lower(), word), "function")
            if len(word) > 1 and word.replace(" ", "").isalpha():
                result = self.scripts(word, "named")
                self.called = True
                return result
            return self.scripts(_Reader(word).sequence(stop=set()) if len(word) > 1 else word, "letter")
        if name in _BIG:
            return self.big(_BIG[name])
        if name in _FUNCTIONS:
            return self.scripts(_FUNCTIONS[name], "function")
        if token in _OPEN:
            return self.fence(token, _OPEN[token])
        if name == "langle":
            return self.angle()
        if token in _NORM:
            return self.norm(token)
        if token in _BAR:
            return self.bar()
        if name and name in _BY_COMMAND:
            result = self.scripts(_BY_COMMAND[name][1], "letter")
            self.called = name in _FUNCTION_LETTERS
            return result
        if name and name in _SYMBOLS:
            return self.scripts(_SYMBOLS[name], "named")
        if name in _RELATIONS or name in _INFIX:
            return (_RELATIONS.get(name) or _INFIX.get(name)), "word"
        if name:
            return self.scripts(name, "named")
        if token in _SYMBOLS:
            return self.scripts(_SYMBOLS[token], "word")
        if token == "'":
            return "prime", "word"
        if token in _CLOSERS:
            return None, ""
        if token.isalpha():
            result = self.scripts(token, "letter")
            self.called = token in _FUNCTION_LETTERS
            return result
        if token[0].isdigit():
            return self.scripts(token, "number")
        return self.scripts(token, "word")

    def fraction(self, top: bool) -> tuple[str, str]:
        upper, lower = _tidy(self.group()), _tidy(self.group())
        # d/dx and the partial derivative read as derivatives.
        order_words = {"squared": "second ", "cubed": "third "}
        head = re.fullmatch(r"(d|partial)(?: (squared|cubed))?(?: (.+))?", upper)
        foot = re.fullmatch(r"(d|partial) (.+?)(?: (squared|cubed))?", lower)
        if head and foot and head.group(1) == foot.group(1):
            kind = "partial derivative" if head.group(1) == "partial" else "derivative"
            order = order_words.get(head.group(2) or "", "")
            if head.group(3):
                return self.scripts(f"the {order}{kind} of {head.group(3)} with respect to {foot.group(2)}", "group")
            return f"the {order}{kind} with respect to {foot.group(2)}", "derivative"
        if (upper, lower) in _FRACTIONS:
            return self.scripts(_FRACTIONS[(upper, lower)], "number")
        upper, lower = _wrap(upper), _wrap(lower)
        return self.scripts(f"{upper}{_BREAK if top else ' '}over {lower}", "fraction")

    def fence(self, opener: str, closer: str) -> tuple[str, str]:
        inside = self.sequence(stop={closer})
        self.skip_sizing()
        if self.peek() == closer:
            self.take()
        left = {"(": "(", "[": "[", "\\{": "{", "\\lfloor": "the floor of ", "\\lceil": "the ceiling of "}[opener]
        right = {"(": ")", "[": "]", "\\{": "}"}.get(opener, "")
        return self.scripts(f"{left}{_tidy(inside)}{right}", "bracket")

    def angle(self) -> tuple[str, str]:
        """⟨A⟩, ⟨x|y⟩, ⟨x|A|y⟩, or a bra ⟨x| with no end."""
        parts = []
        closed = False
        while True:
            parts.append(_tidy(self.sequence(stop=_BAR | {"\\rangle"})))
            token = self.take()
            if token == "\\rangle" or token is None:
                closed = token is not None
                break
            if self.ahead({"\\rangle"}) is None:
                break
        if not closed:
            return self.scripts(f"bra {' '.join(parts)}", "named")
        if len(parts) == 1:
            return self.scripts(f"the expectation value of {parts[0]}", "group")
        if len(parts) == 2:
            return self.scripts(f"the inner product of {parts[0]} and {parts[1]}", "group")
        return self.scripts(f"the matrix element of {parts[1]} between {parts[0]} and {parts[2]}", "group")

    def bar(self) -> tuple[str, str]:
        """|x| is an absolute value. |n⟩ is a ket."""
        inside = _tidy(self.sequence(stop=_BAR | {"\\rangle"}))
        token = self.take()
        if token == "\\rangle":
            return self.scripts(f"ket {inside}", "named")
        squared = self.peek() == "^" and (
            self.peek(1) == "2" or (self.peek(1), self.peek(2), self.peek(3)) == ("{", "2", "}")
        )
        if squared:
            self.take()
            self.group(script=True)
            return self.scripts(f"the squared absolute value of {_wrap(inside)}", "group")
        return self.scripts(f"the absolute value of {_wrap(inside)}", "group")

    def norm(self, opener: str) -> tuple[str, str]:
        inside = _wrap(self.sequence(stop=_NORM))
        self.skip_sizing()
        if self.peek() in _NORM:
            self.take()
        sub = sup = ""
        while self.peek() in ("_", "^"):
            mark = self.take()
            value = _tidy(self.group(script=True))
            if mark == "_":
                sub = value
            else:
                sup = value
        which = {"1": "L1 ", "2": "L2 ", "infinity": "L infinity ", "F": "Frobenius ", "p": "L p "}.get(sub, f"{sub} " if sub else "")
        if sup == "2":
            # A squared norm with no subscript is the usual length, L2.
            return f"the squared {which or 'L2 '}norm of {inside}", "group"
        text = f"the {which}norm of {inside}"
        return (f"{text}, {_power(sup, '')}" if sup else text), "group"

    def big(self, spoken: tuple[str, str]) -> tuple[str, str]:
        name, word = spoken
        lower = upper = ""
        while True:
            self.skip_sizing()
            if self.peek() == "_":
                self.take()
                lower = _tidy(self.group(script=True))
            elif self.peek() == "^":
                self.take()
                upper = _tidy(self.group(script=True))
            else:
                break
        text = name + (f" {word} {lower}" if lower else "") + (f" to {upper}" if upper else "")
        return text, "operator"

    def scripts(self, base: str, kind: str) -> tuple[str, str]:
        """Subscripts, superscripts, and primes on ``base``."""
        if self.bare:
            self.bare = False
            return base, kind
        text, has_sub, long = base, False, False
        while True:
            token = self.peek()
            if token == "_":
                self.take()
                start = self.i
                sub = _tidy(self.group(script=True)).replace(", ", " ")
                plain = "".join(self.tokens[start : self.i]).strip("{}")
                text = f"{text} {sub}" if plain in _SUB_PLAIN else f"{text} sub {sub}"
                has_sub, long = True, len(sub.split()) > 1
            elif token == "^":
                self.take()
                start = self.i
                sup = _tidy(self.group(script=True))
                plain = "".join(self.tokens[start : self.i])
                said = _power(sup, plain)
                if has_sub and said == sup and len(plain.strip("{} ")) == 1 and plain.strip("{} ") in _LABEL_LETTERS:
                    said = f"superscript {sup}"
                text = f"{text} {said}"
                long = len(sup.split()) > 1 and said.startswith("to the")
            elif token == "'":
                self.take()
                text = f"{text} prime"
            else:
                break
        if long and self.continues():
            # e^{i x \xi} d\xi: a pause says where the exponent ends.
            text += ","
        if kind == "bracket" and text != base:
            kind = "group"
        return text, kind

    def continues(self) -> bool:
        """Whether an atom follows: not an operator, a relation, a closer, or the end."""
        j = self.i
        while j < len(self.tokens) and self.tokens[j].startswith("\\") and self.tokens[j][1:] in _SIZING:
            j += 1
        if j >= len(self.tokens):
            return False
        token = self.tokens[j]
        name = token.lstrip("\\")
        return not (token in _CLOSERS or token in "+-=<>,&" or name in _RELATIONS or name in _INFIX or name in _PAUSE)


def _power(sup: str, plain: str) -> str:
    """How a superscript is said after its base."""
    raw = plain.strip().strip("{}").strip()
    if raw in _POWERS:
        return _POWERS[raw][0]
    if sup in ("2", "3"):
        return {"2": "squared", "3": "cubed"}[sup]
    if sup == "minus 1":
        return "inverse"
    if sup in ("transpose", "dagger", "star", "prime", "plus", "minus"):
        return sup
    words = sup.split()
    if "," in sup or re.fullmatch(r"\(.*\)", sup) or (len(words) > 1 and words[-1] in ("transpose", "dagger", "star")):
        # A label with a mark on it, as in K^{l\top}: not a power.
        return f"superscript {sup.replace(', ', ' ')}"
    if len(raw) == 1 and raw in _LABEL_LETTERS:
        return sup
    if sup.isdigit():
        return f"to the {_ordinal(sup)}"
    return f"to the {sup}"


def _ordinal(text: str) -> str:
    words = {"1": "first", "2": "second", "3": "third", "4": "fourth", "5": "fifth", "n": "n-th", "k": "k-th",
             "m": "m-th", "p": "p-th"}
    if text in words:
        return words[text]
    if text.isdigit():
        return text + "th"
    return f"{text}-th"


def _unwrap(text: str) -> str:
    """f(x) is "f of x". An argument that is more than one term, or a fraction, keeps its brackets to say where it ends."""
    text = text.strip()
    if text.startswith("(") and text.endswith(")") and text.count("(") == 1:
        inner = text[1:-1]
        if " over " not in inner and not _compound(inner):
            return inner
    return text
