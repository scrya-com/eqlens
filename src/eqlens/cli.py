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
    parser.add_argument("--format", choices=["svg", "png"], help="svg (default) or png. Overrides the -o extension")
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
        "--define",
        action="append",
        default=[],
        metavar="KEY=MEANING",
        help="say what a symbol means here, for example 'P=what one token can carry'; repeat for more",
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
        fmt = args.format or ("png" if (args.output or "").lower().endswith(".png") else "svg")

    try:
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


def _render(tex: str, fmt: str, args) -> bytes:
    options = {
        "dpi": args.dpi,
        "color": args.color,
        "bg": args.bg,
        "legend": args.legend,
        "brief": args.brief,
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
