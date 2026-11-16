"""Draw a scene as a GLSL fragment shader.

The shader carries the formula itself: every glyph outline, flattened into
line segments, sits in a constant array. A pixel finds the glyphs whose box it
is in, counts windings to learn whether it is inside, and takes its distance to
the nearest edge for a smooth rim. Nothing is sampled from a texture, so the
formula stays sharp at any size.

The output is a WebGL2 (GLSL ES 3.00) fragment shader. The part between the
two Shadertoy lines uses only ``iResolution`` and ``iMouse`` and has a
``mainImage``, so it can be pasted into Shadertoy as it is. Pointing at a
symbol lights it and its row and dims the rest, as the SVG does.
"""

from __future__ import annotations

import numpy as np
from matplotlib.path import Path

from eqlens.engine import ROLES, Scene, outline

# Glyph outlines are in units of a 100 pt em. Curves are cut into lines no
# longer than this, between 2 and 12 per curve.
_STEP = 6.0
_MAX_SYMBOLS = 32
_DIM = 0.28


def to_glsl(scene: Scene, *, label: str, fg: str, bg: str | None) -> str:
    colors = dict(ROLES, fg=fg)
    palette: list[str] = []

    def color(fill: str) -> int:
        value = colors.get(fill, fill).lower()
        if value not in palette:
            palette.append(value)
        return palette.index(value)

    glyphs: dict[tuple[str, int, int], int] = {}
    segments: list[tuple[float, float, float, float]] = []
    spans: list[tuple[int, int]] = []
    boxes: list[tuple[float, float, float, float]] = []
    marks: list[tuple[float, float, float, int, int, int]] = []
    rules: list[tuple[float, float, float, float, int, int]] = []
    groups: list[tuple[tuple[float, float, float, float], int, int]] = []

    for group in scene.groups:
        mask = 0
        for index in group.syms:
            if index < _MAX_SYMBOLS:
                mask |= 1 << index
        # As in the SVG: while a symbol is pointed at, every formula glyph and row that is not it dims.
        dims = group.kind in ("f", "r")
        gi = len(groups)
        # A group with no hit box can never be pointed at: give it an empty one.
        groups.append((group.hit or (0.0, 0.0, -1.0, -1.0), mask, int(dims)))
        for x, y, w, h, fill in group.rules:
            rules.append((x, y, w, h, color(fill), gi))
        for mark in group.marks:
            key = (mark.font, mark.num, mark.index)
            if key not in glyphs:
                lines = _flatten(*outline(*key))
                if not lines:
                    continue
                glyphs[key] = len(spans)
                spans.append((len(segments), len(lines)))
                ends = np.array(lines).reshape(-1, 2)
                low, high = ends.min(axis=0), ends.max(axis=0)
                boxes.append((float(low[0]), float(low[1]), float(high[0]), float(high[1])))
                segments += lines
            marks.append((mark.x, mark.y, mark.scale, glyphs[key], color(mark.fill), gi))

    background = palette_rgb(bg) if bg else None
    return _source(scene, label, palette, segments, spans, boxes, marks, rules, groups, background)


def palette_rgb(value: str) -> tuple[float, float, float]:
    value = value.lstrip("#")
    if len(value) == 3:
        value = "".join(c * 2 for c in value)
    return tuple(int(value[i : i + 2], 16) / 255 for i in (0, 2, 4))


def _flatten(verts: np.ndarray, codes: np.ndarray) -> list[tuple[float, float, float, float]]:
    """An outline as closed loops of line segments, y up, in 100 pt units."""
    lines: list[tuple[float, float, float, float]] = []
    start = here = None

    def to(point) -> None:
        nonlocal here
        if here is not None and (point[0] != here[0] or point[1] != here[1]):
            lines.append((float(here[0]), float(here[1]), float(point[0]), float(point[1])))
        here = point

    def close() -> None:
        if start is not None and here is not None:
            to(start)

    i = 0
    while i < len(codes):
        code = int(codes[i])
        if code == Path.MOVETO:
            close()
            start = here = verts[i]
            i += 1
        elif code == Path.LINETO:
            to(verts[i])
            i += 1
        elif code in (Path.CURVE3, Path.CURVE4):
            count = 2 if code == Path.CURVE3 else 3
            points = np.vstack([here, verts[i : i + count]])
            length = float(np.linalg.norm(np.diff(points, axis=0), axis=1).sum())
            steps = int(min(12, max(2, np.ceil(length / _STEP))))
            for t in np.linspace(0, 1, steps + 1)[1:]:
                to(_bezier(points, t))
            i += count
        elif code == Path.CLOSEPOLY:
            close()
            start = None
            i += 1
        else:
            i += 1
    close()
    return lines


def _bezier(points: np.ndarray, t: float) -> np.ndarray:
    while len(points) > 1:
        points = points[:-1] * (1 - t) + points[1:] * t
    return points[0]


def _f(value: float) -> str:
    text = f"{value:.3f}".rstrip("0").rstrip(".")
    if text in ("-0", ""):
        text = "0"
    return text + ("" if "." in text else ".")


def _array(kind: str, name: str, items: list[str]) -> str:
    if not items:
        # GLSL has no empty arrays: keep one entry that the loops never reach.
        items = [f"{kind}(0)"]
    rows = ",\n".join("  " + item for item in items)
    return f"const {kind} {name}[{len(items)}] = {kind}[](\n{rows}\n);"


def _source(scene, label, palette, segments, spans, boxes, marks, rules, groups, background) -> str:
    label = " ".join(label.split()).replace("*/", "* /")
    pal = [f"vec3({_f(r)}, {_f(g)}, {_f(b)})" for r, g, b in map(palette_rgb, palette)]
    seg = [f"vec4({_f(a)}, {_f(b)}, {_f(c)}, {_f(d)})" for a, b, c, d in segments]
    span = [f"ivec2({start}, {count})" for start, count in spans]
    box = [f"vec4({_f(a)}, {_f(b)}, {_f(c)}, {_f(d)})" for a, b, c, d in boxes]
    mark = [f"vec4({_f(x)}, {_f(y)}, {_f(s)}, 0.)" for x, y, s, _g, _c, _gi in marks]
    mark_ids = [f"ivec3({g}, {c}, {gi})" for _x, _y, _s, g, c, gi in marks]
    rule = [f"vec4({_f(x)}, {_f(y)}, {_f(w)}, {_f(h)})" for x, y, w, h, _c, _gi in rules]
    rule_ids = [f"ivec2({c}, {gi})" for *_r, c, gi in rules]
    hit = [f"vec4({_f(x)}, {_f(y)}, {_f(w)}, {_f(h)})" for (x, y, w, h), _m, _d in groups]
    sym = [f"uvec2({mask}u, {dims}u)" for _h, mask, dims in groups]
    if background:
        under = "vec4({}, {}, {}, 1.)".format(*map(_f, background))
    else:
        under = "vec4(0.)"
    return f"""#version 300 es
// eqlens: {label}
// A WebGL2 fragment shader. Set iResolution (vec3, pixels) and iMouse (vec4,
// pixels from the bottom left, as Shadertoy gives it). For Shadertoy, paste
// only what is between the two Shadertoy lines.
precision highp float;
precision highp int;
uniform vec3 iResolution;
uniform vec4 iMouse;
out vec4 eqlensColor;

// ---- Shadertoy: paste from here ----
const vec2 SCENE = vec2({_f(scene.width)}, {_f(scene.height)});
const vec4 UNDER = {under};
const float DIM = {_f(_DIM)};
const int MARKS = {len(marks)};
const int RULES = {len(rules)};
const int GROUPS = {len(groups)};
{_array("vec3", "PALETTE", pal)}
{_array("vec4", "SEGMENT", seg)}
{_array("ivec2", "SPAN", span)}
{_array("vec4", "BOX", box)}
{_array("vec4", "MARK", mark)}
{_array("ivec3", "MARK_ID", mark_ids)}
{_array("vec4", "RULE", rule)}
{_array("ivec2", "RULE_ID", rule_ids)}
{_array("vec4", "HIT", hit)}
{_array("uvec2", "SYMS", sym)}

// Signed distance to a glyph in its own units: negative inside.
float glyphDistance(int glyph, vec2 p) {{
  ivec2 span = SPAN[glyph];
  float near = 1e9;
  int winding = 0;
  for (int i = span.x; i < span.x + span.y; i++) {{
    vec4 s = SEGMENT[i];
    vec2 a = s.xy, e = s.zw - s.xy, w = p - a;
    vec2 d = w - e * clamp(dot(w, e) / dot(e, e), 0., 1.);
    near = min(near, dot(d, d));
    float side = e.x * w.y - e.y * w.x;
    if (a.y <= p.y && s.w > p.y && side > 0.) winding++;
    if (s.w <= p.y && a.y > p.y && side < 0.) winding--;
  }}
  return winding != 0 ? -sqrt(near) : sqrt(near);
}}

bool inside(vec4 r, vec2 p) {{
  return p.x >= r.x && p.y >= r.y && p.x <= r.x + r.z && p.y <= r.y + r.w;
}}

float shown(int group, uint lit) {{
  uvec2 s = SYMS[group];
  if (lit == 0u || s.y == 0u || (s.x & lit) != 0u) return 1.;
  return DIM;
}}

// The result is premultiplied, which is what a WebGL canvas expects by default.
vec4 over(vec4 under, vec3 color, float alpha) {{
  return vec4(mix(under.rgb, color, alpha), alpha + under.a * (1. - alpha));
}}

void mainImage(out vec4 fragColor, in vec2 fragCoord) {{
  float zoom = min(iResolution.x / SCENE.x, iResolution.y / SCENE.y);
  vec2 corner = (iResolution.xy - SCENE * zoom) * .5;
  vec2 p = (fragCoord - corner) / zoom;
  p.y = SCENE.y - p.y;

  // What the pointer is on lights up everywhere it appears.
  uint lit = 0u;
  if (iMouse.x > 0. || iMouse.y > 0.) {{
    vec2 m = (iMouse.xy - corner) / zoom;
    m.y = SCENE.y - m.y;
    for (int g = 0; g < GROUPS; g++) {{
      if (SYMS[g].x != 0u && inside(HIT[g], m)) lit |= SYMS[g].x;
    }}
  }}

  vec4 color = UNDER;
  if (p.x < 0. || p.y < 0. || p.x > SCENE.x || p.y > SCENE.y) {{
    fragColor = color;
    return;
  }}
  for (int i = 0; i < RULES; i++) {{
    vec4 r = RULE[i];
    vec2 q = abs(p - r.xy - r.zw * .5) - r.zw * .5;
    float d = length(max(q, 0.)) + min(max(q.x, q.y), 0.);
    float a = clamp(.5 - d * zoom, 0., 1.);
    if (a > 0.) color = over(color, PALETTE[RULE_ID[i].x], a * shown(RULE_ID[i].y, lit));
  }}
  for (int i = 0; i < MARKS; i++) {{
    vec4 m = MARK[i];
    ivec3 id = MARK_ID[i];
    vec2 local = vec2(p.x - m.x, m.y - p.y) / m.z;
    vec4 b = BOX[id.x];
    float pad = 1.5 / (zoom * m.z);
    if (local.x < b.x - pad || local.y < b.y - pad || local.x > b.z + pad || local.y > b.w + pad) continue;
    float a = clamp(.5 - glyphDistance(id.x, local) * m.z * zoom, 0., 1.);
    if (a > 0.) color = over(color, PALETTE[id.y], a * shown(id.z, lit));
  }}
  fragColor = color;
}}
// ---- Shadertoy: paste to here ----

void main() {{
  mainImage(eqlensColor, gl_FragCoord.xy);
}}
"""
