"""Draw a formula in a terminal that cannot paint pixels.

The formula is drawn with braille characters: each one is a block of two dots
by four, so a line of text holds four rows of dots. A character takes the color
of the ink under it, so each symbol keeps its ledger color. The ledger and the
notes are plain lines of text under it.

``comment`` writes the same drawing, without color, as a comment for a source
file, and ``burn`` puts it at the head of one.
"""

from __future__ import annotations

import math
import os
from typing import Sequence

import numpy as np

from eqlens.constants import defines as constant_defines
from eqlens.engine import FormulaError, Scene, layout, to_rgba
from eqlens.legend import plain, plan

# Dots across one unit of the formula's type size. Under about 9 the scripts stop being read.
DOTS = 24.0
_LEAST = 14.0
_SIZE = 22.0
_INK = 96
# The braille dot each place in a 2 by 4 block stands for, by (row, column).
_BITS = ((0x01, 0x08), (0x02, 0x10), (0x04, 0x20), (0x40, 0x80))
_FG = "#f2f2f7"
_INK_RGB = (0xF2, 0xF2, 0xF7)


def cells(
    tex: str,
    *,
    columns: int = 80,
    legend: bool = False,
    brief: bool = False,
    define: Sequence[str] = (),
    tier: Sequence[str] = (),
    constant: Sequence[str] = (),
    shared: Sequence[str] = (),
    notes: Sequence[str] = (),
    font: str = "sans",
) -> dict:
    """The formula as lines of colored runs, with its ledger and notes as words.

    ``picture`` is a list of lines, each a list of ``[text, color]`` runs. A
    color of None is plain ink: the terminal's own text color, light or dark.
    ``ledger`` is one ``{"glyph", "color", "words"}`` per row. ``fits`` is False
    when the formula had to be drawn smaller than reads well: widen the terminal.
    """
    from eqlens.render import _formula_groups, normalize_tex

    if not isinstance(columns, int) or isinstance(columns, bool) or not 20 <= columns <= 400:
        raise FormulaError("columns must be a whole number from 20 to 400")
    text = normalize_tex(tex)
    define = constant_defines(constant) + [item for item in define if item and item.strip()]
    shared = [item for item in shared if item and item.strip()]
    tier = [item for item in tier if item and item.strip()]
    formula = layout(text, _SIZE, font)
    _top, rows = plan(text[1:-1], legend=legend or brief, define=define, tier=tier, brief=brief, shared=shared)

    scene = Scene(formula.width + 2.0, formula.ascent + formula.descent + 2.0)
    _formula_groups(scene, formula, rows, 1.0, 1.0 + formula.ascent, font)
    dots = min(DOTS, 2 * columns * _SIZE / scene.width)
    pixels = to_rgba(scene, dpi=72.0 * dots / _SIZE, fg=_FG)
    return {
        "tex": text[1:-1].strip(),
        "picture": _braille(pixels),
        "ledger": [
            {"glyph": plain(f"${row.key}$"), "color": row.color, "words": _words(row)} for row in rows
        ],
        "notes": [plain(note) for note in notes if note and note.strip()],
        "fits": dots >= _LEAST,
    }


def ansi(found: dict, *, color: bool = True) -> str:
    """``cells`` as text for a terminal, in 24-bit color unless ``color`` is False."""
    lines = ["".join(_paint(text, tint, color) for text, tint in line) for line in found["picture"]]
    if found["ledger"]:
        lines.append("")
        width = max(len(row["glyph"]) for row in found["ledger"])
        for row in found["ledger"]:
            lines.append("  " + _paint(row["glyph"].ljust(width), row["color"], color) + "  " + row["words"])
    if found["notes"]:
        lines.append("")
        lines.extend("  " + (f"\033[2m{note}\033[0m" if color else note) for note in found["notes"])
    return "\n".join(lines) + "\n"


def _words(row) -> str:
    name, hint = plain(row.name), plain(row.hint)
    return f"{name}: {hint}" if name and hint else name or hint


def _paint(text: str, tint: str | None, color: bool) -> str:
    if not color or not tint or not text.strip():
        return text
    r, g, b = (int(tint[i : i + 2], 16) for i in (1, 3, 5))
    return f"\033[38;2;{r};{g};{b}m{text}\033[0m"


def _braille(pixels: np.ndarray) -> list[list[list]]:
    high, wide = pixels.shape[:2]
    rows, cols = math.ceil(high / 4), math.ceil(wide / 2)
    grid = np.zeros((rows * 4, cols * 2, 4), dtype=np.uint8)
    grid[:high, :wide] = pixels
    lines = []
    for r in range(rows):
        line: list[list[str]] = []
        for c in range(cols):
            block = grid[r * 4 : r * 4 + 4, c * 2 : c * 2 + 2]
            inked = block[..., 3] >= _INK
            if not inked.any():
                char, tint = " ", None
            else:
                bits = sum(_BITS[y][x] for y in range(4) for x in range(2) if inked[y, x])
                char = chr(0x2800 + bits)
                red, green, blue = (int(round(v)) for v in block[..., :3][inked].mean(axis=0))
                tint = None if (red, green, blue) == _INK_RGB else f"#{red:02x}{green:02x}{blue:02x}"
            if line and line[-1][1] == tint or line and char == " ":
                line[-1][0] += char
            else:
                line.append([char, tint])
        for run in line:
            if not run[0].strip():
                run[1] = None
        while line and not line[-1][0].strip():
            line.pop()
        if line:
            line[-1][0] = line[-1][0].rstrip(" ")
        lines.append(line)
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return lines


# How each language writes a comment: (first line, start of every line, last line).
_LINE = {
    "#": "py pyi sh bash zsh fish rb pl r jl yaml yml toml cfg ini conf nim cmake mk ex exs tcl ps1 dockerfile makefile",
    "//": "c h cc cpp cxx hpp hh m mm cs java kt kts scala swift go rs js jsx mjs cjs ts tsx dart php zig v sv "
    "glsl frag vert wgsl hlsl metal proto groovy gradle",
    "--": "lua sql hs elm ada vhd vhdl",
    "%": "tex sty cls bib erl",
    ";": "lisp cl el clj cljs scm rkt asm s",
    "!": "f90 f95 f03 f08",
}
STYLES: dict[str, tuple[str, str, str]] = {
    ending: ("", mark, "") for mark, endings in _LINE.items() for ending in endings.split()
}
STYLES.update({ending: ("/*", " *", " */") for ending in ("css", "scss", "less")})
STYLES.update({ending: ("<!--", "", "-->") for ending in ("html", "htm", "xml", "svg", "md", "vue", "svelte")})
_MARKS = {"#": "py", "//": "c", "--": "lua", "%": "tex", ";": "lisp", "!": "f90", "/*": "css", "<!--": "html"}
_HEAD, _RULE = "── eqlens ", "─"
WIDTH = 78


def style_of(name: str) -> tuple[str, str, str]:
    """The comment style for a file name, an ending such as ``py``, or a mark such as ``//``."""
    text = (name or "").strip()
    if text in _MARKS:
        return STYLES[_MARKS[text]]
    base = os.path.basename(text).lower()
    ending = base.rsplit(".", 1)[-1] if "." in base else base
    if ending not in STYLES:
        raise FormulaError(
            f"no comment style known for {name!r}: give a file name, an ending such as py or rs, or one of "
            + " ".join(_MARKS)
        )
    return STYLES[ending]


def comment(tex: str, style: str, *, width: int = WIDTH, **options) -> str:
    """The formula in dots as a comment block for a source file, ending in a newline.

    ``style`` is a file name, an ending, or a comment mark. ``width`` is the
    longest line, comment mark and all. The other options are those of ``cells``.
    The block is plain text: a source file holds no colors. Under the dots come
    the ledger, the notes, and the TeX itself, so the formula can be searched for.
    """
    first, mark, last = style_of(style)
    if not isinstance(width, int) or isinstance(width, bool) or not 40 <= width <= 400:
        raise FormulaError("width must be a whole number from 40 to 400")
    room = width - len(mark) - 1
    found = cells(tex, columns=room - 1, **options)
    body = ansi(found, color=False).rstrip("\n").split("\n")
    if "\n" in found["tex"] or any(end and end in found["tex"] for end in (last.strip(), "--" if last == "-->" else "")):
        raise FormulaError("this formula cannot sit inside that kind of comment")
    lines = [_HEAD + _RULE * (room - len(_HEAD)), *(" " + line if line else "" for line in body), "", "   " + found["tex"]]
    lines.append(_RULE * room)
    out = [first] if first else []
    out.extend((mark + " " + line).rstrip() if mark else line.rstrip() for line in lines)
    if last:
        out.append(last)
    return "\n".join(out) + "\n"


def burn(path: str, tex: str, *, style: str | None = None, **options) -> str:
    """Put the comment block at the head of the file at ``path``. Return ``"added"`` or ``"replaced"``.

    The block goes under a ``#!`` line, an encoding line, or an XML or doctype
    line when the file starts with one. A block for the same formula that is
    already in the file is replaced where it stands, so burning twice changes
    nothing. The file must exist and be UTF-8 text.
    """
    block = comment(tex, style or path, **options)
    first, mark, last = style_of(style or path)
    try:
        with open(path, encoding="utf-8", newline="") as handle:
            text = handle.read()
    except UnicodeDecodeError as exc:
        raise FormulaError(f"{path} is not UTF-8 text") from exc
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(newline)
    new = block.rstrip("\n").split("\n")
    start = (mark + " " if mark else "") + _HEAD
    wanted = new[-2 - bool(last)]
    for at, line in enumerate(lines):
        if not line.startswith(start):
            continue
        end = next((i for i in range(at + 1, len(lines)) if lines[i].lstrip(mark).strip().strip(_RULE) == ""
                    and _RULE in lines[i]), None)
        if end is None or wanted not in lines[at:end]:
            continue
        lo, hi = at - bool(first and at and lines[at - 1] == first), end + 1 + bool(last and lines[end + 1 : end + 2] == [last])
        lines[lo:hi] = new
        _write(path, newline.join(lines))
        return "replaced"
    at = 0
    while at < len(lines) and at < 2 and (
        lines[at].startswith(("#!", "<?xml", "<!DOCTYPE", "<!doctype")) or "coding" in lines[at] and lines[at].startswith("#")
    ):
        at += 1
    lines[at:at] = new + ([""] if at < len(lines) and lines[at].strip() else [])
    _write(path, newline.join(lines))
    return "added"


def _write(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)
