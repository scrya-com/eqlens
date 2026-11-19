"""Lay a formula out once, then draw it as SVG or as PNG.

matplotlib mathtext does the typesetting and hands back every glyph with its
font, size, and position. This module keeps those glyphs as a scene: the SVG
writer turns each into a ``<use>`` that can be colored and hovered, and the PNG
writer fills the same outlines, so the two outputs are the same picture.

Units are points. A ``Run`` has its origin on the baseline with y up, the way
mathtext reports it. A ``Scene`` has its origin at the top left with y down.
"""

from __future__ import annotations

import io
import threading
from dataclasses import dataclass, field
from functools import lru_cache
from xml.sax.saxutils import escape, quoteattr

import matplotlib

matplotlib.use("Agg")
import matplotlib.ft2font as ft2font
import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.font_manager import FontProperties
from matplotlib.mathtext import MathTextParser
from matplotlib.patches import PathPatch
from matplotlib.path import Path

# Name, mathtext font set, and the family for words outside ``$...$``.
FONTS = {
    "sans": ("dejavusans", "DejaVu Sans"),
    "serif": ("dejavuserif", "DejaVu Serif"),
    "stix": ("stix", "STIXGeneral"),
    "cm": ("cm", "DejaVu Serif"),
}
# Fill roles. A fill is one of these names or a ``#rrggbb`` color.
ROLES = {"fg": "#f2f2f7", "dim": "#8b949e", "mark": "#c9d1d9"}

LOCK = threading.RLock()
_PARSER = MathTextParser("path")
_UNIT = 100.0
_FACES: dict[str, object] = {}
try:
    _NO_HINTING = ft2font.LoadFlags.NO_HINTING
except AttributeError:  # matplotlib before 3.10
    _NO_HINTING = ft2font.LOAD_NO_HINTING


class FormulaError(ValueError):
    """The formula is empty or mathtext cannot parse it."""


@dataclass(frozen=True)
class Glyph:
    """``index`` is the glyph's index in its font, or -1 when matplotlib gives only ``num``."""

    font: str
    num: int
    size: float
    x: float
    y: float
    index: int = -1


@dataclass(frozen=True)
class Run:
    """One typeset string: its box, its glyphs, and its rules (fraction bars)."""

    width: float
    ascent: float
    descent: float
    glyphs: tuple[Glyph, ...]
    rules: tuple[tuple[float, float, float, float], ...]


@dataclass
class Mark:
    """A glyph placed in a scene. ``y`` is the baseline, measured down from the top."""

    font: str
    num: int
    scale: float
    x: float
    y: float
    fill: str
    index: int = -1


@dataclass
class Group:
    """Marks that hover together: one formula glyph, one ledger row, or the notes.

    ``kind`` is ``f`` for a formula, ``r`` for a ledger row, ``n`` for notes,
    ``t`` for the rule down the side of a tier, and ``v`` for the small triangle
    that says a row opens. (``d`` and ``k`` are taken: they are the fill classes
    for dim and mark-colored ink, and a kind must never share a name with one.) ``extra`` is one more class; ``x`` marks what can be
    clicked to open or shut the tiers.
    ``syms`` are the indexes of the symbols this group belongs to.
    """

    kind: str
    marks: list[Mark] = field(default_factory=list)
    rules: list[tuple[float, float, float, float, str]] = field(default_factory=list)
    syms: tuple[int, ...] = ()
    tip: str = ""
    hit: tuple[float, float, float, float] | None = None
    extra: str = ""


@dataclass
class Scene:
    width: float
    height: float
    groups: list[Group] = field(default_factory=list)


def layout(text: str, size: float, font: str = "sans") -> Run:
    """Typeset ``text``. Math goes between ``$`` signs; the rest is plain words."""
    math, family = FONTS[font]
    prop = FontProperties(family=family, size=size, math_fontfamily=math)
    with LOCK:
        try:
            parsed = _PARSER.parse(text, dpi=72, prop=prop)
        except Exception as exc:
            raise FormulaError(" ".join(str(exc).split()) or "could not parse formula") from exc
        glyphs = []
        for item in parsed.glyphs:
            # matplotlib 3.11 adds the glyph index: (font, size, char, index, x, y).
            face, size_, num = item[:3]
            index = int(item[3]) if len(item) == 6 else -1
            x, y = item[-2:]
            _FACES.setdefault(face.fname, face)
            glyphs.append(Glyph(face.fname, int(num), float(size_), float(x), float(y), index))
    rules = tuple((float(x), float(y), float(w), float(h)) for x, y, w, h in parsed.rects)
    depth = float(parsed.depth)
    return Run(float(parsed.width), float(parsed.height) - depth, depth, tuple(glyphs), rules)


def parses(text: str) -> bool:
    try:
        layout(text, 12)
    except FormulaError:
        return False
    return True


@lru_cache(maxsize=4096)
def outline(font: str, num: int, index: int = -1) -> tuple[np.ndarray, np.ndarray]:
    """The glyph's outline at 100 pt, y up. Empty for a space."""
    with LOCK:
        face = _FACES[font]
        face.set_size(_UNIT, 72)
        if index >= 0:
            face.load_glyph(index, flags=_NO_HINTING)
        else:
            face.load_char(num, flags=_NO_HINTING)
        verts, codes = face.get_path()
    return np.array(verts, dtype=float).reshape(-1, 2), np.array(codes, dtype=np.uint8)


def has_ink(glyph: Glyph) -> bool:
    """False for a space."""
    return len(outline(glyph.font, glyph.num, glyph.index)[0]) > 0


def place(run: Run, x: float, baseline: float, fill: str) -> tuple[list[Mark], list[tuple[float, float, float, float, str]]]:
    """Put a run in scene coordinates. Spaces are dropped."""
    marks = [
        Mark(g.font, g.num, g.size / _UNIT, x + g.x, baseline - g.y, fill, g.index)
        for g in run.glyphs
        if has_ink(g)
    ]
    rules = [(x + rx, baseline - ry - rh, rw, rh, fill) for rx, ry, rw, rh in run.rules]
    return marks, rules


def box(mark: Mark, pad: float = 1.0) -> tuple[float, float, float, float]:
    """The mark's ink box in scene coordinates, a little larger so it is easy to point at."""
    verts, _codes = outline(mark.font, mark.num, mark.index)
    left, bottom = verts.min(axis=0) * mark.scale
    right, top = verts.max(axis=0) * mark.scale
    return (mark.x + left - pad, mark.y - top - pad, right - left + 2 * pad, top - bottom + 2 * pad)


def to_svg(
    scene: Scene,
    *,
    uid: str,
    label: str,
    fg: str,
    bg: str | None,
    tips: bool = False,
    credit: tuple[float, float, float, str, str] | None = None,
    desc: str = "",
) -> str:
    """One self-contained SVG. ``uid`` scopes its ids and CSS so many can share a page.

    Colors fall back to the ones given here. A page that inlines the SVG can set
    ``--eq-fg``, ``--eq-bg``, ``--eq-dim``, and ``--eq-mark`` to restyle it.
    Hover needs the SVG inline or opened on its own. Inside ``<img>`` it is a still.
    ``tips`` adds a browser tooltip to each symbol. It is off by default: the
    ledger row that lights up already says the same thing, and a tooltip covers it.
    ``credit`` is ``(x, y, size, url, png_base64)``: a small picture that links out.
    ``desc`` is the formula in words, for a screen reader. It draws nothing.
    """
    ids: dict[tuple[str, int, int], str] = {}
    body: list[str] = []
    count = 0
    for group in scene.groups:
        count = max([count, *(index + 1 for index in group.syms)])
        classes = group.kind + "".join(f" s{index}" for index in group.syms) + (" h" if group.syms else "")
        if group.extra:
            classes += " " + group.extra
        body.append(f'<g class="{classes}">')
        if tips and group.tip:
            body.append(f"<title>{escape(group.tip)}</title>")
        if group.hit:
            x, y, w, h = group.hit
            body.append(f'<rect class="hit" x="{_n(x)}" y="{_n(y)}" width="{_n(w)}" height="{_n(h)}"/>')
        for x, y, w, h, fill in group.rules:
            body.append(f'<rect x="{_n(x)}" y="{_n(y)}" width="{_n(w)}" height="{_n(h)}"{_fill(fill)}/>')
        for mark in group.marks:
            key = (mark.font, mark.num, mark.index)
            if key not in ids:
                ids[key] = f"{uid}g{len(ids)}"
            body.append(
                f'<use xlink:href="#{ids[key]}" transform="translate({_n(mark.x)} {_n(mark.y)}) '
                f'scale({mark.scale:.4g})"{_fill(mark.fill)}/>'
            )
        body.append("</g>")

    css = [
        f".{uid}{{fill:var(--eq-fg,{fg})}}",
        f".{uid} .d{{fill:var(--eq-dim,{ROLES['dim']})}}",
        f".{uid} .k{{fill:var(--eq-mark,{ROLES['mark']})}}",
        f".{uid} .hit{{fill:none;pointer-events:all}}",
    ]
    if bg:
        css.append(f".{uid} .bg{{fill:var(--eq-bg,{bg})}}")
    if any(group.kind == "v" for group in scene.groups):
        # The triangle shows when its symbol is pointed at, and always where there is no pointer.
        css += [
            f".{uid} .v{{opacity:0;transition:opacity .12s}}",
            f"@media (hover:none){{.{uid} .v{{opacity:.7}}}}",
            f".{uid} .x{{cursor:pointer}}",
        ]
    if count:
        lit = ",".join(f".{uid}:has(.s{index}:hover) .s{index}" for index in range(count))
        css += [
            f".{uid} .f,.{uid} .r{{transition:opacity .12s}}",
            f".{uid}:has(.h:hover) :is(.f,.r){{opacity:.28}}",
            f"{lit}{{opacity:1}}",
        ]
    if credit:
        x, y, size, url, picture = credit
        css += [f".{uid} .cr{{opacity:.45;transition:opacity .12s}}", f".{uid} .cr:hover{{opacity:1}}"]
        body.append(
            f'<a class="cr" href={quoteattr(url)} xlink:href={quoteattr(url)} target="_blank" rel="noopener" '
            f'aria-label="Drawn with eqlens"><image x="{_n(x)}" y="{_n(y)}" width="{_n(size)}" height="{_n(size)}" '
            f'href="data:image/png;base64,{picture}" xlink:href="data:image/png;base64,{picture}"/></a>'
        )
    defs = "".join(f'<path id="{name}" d="{_d(*outline(*key))}"/>' for key, name in ids.items())
    width, height = _n(scene.width), _n(scene.height)
    backdrop = f'<rect class="bg" width="{width}" height="{height}"/>' if bg else ""
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'class="{uid}" viewBox="0 0 {width} {height}" width="{_n(scene.width * 4 / 3)}" '
        f'height="{_n(scene.height * 4 / 3)}" role="img" aria-label={quoteattr(label)}>'
        + (f"<desc>{escape(desc)}</desc>" if desc else "")
        + f"<style>{''.join(css)}</style><defs>{defs}</defs>{backdrop}{''.join(body)}</svg>\n"
    )


def to_png(scene: Scene, *, dpi: int, fg: str, bg: str | None) -> bytes:
    """Fill the same outlines the SVG uses."""
    with LOCK:
        figure = _painted(scene, dpi, fg, bg)
        out = io.BytesIO()
        figure.savefig(out, format="png", dpi=dpi, transparent=not bg, facecolor=bg or "none")
    return out.getvalue()


def to_rgba(scene: Scene, *, dpi: float, fg: str) -> np.ndarray:
    """The same picture as rows of RGBA pixels on a clear ground, for a text drawing."""
    with LOCK:
        figure = _painted(scene, dpi, fg, None)
        figure.canvas.draw()
        return np.asarray(figure.canvas.buffer_rgba()).copy()


def _painted(scene: Scene, dpi: float, fg: str, bg: str | None) -> Figure:
    colors = dict(ROLES, fg=fg)
    by_color: dict[str, list[Path]] = {}
    for group in scene.groups:
        for mark in group.marks:
            verts, codes = outline(mark.font, mark.num, mark.index)
            placed = verts * (mark.scale, -mark.scale) + (mark.x, mark.y)
            by_color.setdefault(colors.get(mark.fill, mark.fill), []).append(Path(placed, codes))
        for x, y, w, h, fill in group.rules:
            corners = [(x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y)]
            by_color.setdefault(colors.get(fill, fill), []).append(Path(corners, closed=True))
    figure = Figure(figsize=(scene.width / 72, scene.height / 72), dpi=dpi)
    FigureCanvasAgg(figure)
    if bg:
        figure.patch.set_facecolor(bg)
    else:
        figure.patch.set_alpha(0)
    axes = figure.add_axes((0, 0, 1, 1))
    axes.axis("off")
    axes.set_xlim(0, scene.width)
    axes.set_ylim(scene.height, 0)
    for color, paths in by_color.items():
        axes.add_patch(PathPatch(Path.make_compound_path(*paths), facecolor=color, edgecolor="none", linewidth=0))
    return figure


def _fill(fill: str) -> str:
    if fill == "fg":
        return ""
    if fill == "dim":
        return ' class="d"'
    if fill == "mark":
        return ' class="k"'
    return f' fill="{fill}"'


def _n(value: float) -> str:
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


def _d(verts: np.ndarray, codes: np.ndarray) -> str:
    """SVG path data for an outline, flipped so y runs down."""
    parts: list[str] = []
    i = 0
    while i < len(codes):
        code = int(codes[i])
        if code == Path.CLOSEPOLY:
            parts.append("Z")
            i += 1
            continue
        letter, points = {Path.MOVETO: ("M", 1), Path.LINETO: ("L", 1), Path.CURVE3: ("Q", 2), Path.CURVE4: ("C", 3)}[code]
        coords = " ".join(f"{_n(round(x, 1))} {_n(round(-y, 1))}" for x, y in verts[i : i + points])
        parts.append(letter + coords)
        i += points
    return "".join(parts)
