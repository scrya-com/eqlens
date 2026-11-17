"""The bench as a ManimGX scene: the curve, redrawn as each symbol in turn crosses its range.

This writes a Python file. It does not import ManimGX, which needs a newer
Python than eqlens does. Render the file with ``manimgx render FILE Bench``.
"""

from __future__ import annotations

import keyword
import math
import re

from eqlens.bench.expr import to_python
from eqlens.bench.spec import curve, tree

_TEMPLATE = '''"""{title}

{formula}

Each symbol crosses its range in turn while the others stay put, so you see
what that symbol alone does to the curve. The grey curve is where it started.

Written by eqlens bench. Render it with:  manimgx render {file} Bench
"""

from __future__ import annotations

import math

import numpy as np

import manimgx as m

TEX = {tex!r}
SWEEP = "{sweep}"  # along the bottom of the plot
# name: (TeX, color, start, from, to, power of ten its readout is shown in)
MOVING = {{
{moving}
}}
FIXED = {{{fixed}}}  # constants
COLORS = {{{colors}}}  # the symbols colored in the formula
Y0, Y1 = {y0!r}, {y1!r}  # the plot's height, wide enough for every sweep
STEPS = 240


def f(v: dict[str, float]) -> float:
    """The formula, worked out. nan where it has no real value."""
{unpack}
    try:
        y = {expr}
    except (ZeroDivisionError, ValueError, OverflowError):
        return math.nan
    return y if isinstance(y, float | int) and math.isfinite(y) else math.nan


def stroke(run: list[np.ndarray], color: m.ParsableManimColor, width: float) -> m.VMobject:
    line = m.VMobject(stroke_color=color, stroke_width=width)
    line.set_points_as_corners(np.array(run))
    return line


def written() -> m.MathTex:
    """The formula, with the symbols that can be found whole in their colors."""
    try:
        return m.MathTex(TEX, tex_to_color_map=COLORS, font_size=40)
    except Exception:  # a formula whose parts cannot be told apart is drawn in one color
        return m.MathTex(TEX, font_size=40)


class Bench(m.Scene):
    def construct(self) -> None:
        formula = written().to_edge(m.UP, buff=0.35)
        x0, x1 = MOVING[SWEEP][3], MOVING[SWEEP][4]
        # The axes run 0 to 1 both ways and the numbers are scaled onto them, so any size of number fits.
        axes = m.Axes(
            x_range=[0, 1, 0.25],
            y_range=[0, 1, 0.25],
            x_length=8.4,
            y_length=4.0,
            tips=False,
            axis_config={{"stroke_width": 3, "color": m.GREY_B}},
        ).to_edge(m.DOWN, buff=0.95).to_edge(m.LEFT, buff=1.5)
        ends = m.VGroup(
            m.Text(f"{{x0:.3g}}", font_size=24, color=m.GREY_B).next_to(axes.c2p(0, 0), m.DOWN, buff=0.2),
            m.Text(f"{{x1:.3g}}", font_size=24, color=m.GREY_B).next_to(axes.c2p(1, 0), m.DOWN, buff=0.2),
            m.Text(f"{{Y0:.3g}}", font_size=24, color=m.GREY_B).next_to(axes.c2p(0, 0), m.LEFT, buff=0.2),
            m.Text(f"{{Y1:.3g}}", font_size=24, color=m.GREY_B).next_to(axes.c2p(0, 1), m.LEFT, buff=0.2),
            m.MathTex(MOVING[SWEEP][0], font_size=44, color=MOVING[SWEEP][1]).next_to(axes.c2p(0.5, 0), m.DOWN, buff=0.25),
        )

        def spot(x: float, y: float) -> np.ndarray:
            return axes.c2p((x - x0) / (x1 - x0), (y - Y0) / (Y1 - Y0))

        trackers = {{name: m.ValueTracker(entry[2]) for name, entry in MOVING.items()}}

        def now() -> dict[str, float]:
            return FIXED | {{name: tracker.get_value() for name, tracker in trackers.items()}}

        def trace(v: dict[str, float], color: m.ParsableManimColor, width: float) -> m.VGroup:
            """The curve for these values: one stroke for each stretch that is real and on the plot."""
            strokes = m.VGroup()
            run: list[np.ndarray] = []
            for i in range(STEPS + 1):
                x = x0 + (x1 - x0) * i / STEPS
                y = f(v | {{SWEEP: x}})
                if math.isnan(y) or not Y0 <= y <= Y1:
                    if len(run) > 1:
                        strokes.add(stroke(run, color, width))
                    run = []
                else:
                    run.append(spot(x, y))
            if len(run) > 1:
                strokes.add(stroke(run, color, width))
            return strokes

        start = now()
        ghost = trace(start, m.GREY_D, 3)
        graph = m.always_redraw(lambda: trace(now(), MOVING[SWEEP][1], 6))

        def dot() -> m.Dot:
            v = now()
            y = f(v)
            if math.isnan(y) or not Y0 <= y <= Y1:
                return m.Dot(spot(v[SWEEP], Y0), radius=0.09, fill_opacity=0.0)
            return m.Dot(spot(v[SWEEP], y), radius=0.09, color=m.WHITE)

        marker = m.always_redraw(dot)

        rows = m.VGroup()
        readouts = {{}}
        for name, (tex, color, value, _lo, _hi, power) in MOVING.items():
            unit = 10.0**power
            label = m.MathTex(tex + (rf"\\,/\\,10^{{{{{{power}}}}}}" if power else "") + "=", font_size=40, color=color)
            number = m.DecimalNumber(value / unit, num_decimal_places=2, font_size=40, color=color)
            number.next_to(label, m.RIGHT, buff=0.15)
            number.add_updater(lambda d, name=name, unit=unit: d.set_value(trackers[name].get_value() / unit))
            readouts[name] = m.VGroup(label, number)
            rows.add(readouts[name])
        rows.arrange(m.DOWN, aligned_edge=m.LEFT, buff=0.35).to_edge(m.RIGHT, buff=0.6).shift(0.6 * m.DOWN)

        self.play(m.Write(formula), run_time=1.5)
        self.play(m.Create(axes), m.FadeIn(ends), m.FadeIn(rows), run_time=1.2)
        self.add(ghost, graph, marker)
        self.wait(0.6)
        # The swept symbol first, so the dot shows what the bottom of the plot is.
        for name in [SWEEP] + [name for name in MOVING if name != SWEEP]:
            _tex, _color, value, lo, hi, _power = MOVING[name]
            self.play(m.Indicate(readouts[name]), run_time=0.6)
            self.play(trackers[name].animate.set_value(hi), run_time=1.8)
            self.play(trackers[name].animate.set_value(lo), run_time=2.6)
            self.play(trackers[name].animate.set_value(value), run_time=1.6)
            self.wait(0.3)
        self.wait(1)'''


def _whole(tex: str, key: str) -> bool:
    """True when every place ``key`` is written in ``tex`` is that symbol and not part of a longer command."""
    found = [m.start() for m in re.finditer(re.escape(key), tex)]
    return bool(found) and all(not tex[at + len(key) : at + len(key) + 1].isalpha() for at in found)


def write(spec: dict, file: str = "bench.py") -> bytes:
    """The scene file as bytes. ``file`` is the name it will be saved under, for the note at its top."""
    node = tree(spec)
    symbols = spec["symbols"]
    moving = [entry for entry in symbols if entry["role"] != "constant"]
    fixed = [entry for entry in symbols if entry["role"] == "constant"]
    sweep = next(entry for entry in moving if entry["key"] == spec["sweep"])

    # Every curve the scene will draw: each symbol at both ends of its range.
    seen: list[float] = []
    for entry in moving:
        if entry is sweep:
            seen += [y for y in curve(spec, sweep["key"], 120)[1] if not math.isnan(y)]
            continue
        for end in (entry["min"], entry["max"]):
            trial = dict(spec, symbols=[dict(item, value=end) if item is entry else item for item in symbols])
            seen += [y for y in curve(trial, sweep["key"], 120)[1] if not math.isnan(y)]
    if seen:
        seen.sort()
        low, high = seen[0], seen[-1]
        inner_low, inner_high = seen[int(0.03 * len(seen))], seen[min(len(seen) - 1, int(0.97 * len(seen)))]
        if inner_high > inner_low and high - low > 40 * (inner_high - inner_low):
            low, high = inner_low - (inner_high - inner_low), inner_high + (inner_high - inner_low)
    else:
        low, high = 0.0, 1.0
    if high == low:
        low, high = low - (abs(low) or 1.0), high + (abs(high) or 1.0)
    pad = 0.06 * (high - low)
    y0, y1 = float(f"{low - pad:.4g}"), float(f"{high + pad:.4g}")


    def power(entry: dict) -> int:
        """The power of ten to show a readout in, so 3e14 reads as 3.00 and not as fifteen digits."""
        size = max(abs(entry["min"]), abs(entry["max"]))
        return 0 if 0.1 <= size < 10000 else math.floor(math.log10(size))

    rows = "\n".join(
        f'    "{entry["name"]}": ({entry["key"]!r}, "{entry["color"]}", {entry["value"]!r}, {entry["min"]!r}, {entry["max"]!r}, {power(entry)}),'
        for entry in moving
    )
    constants = ", ".join(f'"{entry["name"]}": {entry["value"]!r}' for entry in fixed)
    taken = {"f", "v", "m", "np", "math", "y"}
    local = lambda entry: entry["name"] + ("_" if entry["name"] in taken or keyword.iskeyword(entry["name"]) else "")  # noqa: E731
    by_key = {entry["key"]: local(entry) for entry in symbols}
    unpack = "\n".join(f'    {local(entry)} = v["{entry["name"]}"]' for entry in symbols)
    # Color in the formula only what can be found whole: a lone x would also match the x in \exp.
    colors = {
        entry["key"]: entry["color"]
        for entry in symbols + [spec["output"]]
        if len(entry["key"]) > 1 and _whole(spec["tex"], entry["key"])
    }
    color_map = ", ".join(f'{key!r}: "{color}"' for key, color in colors.items())
    return _TEMPLATE.format(
        title=(spec["name"] or "An eqlens bench").replace("\\", "").replace('"', "'"),
        formula=(spec["output"]["name"] + " = " + spec["expr"]),
        file=file,
        tex=spec["tex"],
        sweep=sweep["name"],
        moving=rows,
        fixed=constants,
        y0=y0,
        y1=y1,
        unpack=unpack,
        expr=to_python(node, lambda key: by_key[key]),
        colors=color_map,
    ).encode("utf-8")
