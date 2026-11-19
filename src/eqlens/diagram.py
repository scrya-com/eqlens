"""A formula as a Mermaid flowchart: what goes in, what is done to it, and what comes out.

    diagram(r"E = \\frac{1}{2} m v^2 + m g h")["mermaid"]

Two kinds of formula make a picture worth having.

A formula that can be worked out is drawn as its steps: each symbol is a box,
each operation a rounded box, and the arrows run to the result.

A formula that names what is done, such as
``L_0' = \\mathrm{Conv}_\\theta(L_0, L_1, S_0)``, is drawn as its calls: the
inputs run into the operation and on to what it gives. Several such statements,
set apart by commas or ``\\quad``, share one picture, and a result that is used
again is one box.

Every box has the color its symbol has in the eqlens drawing, so a page can
show both and the reader can match them by eye. ``fits`` says whether the
picture adds anything: a formula with one step does not need one. Nothing is
guessed: a formula eqlens cannot read gives no picture, and ``why`` says so.

The result is Mermaid source. eqlens does not run Mermaid: a page that loads
it, a Markdown file on GitHub, or a Claude artifact draws the picture.
"""

from __future__ import annotations

import re
from typing import Sequence

from eqlens.bench.expr import Unreadable, from_tex
from eqlens.engine import FormulaError
from eqlens.legend import _BY_COMMAND, _shape, plain, symbols

__all__ = ["STYLES", "diagram", "fenced"]

STYLES = ("dark", "light", "plain")
_MOST = 16  # steps: past this a flowchart is harder to read than the formula
_GROUNDS = {"dark": (0x19, 0x1C, 0x24), "light": (0xFF, 0xFF, 0xFF)}
_INIT = {
    "dark": '%%{init: {"theme": "dark", "themeVariables": {"background": "#12141a", "primaryColor": "#232734", '
    '"primaryTextColor": "#e6e8ee", "lineColor": "#8b949e"}}}%%',
    "light": '%%{init: {"theme": "neutral"}}%%',
}
_BOX = {
    "dark": "fill:#232734,stroke:#8b949e,color:#e6e8ee",
    "light": "fill:#f6f8fa,stroke:#57606a,color:#1f2328",
}
_STEP = {
    "dark": "fill:#191c24,stroke:#8b949e,color:#c9d1d9",
    "light": "fill:#ffffff,stroke:#57606a,color:#1f2328",
}

_SUB = str.maketrans("0123456789+-=()aeoxhklmnpstijruv", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑₒₓₕₖₗₘₙₚₛₜᵢⱼᵣᵤᵥ")
_SUP = str.maketrans("0123456789+-=()ni", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿⁱ")
_SCRIPT = re.compile(r"([_^])\s*(?:\{([^{}\\]*)\}|([A-Za-z0-9]))")
_FUNCS = {"sqrt": "square root", "abs": "size of", "exp": "e to the power", "ln": "natural log", "log10": "log base 10",
          "log2": "log base 2", "asin": "arcsin", "acos": "arccos", "atan": "arctan"}
_CONSTS = {"pi": "π", "e": "e"}
_POWERS = {2.0: "square", 3.0: "cube", 0.5: "square root", -1.0: "one over"}

_FONT = r"\\(?:mathrm|operatorname|text|mathsf|mathit|mathbf|mathcal|mathbb)\s*\{[^{}]+\}"
_TAIL = r"(?:\s*[_^]\s*(?:\{[^{}]*\}|\\[A-Za-z]+|[A-Za-z0-9])|\s*')*"
_NAME = re.compile(rf"(?P<name>(?:{_FONT}|\\[A-Za-z]+|[A-Za-z]){_TAIL})\s*(?:\\left\s*)?\(")
_ATOM = re.compile(rf"(?:{_FONT}|\\[A-Za-z]+|[A-Za-z]){_TAIL}")
_WORD = re.compile(r"\\(?:mathrm|operatorname|text|mathsf|mathit|mathbf)\s*\{[A-Za-z][A-Za-z -]+\}")
_DOTS = {r"\ldots", r"\dots", r"\cdots", "...", "…"}
_BREAKS = {"quad", "qquad", "\\"}
_OPEN, _CLOSE = "({[", ")}]"


def _label(tex: str) -> str:
    """A symbol as plain characters: ``L_0'`` is L₀′, ``x^2`` is x²."""

    def script(match: re.Match) -> str:
        mark, body = match.group(1), match.group(2) if match.group(2) is not None else match.group(3)
        table = _SUB if mark == "_" else _SUP
        moved = body.replace(" ", "").translate(table)
        return moved if body and not set(moved) & set(body.replace(" ", "")) else match.group(0)

    text = _SCRIPT.sub(script, tex.strip()).replace("'", "′")
    text = re.sub(r"\s*\\(?:ldots|cdots|dots)(?![A-Za-z])\s*", " … ", text)
    return plain(f"${text}$")


def _quote(text: str) -> str:
    return text.replace("&", "&amp;").replace('"', "#quot;").replace("<", "&lt;").replace(">", "&gt;")


def _number(value: float) -> str:
    return str(int(value)) if value == int(value) and abs(value) < 1e15 else f"{value:g}"


def _mix(color: str, ground: tuple[int, int, int], share: float) -> str:
    rgb = [int(color[i : i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(g + (c - g) * share):02x}" for c, g in zip(rgb, ground))


class _Graph:
    """Boxes and arrows, in the order they were met."""

    def __init__(self, colors: list[tuple[tuple, str]], greek: bool):
        self.colors, self.greek = colors, greek
        self.boxes: list[tuple[str, str, str, str | None]] = []  # id, label, shape, color
        self.arrows: list[tuple[str, str, str]] = []
        self.known: dict[str, str] = {}
        self.steps = 0

    def color(self, tex: str) -> str | None:
        shape = _shape(tex)
        for other, color in self.colors:
            if other == shape:
                return color
        head = re.match(r"\\([A-Za-z]+)", tex.strip())
        if self.greek and head and head.group(1) in _BY_COMMAND:
            return _BY_COMMAND[head.group(1)][2]
        return None

    def box(self, label: str, shape: str = "box", color: str | None = None) -> str:
        ident = f"n{len(self.boxes)}"
        self.boxes.append((ident, label, shape, color))
        return ident

    def symbol(self, tex: str, shape: str = "box") -> str:
        """One box per symbol, however often it is used."""
        key = re.sub(r"\s+", "", tex)
        if key not in self.known:
            self.known[key] = self.box(_label(tex), shape, self.color(tex))
        return self.known[key]

    def step(self, label: str, tex: str | None = None) -> str:
        self.steps += 1
        return self.box(label, "step", self.color(tex) if tex else None)

    def arrow(self, start: str, end: str, label: str = "") -> None:
        self.arrows.append((start, end, label))

    def source(self, style: str, direction: str) -> str:
        lines = [_INIT[style]] if style in _INIT else []
        lines.append(f"flowchart {direction}")
        classes: dict[str, str] = {}
        for ident, label, shape, color in self.boxes:
            if color:
                name = classes.setdefault(color, f"c{len(classes)}")
            else:
                name = "step" if shape == "step" else "box"
            text = _quote(label)
            body = {"step": f'(["{text}"])', "out": f'[["{text}"]]', "call": f'{{{{"{text}"}}}}'}.get(shape, f'["{text}"]')
            lines.append(f"  {ident}{body}" + ("" if style == "plain" and not color else f":::{name}"))
        for start, end, label in self.arrows:
            lines.append(f'  {start} -- "{_quote(label)}" --> {end}' if label else f"  {start} --> {end}")
        if style != "plain":
            lines += [f"  classDef box {_BOX[style]}", f"  classDef step {_STEP[style]}"]
        for color, name in classes.items():
            if style == "plain":
                lines.append(f"  classDef {name} stroke:{color},stroke-width:2px")
            elif style == "dark":
                lines.append(f"  classDef {name} fill:{_mix(color, _GROUNDS['dark'], 0.14)},stroke:{color},color:{color}")
            else:
                lines.append(
                    f"  classDef {name} fill:{_mix(color, _GROUNDS['light'], 0.3)},stroke:{_mix(color, (0, 0, 0), 0.72)},color:#1f2328"
                )
        return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- a formula that can be worked out


def _flat(node: tuple, kinds: tuple[str, str], sign: int = 1) -> list[tuple[int, tuple]]:
    """``a + b - c`` as signed terms, or ``a * b`` as factors."""
    more, less = kinds
    if node[0] == more:
        return _flat(node[1], kinds, sign) + _flat(node[2], kinds, sign)
    if less and node[0] == less:
        return _flat(node[1], kinds, sign) + _flat(node[2], kinds, -sign)
    return [(sign, node)]


def _plain_number(node: tuple) -> str | None:
    """A number, or a fraction of two numbers such as 1/2, as it is written."""
    if node[0] == "num":
        return _number(node[1])
    if node[0] == "div" and node[1][0] == "num" and node[2][0] == "num":
        return f"{_number(node[1][1])}/{_number(node[2][1])}"
    return None


def _walk(node: tuple, graph: _Graph) -> str:
    kind = node[0]
    if kind == "div" and _plain_number(node):
        return graph.box(_plain_number(node))
    if kind == "sym":
        return graph.symbol(node[1])
    if kind == "num":
        return graph.box(_number(node[1]))
    if kind == "const":
        return graph.symbol(_CONSTS.get(node[1], node[1]))
    if kind in ("add", "sub"):
        terms = _flat(node, ("add", "sub"))
        numbers = [(sign, part) for sign, part in terms if part[0] == "num"]
        rest = [(sign, part) for sign, part in terms if part[0] != "num"]
        less = sum(sign < 0 for sign, _part in terms)
        label = "add" if not less else "subtract" if len(terms) == 2 else "add and take away"
        if len(numbers) == 1 and rest:
            sign, part = numbers[0]
            label = ("add " if sign > 0 else "take away ") + _number(part[1])
        else:
            rest = terms
        step = graph.step(label)
        for sign, part in rest:
            graph.arrow(_walk(part, graph), step, "" if sign > 0 else "take away")
        return step
    if kind == "mul":
        factors = [part for _sign, part in _flat(node, ("mul", ""))]
        numbers = [part for part in factors if _plain_number(part)]
        rest = [part for part in factors if not _plain_number(part)]
        label = "multiply"
        if len(numbers) == 1 and rest:
            label = "times " + _plain_number(numbers[0])
        else:
            rest = factors
        step = graph.step(label)
        for part in rest:
            graph.arrow(_walk(part, graph), step)
        return step
    if kind == "div":
        top, bottom = node[1], node[2]
        if bottom[0] == "num":
            step = graph.step("divide by " + _number(bottom[1]))
            graph.arrow(_walk(top, graph), step)
        elif top == ("num", 1.0):
            step = graph.step("one over")
            graph.arrow(_walk(bottom, graph), step)
        else:
            step = graph.step("divide")
            graph.arrow(_walk(top, graph), step, "top")
            graph.arrow(_walk(bottom, graph), step, "bottom")
        return step
    if kind == "pow":
        base, power = node[1], node[2]
        if power[0] == "num":
            step = graph.step(_POWERS.get(power[1], "to the power " + _number(power[1])))
            graph.arrow(_walk(base, graph), step)
        elif base == ("const", "e"):
            step = graph.step("e to the power")
            graph.arrow(_walk(power, graph), step)
        else:
            step = graph.step("to the power")
            graph.arrow(_walk(base, graph), step, "base")
            graph.arrow(_walk(power, graph), step, "power")
        return step
    if kind == "neg":
        step = graph.step("change sign")
        graph.arrow(_walk(node[1], graph), step)
        return step
    if kind == "call":
        step = graph.step(_FUNCS.get(node[1], node[1]))
        graph.arrow(_walk(node[2], graph), step)
        return step
    raise Unreadable("cannot draw this formula as steps")


def _worked(tex: str, graph: _Graph, solve: str | None) -> None:
    out, _args, node = from_tex(tex, solve)
    last = _walk(node, graph)
    end = graph.box(_label(out), "out", graph.color(out)) if out else graph.box("result", "out")
    graph.arrow(last, end)


# ---------------------------------------------------------------- a formula that names what is done


def _cut(tex: str, at: str) -> list[str]:
    """Cut at each ``at`` character, and at each ``\\quad`` when cutting statements, outside every bracket."""
    parts, depth, start, i = [], 0, 0, 0
    while i < len(tex):
        char = tex[i]
        if char == "\\":
            match = re.match(r"\\([A-Za-z]+|.)", tex[i:], re.S)
            name = match.group(1) if match else ""
            if depth == 0 and "," in at and name in _BREAKS:
                parts.append(tex[start:i])
                start = i + len(name) + 1
            i += len(name) + 1
            continue
        if char in _OPEN:
            depth += 1
        elif char in _CLOSE:
            depth -= 1
        elif char in at and depth == 0:
            parts.append(tex[start:i])
            start = i + 1
        i += 1
    parts.append(tex[start:])
    return [part.strip() for part in parts]


def _inside(text: str) -> str | None:
    """What is between the brackets when ``text`` is one bracketed group, ``\\left`` and ``\\right`` or not."""
    text = re.sub(r"^\\left\s*", "", text.strip())
    if not text or text[0] not in "([":
        return None
    depth = 0
    for i, char in enumerate(text):
        if char == "\\":
            continue
        if char in _OPEN and (i == 0 or text[i - 1] != "\\"):
            depth += 1
        elif char in _CLOSE and (i == 0 or text[i - 1] != "\\"):
            depth -= 1
            if depth == 0:
                return re.sub(r"\\right\s*$", "", text[1:i]).strip() if i == len(text) - 1 else None
    return None


def _inputs(text: str) -> list[str]:
    """The things in a list, with ``C_1, \\ldots, C_5`` kept as one."""
    items = [item for item in _cut(text, ",") if item]
    out: list[str] = []
    i = 0
    while i < len(items):
        if items[i] in _DOTS and out and i + 1 < len(items):
            out[-1] = f"{out[-1]} \\ldots {items[i + 1]}"
            i += 2
            continue
        out.append(items[i])
        i += 1
    return out


def _named(tex: str, graph: _Graph) -> bool:
    """Read ``OUT = Name(a, b, ...)`` statements. False when the formula is not made of them."""
    statements = [part for part in _cut(tex, ",;") if part]
    found: list[tuple[str, str | None, list[str]]] = []
    calls = 0
    for statement in statements:
        sides = _cut(statement, "=")
        if len(sides) != 2 or not all(sides):
            return False
        left, right = sides
        match = _NAME.match(right)
        inner = _inside(right[match.end() - 1 :]) if match else None
        if match and inner is not None:
            name, inputs = match.group("name").strip(), _inputs(inner)
            if not inputs:
                return False
            found.append((left, name, inputs))
            # f(x) alone may be f times x: it counts as a call only beside one that cannot be.
            calls += bool(_WORD.match(name) or len(inputs) > 1)
            continue
        inner = _inside(right)
        if inner is not None and len(_inputs(inner)) > 1:
            found.append((left, None, _inputs(inner)))
        elif _ATOM.fullmatch(right):
            found.append((left, None, [right]))
        else:
            return False
    if not calls:
        return False
    for left, name, inputs in found:
        end = graph.symbol(left)
        if name:
            step = graph.box(_label(name), "call", graph.color(name))
            graph.steps += 1
            for item in inputs:
                graph.arrow(graph.symbol(item), step)
            graph.arrow(step, end)
        else:
            for item in inputs:
                graph.arrow(graph.symbol(item), end, "kept")
    return True


# ---------------------------------------------------------------- the diagram


def diagram(
    tex: str,
    *,
    style: str = "dark",
    direction: str = "LR",
    define: Sequence[str] = (),
    legend: bool = False,
    solve: str | None = None,
) -> dict:
    """The flowchart for ``tex``.

    Returns ``tex``, ``kind`` (``"steps"``, ``"calls"``, or None), ``fits``,
    ``why``, ``steps`` (how many operations), and ``mermaid`` (the source, or
    an empty string when there is nothing to draw). ``style`` is ``dark`` (the
    eqlens ground), ``light``, or ``plain`` (no theme and no fills, for a page
    that sets its own). ``define`` items give symbols the colors they have in
    the drawing. ``legend`` colors the Greek letters, as ``--legend`` does.
    """
    text = (tex or "").strip().strip("$").strip()
    if not text:
        raise FormulaError("give a formula")
    if style not in STYLES:
        raise FormulaError("the diagram style is one of: " + ", ".join(STYLES))
    direction = (direction or "LR").upper()
    if direction not in ("LR", "TB", "RL", "BT"):
        raise FormulaError("the diagram direction is LR, TB, RL, or BT")
    rows = symbols(text, legend=legend, define=define)
    colors = [(_shape(row.key), row.color) for row in rows if row.color]
    found = {"tex": text, "kind": None, "fits": False, "why": "", "steps": 0, "mermaid": ""}

    graph = _Graph(colors, legend)
    if _named(text, graph):
        found["kind"] = "calls"
    else:
        graph = _Graph(colors, legend)
        try:
            _worked(text, graph, solve)
        except Unreadable as exc:
            found["why"] = f"no diagram: {exc}"
            return found
        found["kind"] = "steps"
    found["steps"] = graph.steps
    found["mermaid"] = graph.source(style, direction)
    inputs = len(graph.known)
    if found["kind"] == "steps" and graph.steps < 2:
        found["why"] = "one step only: a diagram would say no more than the formula"
    elif found["kind"] == "calls" and len(graph.arrows) < 3:
        found["why"] = "one thing in and one thing out: a diagram would say no more than the formula"
    elif graph.steps > _MOST:
        found["why"] = f"{graph.steps} steps: too many to read as one picture"
    else:
        found["fits"] = True
        found["why"] = f"{graph.steps} step{'s' if graph.steps != 1 else ''} from {inputs} symbol{'s' if inputs != 1 else ''}"
    return found


def fenced(source: str) -> str:
    """The source as a Markdown block, which GitHub and many editors draw."""
    return "```mermaid\n" + source + "```\n"
