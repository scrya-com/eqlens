"""The ledger: what each symbol is called, what it means, and where it is.

Each Greek command has one English name and one color. The same command is the
same color in every ledger. Accents, subscripts, and superscripts that the
formula uses are read aloud after the Greek ("x hat", "x sub i", "x squared").
A mark that is a convention and not arithmetic also gets one dim line saying
what it usually means: "u star" is a marked u, not a power.

``--define 'P=keeps what one token can carry'`` gives a symbol its meaning in
this formula. A defined symbol gets a color and a row of its own.

Every symbol is found again in the typeset formula by its glyphs, so the
formula can wear the ledger's colors and each glyph knows its row.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field

from eqlens.engine import FormulaError, Run, has_ink, layout, parses

# Command, glyph, spoken name, color. Colors are the single palette.
_LETTERS: tuple[tuple[str, str, str, str], ...] = (
    ("alpha", "α", "alpha", "#ff7b72"),
    ("beta", "β", "beta", "#79c0ff"),
    ("gamma", "γ", "gamma", "#d2a8ff"),
    ("delta", "δ", "delta", "#ffa657"),
    ("epsilon", "ε", "epsilon", "#7ee787"),
    ("varepsilon", "ϵ", "curly epsilon", "#56d364"),
    ("zeta", "ζ", "zeta", "#ff9bce"),
    ("eta", "η", "eta", "#a5d6ff"),
    ("theta", "θ", "theta", "#f2cc60"),
    ("vartheta", "ϑ", "curly theta", "#e3b341"),
    ("iota", "ι", "iota", "#d2d8e0"),
    ("kappa", "κ", "kappa", "#ffa198"),
    ("lambda", "λ", "lambda", "#bc8cff"),
    ("mu", "μ", "mu", "#2dd4bf"),
    ("nu", "ν", "nu", "#56d4dd"),
    ("xi", "ξ", "xi", "#c3e88d"),
    ("pi", "π", "pi", "#3fb950"),
    ("varpi", "ϖ", "curly pi", "#56d364"),
    ("rho", "ρ", "rho", "#ffb86c"),
    ("varrho", "ϱ", "curly rho", "#e3b341"),
    ("sigma", "σ", "sigma", "#ff7eb6"),
    ("varsigma", "ς", "final sigma", "#ffb3d9"),
    ("tau", "τ", "tau", "#89ddff"),
    ("upsilon", "υ", "upsilon", "#ffcb6b"),
    ("phi", "φ", "phi", "#c792ea"),
    ("varphi", "ϕ", "curly phi", "#d2a8ff"),
    ("chi", "χ", "chi", "#f07178"),
    ("psi", "ψ", "psi", "#82aaff"),
    ("omega", "ω", "omega", "#ff9e64"),
    ("Gamma", "Γ", "Gamma", "#d2a8ff"),
    ("Delta", "Δ", "Delta", "#ffa657"),
    ("Theta", "Θ", "Theta", "#f2cc60"),
    ("Lambda", "Λ", "Lambda", "#bc8cff"),
    ("Xi", "Ξ", "Xi", "#c3e88d"),
    ("Pi", "Π", "Pi", "#3fb950"),
    ("Sigma", "Σ", "Sigma", "#ff7eb6"),
    ("Upsilon", "Υ", "Upsilon", "#ffcb6b"),
    ("Phi", "Φ", "Phi", "#c792ea"),
    ("Psi", "Ψ", "Psi", "#82aaff"),
    ("Omega", "Ω", "Omega", "#ff9e64"),
)

_BY_COMMAND = {command: (glyph, name, color) for command, glyph, name, color in _LETTERS}
_COMMAND = re.compile(r"\\([A-Za-z]+)")
_CARD = (18, 20, 26, 255)

# Accent command: spoken suffix, and what the accent usually means. ``{b}`` is the base.
_ACCENTS = {
    "hat": ("hat", "An estimate of ${b}$, or in quantum mechanics an operator."),
    "widehat": ("hat", "An estimate of ${b}$, or in quantum mechanics an operator."),
    "bar": ("bar", "Often the average of ${b}$."),
    "overline": ("bar", "Often the average of ${b}$."),
    "tilde": ("tilde", "A changed ${b}$, such as smoothed or approximate."),
    "widetilde": ("tilde", "A changed ${b}$, such as smoothed or approximate."),
    "vec": ("vector", "${b}$ has a direction as well as a size."),
    "dot": ("dot", "How fast ${b}$ changes in time."),
    "ddot": ("double dot", "How fast the change in ${b}$ itself changes."),
}
# Commands whose limits read "from ... to ...".
_LIMIT_OPERATORS = {"int", "oint", "iint", "iiint", "sum", "prod", "coprod", "bigcup", "bigcap"}
# Commands whose subscript reads "as ..." or "over ...".
_UNDER_OPERATORS = {"lim": "as", "max": "over", "min": "over", "sup": "over", "inf": "over"}
# Superscripts with their own spoken name. The ones that are a label and not a
# power also say so.
_STAR = ("star", "A marked ${b}$: often the best one, or its complex conjugate. Not a power.")
_TRANSPOSE = ("transpose", "${b}$ with rows and columns swapped. Not a power.")
_DAGGER = ("dagger", "${b}$ transposed and complex-conjugated. Not a power.")
_PRIME = ("prime", "A second ${b}$, or its derivative. Not a power.")
_POWERS = {
    "2": ("squared", ""),
    "3": ("cubed", ""),
    "-1": ("inverse", "What undoes ${b}$."),
    "+": ("plus", ""),
    "-": ("minus", ""),
    "*": _STAR,
    r"\ast": _STAR,
    r"\star": _STAR,
    "T": _TRANSPOSE,
    r"\top": _TRANSPOSE,
    r"\intercal": _TRANSPOSE,
    r"\mathsf{T}": _TRANSPOSE,
    r"\mathrm{T}": _TRANSPOSE,
    r"\text{T}": _TRANSPOSE,
    r"\mathbf{T}": _TRANSPOSE,
    r"\mathit{T}": _TRANSPOSE,
    r"\dagger": _DAGGER,
    "H": _DAGGER,
    r"\prime": _PRIME,
}
# Font commands. As a script they take the group after them: x_\mathrm{in}.
_FONTS = {"mathrm", "text", "mathit", "mathsf", "mathbf", "mathtt", "operatorname"}
# A subscript that is already a word, as in N_{\mathrm{dense}}, names itself.
_WORD = re.compile(r"^\\(?:mathrm|text|mathit|mathsf|operatorname)\{[A-Za-z][A-Za-z -]+\}$")
# Symbols with a name of their own that are not Greek: command, spoken name, meaning.
_NAMED = (
    ("hbar", "h bar", "Planck's constant divided by $2\\pi$, about $1.055\\times10^{-34}$ J s."),
    ("nabla", "del", "The gradient: which way a value rises fastest, and how fast."),
    ("partial", "partial", "A derivative in one variable, holding the others still."),
    ("odot", "elementwise product", "Multiply matching entries, one by one."),
    ("otimes", "tensor product", "Every entry of one times every entry of the other."),
    ("oplus", "direct sum", "The two set side by side, not added entry by entry."),
    ("oint", "closed integral", "An integral around a loop or over a closed surface."),
    ("propto", "proportional to", "One side is a fixed multiple of the other."),
    ("ell", "ell", "A script l, used so it is not read as the digit 1."),
    ("mathbb{E}", "expectation", "The average over everything that can happen."),
    ("mathbb{1}", "indicator", "1 where the condition holds, 0 elsewhere."),
    ("mathbb{R}", "the real numbers", "Every point on the number line."),
    ("mathbb{C}", "the complex numbers", "Numbers with a real and an imaginary part."),
    ("mathbb{N}", "the natural numbers", "The counting numbers."),
    ("mathbb{Z}", "the integers", "Whole numbers, negative ones too."),
    ("mathcal{L}", "script L", "Usually the loss, or the Lagrangian."),
    ("mathcal{N}", "script N", "Usually the normal (bell curve) distribution."),
    ("mathcal{O}", "big O", "How fast something grows, ignoring constants."),
    ("mathcal{D}", "script D", "Usually the data set, or a sum over all paths."),
    ("mathcal{H}", "script H", "Usually a Hilbert space, or the Hamiltonian."),
)
_NAMED_AT = re.compile(r"\\(mathbb|mathcal)\s*\{\s*([A-Za-z0-9])\s*\}|\\([A-Za-z]+)")
_LAPLACIAN = "The Laplacian: how a point differs from the average around it."
# Symbols whose meaning is itself a formula. They open into it without being asked:
# symbol, and what it is made of.
_KNOWN_TIERS = (
    (r"\hbar", r"\frac{h}{2\pi}"),
    (
        r"\nabla^{2}",
        r"\frac{\partial^2}{\partial x^2}+\frac{\partial^2}{\partial y^2}+\frac{\partial^2}{\partial z^2}",
    ),
)
_NOTATION_COLOR = "#c9d1d9"
_NOTE_COLOR = "#8b949e"
# Colors for defined symbols that are not Greek, in the order they are defined.
_DEFINED_COLORS = ("#ffa657", "#79c0ff", "#7ee787", "#d2a8ff", "#f778ba", "#f2cc60", "#56d4dd", "#ff7b72")


def greek_in(tex: str) -> list[tuple[str, str, str, str]]:
    """Greek commands in ``tex``, in order, once each.

    Each item is ``(command, glyph, english_name, color)``.
    """
    found: list[tuple[str, str, str, str]] = []
    seen: set[str] = set()
    for match in _COMMAND.finditer(tex or ""):
        command = match.group(1)
        if command in seen or command not in _BY_COMMAND:
            continue
        seen.add(command)
        glyph, name, color = _BY_COMMAND[command]
        found.append((command, glyph, name, color))
    return found


def named_in(tex: str) -> list[tuple[str, str, str]]:
    """Named symbols that are not Greek, in order, once each: ``(key, spoken, meaning)``.

    ``named_in(r"i\\hbar\\partial_t")`` names ``\\hbar`` "h bar" and ``\\partial`` "partial".
    """
    table = {command: (name, hint) for command, name, hint in _NAMED}
    found: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for match in _NAMED_AT.finditer(tex or ""):
        command = f"{match.group(1)}{{{match.group(2)}}}" if match.group(1) else match.group(3)
        if command in seen or command not in table:
            continue
        seen.add(command)
        found.append((f"\\{command}", *table[command]))
    return found


def notation_in(tex: str) -> list[tuple[str, str, str, str]]:
    """Accents, subscripts, and superscripts in ``tex``, in order, once each.

    Each item is ``(key, glyph, spoken, color)``. ``glyph`` and ``spoken`` may hold
    mathtext between ``$`` signs, for example ``("x_i", "$x_i$", "$x$ sub $i$", ...)``.
    """
    return [row[:4] for row in _notation(tex)]


def hints_in(tex: str) -> dict[str, str]:
    """What a conventional mark usually means, by ``notation_in`` key.

    For ``u^*`` it is ``{"u^{*}": "A marked $u$, often the best or target one. Not a power."}``.
    Plain powers and plain subscripts have no hint. A kind of mark is explained
    once, on the first row that has it.
    """
    return {row[0]: row[4] for row in _notation(tex) if row[4]}


def _notation(tex: str) -> list[tuple[str, str, str, str, str]]:
    tex = tex or ""
    found: list[tuple[str, str, str, str, str]] = []
    seen: set[str] = set()
    explained: set[str] = set()

    def add(glyph: str, spoken: tuple[str, str, str]) -> None:
        name, kind, hint = spoken
        if glyph in seen or not _parses(glyph) or not _parses(name):
            return
        seen.add(glyph)
        # Three transposes in one formula explain "transpose" once.
        if kind in explained or not _parses(hint):
            hint = ""
        elif hint:
            explained.add(kind)
        found.append((glyph, f"${glyph}$", name, _NOTATION_COLOR, hint))

    base: str | None = None
    base_command: str | None = None
    command_start: int | None = None
    groups: list[int] = []
    parens: list[int] = []
    i = 0
    while i < len(tex):
        c = tex[i]
        if c.isspace():
            i += 1
            continue
        if c in "_^":
            arg, end = _argument(tex, i + 1)
            if base and arg:
                glyph = f"{base}{c}{{{arg}}}"
                if not (c == "_" and _WORD.match(arg)):
                    add(glyph, _script_name(base, base_command, c, arg))
                # A_e^T is one thing: "A sub e transpose", not "A transpose".
                after = _skip_space(tex, end)
                operator = base_command in _LIMIT_OPERATORS or base_command in _UNDER_OPERATORS
                if c == "_" and not operator and after < len(tex) and tex[after] == "^":
                    upper, end = _argument(tex, after + 1)
                    if upper:
                        add(f"{glyph}^{{{upper}}}", _script_name(glyph, None, "^", upper))
            i = end
            command_start = None
            continue
        if c == "\\":
            name, end = _command(tex, i)
            if name in _ACCENTS:
                arg, end = _argument(tex, end)
                if arg:
                    glyph = f"\\{name}{{{arg}}}"
                    suffix, hint = _ACCENTS[name]
                    add(glyph, (f"${arg}$ {suffix}", suffix, hint.format(b=arg)))
                    base, base_command = glyph, None
                i = end
                command_start = None
                continue
            base, base_command = tex[i:end], name
            command_start = i
            i = end
            continue
        if c == "{":
            groups.append(command_start if command_start is not None else i)
            base = base_command = command_start = None
            i += 1
            continue
        if c == "}":
            if groups:
                base, base_command = tex[groups.pop() : i + 1], None
            i += 1
            command_start = None
            continue
        if c == "'":
            if base:
                add(f"{base}'", (f"${base}$ prime", "prime", _PRIME[1].format(b=base)))
            i += 1
            continue
        if c == "(":
            # f(x)^2 reads as "f(x) squared", not "(x) squared".
            follows = base is not None and i > 0 and tex[i - 1] == base[-1] and tex.endswith(base, 0, i)
            parens.append(i - len(base) if follows else i)
            base = None
        elif c == ")":
            base = tex[parens.pop() : i + 1] if parens else None
        elif c.isdigit():
            end = i
            while end < len(tex) and tex[end].isdigit():
                end += 1
            base = tex[i:end]
            i = end
            base_command = command_start = None
            continue
        elif c.isalpha():
            base = c
        else:
            base = None
        base_command = command_start = None
        i += 1
    return found


def legend_entries(tex: str) -> list[tuple[str, str, str, str]]:
    """Greek letters first, then accents and scripts."""
    return greek_in(tex) + notation_in(tex)


def _rows(tex: str) -> list[tuple[str, str, str, str, str]]:
    """``legend_entries`` with the hint for each row, empty when there is none."""
    return [(*row, "") for row in greek_in(tex)] + _notation(tex)


def _skip_space(tex: str, i: int) -> int:
    while i < len(tex) and tex[i].isspace():
        i += 1
    return i


def _command(tex: str, i: int) -> tuple[str, int]:
    end = i + 1
    while end < len(tex) and tex[end].isalpha():
        end += 1
    if end == i + 1 and end < len(tex):
        end += 1
    return tex[i + 1 : end], end


def _argument(tex: str, i: int) -> tuple[str, int]:
    """One script or accent argument: a braced group, a command, or one character."""
    while i < len(tex) and tex[i].isspace():
        i += 1
    if i >= len(tex):
        return "", i
    if tex[i] == "{":
        depth = 0
        for end in range(i, len(tex)):
            if tex[end] == "{":
                depth += 1
            elif tex[end] == "}":
                depth -= 1
                if depth == 0:
                    return tex[i + 1 : end].strip(), end + 1
        return "", len(tex)
    if tex[i] == "\\":
        name, end = _command(tex, i)
        if name in _FONTS and end < len(tex) and tex[end] == "{":
            group, after = _argument(tex, end)
            if group:
                return f"{tex[i:end]}{{{group}}}", after
        return tex[i:end], end
    return tex[i], i + 1


def _script_name(base: str, command: str | None, mark: str, arg: str) -> tuple[str, str, str]:
    """Spoken name of a script, its kind, and what it usually means when it is not arithmetic."""
    if base == r"\|" and mark == "_":
        hint = {"1": "Add up the sizes of the entries.", "2": "The usual length."}.get(arg, "")
        return f"norm sub ${arg}$", f"norm{arg}", hint
    if mark == "_":
        if command in _LIMIT_OPERATORS:
            return f"${base}$ from ${arg}$", "from", ""
        if command in _UNDER_OPERATORS:
            return f"${base}$ {_UNDER_OPERATORS[command]} ${arg}$", "under", ""
        return f"${base}$ sub ${arg}$", "sub", ""
    if command in _LIMIT_OPERATORS:
        return f"${base}$ to ${arg}$", "to", ""
    if base == r"\|" and arg == "2":
        return "norm squared", "norm", "The length of what is between the bars, squared."
    if base == r"\nabla" and arg == "2":
        return f"${base}$ squared", "laplacian", _LAPLACIAN
    if arg in _POWERS and not (arg in ("T", "H") and base.isdigit()):
        suffix, hint = _POWERS[arg]
        return f"${base}$ {suffix}", suffix, hint.format(b=base)
    return f"${base}$ to the ${arg}$", "power", ""


def _parses(text: str) -> bool:
    return parses(text)


@dataclass
class Symbol:
    """One ledger row.

    ``key`` is the TeX of the symbol. ``name`` is how it is said, with math
    between ``$`` signs, and is empty for a defined symbol that has no reading.
    ``hint`` is what it means. ``color`` is None for accents and scripts.
    """

    key: str
    name: str
    hint: str
    color: str | None
    defined: bool = False

    @property
    def tip(self) -> str:
        """Plain text for a tooltip: the name, then the meaning."""
        name = plain(self.name) if self.name else plain(f"${self.key}$")
        hint = plain(self.hint)
        if not hint:
            return name
        return f"{name}: {hint}" if not self.name else f"{name}. {hint}"


def symbols(tex: str, *, legend: bool = True, define: Sequence[str] = (), brief: bool = False) -> list[Symbol]:
    """The ledger rows for ``tex``: Greek and named symbols, defined symbols, then accents and scripts.

    ``define`` items are ``"KEY=meaning"``. A key that is already a row gives that
    row its meaning. With ``legend`` false only the defined rows are kept.
    ``brief`` leaves out plain subscripts and powers ("x sub 0", "c squared"):
    the rows left are the ones with something to say.
    """
    greek = [Symbol(f"\\{command}", name, "", color) for command, _glyph, name, color in greek_in(tex)]
    greek += [Symbol(key, name, hint, None) for key, name, hint in named_in(tex)]
    marks = [Symbol(key, name, hint, None) for key, _glyph, name, _color, hint in _notation(tex)]
    rows = greek + marks
    added: list[Symbol] = []
    used = {row.color for row in greek if row.color}
    palette = [color for color in _DEFINED_COLORS if color not in used] or list(_DEFINED_COLORS)
    taken = 0
    for item in define:
        key, sep, meaning = (item or "").partition("=")
        key = key.strip().strip("$").strip()
        meaning = meaning.strip()
        if not sep or not key or not meaning:
            raise FormulaError("--define takes KEY=meaning, for example P=what one token can carry")
        if not parses(f"${key}$"):
            raise FormulaError(f"--define cannot read the symbol {key}")
        if not parses(meaning):
            meaning = meaning.replace("$", r"\$")
        shape = _shape(key)
        row = next((row for row in rows + added if _shape(row.key) == shape), None)
        if row is None:
            row = Symbol(key, "", "", None)
            added.append(row)
        row.hint = meaning
        row.defined = True
        if row.color is None:
            row.color = palette[taken % len(palette)]
            taken += 1
    if brief:
        # A defined symbol speaks for the plain mark it is built on: with
        # \bar{\alpha}_t defined, the generic line about \bar{\alpha} goes.
        defined = [row.key for row in marks if row.defined]
        marks = [
            row
            for row in marks
            if row.defined or (row.hint and not any(key != row.key and key.startswith(row.key) for key in defined))
        ]
    rows = greek + added + marks
    return rows if legend else [row for row in rows if row.defined]


# How many tiers deep a formula may open. A tier that names itself is never opened.
MAX_TIERS = 4


@dataclass
class Block:
    """A formula and the ledger rows under it.

    Each row is ``(index, tier)``: an index into the plan's shared symbol list,
    and the block that symbol opens into, or None.
    """

    tex: str
    rows: list[tuple[int, "Block | None"]] = field(default_factory=list)


def plan(
    tex: str,
    *,
    legend: bool = True,
    define: Sequence[str] = (),
    tier: Sequence[str] = (),
    brief: bool = False,
    known: bool = False,
) -> tuple[Block, list[Symbol]]:
    """The formula, its rows, and the tiers its symbols open into.

    ``tier`` items are ``"KEY=formula"``: what the symbol ``KEY`` is made of. Its
    row then carries ``KEY = formula`` as a formula of its own, with its own rows,
    and a symbol in there may have a tier too. One list of symbols is shared by
    every tier, so a symbol is the same color, and lights up, wherever it appears,
    and it is listed once: under the first formula that has it.

    ``known`` also opens the symbols whose meaning is a formula everyone uses:
    h bar into h over 2 pi, and the Laplacian into its second derivatives. A
    ``tier`` item for the same symbol wins.
    """
    tiers: dict[tuple, tuple[str, str]] = {}
    if known:
        tiers = {_shape(key): (key, inside) for key, inside in _KNOWN_TIERS}
    for item in tier:
        key, sep, inside = (item or "").partition("=")
        key = key.strip().strip("$").strip()
        inside = inside.strip().strip("$").strip()
        if not sep or not key or not inside:
            raise FormulaError("--tier takes KEY=formula, for example P=A_eA_e^\\top")
        if not parses(f"${key}$"):
            raise FormulaError(f"--tier cannot read the symbol {key}")
        if not parses(f"${inside}$"):
            raise FormulaError(f"--tier cannot read the formula for {key}")
        tiers[_shape(key)] = (key, inside)

    define = [item for item in define if item and item.strip()]
    keys = [item.partition("=")[0].strip().strip("$").strip() for item in define]
    registry: list[Symbol] = []
    index_of: dict[tuple, int] = {}
    spent: set[int] = set()

    # Greek keeps its own colors, so a defined symbol never borrows one that is in play.
    everything = " ".join([tex, *(inside for _key, inside in tiers.values())])
    reserved = {found[3] for found in greek_in(everything)}

    def color() -> str:
        used = {row.color for row in registry} | reserved
        free = [candidate for candidate in _DEFINED_COLORS if candidate not in used]
        return free[0] if free else _DEFINED_COLORS[len(registry) % len(_DEFINED_COLORS)]

    def build(text: str, path: frozenset) -> Block:
        formula = layout(f"${text}$", 22)
        here = [i for i, key in enumerate(keys) if key and parses(f"${key}$") and occurrences(formula, key)]
        spent.update(here)
        items = [define[i] for i in here]
        rows = symbols(text, legend=legend, define=items, brief=brief)
        opens = [
            shape
            for shape, (key, _inside) in tiers.items()
            if shape not in path and len(path) < MAX_TIERS and occurrences(formula, key)
        ]
        for shape in opens:
            # A symbol with a tier gets a row and a color even when nothing else is said of it.
            if not any(_shape(row.key) == shape for row in rows):
                known = symbols(text, legend=True, define=items)
                row = next((row for row in known if _shape(row.key) == shape), None)
                rows.append(row or Symbol(tiers[shape][0], "", "", None))
        block = Block(text)
        # List everything this formula has before opening any tier, so a symbol
        # that is in this formula is listed here and not inside a tier that also has it.
        fresh: list[tuple] = []
        for row in rows:
            shape = _shape(row.key)
            if shape in index_of:
                continue
            if shape in opens:
                row.defined = True
            if row.defined and row.key[1:] not in _BY_COMMAND:
                row.color = color()
            index_of[shape] = len(registry)
            registry.append(row)
            fresh.append(shape)
        for shape in fresh:
            row = registry[index_of[shape]]
            inside = build(f"{row.key}={tiers[shape][1]}", path | {shape}) if shape in opens else None
            block.rows.append((index_of[shape], inside))
        return block

    top = build(tex, frozenset())
    # A definition for a symbol that is nowhere still gets its row, as it always did.
    left = [define[i] for i in range(len(define)) if i not in spent]
    for row in symbols(tex, legend=False, define=left) if left else []:
        if _shape(row.key) not in index_of:
            if row.key[1:] not in _BY_COMMAND:
                row.color = color()
            index_of[_shape(row.key)] = len(registry)
            registry.append(row)
            top.rows.append((len(registry) - 1, None))
    return top, registry


def occurrences(formula: Run, key: str, font: str = "sans") -> list[frozenset[int]]:
    """Where the symbol ``key`` sits in ``formula``, as sets of glyph indexes.

    The symbol is typeset on its own and its glyphs are looked for in the
    formula: same font, same character, same relative size, same place relative
    to the first glyph. A script moves a little when it has a neighbor, so the
    place is allowed a third of an em.
    """
    try:
        want = [g for g in layout(f"${key}$", 22, font).glyphs if has_ink(g)]
    except FormulaError:
        return []
    if not want:
        return []
    first = want[0]
    found: list[frozenset[int]] = []
    for i, anchor in enumerate(formula.glyphs):
        if (anchor.font, anchor.num) != (first.font, first.num):
            continue
        scale = anchor.size / first.size
        slack = 0.34 * anchor.size
        members = {i}
        for part in want[1:]:
            x = anchor.x + (part.x - first.x) * scale
            y = anchor.y + (part.y - first.y) * scale
            match = next(
                (
                    j
                    for j, g in enumerate(formula.glyphs)
                    if j not in members
                    and (g.font, g.num) == (part.font, part.num)
                    and abs(g.size - part.size * scale) < 0.05 * g.size
                    and abs(g.x - x) < slack
                    and abs(g.y - y) < slack
                ),
                None,
            )
            if match is None:
                break
            members.add(match)
        else:
            found.append(frozenset(members))
    return found


def _shape(key: str) -> tuple:
    """What a symbol looks like when typeset. Two keys with one shape are one symbol."""
    try:
        run = layout(f"${key}$", 22)
    except FormulaError:
        return (key,)
    # Height but not x: u^\star and u^{\star} are spaced a hair differently.
    return tuple((g.font, g.num, round(g.size, 1), round(g.y)) for g in run.glyphs)


_PLAIN = {
    "star": "★", "ast": "*", "top": "⊤", "intercal": "⊺", "dagger": "†", "prime": "′", "infty": "∞",
    "int": "∫", "oint": "∮", "sum": "∑", "prod": "∏", "to": "→", "uparrow": "↑", "downarrow": "↓",
    "cdot": "·", "times": "×", "pm": "±", "odot": "⊙", "partial": "∂", "nabla": "∇", "ell": "ℓ",
    "hbar": "ℏ", "iint": "∬", "iiint": "∭", "otimes": "⊗", "oplus": "⊕", "langle": "⟨", "rangle": "⟩",
    "max": "max", "min": "min", "lim": "lim", "|": "‖", "varepsilon": "ε",
    "leq": "≤", "geq": "≥", "neq": "≠", "approx": "≈", "propto": "∝", "in": "∈",
}
_COMBINING = {
    "hat": "\u0302", "widehat": "\u0302", "bar": "\u0304", "overline": "\u0304", "tilde": "\u0303",
    "widetilde": "\u0303", "vec": "\u20d7", "dot": "\u0307", "ddot": "\u0308",
}


def plain(text: str) -> str:
    """Tooltip text: TeX between ``$`` signs becomes plain characters where it can."""
    pieces = (text or "").replace(r"\$", "\0").split("$")
    out = [_plain_math(piece) if index % 2 else piece for index, piece in enumerate(pieces)]
    return " ".join("".join(out).replace("\0", "$").split())


def _plain_math(tex: str) -> str:
    def accent(match: re.Match) -> str:
        return match.group(2) + _COMBINING[match.group(1)]

    tex = re.sub(r"\\(" + "|".join(_COMBINING) + r")\{([^{}]*)\}", accent, tex)
    fonts = sorted(_FONTS | {"mathbb", "mathcal", "mathfrak"}, key=len, reverse=True)
    tex = re.sub(r"\\(?:" + "|".join(fonts) + r")(?![A-Za-z])", "", tex).replace(r"\|", "‖")

    def command(match: re.Match) -> str:
        name = match.group(1)
        if name in _BY_COMMAND:
            return _BY_COMMAND[name][0]
        return _PLAIN.get(name, name)

    tex = re.sub(r"\\([A-Za-z]+) ?", command, tex)
    tex = re.sub(r"\\[,;:! ]", " ", tex)
    return re.sub(r"([_^])\{(.)\}", r"\1\2", tex).replace("{", "").replace("}", "")
