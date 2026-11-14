"""Render one formula. SVG by default. Inline PNG in iTerm2, WezTerm, and Kitty."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

from eqlens.display import detect_display, display_png, write_file
from eqlens.engine import FONTS
from eqlens.render import FormulaError, render

_DEFAULT_URL = "http://127.0.0.1:8765"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="eqlens",
        description="Draw a mathtext formula as SVG or PNG. A terminal that can show images gets it inline.",
    )
    parser.add_argument("tex", nargs="+", help="formula, for example e^{i\\pi}+1=0")
    parser.add_argument("-o", "--output", help="write to this path instead of displaying. .png writes a PNG, anything else an SVG")
    parser.add_argument(
        "--format",
        choices=["svg", "png", "html"],
        help="svg (default), png, or html: the SVG in a fragment with Copy and Expand buttons. Overrides the -o extension",
    )
    parser.add_argument(
        "--url",
        default=os.environ.get("EQLENS_URL") or os.environ.get("MATHCAT_URL") or _DEFAULT_URL,
        help="eqlensd base URL. Use --local to skip it.",
    )
    parser.add_argument("--local", action="store_true", help="render in this process even if eqlensd is running")
    parser.add_argument("--dpi", type=int, default=220, help="PNG resolution")
    parser.add_argument("--color", default="#f2f2f7")
    parser.add_argument("--bg", default=None, help='opaque background such as #1c1c1e, or "transparent"')
    parser.add_argument("--font", choices=sorted(FONTS), default="sans", help="sans (default), serif, stix, or cm")
    parser.add_argument("--display", choices=["auto", "iterm", "kitty", "file"], default="auto")
    parser.add_argument(
        "--legend",
        action="store_true",
        help="color Greek letters and add a ledger that names them, accents, subscripts, and superscripts",
    )
    parser.add_argument(
        "--brief",
        action="store_true",
        help="--legend without the plain subscripts and powers: only the rows with something to say",
    )
    parser.add_argument(
        "--tips",
        action="store_true",
        help="SVG only: also show a browser tooltip with the name and meaning when a symbol is pointed at",
    )
    parser.add_argument(
        "--define",
        action="append",
        default=[],
        metavar="KEY=MEANING",
        help="say what a symbol means here, for example 'P=what one token can carry'; repeat for more",
    )
    parser.add_argument(
        "--tier",
        action="append",
        default=[],
        metavar="KEY=FORMULA",
        help="what a symbol is made of, drawn under its row as a formula of its own, for example "
        "'P=A_eA_e^\\top'; repeat for more. A symbol inside a tier can have a tier too",
    )
    parser.add_argument("--no-credit", action="store_true", help="leave the small eqlens mark off an SVG card")
    parser.add_argument(
        "--introspect",
        action="store_true",
        help="ask Claude what the parts of the formula mean and draw them as --define items. "
        "Needs `pip install 'eqlens[ai]'` and ANTHROPIC_API_KEY. Implies --brief unless --legend is given",
    )
    parser.add_argument("--context", default="", help="with --introspect: a sentence on where the formula comes from")
    parser.add_argument(
        "--inspect",
        action="store_true",
        help="print what is in the formula as JSON and draw nothing. With --introspect, the JSON carries Claude's "
        "meanings as --define items, so they can be kept and drawn again without asking",
    )
    parser.add_argument(
        "--note",
        action="append",
        default=[],
        help="a short intuitive note in fine print under the formula; repeat for more lines",
    )
    args = parser.parse_args(argv)
    tex = " ".join(args.tex).strip()

    mode = args.display
    if args.output:
        mode = "file"
    elif mode == "auto":
        mode = detect_display() if sys.stdout.isatty() else "stdout"
    # A terminal paints pixels, so inline display is always PNG.
    if mode in ("iterm", "kitty"):
        fmt = "png"
    else:
        name = (args.output or "").lower()
        fmt = args.format or ("png" if name.endswith(".png") else "html" if name.endswith((".html", ".htm")) else "svg")

    try:
        if args.introspect:
            from eqlens.introspect import introspect

            found = introspect(tex, context=args.context, define=args.define, tier=args.tier)
            args.define = found["define"]
            args.tier = found["tier"]
            if not args.legend:
                args.brief = True
            headline = ": ".join(part for part in (found["name"], found["about"]) if part)
            if headline and not args.note and not args.inspect:
                args.note = [headline if _plain_note(headline) else found["about"]]
            if args.inspect:
                print(json.dumps(found, ensure_ascii=False, indent=2))
                return 0
        elif args.inspect:
            from eqlens.introspect import inspect

            print(json.dumps(inspect(tex, args.define, args.tier), ensure_ascii=False, indent=2))
            return 0
        data = _render(tex, fmt, args)
    except FormulaError as exc:
        print(f"eqlens: {exc}", file=sys.stderr)
        return 1

    if args.output:
        with open(args.output, "wb") as handle:
            handle.write(data)
        print(os.path.abspath(args.output))
    elif mode == "stdout":
        sys.stdout.buffer.write(data)
        sys.stdout.buffer.flush()
    elif mode == "file":
        print(write_file(data, "." + fmt))
    else:
        display_png(data, mode, sys.stdout.buffer)
    return 0


def _plain_note(text: str) -> bool:
    """A note is mathtext, so a stray ``$`` in a sentence would break it."""
    return "$" not in text


def _render(tex: str, fmt: str, args) -> bytes:
    options = {
        "dpi": args.dpi,
        "color": args.color,
        "bg": args.bg,
        "legend": args.legend,
        "brief": args.brief,
        "tips": args.tips,
        "tier": args.tier,
        "credit": not args.no_credit,
        "notes": args.note,
        "define": args.define,
        "font": args.font,
    }
    if not args.local and args.url and _healthy(args.url):
        data = _fetch(args.url, tex, fmt, options)
        if data is not None:
            return data
    return render(tex, fmt, **options)


def _healthy(url: str) -> bool:
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/health", timeout=0.3) as response:
            return response.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def _fetch(url: str, tex: str, fmt: str, options: dict) -> bytes | None:
    """Ask eqlensd. None means it is an older eqlensd that cannot draw this, so draw here."""
    body = json.dumps({"tex": tex, **options}).encode("utf-8")
    request = urllib.request.Request(
        url.rstrip("/") + "/" + fmt,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = response.read()
            current = response.headers.get("X-Eqlens-Card") == "1"
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        detail = exc.read().decode("utf-8", "replace")
        try:
            detail = json.loads(detail).get("error", detail)
        except json.JSONDecodeError:
            pass
        raise FormulaError(detail) from exc
    if not current:
        return None
    return data


if __name__ == "__main__":
    raise SystemExit(main())
