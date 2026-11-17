r"""The bench: a formula you can work, as a sheet, a page, or an animation.

    from eqlens.bench import build, make
    spec = build(r"f(x)=\frac{1}{\sigma\sqrt{2\pi}}\exp\left(-\frac{(x-\mu)^2}{2\sigma^2}\right)")
    make(spec, "gauss.xlsx")
    make(spec, "gauss.html")
    make(spec, "gauss.py")     # a ManimGX scene
    make(spec, "gauss.json")   # the spec, to keep

Every output is written from the one spec, with each symbol in the color it
has on the eqlens card.
"""

from __future__ import annotations

import json
import os

from eqlens.bench.expr import Unreadable
from eqlens.bench.spec import build, curve, load, points, work_out
from eqlens.engine import FormulaError

__all__ = ["KINDS", "Unreadable", "build", "curve", "data", "load", "make", "points", "work_out"]

# What each file ending gives.
KINDS = {".xlsx": "sheet", ".html": "page", ".htm": "page", ".py": "scene", ".json": "spec"}


def data(spec: dict, kind: str, *, file: str = "bench.py", font: str = "sans") -> bytes:
    """One output of ``spec`` as bytes. ``kind`` is ``sheet``, ``page``, ``scene``, or ``spec``."""
    if kind == "spec":
        return (json.dumps(spec, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if kind == "page":
        from eqlens.bench.page import write

        return write(spec, font=font)
    if kind == "scene":
        from eqlens.bench.scene import write

        return write(spec, file=file)
    if kind == "sheet":
        from eqlens.bench.sheet import _openpyxl, write
        from eqlens.render import render

        _openpyxl()
        card = render(
            spec["tex"], "png", brief=True, define=spec["define"], tier=spec["tier"], constant=spec["constant"],
            shared=spec["shared"], notes=spec["notes"], known=False, font=font, dpi=144,
        )
        return write(spec, card_png=card)
    raise FormulaError("a bench output is a sheet, a page, a scene, or a spec")


def make(spec: dict, path: str, *, font: str = "sans") -> str:
    """Write the output that ``path``'s ending asks for. Return the full path."""
    kind = KINDS.get(os.path.splitext(path)[1].lower())
    if kind is None:
        raise FormulaError("a bench file ends in .xlsx, .html, .py, or .json")
    body = data(spec, kind, file=os.path.basename(path), font=font)
    with open(path, "wb") as handle:
        handle.write(body)
    return os.path.abspath(path)
