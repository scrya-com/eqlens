"""A symbols file: what the symbols of one paper mean, written once and used by every formula.

It is JSON::

    {
      "source": "arXiv:2610.05816, sections 3.1 and 3.2",
      "define": {"P": "keeps the part the cell can see", "A_e": "squeezes a cell into one token"},
      "tier": {"P": "A_eA_e^\\top"},
      "constant": ["c", "k_B"]
    }

``define`` is symbol to meaning, ``tier`` is symbol to what it is made of, and
``constant`` names constants from the built-in table. ``source`` and ``title``
are for the person who reviews the file; anything else is an error, so a typo
in a key name is caught.

An entry is used only in a formula that has its symbol, so one file can hold
every symbol of a paper. A ``--define`` or ``--tier`` on the command line wins
over the file for the same symbol.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

from eqlens.constants import defines as constant_defines
from eqlens.engine import FormulaError, parses

_FOR_PEOPLE = {"source", "title"}


def load(paths: Sequence[str]) -> dict[str, list[str]]:
    """Read symbols files. Returns ``{"shared": [...], "tier": [...]}`` as ``KEY=...`` items.

    Later files win over earlier ones for the same symbol.
    """
    shared: dict[str, str] = {}
    tiers: dict[str, str] = {}
    for path in paths:
        try:
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)
        except OSError as exc:
            raise FormulaError(f"--symbols cannot open {path}: {exc.strerror or exc}") from exc
        except json.JSONDecodeError as exc:
            raise FormulaError(f"--symbols {path} is not JSON: {exc.msg} at line {exc.lineno}") from exc
        if not isinstance(data, dict):
            raise FormulaError(f"--symbols {path} must be a JSON object")
        unknown = sorted(set(data) - {"define", "tier", "constant"} - _FOR_PEOPLE)
        if unknown:
            raise FormulaError(f"--symbols {path} has a key it does not know: {', '.join(unknown)}")
        for name in ("define", "tier"):
            section = data.get(name, {})
            if not isinstance(section, dict) or not all(isinstance(v, str) for v in section.values()):
                raise FormulaError(f'--symbols {path}: "{name}" must map each symbol to a string')
        constant = data.get("constant", [])
        if not isinstance(constant, list) or not all(isinstance(v, str) for v in constant):
            raise FormulaError(f'--symbols {path}: "constant" must be a list of names')

        for item in constant_defines(constant):
            key, _sep, text = item.partition("=")
            shared[key] = text
        for key, text in data.get("define", {}).items():
            key, text = _key(path, key), text.strip()
            if not text:
                raise FormulaError(f"--symbols {path}: {key} has no meaning")
            shared[key] = text if parses(text) else text.replace("$", r"\$")
        for key, inside in data.get("tier", {}).items():
            key, inside = _key(path, key), inside.strip().strip("$").strip()
            if not inside or not parses(f"${inside}$"):
                raise FormulaError(f"--symbols {path}: cannot read the formula for {key}")
            tiers[key] = inside
    return {
        "shared": [f"{key}={text}" for key, text in shared.items()],
        "tier": [f"{key}={inside}" for key, inside in tiers.items()],
    }


def _key(path: str, key: str) -> str:
    key = key.strip().strip("$").strip()
    if not key or "=" in key or not parses(f"${key}$"):
        raise FormulaError(f"--symbols {path}: cannot read the symbol {key or '(empty)'}")
    return key
