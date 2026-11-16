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
import html
import json
import re
from collections.abc import Sequence

from eqlens.constants import defines as constant_defines
from eqlens.credit import LOGO_PNG_BASE64, SIZE, URL
from eqlens.engine import FONTS, FormulaError, Group, Run, Scene, box, has_ink, layout, parses, place, to_png, to_svg
from eqlens.legend import Block, Symbol, occurrences, plan
from eqlens.shader import to_glsl

__all__ = ["FormulaError", "normalize_tex", "render", "render_glsl", "render_html", "render_png", "render_svg"]

_COLOR = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
_MAX_TEX = 8000
_CARD = "#12141a"
# Sizes in points.
_FORMULA, _TIER, _GLYPH, _NAME, _FINE = 22.0, 15.0, 16.0, 12.0, 9.5
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


def render_html(tex: str, **options) -> str:
    """Return an HTML fragment: the SVG with a Copy button, and an Expand button when it has tiers."""
    return render(tex, "html", **options).decode("utf-8")


def render_glsl(tex: str, **options) -> str:
    """Return a WebGL2 fragment shader that draws the formula, with a Shadertoy ``mainImage`` inside."""
    return render(tex, "glsl", **options).decode("utf-8")


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
    tier: Sequence[str] = (),
    credit: bool = True,
    known: bool | None = None,
    constant: Sequence[str] = (),
    shared: Sequence[str] = (),
    _disclose: str | None = None,
) -> bytes:
    """Draw ``tex`` as ``svg``, ``png``, ``html``, or ``glsl`` bytes.

    ``glsl`` is a WebGL2 fragment shader that carries the glyph outlines and
    draws the same picture as the PNG, sharp at any size. Pointing at a symbol
    (``iMouse``) lights it as in the SVG. Its ``mainImage`` pastes into Shadertoy.

    ``html`` is a fragment to put in a page: the SVG under a small bar with a
    Copy button (the TeX goes to the clipboard) and, when there are tiers, an
    Expand button that swaps in the drawing with the tiers open. A symbol that
    opens shows a small triangle when pointed at, and clicking it or its row
    does what Expand does. It is the only output with a script in it.

    ``bg`` None or ``"transparent"`` keeps a bare formula transparent. A card
    (ledger, defined symbols, or notes) is always opaque: ``bg`` or a dark default.
    ``legend`` names Greek, accents, and scripts. ``define`` is ``"KEY=meaning"``
    items. ``brief`` (which turns ``legend`` on) leaves plain subscripts and
    powers out of the ledger. ``notes`` are fine print. ``tips`` adds a browser
    tooltip to each symbol in the SVG. ``tier`` is ``"KEY=formula"`` items:
    what a symbol is made of, drawn under its row as a formula of its own.
    ``credit`` puts the small eqlens mark, a link, in the corner of an SVG card.
    ``known`` opens symbols whose meaning is a well-known formula, such as h bar
    into h over 2 pi. Left as None it is on for ``html``, where tiers start shut,
    and off for ``svg`` and ``png``, where they would make every card taller.
    ``constant`` names constants from the built-in table, such as ``c`` or
    ``k_B``: each gets its meaning and value without anyone typing a number.
    ``shared`` is ``"KEY=meaning"`` items from a symbols file: one is used only
    where its symbol appears, and ``define`` wins for the same symbol. ``font`` is one of ``sans``, ``serif``,
    ``stix``, ``cm``. ``dpi`` only matters for PNG.
    """
    if fmt not in ("svg", "png", "html", "glsl"):
        raise FormulaError("format must be svg, png, html, or glsl")
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
    # A constant is a define the library writes; one of the caller's own for the same symbol is read later and wins.
    define = constant_defines(constant) + [item for item in define if item and item.strip()]
    shared = [item for item in shared if item and item.strip()]

    tier = [item for item in tier if item and item.strip()]

    if fmt == "html":
        options = dict(dpi=dpi, color=color, bg=bg, legend=legend, notes=notes, define=define, font=font)
        options.update(brief=brief, tips=tips, credit=credit, shared=shared)
        opens = known is not False
        wide = render(text, "svg", tier=tier, known=opens, _disclose="open", **options).decode("utf-8")
        if _tiers(wide):
            shut = render(text, "svg", tier=tier, known=opens, _disclose="shut", **options).decode("utf-8")
        else:
            wide = ""
            shut = render(text, "svg", known=False, **options).decode("utf-8")
        return _html(text[1:-1].strip(), shut, wide).encode("utf-8")

    formula = layout(text, _FORMULA, font)
    top, rows = plan(text[1:-1], legend=legend or brief, define=define, tier=tier, brief=brief, known=bool(known), shared=shared)
    card = bool(rows or notes)
    if card:
        bg = bg or _CARD
    scene = _scene(formula, top, rows, notes, font, card, _disclose)
    if fmt == "png":
        return to_png(scene, dpi=dpi, fg=color, bg=bg)
    if fmt == "glsl":
        return to_glsl(scene, label=text[1:-1].strip(), fg=color, bg=bg).encode("utf-8")
    mark = None
    if card and credit:
        # Room under the last line, then the mark in the corner.
        scene.height += 14.0
        mark = (scene.width - SIZE - 8.0, scene.height - SIZE - 8.0, SIZE, URL, LOGO_PNG_BASE64)
    seed = json.dumps([text, legend, brief, notes, define, shared, tier, color, bg, font, tips, credit, bool(known), _disclose])
    uid = "eq" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:8]
    return to_svg(scene, uid=uid, label=text[1:-1].strip(), fg=color, bg=bg, tips=tips, credit=mark).encode("utf-8")


_STYLE = (
    ".eqlens{margin:0}"
    ".eqlens-bar{display:flex;justify-content:flex-end;gap:6px;margin:0 0 6px}"
    ".eqlens-bar button{font:500 12px/1 system-ui,sans-serif;color:var(--eq-dim,#8b949e);background:transparent;"
    "border:1px solid currentColor;border-radius:6px;padding:5px 9px;cursor:pointer;opacity:.75}"
    ".eqlens-bar button:hover,.eqlens-bar button:focus-visible{opacity:1;color:var(--eq-fg,#f2f2f7)}"
    ".eqlens svg{max-width:100%;height:auto}"
    ".eqlens [hidden]{display:none}"
)
# One listener for every eqlens figure on the page, however many fragments carry this script.
_SCRIPT = (
    "(function(){if(window.__eqlens)return;window.__eqlens=1;"
    "document.addEventListener('click',function(e){"
    "if(!e.target.closest)return;"
    "function flip(f){var o=f.querySelector('.eqlens-open'),c=f.querySelector('.eqlens-closed'),"
    "k=f.querySelector('.eqlens-expand'),open=o.hidden;o.hidden=!open;c.hidden=open;"
    "k.setAttribute('aria-expanded',String(open));k.textContent=open?'Collapse':'Expand'}"
    # A symbol that opens, or its row, does what the Expand button does.
    "var x=e.target.closest('.eqlens svg .x');if(x){flip(x.closest('.eqlens'));return}"
    "var b=e.target.closest('.eqlens-bar button');if(!b)return;"
    "var f=b.closest('.eqlens');"
    "if(b.classList.contains('eqlens-expand')){flip(f);return}"
    "var t=f.getAttribute('data-tex');"
    "function done(){b.textContent='Copied';setTimeout(function(){b.textContent='Copy'},1200)}"
    "function old(){var a=document.createElement('textarea');a.value=t;a.style.position='fixed';"
    "a.style.opacity='0';document.body.appendChild(a);a.select();"
    "try{document.execCommand('copy');done()}catch(_){}a.remove()}"
    "if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(t).then(done,old)}"
    "else{old()}"
    "})})();"
)


def _tiers(svg: str) -> int:
    """How many tiers a drawing has open: each one has a rule down its side."""
    return svg.count('<g class="t">')


def _html(tex: str, shut: str, wide: str) -> str:
    """The fragment: a bar of buttons, the drawing, and the drawing with its tiers open."""
    expand = '<button type="button" class="eqlens-expand" aria-expanded="false">Expand</button>' if wide else ""
    opened = f'<div class="eqlens-open" hidden>{wide.strip()}</div>' if wide else ""
    return (
        f'<figure class="eqlens" data-tex="{html.escape(tex, quote=True)}">'
        f'<div class="eqlens-bar">{expand}'
        '<button type="button" class="eqlens-copy" aria-label="Copy the TeX of this formula">Copy</button></div>'
        f'<div class="eqlens-closed">{shut.strip()}</div>{opened}</figure>'
        f"<style>{_STYLE}</style><script>{_SCRIPT}</script>\n"
    )


def _openable(block: Block, deep: bool) -> set[int]:
    """The symbols that open into a tier: on this block, and in its tiers too when ``deep``."""
    found: set[int] = set()
    for index, tier in block.rows:
        if tier:
            found.add(index)
            if deep:
                found |= _openable(tier, deep)
    return found


def _scene(
    formula, top: Block, rows: list[Symbol], notes: list[str], font: str, card: bool, disclose: str | None = None
) -> Scene:
    """``disclose`` is None for a plain drawing with every tier open, ``"shut"`` for
    one with the tiers shut and a triangle on each row that opens, or ``"open"``
    for the tiers open and a triangle that shuts them."""
    pad = _CARD_PAD if card else _PAD
    click = _openable(top, deep=disclose == "open") if disclose else set()
    lines = [layout(note if parses(note) else note.replace("$", r"\$"), _FINE, font) for note in notes]
    # Lay the ledger out once to learn how wide it is, then again where it goes.
    ledger_width, _bottom = _ledger(Scene(0.0, 0.0), top, rows, 0.0, 0.0, font, disclose, click)
    under = max([ledger_width, *(line.width for line in lines)], default=0.0)
    inner = max(formula.width, under)
    width = inner + 2 * pad
    # The ledger and notes start under the formula's left edge when they fit there.
    formula_x = pad + (inner - formula.width) / 2
    left = formula_x if formula_x + under <= width - pad else pad

    scene = Scene(width, 0.0)
    y = pad
    _formula_groups(scene, formula, rows, formula_x, y + formula.ascent, font, click)
    y += formula.ascent + formula.descent

    if top.rows:
        _width, y = _ledger(scene, top, rows, left, y + _SECTION, font, disclose, click)
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


def _ledger(
    scene: Scene,
    block: Block,
    rows: list[Symbol],
    left: float,
    y: float,
    font: str,
    disclose: str | None = None,
    click: frozenset[int] | set[int] = frozenset(),
) -> tuple[float, float]:
    """Draw a block's rows from ``(left, y)`` down. Return how wide they are and where they end.

    A row with a tier is followed by that tier's formula and rows, set in under
    the row's text, with a rule down the side to show what they belong to.
    """
    runs = [_row_runs(rows[index], font) for index, _tier in block.rows]
    glyph_width = max((glyph.width for glyph, _main, _fine in runs), default=0.0)
    text_x = left + glyph_width + _COLUMN
    right = left
    for (index, tier), (glyph, main, fine) in zip(block.rows, runs):
        row = rows[index]
        top = y
        ascent = max(glyph.ascent, main.ascent, _NAME * 0.75)
        descent = max(glyph.descent, main.descent, _NAME * 0.25)
        group = Group("r", syms=(index,), tip=row.tip)
        _add(group, glyph, left, y + ascent, row.color or "mark")
        _add(group, main, text_x, y + ascent, "fg")
        y += ascent + descent
        if fine:
            y += 4.0
            _add(group, fine, text_x, y + fine.ascent, "dim")
            y += fine.ascent + fine.descent
        reach = text_x + max(main.width, fine.width if fine else 0.0)
        if tier and disclose:
            # A triangle after the name: pointing right when shut, down when open.
            group.extra = "x"
            arrow = layout(r"$\blacktriangleright$" if disclose == "shut" else r"$\blacktriangledown$", 8.0, font)
            sign = Group("v", syms=(index,))
            at = text_x + main.width + (7.0 if main.width else 0.0)
            _add(sign, arrow, at, top + ascent - 1.0, "dim")
            scene.groups.append(sign)
            reach = max(reach, at + arrow.width)
        group.hit = (left - 6, top - _ROW / 2, reach - left + 12, y - top + _ROW)
        scene.groups.append(group)
        right = max(right, reach)
        if tier and disclose != "shut":
            y += _ROW
            inside_top = y
            inside = layout(f"${tier.tex}$", _TIER, font)
            _formula_groups(scene, inside, rows, text_x, y + inside.ascent, font, click)
            y += inside.ascent + inside.descent
            right = max(right, text_x + inside.width)
            if tier.rows:
                width, y = _ledger(scene, tier, rows, text_x, y + _ROW + 2.0, font, disclose, click)
                right = max(right, text_x + width)
            scene.groups.append(Group("t", rules=[(text_x - 11.0, inside_top - 2.0, 1.2, y - inside_top + 4.0, "dim")]))
            y += 4.0
        y += _ROW
    return right - left, y - _ROW


def _row_runs(row: Symbol, font: str):
    """A row's glyph, its main line, and its fine line (or None)."""
    glyph = layout(f"${row.key}$", _GLYPH, font)
    if row.name:
        return glyph, layout(row.name, _NAME, font), layout(row.hint, _FINE, font) if row.hint else None
    if row.hint:
        return glyph, layout(row.hint, _NAME, font), None
    return glyph, Run(0.0, 0.0, 0.0, (), ()), None


def _formula_groups(
    scene: Scene, formula, rows: list[Symbol], x: float, baseline: float, font: str, click=frozenset()
) -> None:
    """One group per glyph, so each can carry its own color, symbols, and tooltip."""
    member: dict[int, list[tuple[int, int]]] = {}
    places = [occurrences(formula, row.key, font) for row in rows]
    for index, row in enumerate(rows):
        for found in places[index]:
            # R and R_{\mu\nu} are two things when both are given a meaning: the R
            # inside R_{\mu\nu} is not the first one. A_e inside A_e^\top still is A_e,
            # because nobody gave A_e^\top a meaning of its own.
            if row.defined and any(
                other is not row and other.defined and any(found < bigger for bigger in places[at])
                for at, other in enumerate(rows)
            ):
                continue
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
        if any(index in click for _size, index in owners):
            group.extra = "x"
        if owners:
            # Widest reading first: "A sub e transpose" before "A sub e".
            group.tip = "\n".join(rows[index].tip for _size, index in sorted(owners, reverse=True))
            group.hit = box(mark)
        scene.groups.append(group)


def _add(group: Group, run, x: float, baseline: float, fill: str) -> None:
    marks, rules = place(run, x, baseline, fill)
    group.marks += marks
    group.rules += rules
