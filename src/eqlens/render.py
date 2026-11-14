"""Render one matplotlib mathtext formula to SVG or PNG.

This is not a TeX install. matplotlib.mathtext draws a single formula:
fractions, roots, integrals, Greek, subscripts, superscripts, \\mathrm, and
\\text. It rejects preamble commands, \\begin environments, and user macros.

With a ledger, defined symbols, or notes the formula sits on a dark card. The
formula wears the ledger's colors. In the SVG, pointing at a symbol lights it,
its other appearances, and its row. Tooltips are off unless ``tips`` is set.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence

from eqlens.engine import FONTS, FormulaError, Group, Scene, box, has_ink, layout, parses, place, to_png, to_svg
from eqlens.legend import Symbol, occurrences, symbols

__all__ = ["FormulaError", "normalize_tex", "render", "render_png", "render_svg"]

_COLOR = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
_MAX_TEX = 8000
_CARD = "#12141a"
# Sizes in points.
_FORMULA, _GLYPH, _NAME, _FINE = 22.0, 16.0, 12.0, 9.5
_PAD, _CARD_PAD = 12.0, 24.0
_SECTION, _ROW, _COLUMN, _LINE = 20.0, 11.0, 26.0, 6.0


def normalize_tex(tex: str) -> str:
    text = (tex or "").strip()
    if not text:
        raise FormulaError("empty formula")
    if len(text) > _MAX_TEX:
        raise FormulaError("formula too long")
    if text.startswith("$$") and text.endswith("$$"):
        text = "$" + text[2:-2].strip() + "$"
    elif not (text.startswith("$") and text.endswith("$")):
        text = f"${text}$"
    if text == "$$" or text == "$":
        raise FormulaError("empty formula")
    return text


def _check_color(value: str, label: str) -> str:
    if not _COLOR.match(value or ""):
        raise FormulaError(f"{label} must be #rgb or #rrggbb")
    return value


def render_svg(tex: str, **options) -> str:
    """Return an SVG document. See ``render`` for the options."""
    return render(tex, "svg", **options).decode("utf-8")


def render_png(tex: str, **options) -> bytes:
    """Return a PNG. See ``render`` for the options."""
    return render(tex, "png", **options)


def render(
    tex: str,
    fmt: str = "svg",
    *,
    dpi: int = 220,
    color: str = "#f2f2f7",
    bg: str | None = None,
    legend: bool = False,
    notes: Sequence[str] = (),
    define: Sequence[str] = (),
    font: str = "sans",
    brief: bool = False,
    tips: bool = False,
) -> bytes:
    """Draw ``tex`` as ``svg`` or ``png`` bytes.

    ``bg`` None or ``"transparent"`` keeps a bare formula transparent. A card
    (ledger, defined symbols, or notes) is always opaque: ``bg`` or a dark default.
    ``legend`` names Greek, accents, and scripts. ``define`` is ``"KEY=meaning"``
    items. ``brief`` (which turns ``legend`` on) leaves plain subscripts and
    powers out of the ledger. ``notes`` are fine print. ``tips`` adds a browser
    tooltip to each symbol in the SVG. ``font`` is one of ``sans``, ``serif``,
    ``stix``, ``cm``. ``dpi`` only matters for PNG.
    """
    if fmt not in ("svg", "png"):
        raise FormulaError("format must be svg or png")
    if not isinstance(dpi, int) or isinstance(dpi, bool) or not 72 <= dpi <= 600:
        raise FormulaError("dpi must be an integer from 72 to 600")
    if font not in FONTS:
        raise FormulaError("font must be one of " + ", ".join(FONTS))
    color = _check_color(color, "color")
    if bg in (None, "", "transparent"):
        bg = None
    else:
        bg = _check_color(bg, "bg")
    text = normalize_tex(tex)
    notes = [note.strip() for note in notes if note and note.strip()]
    define = [item for item in define if item and item.strip()]

    formula = layout(text, _FORMULA, font)
    rows = symbols(text[1:-1], legend=legend or brief, define=define, brief=brief)
    card = bool(rows or notes)
    if card:
        bg = bg or _CARD
    scene = _scene(formula, rows, notes, font, card)
    if fmt == "png":
        return to_png(scene, dpi=dpi, fg=color, bg=bg)
    seed = json.dumps([text, legend, brief, notes, define, color, bg, font, tips])
    uid = "eq" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:8]
    return to_svg(scene, uid=uid, label=text[1:-1].strip(), fg=color, bg=bg, tips=tips).encode("utf-8")


def _scene(formula, rows: list[Symbol], notes: list[str], font: str, card: bool) -> Scene:
    pad = _CARD_PAD if card else _PAD
    ledger = [_row_runs(row, font) for row in rows]
    lines = [layout(note if parses(note) else note.replace("$", r"\$"), _FINE, font) for note in notes]
    glyph_width = max((glyph.width for glyph, _main, _fine in ledger), default=0.0)
    text_width = max((max(main.width, fine.width if fine else 0.0) for _glyph, main, fine in ledger), default=0.0)
    ledger_width = glyph_width + _COLUMN + text_width if ledger else 0.0
    under = max([ledger_width, *(line.width for line in lines)], default=0.0)
    inner = max(formula.width, under)
    width = inner + 2 * pad
    # The ledger and notes start under the formula's left edge when they fit there.
    formula_x = pad + (inner - formula.width) / 2
    left = formula_x if formula_x + under <= width - pad else pad

    scene = Scene(width, 0.0)
    y = pad
    _formula_groups(scene, formula, rows, formula_x, y + formula.ascent, font)
    y += formula.ascent + formula.descent

    if ledger:
        y += _SECTION
        for index, (glyph, main, fine) in enumerate(ledger):
            row = rows[index]
            top = y
            ascent = max(glyph.ascent, main.ascent, _NAME * 0.75)
            descent = max(glyph.descent, main.descent, _NAME * 0.25)
            group = Group("r", syms=(index,), tip=row.tip)
            _add(group, glyph, left, y + ascent, row.color or "mark")
            _add(group, main, left + glyph_width + _COLUMN, y + ascent, "fg")
            y += ascent + descent
            if fine:
                y += 4.0
                _add(group, fine, left + glyph_width + _COLUMN, y + fine.ascent, "dim")
                y += fine.ascent + fine.descent
            group.hit = (left - 6, top - _ROW / 2, ledger_width + 12, y - top + _ROW)
            scene.groups.append(group)
            y += _ROW
        y -= _ROW
    if lines:
        y += _SECTION
        group = Group("n")
        for line in lines:
            ascent = max(line.ascent, _FINE * 0.75)
            _add(group, line, left, y + ascent, "dim")
            y += ascent + max(line.descent, _FINE * 0.25) + _LINE
        y -= _LINE
        scene.groups.append(group)
    scene.height = y + pad
    return scene


def _row_runs(row: Symbol, font: str):
    """A row's glyph, its main line, and its fine line (or None)."""
    glyph = layout(f"${row.key}$", _GLYPH, font)
    if row.name:
        return glyph, layout(row.name, _NAME, font), layout(row.hint, _FINE, font) if row.hint else None
    return glyph, layout(row.hint, _NAME, font), None


def _formula_groups(scene: Scene, formula, rows: list[Symbol], x: float, baseline: float, font: str) -> None:
    """One group per glyph, so each can carry its own color, symbols, and tooltip."""
    member: dict[int, list[tuple[int, int]]] = {}
    for index, row in enumerate(rows):
        for found in occurrences(formula, row.key, font):
            for glyph in found:
                member.setdefault(glyph, []).append((len(found), index))
    marks, rules = place(formula, x, baseline, "fg")
    if rules:
        scene.groups.append(Group("f", rules=rules))
    # place() drops spaces, so walk the glyphs that have ink in the same order.
    inked = [i for i, glyph in enumerate(formula.glyphs) if has_ink(glyph)]
    for i, mark in zip(inked, marks):
        owners = sorted(member.get(i, []))
        colored = [index for _size, index in owners if rows[index].color]
        if colored:
            mark.fill = rows[colored[0]].color
        group = Group("f", marks=[mark], syms=tuple(sorted({index for _size, index in owners})))
        if owners:
            # Widest reading first: "A sub e transpose" before "A sub e".
            group.tip = "\n".join(rows[index].tip for _size, index in sorted(owners, reverse=True))
            group.hit = box(mark)
        scene.groups.append(group)


def _add(group: Group, run, x: float, baseline: float, fill: str) -> None:
    marks, rules = place(run, x, baseline, fill)
    group.marks += marks
    group.rules += rules
