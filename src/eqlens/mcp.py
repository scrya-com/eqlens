"""eqlens as an MCP server, over stdio. No packages beyond eqlens's own.

    eqlens-mcp

Three tools. ``eqlens_render`` draws a formula. ``eqlens_inspect`` lists what
is in one, and says whether it can be worked out as written. ``eqlens_bench``
writes the bench: a workbook, a page with sliders, and a ManimGX scene, each
symbol in its ledger color.

The model on the other end is the one that knows what a formula means, so the
server asks nobody: the meanings, the special case, and the ranges all come in
as arguments. It needs no API key.

Messages are JSON-RPC 2.0, one per line, as the MCP stdio transport sets out.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import tempfile

from eqlens import __version__
from eqlens.engine import FormulaError

_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
_STRINGS = {"type": "array", "items": {"type": "string"}}

_INSTRUCTIONS = (
    "eqlens draws one TeX formula with every symbol colored and explained, and builds a bench for it: a workbook, "
    "a web page with sliders, and a ManimGX animation that show what each symbol does. "
    "Use eqlens_render to show a formula. Use eqlens_bench when the user wants to explore, play with, plot, "
    "animate, or put a formula in a spreadsheet. A formula with a derivative, an integral, a sum, or an operator "
    "cannot be worked out as written: eqlens_bench then says so, and you call it again with expr giving one "
    "standard special case, and symbols giving each number a value, a range, a unit, and a meaning. "
    "One formula per call, in matplotlib mathtext: no \\begin environments."
)

TOOLS = [
    {
        "name": "eqlens_render",
        "title": "Draw a formula",
        "description": (
            "Draw one TeX formula as a PNG, an SVG, or an HTML fragment, with each symbol colored, a ledger that says "
            "how each is read, and what each means. Returns the file's path, and the picture itself for a PNG. "
            "Give define items for the symbols a reader needs explained: 'KEY=meaning', the key being the TeX as "
            "written in the formula, the meaning plain words under 60 characters."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "tex": {"type": "string", "description": "The formula, as TeX. No $ signs needed."},
                "format": {"type": "string", "enum": ["png", "svg", "html"], "description": "Default png."},
                "legend": {"type": "boolean", "description": "Name every Greek letter, accent, and script."},
                "brief": {"type": "boolean", "description": "As legend, but leave out plain subscripts and powers."},
                "define": {**_STRINGS, "description": "'KEY=meaning' items."},
                "tier": {**_STRINGS, "description": "'KEY=formula' items: what a symbol is made of."},
                "constant": {**_STRINGS, "description": "Constants from the built-in table: c, G, h, hbar, k_B, R, ..."},
                "notes": {**_STRINGS, "description": "One to four short lines of fine print."},
                "path": {"type": "string", "description": "Where to write the file. Default: a temporary folder."},
            },
            "required": ["tex"],
        },
    },
    {
        "name": "eqlens_inspect",
        "title": "Look inside a formula",
        "description": (
            "List what is in one TeX formula: each symbol, how it is said, and how often it appears. Also says "
            "whether the formula can be worked out as written, the plain name of each symbol (the name to use in "
            "an eqlens_bench expr), and, when it cannot be worked out, why. Draws nothing."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "tex": {"type": "string"},
                "define": _STRINGS,
                "tier": _STRINGS,
                "constant": _STRINGS,
            },
            "required": ["tex"],
        },
    },
    {
        "name": "eqlens_bench",
        "title": "Build a bench for a formula",
        "description": (
            "Turn one formula into things a person can work by hand, written to files: an .xlsx workbook (a colored "
            "cell per symbol, the formula as a live cell formula, a chart per symbol, and a sheet that checks the "
            "formula), an .html page (the eqlens drawing, a slider per symbol, a live plot, and a small plot beside "
            "each slider of what that symbol alone does), a ManimGX scene (.py) that animates each symbol across its "
            "range, and the spec (.json). Every symbol has the same color in all of them.\n"
            "A real, closed-form formula is read as written. For any other, give expr: 'OUT = expression' for one "
            "standard case, using the plain names eqlens_inspect lists, numbers, + - * / **, pi, e, and sqrt exp ln "
            "log10 sin cos tan asin acos atan sinh cosh tanh abs. A new name a case needs (such as L for a box's "
            "width) must be listed in symbols. An expr is checked against the formula wherever the formula can be "
            "read, and the call fails if they disagree.\n"
            "Always give symbols for a good bench: each symbol's value, a min and max worth exploring, its unit, and "
            "what it means. Without them every symbol starts at 1.\n"
            "Returns the paths written, what is worked out, how it was checked, and the result at the starting "
            "values. To render the scene: manimgx render FILE.py Bench."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "tex": {"type": "string", "description": "The formula, as TeX."},
                "expr": {"type": "string", "description": "'OUT = expression', when the formula cannot be read as written or one case is wanted."},
                "solve": {"type": "string", "description": "Turn the formula round to give this symbol, as in PV=nRT for T."},
                "sweep": {"type": "string", "description": "The symbol along the bottom of the plot."},
                "symbols": {
                    "type": "array",
                    "description": "A number and a range for each symbol.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "key": {"type": "string", "description": "The symbol's TeX as written, or its plain name."},
                            "value": {"type": "number"},
                            "min": {"type": "number"},
                            "max": {"type": "number"},
                            "step": {"type": "number", "description": "For a symbol that moves in steps, such as a level n that is 0, 1, 2: the size of one step."},
                            "unit": {"type": "string"},
                            "means": {"type": "string", "description": "What it stands for here, under 60 characters."},
                        },
                        "required": ["key"],
                    },
                },
                "constant": {**_STRINGS, "description": "Constants that hold their real SI values: c, G, h, hbar, k_B, R, ..."},
                "define": {**_STRINGS, "description": "'KEY=meaning' items, as for eqlens_render."},
                "tier": _STRINGS,
                "notes": _STRINGS,
                "name": {"type": "string", "description": "What the formula is called."},
                "about": {"type": "string", "description": "One plain sentence with the idea of it."},
                "outputs": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["html", "xlsx", "scene", "spec"]},
                    "description": "Which files to write. Default: html and xlsx.",
                },
                "out_dir": {"type": "string", "description": "The folder to write into. Default: a temporary folder. Give one when the user wants to keep the files."},
                "basename": {"type": "string", "description": "The files' name without an ending. Default: from the formula's name."},
            },
            "required": ["tex"],
        },
    },
]


def _strings(args: dict, name: str) -> list[str]:
    value = args.get(name) or []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise FormulaError(f"{name} must be a list of strings")
    return value


def _folder(path: str | None) -> str:
    folder = os.path.abspath(os.path.expanduser(path)) if path else os.path.join(tempfile.gettempdir(), "eqlens-mcp")
    os.makedirs(folder, exist_ok=True)
    return folder


def _stem(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()[:48] or "bench"


def _text(payload) -> dict:
    body = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False, indent=2)
    return {"content": [{"type": "text", "text": body}]}


def render_tool(args: dict) -> dict:
    from eqlens.render import render

    fmt = args.get("format") or "png"
    data = render(
        str(args.get("tex", "")),
        fmt,
        legend=args.get("legend") is True,
        brief=args.get("brief") is True,
        define=_strings(args, "define"),
        tier=_strings(args, "tier"),
        constant=_strings(args, "constant"),
        notes=_strings(args, "notes"),
    )
    path = args.get("path")
    if path:
        path = os.path.abspath(os.path.expanduser(str(path)))
        os.makedirs(os.path.dirname(path), exist_ok=True)
    else:
        import hashlib

        name = hashlib.sha1(data).hexdigest()[:12] + "." + fmt
        path = os.path.join(_folder(None), name)
    with open(path, "wb") as handle:
        handle.write(data)
    result = _text(path)
    if fmt == "png":
        result["content"].append({"type": "image", "data": base64.b64encode(data).decode("ascii"), "mimeType": "image/png"})
    return result


def inspect_tool(args: dict) -> dict:
    from eqlens.bench.expr import Unreadable, from_tex, slug, symbols_in, to_text
    from eqlens.introspect import _keys, inspect

    tex = str(args.get("tex", ""))
    found = inspect(tex, _strings(args, "define"), _strings(args, "tier"), constant=_strings(args, "constant"))
    try:
        out, _args, node = from_tex(found["tex"])
        found["works_out"] = {
            "as_written": True,
            "gives": slug(out) if out else None,
            "expr": to_text(node),
            "names": {slug(key): key for key in symbols_in(node)},
        }
    except Unreadable as exc:
        found["works_out"] = {
            "as_written": False,
            "why": str(exc),
            "names": {slug(row["key"]): row["key"] for row in _keys(found)},
            "next": "call eqlens_bench with expr giving one standard case, and symbols for its numbers",
        }
    return _text(found)


def bench_tool(args: dict) -> dict:
    from eqlens.bench import build, make, work_out

    spec = build(
        str(args.get("tex", "")),
        expr=args.get("expr") or None,
        solve=args.get("solve") or None,
        sweep=args.get("sweep") or None,
        sets=args.get("symbols") or (),
        define=_strings(args, "define"),
        tier=_strings(args, "tier"),
        constant=_strings(args, "constant"),
        notes=_strings(args, "notes"),
        name=str(args.get("name") or ""),
        about=str(args.get("about") or ""),
    )
    outputs = args.get("outputs") or ["html", "xlsx"]
    endings = {"html": ".html", "xlsx": ".xlsx", "scene": ".py", "spec": ".json"}
    if not isinstance(outputs, list) or any(item not in endings for item in outputs):
        raise FormulaError("outputs may hold html, xlsx, scene, and spec")
    folder = _folder(args.get("out_dir"))
    stem = _stem(str(args.get("basename") or spec["name"] or spec["output"]["name"] or "bench"))
    files, skipped = {}, {}
    for kind in outputs:
        name = stem + ("_scene" if kind == "scene" else "") + endings[kind]
        try:
            files[kind] = make(spec, os.path.join(folder, name))
        except FormulaError as exc:
            if kind != "xlsx":
                raise
            skipped[kind] = str(exc)
    report = {
        "files": files,
        "gives": spec["output"]["name"],
        "expr": spec["expr"],
        "checked": spec["checked"],
        "one_case_only": spec["case"],
        "sweep": next(entry["name"] for entry in spec["symbols"] if entry["key"] == spec["sweep"]),
        "symbols": [
            {name: entry[name] for name in ("name", "key", "role", "value", "min", "max", "step", "unit", "color") if name in entry}
            for entry in spec["symbols"]
        ],
        "result_at_start": work_out(spec),
    }
    if skipped:
        report["not_written"] = skipped
    if "scene" in files:
        report["render_scene_with"] = f"manimgx render {files['scene']} Bench"
    return _text(report)


_CALLS = {"eqlens_render": render_tool, "eqlens_inspect": inspect_tool, "eqlens_bench": bench_tool}


def handle(message: dict) -> dict | None:
    """Answer one JSON-RPC message. None for a notification, which gets no answer."""
    method, ident = message.get("method"), message.get("id")
    if ident is None:
        return None

    def ok(result: dict) -> dict:
        return {"jsonrpc": "2.0", "id": ident, "result": result}

    def fail(code: int, text: str) -> dict:
        return {"jsonrpc": "2.0", "id": ident, "error": {"code": code, "message": text}}

    params = message.get("params") or {}
    if method == "initialize":
        asked = params.get("protocolVersion")
        return ok(
            {
                "protocolVersion": asked if asked in _VERSIONS else _VERSIONS[0],
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "eqlens", "title": "eqlens", "version": __version__},
                "instructions": _INSTRUCTIONS,
            }
        )
    if method == "ping":
        return ok({})
    if method == "tools/list":
        return ok({"tools": TOOLS})
    if method == "tools/call":
        call = _CALLS.get(params.get("name"))
        if call is None:
            return fail(-32602, f"unknown tool: {params.get('name')}")
        args = params.get("arguments") or {}
        if not isinstance(args, dict):
            return fail(-32602, "arguments must be an object")
        try:
            return ok(call(args))
        except FormulaError as exc:
            return ok({"content": [{"type": "text", "text": f"eqlens: {exc}"}], "isError": True})
        except OSError as exc:
            return ok({"content": [{"type": "text", "text": f"eqlens: cannot write the file: {exc}"}], "isError": True})
        except Exception as exc:  # noqa: BLE001 - a tool must answer, whatever went wrong inside it
            return ok({"content": [{"type": "text", "text": f"eqlens failed: {type(exc).__name__}: {exc}"}], "isError": True})
    if method in ("resources/list", "prompts/list"):
        return ok({method.split("/")[0]: []})
    return fail(-32601, f"method not found: {method}")


def serve(stdin=None, stdout=None) -> None:
    stdin = stdin or sys.stdin.buffer
    stdout = stdout or sys.stdout.buffer
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line.decode("utf-8") if isinstance(line, bytes) else line)
        except (UnicodeDecodeError, json.JSONDecodeError):
            answer = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
        else:
            answer = handle(message) if isinstance(message, dict) else {
                "jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "one message per line"}
            }
        if answer is not None:
            stdout.write(json.dumps(answer, ensure_ascii=False).encode("utf-8") + b"\n")
            stdout.flush()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="eqlens-mcp",
        description="Serve eqlens to an MCP client over stdio: draw a formula, look inside one, build a bench for one.",
    )
    parser.add_argument("--tools", action="store_true", help="list the tools and exit")
    args = parser.parse_args(argv)
    if args.tools:
        for tool in TOOLS:
            print(f"{tool['name']:<16} {tool['title']}")
        return 0
    # matplotlib may write warnings to stdout, which belongs to the protocol.
    out = sys.stdout.buffer
    sys.stdout = sys.stderr
    try:
        serve(stdout=out)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
