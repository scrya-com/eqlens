"""Constants whose values the library knows, so no model has to remember them.

``--constant c`` gives the symbol ``c`` the meaning and value below. A symbol
is only a constant when the caller says so: ``c`` is not always the speed of
light. ``--constant 'KEY=NAME'`` is for a formula that writes one differently,
such as ``--constant '\\epsilon_0=epsilon_0'``.

Values are CODATA recommended values. Those fixed by the SI definitions are
exact and given in full; the rest are rounded to four figures and marked
"about". Lambda is the measured cosmological constant, good to two figures.
"""

from __future__ import annotations

from collections.abc import Sequence

from eqlens.engine import FormulaError, parses

# name: (symbol as TeX, what it is, exact, value with its unit)
CONSTANTS: dict[str, tuple[str, str, bool, str]] = {
    "c": ("c", "the speed of light", True, r"$299\,792\,458$ m/s"),
    "G": ("G", "Newton's constant of gravitation", False, r"$6.674\times10^{-11}\,\mathrm{m}^{3}\,\mathrm{kg}^{-1}\,\mathrm{s}^{-2}$"),
    "h": ("h", "Planck's constant", True, r"$6.626\,070\,15\times10^{-34}$ J s"),
    "hbar": (r"\hbar", "Planck's constant divided by $2\\pi$", False, r"$1.055\times10^{-34}$ J s"),
    "k_B": ("k_B", "Boltzmann's constant: energy per degree", True, r"$1.380\,649\times10^{-23}$ J/K"),
    "e": ("e", "the charge of one proton", True, r"$1.602\,176\,634\times10^{-19}$ C"),
    "epsilon_0": (r"\varepsilon_0", "the electric constant", False, r"$8.854\times10^{-12}$ F/m"),
    "mu_0": (r"\mu_0", "the magnetic constant", False, r"$1.257\times10^{-6}\,\mathrm{N}\,\mathrm{A}^{-2}$"),
    "N_A": ("N_A", "Avogadro's number: how many in a mole", True, r"$6.022\,140\,76\times10^{23}\,\mathrm{mol}^{-1}$"),
    "R": ("R", "the gas constant", False, r"$8.314\,\mathrm{J}\,\mathrm{mol}^{-1}\,\mathrm{K}^{-1}$"),
    "sigma": (r"\sigma", "the Stefan-Boltzmann constant", False, r"$5.670\times10^{-8}\,\mathrm{W}\,\mathrm{m}^{-2}\,\mathrm{K}^{-4}$"),
    "alpha": (r"\alpha", "the fine-structure constant", False, r"$1/137.036$"),
    "m_e": ("m_e", "the mass of an electron", False, r"$9.109\times10^{-31}$ kg"),
    "m_p": ("m_p", "the mass of a proton", False, r"$1.673\times10^{-27}$ kg"),
    "Lambda": (r"\Lambda", "the cosmological constant", False, r"$1.1\times10^{-52}\,\mathrm{m}^{-2}$"),
    "g": ("g", "standard gravity at Earth's surface", True, r"$9.806\,65\,\mathrm{m}/\mathrm{s}^{2}$"),
    "pi": (r"\pi", "a circle's circumference over its diameter", False, r"$3.14159$"),
    "euler": ("e", "Euler's number, the base of natural growth", False, r"$2.71828$"),
}


def meaning(name: str) -> str:
    """The ledger line for a constant: what it is, then its value."""
    _symbol, what, exact, value = CONSTANTS[name]
    return f"{what}, {value}" if exact else f"{what}, about {value}"


def defines(items: Sequence[str]) -> list[str]:
    """Turn ``--constant`` items into ``KEY=meaning`` items.

    An item is a name from the table (``c``, ``k_B``, ``Lambda``), the symbol it
    is usually written as (``\\Lambda``), or ``KEY=NAME`` to give the symbol.
    """
    found: list[str] = []
    for item in items:
        text = (item or "").strip().strip("$").strip()
        if not text:
            continue
        key, sep, name = text.partition("=")
        key, name = key.strip(), (name.strip() if sep else key.strip())
        name = _name(name)
        if name is None:
            raise FormulaError(f"--constant does not know {item.strip()}. Known: " + ", ".join(CONSTANTS))
        key = key if sep else CONSTANTS[name][0]
        if not parses(f"${key}$"):
            raise FormulaError(f"--constant cannot read the symbol {key}")
        found.append(f"{key}={meaning(name)}")
    return found


def _name(text: str) -> str | None:
    if text in CONSTANTS:
        return text
    bare = text.lstrip("\\")
    if bare in CONSTANTS:
        return bare
    # By the symbol it is written as, when only one constant is written that way.
    matches = [name for name, entry in CONSTANTS.items() if entry[0] == text]
    return matches[0] if len(matches) == 1 else None
