"""The bench spec: one formula, what works it out, and a number and a range for every symbol.

``build`` makes the spec. It is plain JSON, so it can be kept and given back
to ``build`` (through ``load``) with no key and no model. Every output, the
sheet, the page, and the scene, is written from this one spec, so they agree.
"""

from __future__ import annotations

import hashlib
import math
import random
import re
from collections.abc import Sequence

from eqlens.bench.expr import Unreadable, from_tex, from_text, slug, symbols_in, to_tex, to_text, value
from eqlens.constants import CONSTANTS, _name as constant_name
from eqlens.constants import defines as constant_defines
from eqlens.engine import FormulaError, layout, parses
from eqlens.legend import _shape, occurrences, plain, plan
from eqlens.render import normalize_tex

__all__ = ["VALUES", "build", "curve", "load", "points", "tree", "work_out"]

# The constants table says each value in words. These are the same values as numbers, in SI units.
VALUES: dict[str, tuple[float, str]] = {
    "c": (299792458.0, "m/s"),
    "G": (6.674e-11, "m^3 kg^-1 s^-2"),
    "h": (6.62607015e-34, "J s"),
    "hbar": (1.054571817e-34, "J s"),
    "k_B": (1.380649e-23, "J/K"),
    "e": (1.602176634e-19, "C"),
    "epsilon_0": (8.8541878128e-12, "F/m"),
    "mu_0": (1.25663706212e-6, "N A^-2"),
    "N_A": (6.02214076e23, "1/mol"),
    "R": (8.314462618, "J mol^-1 K^-1"),
    "sigma": (5.670374419e-8, "W m^-2 K^-4"),
    "alpha": (1 / 137.035999, ""),
    "m_e": (9.1093837e-31, "kg"),
    "m_p": (1.67262192e-27, "kg"),
    "Lambda": (1.1e-52, "m^-2"),
    "g": (9.80665, "m/s^2"),
}

_MEANS = {
    "variable": "what the curve is drawn against",
    "parameter": "a number you can change",
    "output": "what the formula gives",
}
_TRIES = ((-5.0, 5.0), (0.1, 5.0), (-0.95, 0.95), (0.05, 0.95))
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_WORDS = {"sqrt", "exp", "ln", "log", "log10", "log2", "sin", "cos", "tan", "asin", "acos", "atan", "arcsin",
          "arccos", "arctan", "sinh", "cosh", "tanh", "abs", "fabs", "pow", "pi", "e", "E"}
_GREEK = {name for name in ("alpha beta gamma delta epsilon varepsilon zeta eta theta vartheta iota kappa lambda mu nu xi "
                            "rho sigma tau upsilon phi varphi chi psi omega Gamma Delta Theta Lambda Xi Pi Sigma Upsilon "
                            "Phi Psi Omega hbar ell").split()}
_ACCENT = {"hat", "bar", "tilde", "vec", "dot", "ddot"}


def _guesses(name: str) -> list[str]:
    """The ways a plain name such as ``alpha_bar_t`` may have been written in TeX."""
    parts = [part for part in name.rstrip("_").split("_") if part]
    if not parts:
        return []
    tex = lambda part: "\\" + part if part in _GREEK else part  # noqa: E731
    base, rest = tex(parts[0]), parts[1:]
    if rest and rest[0] in _ACCENT:
        base, rest = f"\\{rest[0]}{{{base}}}", rest[1:]
    mark = ""
    if rest and rest[-1] in ("star", "prime"):
        mark, rest = ("^\\star" if rest[-1] == "star" else "'"), rest[:-1]
    if not rest:
        return [base + mark]
    sub = "".join(tex(part) for part in rest)
    spaced = " ".join(tex(part) for part in rest)
    found = [f"{base}_{{{sub}}}{mark}", f"{base}_{{{spaced}}}{mark}"]
    if len(rest) == 1:
        found.insert(0, f"{base}_{sub}{mark}")
    return found


def _sets(items: Sequence) -> list[dict]:
    """``KEY=value``, ``KEY=value:min:max``, ``KEY=value:min:max:unit``, or the same as a dict.

    ``max/step`` says the symbol moves in steps: ``n=0:0:10/1`` is a level that
    is 0, 1, 2, up to 10 and nothing between. A dict says it with ``step``.
    """
    found = []
    for item in items or ():
        if isinstance(item, dict):
            entry = {name: item[name] for name in ("key", "value", "min", "max", "step", "unit", "means") if item.get(name) not in (None, "")}
            if not str(entry.get("key", "")).strip():
                raise FormulaError("a symbol setting needs a key")
            entry["key"] = str(entry["key"]).strip().strip("$").strip()
        else:
            key, sep, rest = str(item).partition("=")
            parts = rest.split(":", 3)
            if not sep or not key.strip() or not parts[0].strip():
                raise FormulaError("--set takes KEY=value or KEY=value:min:max, for example '\\sigma=1:0.2:3'")
            entry = {"key": key.strip().strip("$").strip(), "value": parts[0]}
            if len(parts) == 2:
                raise FormulaError("--set takes a range as min:max, for example '\\sigma=1:0.2:3'")
            if len(parts) >= 3:
                top, slash, step = parts[2].partition("/")
                entry["min"], entry["max"] = parts[1], top
                if slash:
                    entry["step"] = step
            if len(parts) == 4:
                entry["unit"] = parts[3].strip()
        for name in ("value", "min", "max", "step"):
            if name in entry:
                try:
                    entry[name] = float(entry[name])
                except (TypeError, ValueError) as exc:
                    raise FormulaError(f"the {name} of {entry['key']} is not a number") from exc
                if not math.isfinite(entry[name]):
                    raise FormulaError(f"the {name} of {entry['key']} is not a number")
        if "min" in entry and "max" in entry and not entry["min"] < entry["max"]:
            raise FormulaError(f"the range of {entry['key']} must run from a smaller number to a larger one")
        if "step" in entry:
            if "min" not in entry:
                raise FormulaError(f"the step of {entry['key']} needs a range: value:min:max/step")
            count = (entry["max"] - entry["min"]) / entry["step"] if entry["step"] > 0 else 0
            if not 1 <= count <= 200:
                raise FormulaError(f"the step of {entry['key']} must cut its range into 1 to 200 steps")
            # The range ends on a step, and the symbol stands on one.
            entry["max"] = entry["min"] + math.floor(count + 1e-9) * entry["step"]
            if "value" in entry:
                at = round((entry["value"] - entry["min"]) / entry["step"])
                entry["value"] = min(entry["max"], max(entry["min"], entry["min"] + at * entry["step"]))
        found.append(entry)
    return found


def _same(a: str, b: str) -> bool:
    return a == b or a.replace(" ", "") == b.replace(" ", "") or slug(a) == slug(b) or _shape(a) == _shape(b)


def _agree(a: float, b: float) -> bool:
    if math.isnan(a) or math.isnan(b):
        return math.isnan(a) and math.isnan(b)
    return abs(a - b) <= 1e-9 * max(abs(a), abs(b), 1e-300)


def _check(node: tuple, other: tuple, seed: str) -> tuple[bool, int, dict | None]:
    """Work both out at the same points. Return whether they agree, at how many points, and one where they do not."""
    keys = sorted(set(symbols_in(node)) | set(symbols_in(other)))
    rng = random.Random(seed)
    seen = 0
    for lo, hi in ((0.3, 2.5), (0.05, 0.9), (-3.0, 3.0)):
        for _ in range(12):
            env = {key: rng.uniform(lo, hi) for key in keys}
            a, b = value(node, env), value(other, env)
            if math.isnan(a) and math.isnan(b):
                continue
            seen += 1
            if not _agree(a, b):
                return False, seen, {"at": env, "formula": b, "expr": a}
    return True, seen, None


def build(
    tex: str,
    *,
    expr: str | None = None,
    solve: str | None = None,
    sets: Sequence = (),
    sweep: str | None = None,
    define: Sequence[str] = (),
    tier: Sequence[str] = (),
    constant: Sequence[str] = (),
    shared: Sequence[str] = (),
    name: str = "",
    about: str = "",
    notes: Sequence[str] = (),
    hints: Sequence = (),
) -> dict:
    """Make the spec for ``tex``.

    The formula is read as written when it is real and closed-form. ``expr``
    says how to work it out when it is not, or when the caller wants a special
    case: ``"E = sqrt((p*c)**2 + (m*c**2)**2)"``, with each symbol under its
    plain name. An ``expr`` is checked against the formula as written wherever
    the formula can be read. ``solve`` turns the formula round to give another
    symbol. ``sets`` give a symbol its number, range, and unit. ``sweep`` is the
    symbol along the bottom of the plot. ``constant`` names constants from the
    built-in table, which then hold their real values. ``hints`` are settings
    from a model: one for a symbol that is not there is dropped without a word,
    and a ``sets`` item for the same symbol wins.
    """
    text = normalize_tex(tex)[1:-1].strip()
    formula = layout(f"${text}$", 22)
    settings = _sets(sets)
    try:
        suggested = _sets(hints)
    except FormulaError:
        suggested = []
    define = [item for item in define if item and item.strip()]
    for entry in settings + suggested:
        if entry.get("means") and not any(_same(item.partition("=")[0].strip(), entry["key"]) for item in define):
            define.append(f"{entry['key']}={entry['means']}")

    read, why = None, ""
    try:
        read = from_tex(text, solve)
    except Unreadable as exc:
        why = str(exc)
    if read and "i" in symbols_in(read[2]) and not any(entry["key"] == "i" for entry in settings + suggested):
        # An i is the imaginary unit more often than it is a number, and the bench works in real numbers.
        read, why = None, "the formula has an i, which may be the imaginary unit: give i a number if it is an ordinary symbol"

    if expr and expr.strip():
        known: dict[str, str] = {}
        candidates = list(symbols_in(read[2])) + ([read[0]] if read and read[0] else []) if read else []
        candidates += [entry["key"] for entry in settings + suggested]
        candidates += [item.partition("=")[0].strip().strip("$").strip() for item in define]
        for key in candidates:
            known.setdefault(slug(key), key)
        head, _, body = expr.partition("=") if re.match(r"^\s*[A-Za-z_][A-Za-z0-9_]*\s*=(?!=)", expr) else ("", "", expr)
        for ident in _IDENT.findall(body):
            if ident in known or ident.rstrip("_") in known or ident in _WORDS:
                continue
            guess = next((g for g in _guesses(ident) if parses(f"${g}$") and occurrences(formula, g)), None)
            if guess is None:
                raise Unreadable(
                    f"{ident} in the expression is not a symbol in the formula. "
                    "Write each symbol under its plain name: " + (", ".join(sorted(known)) or "sigma for \\sigma, m_1 for m_1")
                )
            known[ident] = guess
        for plain_name in list(known):
            known.setdefault(plain_name + "_", known[plain_name])
        out_name, node = from_text(body if head else expr, known)
        out_name = head.strip() or out_name
        out = None
        if out_name:
            out = known.get(out_name) or next(
                (g for g in _guesses(out_name) if parses(f"${g}$") and occurrences(formula, g)), None
            )
            if out is None:
                out = out_name if parses(f"${out_name}$") else None
        elif read:
            out = read[0]
        other = None
        if read and (out is None or read[0] is None or _same(out, read[0])):
            other = read[2]
        elif out is not None:
            try:
                other = from_tex(text, out)[2]
            except Unreadable:
                other = None
        if other is not None:
            ok, seen, miss = _check(node, other, text)
            if not ok:
                where = ", ".join(f"{slug(key)}={number:.4g}" for key, number in miss["at"].items())
                raise FormulaError(
                    f"the expression does not give what the formula says: at {where} the formula gives "
                    f"{miss['formula']:.6g} and the expression gives {miss['expr']:.6g}"
                )
            checked = f"agrees with the formula as written at {seen} points" if seen else "not checked: no point had a real value"
        else:
            checked = "not checked against the formula" + (f": {why}" if why else "")
        args: tuple[str, ...] = read[1] if read else ()
    else:
        if read is None:
            raise Unreadable(
                f"{why}. Give an expression (--expr, or expr in a tool call) that works it out for one case, with each symbol "
                "under its plain name, for example 'E = sqrt((p*c)**2 + (m*c**2)**2)'"
            )
        out, args, node = read
        checked = "read from the formula as written"

    inputs = symbols_in(node)
    if not inputs:
        raise Unreadable("the formula has no symbol to change, so there is nothing to put on a bench")
    if out is not None and out in inputs:
        raise Unreadable(f"{slug(out)} is on both sides, so the formula does not give it")

    # Constants the caller named hold their real values.
    fixed: dict[str, tuple[float, str]] = {}
    for item in constant:
        raw = (item or "").strip().strip("$").strip()
        if not raw:
            continue
        key, sep, known_as = raw.partition("=")
        table = constant_name((known_as if sep else key).strip())
        if table is None:
            raise FormulaError(f"--constant does not know {raw}. Known: " + ", ".join(CONSTANTS))
        symbol = key.strip() if sep else CONSTANTS[table][0]
        match = next((k for k in inputs if _same(k, symbol)), None)
        if match and table in VALUES:
            fixed[match] = VALUES[table]

    chosen: dict[str, dict] = {}
    for entry in suggested:
        match = next((k for k in inputs if _same(k, entry["key"])), None)
        if match is not None and match not in fixed:
            if "value" in entry and "min" in entry and not entry["min"] <= entry["value"] <= entry["max"]:
                del entry["value"]
            chosen[match] = entry
    for entry in settings:
        match = next((k for k in inputs if _same(k, entry["key"])), None)
        if match is None:
            if out is not None and _same(out, entry["key"]):
                chosen[out] = entry
                continue
            raise FormulaError(f"{entry['key']} is given a number but is not in what is worked out. It has: " + ", ".join(slug(k) for k in inputs))
        chosen[match] = entry if "min" in entry or "value" in entry else {**chosen.get(match, {}), **entry}

    free = [key for key in inputs if key not in fixed]
    if not free:
        raise Unreadable("every symbol is a constant, so there is nothing to change")
    if sweep:
        target = next((key for key in free if _same(key, sweep.strip().strip("$").strip())), None)
        if target is None:
            raise FormulaError(f"--sweep {sweep} is not a symbol that can change. It can be: " + ", ".join(slug(k) for k in free))
    else:
        target = next((key for key in args if key in free), None) or next((key for key in free if key in ("x", "t")), None) or free[0]

    values = {key: fixed[key][0] if key in fixed else chosen.get(key, {}).get("value", 1.0) for key in inputs}
    ranges: dict[str, tuple[float, float]] = {}
    for key in free:
        entry = chosen.get(key, {})
        if "min" in entry and "max" in entry:
            ranges[key] = (entry["min"], entry["max"])
        elif "value" in entry:
            v = entry["value"]
            ranges[key] = (-5.0, 5.0) if v == 0 else tuple(sorted((0.2 * v, 3.0 * v)))
        elif key == target:
            ranges[key] = _best_range(node, values, key)
        else:
            ranges[key] = (0.2, 3.0)
    for key in free:
        lo, hi = ranges[key]
        if "value" not in chosen.get(key, {}):
            if not lo <= values[key] <= hi:
                values[key] = (lo + hi) / 2
        elif not lo <= values[key] <= hi:
            raise FormulaError(f"the value of {slug(key)} is outside its range")
    if math.isnan(value(node, values)) and "value" not in chosen.get(target, {}):
        # Start where the formula has a value.
        lo, hi = ranges[target]
        for i in range(41):
            trial = dict(values, **{target: lo + (hi - lo) * i / 40})
            if not math.isnan(value(node, trial)):
                values = trial
                break

    # The same plan the drawing uses, so each symbol has the color and the row it has on the card.
    base = constant_defines(list(constant)) + define
    _top, rows = plan(text, legend=True, define=base, tier=tier, known=False, shared=shared)
    meant = {_shape(row.key) for row in rows if row.hint and row.defined}
    auto = []
    for key in inputs + ([out] if out else []):
        if _shape(key) in meant:
            continue
        role = "output" if key == out else "variable" if key == target else "parameter"
        if key in fixed:
            continue
        auto.append(f"{key}={_MEANS[role]}")
    full = define + auto
    _top, rows = plan(text, legend=True, define=constant_defines(list(constant)) + full, tier=tier, brief=True, known=False, shared=shared)
    by_shape = {_shape(row.key): (index, row) for index, row in enumerate(rows)}

    taken: set[str] = set()

    def describe(key: str, role: str) -> dict:
        index, row = by_shape.get(_shape(key), (None, None))
        plain_name = slug(key)
        while plain_name in taken:
            plain_name += "_"
        taken.add(plain_name)
        entry = {
            "key": key,
            "name": plain_name,
            "shown": plain(f"${key}$"),
            "says": plain(row.name) if row is not None and row.name else "",
            "means": plain(row.hint) if row is not None else "",
            "role": role,
            "color": (row.color if row is not None else None) or "#f2f2f7",
            "row": index,
        }
        if role != "output":
            entry["value"] = values[key]
            if key in fixed:
                entry["unit"] = fixed[key][1]
            else:
                entry["min"], entry["max"] = ranges[key]
        unit = chosen.get(key, {}).get("unit")
        if unit:
            entry["unit"] = unit
        if role != "output" and key not in fixed and chosen.get(key, {}).get("step"):
            entry["step"] = chosen[key]["step"]
        entry.setdefault("unit", "")
        return entry

    symbols = [describe(key, "constant" if key in fixed else "variable" if key == target else "parameter") for key in inputs]
    output = describe(out, "output") if out else {
        "key": "", "name": "result", "shown": "result", "says": "", "means": "what the expression gives",
        "role": "output", "color": "#f2f2f7", "row": None, "unit": "",
    }
    names = {entry["key"]: entry["name"] for entry in symbols}
    return {
        "eqlens_bench": 1,
        "tex": text,
        "name": " ".join((name or "").split()),
        "about": " ".join((about or "").split()),
        "expr": to_text(node, lambda key: names[key]),
        "computed": (f"{out}=" if out else "") + to_tex(node),
        "checked": checked,
        # True when what is worked out has symbols the formula does not: one case of it, not the whole.
        "case": any(not occurrences(formula, key) for key in inputs),
        "sweep": target,
        "output": output,
        "symbols": symbols,
        "define": full,
        "tier": [item for item in tier if item and item.strip()],
        "constant": [item for item in constant if item and item.strip()],
        "shared": [item for item in shared if item and item.strip()],
        "notes": [note.strip() for note in notes if note and note.strip()],
    }


def _best_range(node: tuple, values: dict[str, float], key: str) -> tuple[float, float]:
    """A stretch of ``key`` where the formula has a value nearly everywhere."""
    best, share = _TRIES[0], -1.0
    for lo, hi in _TRIES:
        good = sum(not math.isnan(value(node, dict(values, **{key: lo + (hi - lo) * i / 60}))) for i in range(61)) / 61
        if good >= 0.95:
            return lo, hi
        if good > share:
            best, share = (lo, hi), good
    return best


def load(data: dict) -> dict:
    """Check a spec that was kept as JSON, and make it whole again. Raises when it is not one."""
    if not isinstance(data, dict) or data.get("eqlens_bench") != 1 or not isinstance(data.get("symbols"), list):
        raise FormulaError("this is not an eqlens bench spec")
    try:
        output = data.get("output") or {}
        expr = data["expr"] if not output.get("name") or not output.get("key") else f"{output['name']} = {data['expr']}"
        sets = [
            {name: entry.get(name) for name in ("key", "value", "min", "max", "step", "unit")}
            for entry in data["symbols"]
            if entry.get("role") != "constant"
        ]
        if output.get("key") and output.get("unit"):
            sets.append({"key": output["key"], "unit": output["unit"]})
        built = build(
            data["tex"],
            expr=expr,
            sets=sets,
            sweep=data.get("sweep"),
            define=data.get("define") or (),
            tier=data.get("tier") or (),
            constant=data.get("constant") or (),
            shared=data.get("shared") or (),
            name=data.get("name", ""),
            about=data.get("about", ""),
            notes=data.get("notes") or (),
        )
        # A spec read from the formula still is, though it comes back as an expression.
        if built["checked"].startswith("agrees") and str(data.get("checked", "")).startswith(("read from", "agrees")):
            built["checked"] = data["checked"]
        return built
    except KeyError as exc:
        raise FormulaError(f"the bench spec is missing {exc.args[0]}") from exc


def tree(spec: dict) -> tuple:
    """The expression of a spec."""
    return from_text(spec["expr"], {entry["name"]: entry["key"] for entry in spec["symbols"]})[1]


def work_out(spec: dict, changes: dict[str, float] | None = None) -> float:
    """What the formula gives at the spec's values, with ``changes`` by symbol key on top."""
    env = {entry["key"]: entry["value"] for entry in spec["symbols"]}
    env.update(changes or {})
    return value(tree(spec), env)


def curve(spec: dict, key: str, steps: int = 80) -> tuple[list[float], list[float]]:
    """The result as ``key`` alone runs across its range and every other symbol stays where it is."""
    entry = next(item for item in spec["symbols"] if item["key"] == key)
    node = tree(spec)
    env = {item["key"]: item["value"] for item in spec["symbols"]}
    if entry.get("step"):
        # A symbol that moves in steps is worked out on its steps and nowhere between.
        steps = round((entry["max"] - entry["min"]) / entry["step"])
    xs = [entry["min"] + (entry["max"] - entry["min"]) * i / steps for i in range(steps + 1)]
    return xs, [value(node, dict(env, **{key: x})) for x in xs]


def points(spec: dict, count: int = 8) -> list[dict[str, float]]:
    """Places to test a copy of the formula: the spec's own values, then others inside every range."""
    node = tree(spec)
    start = {entry["key"]: entry["value"] for entry in spec["symbols"]}
    found = [start] if not math.isnan(value(node, start)) else []
    rng = random.Random(hashlib.sha1(spec["tex"].encode("utf-8")).hexdigest())
    for _ in range(count * 40):
        if len(found) >= count:
            break
        env = {
            entry["key"]: entry["value"] if entry["role"] == "constant" else float(f"{rng.uniform(entry['min'], entry['max']):.6g}")
            for entry in spec["symbols"]
        }
        if not math.isnan(value(node, env)):
            found.append(env)
    return found
