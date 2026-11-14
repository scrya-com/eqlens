"""Look inside a formula: what its parts are, and, with Claude, what they mean.

``inspect`` needs nothing but the formula. It lists every symbol and
sub-expression the ledger knows, how it is said, and how often it appears.

``introspect`` asks Claude what the parts stand for in this formula and returns
``KEY=meaning`` items ready for ``render(define=...)``. It needs the
``anthropic`` package (``pip install 'eqlens[ai]'``) and a credential:
``ANTHROPIC_API_KEY``, or a profile from ``ant auth login``. Every key Claude
returns is checked against the typeset formula, and one that is not there is
dropped.
"""

from __future__ import annotations

import json
import os
from collections.abc import Sequence

from eqlens.engine import FormulaError, layout, parses
from eqlens.legend import Block, Symbol, _shape, occurrences, plain, plan
from eqlens.render import normalize_tex

MODEL = "claude-opus-5-5"

_SYSTEM = """You explain one math formula to a reader who cannot read it yet.

You are given the formula as TeX, and the symbols and sub-expressions a ledger \
already lists for it with how each is said aloud. Work out what the formula is, \
then say what its parts stand for in this formula.

Pick the parts a reader must know to follow it: usually three to six. A part is \
a single symbol or a sub-expression, such as G_{\\mu\\nu}, \\hat{H}, or \
\\bar{\\alpha}_t. Prefer a whole sub-expression to its pieces when the pieces \
mean nothing alone: explain G_{\\mu\\nu}, not \\mu and \\nu. Leave out digits, \
operators, and parts whose meaning is only their name.

For each part give:
- key: its TeX exactly as written in the formula, with no $ signs. Where the \
ledger lists the part, copy the ledger's key.
- inside: when the part is itself defined by a formula that a reader would \
want opened, the right-hand side of that formula as TeX, such as \
A_eA_e^\\top for P. Give it only when the reader's context states it or it is \
the standard definition. Otherwise an empty string. Never restate the formula \
you were given.
- meaning: what it does or stands for here, in plain words. At most 60 \
characters, lower case except proper names, no full stop. Say what it is for, \
not what it is called: "how spacetime curves", not "the Einstein tensor". No \
equations in it.

Also give:
- name: what the formula is usually called, such as "Einstein field equations", \
or an empty string when it has no settled name.
- about: one plain sentence, at most 80 characters, with the idea of the whole \
formula. No symbols in it.

If the reader's context says what the symbols mean in their work, that wins \
over the textbook meaning. If you cannot tell what a part means, leave it out \
rather than guess."""

_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "about": {"type": "string"},
        "symbols": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"key": {"type": "string"}, "meaning": {"type": "string"}, "inside": {"type": "string"}},
                "required": ["key", "meaning", "inside"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["name", "about", "symbols"],
    "additionalProperties": False,
}


class IntrospectError(FormulaError):
    """Claude could not be asked, or did not answer."""


def inspect(tex: str, define: Sequence[str] = (), tier: Sequence[str] = ()) -> dict:
    """What is in ``tex``: each ledger row, how it is said, what it means, and how often it appears.

    A symbol that opens into a tier carries ``"tier"``: that formula and its own rows, in the same form.
    """
    text = normalize_tex(tex)[1:-1].strip()
    top, rows = plan(text, define=define, tier=tier)
    return _describe(top, rows)


def _describe(block: Block, rows: list[Symbol]) -> dict:
    formula = layout(f"${block.tex}$", 22)
    listed = []
    for index, inside in block.rows:
        row = rows[index]
        entry = {
            "key": row.key,
            "says": plain(row.name) if row.name else "",
            "means": plain(row.hint),
            "defined": bool(row.hint) and row.defined,
            "appears": len(occurrences(formula, row.key)),
        }
        if inside:
            entry["tier"] = _describe(inside, rows)
        listed.append(entry)
    return {"tex": block.tex, "symbols": listed}


def _keys(found: dict) -> list[dict]:
    """Every row in an ``inspect`` result, tiers included."""
    flat = []
    for row in found["symbols"]:
        flat.append(row)
        if "tier" in row:
            flat += _keys(row["tier"])
    return flat


def introspect(
    tex: str,
    *,
    context: str = "",
    define: Sequence[str] = (),
    tier: Sequence[str] = (),
    model: str | None = None,
    client=None,
) -> dict:
    """Ask Claude what the parts of ``tex`` mean, and which of them open into a formula.

    Returns ``{"tex", "name", "about", "define", "tier"}``. ``define`` and ``tier``
    hold the caller's own items first, then Claude's for the parts the caller
    left alone, as ``"KEY=meaning"`` and ``"KEY=formula"`` strings. ``context`` is
    a sentence or two about where the formula comes from. ``client`` is an
    ``anthropic.Anthropic``; one is made when it is left out.
    """
    found = inspect(tex, define, tier)
    text = found["tex"]
    formula = layout(f"${text}$", 22)
    answer = _ask(text, _keys(found), context, model or os.environ.get("EQLENS_MODEL") or MODEL, client)

    def key_of(item: str) -> str:
        return item.partition("=")[0].strip().strip("$").strip()

    own = [item for item in define if item and item.strip()]
    own_tiers = [item for item in tier if item and item.strip()]
    taken = {_shape(key_of(item)) for item in own}
    opened = {_shape(key_of(item)) for item in own_tiers}
    added: list[str] = []
    tiers: list[str] = []
    for part in answer.get("symbols") or []:
        key = str(part.get("key", "")).strip().strip("$").strip()
        meaning = " ".join(str(part.get("meaning", "")).split()).rstrip(".")
        inside = str(part.get("inside", "") or "").strip().strip("$").strip()
        if not key or "=" in key or not parses(f"${key}$") or not occurrences(formula, key):
            continue
        shape = _shape(key)
        if meaning and shape not in taken:
            taken.add(shape)
            if not parses(meaning):
                meaning = meaning.replace("$", r"\$")
            added.append(f"{key}={meaning}")
        # A tier that only repeats the formula it came from opens nothing.
        if inside and shape not in opened and parses(f"${inside}$") and _shape(f"{key}={inside}") != _shape(text):
            opened.add(shape)
            tiers.append(f"{key}={inside}")
    return {
        "tex": text,
        "name": " ".join(str(answer.get("name", "")).split()),
        "about": " ".join(str(answer.get("about", "")).split()),
        "define": own + added,
        "tier": own_tiers + tiers,
    }


def _ask(text: str, rows: list[dict], context: str, model: str, client) -> dict:
    try:
        import anthropic
    except ImportError as exc:
        raise IntrospectError("--introspect needs the anthropic package: pip install 'eqlens[ai]'") from exc
    ledger = "\n".join(f"- {row['key']}" + (f"  (said: {row['says']})" if row["says"] else "") for row in rows) or "(none)"
    prompt = f"Formula:\n{text}\n\nLedger keys:\n{ledger}"
    if context.strip():
        prompt += f"\n\nThe reader's context:\n{context.strip()}"
    try:
        client = client or anthropic.Anthropic()
        response = client.messages.create(
            model=model,
            max_tokens=16000,
            system=_SYSTEM,
            output_config={"effort": "medium", "format": {"type": "json_schema", "schema": _SCHEMA}},
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.AuthenticationError as exc:
        raise IntrospectError("--introspect could not sign in: set ANTHROPIC_API_KEY or run `ant auth login`") from exc
    except anthropic.RateLimitError as exc:
        raise IntrospectError("--introspect was rate limited; try again in a minute") from exc
    except anthropic.APIStatusError as exc:
        raise IntrospectError(f"--introspect failed ({exc.status_code}): {exc.message}") from exc
    except anthropic.APIConnectionError as exc:
        raise IntrospectError("--introspect could not reach the Claude API") from exc
    except anthropic.AnthropicError as exc:
        # No credential at all is raised here, before any request is made.
        raise IntrospectError(f"--introspect could not start: {exc}. Set ANTHROPIC_API_KEY or run `ant auth login`") from exc
    except TypeError as exc:
        # The SDK raises a bare TypeError when it finds no credential.
        if "authentication" not in str(exc).lower():
            raise
        raise IntrospectError("--introspect found no credential: set ANTHROPIC_API_KEY or run `ant auth login`") from exc
    if response.stop_reason == "refusal":
        raise IntrospectError("Claude declined to explain this formula")
    if response.stop_reason == "max_tokens":
        raise IntrospectError("Claude ran out of room before finishing its answer")
    body = next((block.text for block in response.content if block.type == "text"), "")
    try:
        answer = json.loads(body)
    except json.JSONDecodeError as exc:
        raise IntrospectError("Claude's answer was not the JSON that was asked for") from exc
    if not isinstance(answer, dict):
        raise IntrospectError("Claude's answer was not the JSON that was asked for")
    return answer
