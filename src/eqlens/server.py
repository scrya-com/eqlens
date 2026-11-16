"""HTTP service. Binds to 127.0.0.1 unless --host says otherwise.

GET  /health
GET  /svg?tex=...&color=%23f2f2f7&bg=transparent&legend=1&note=...&define=P%3Dmeaning
GET  /png?tex=...&dpi=220
GET  /glsl?tex=...   a WebGL2 fragment shader that draws the formula
POST /svg    {"tex": "...", "legend": true, "notes": ["..."], "define": ["P=meaning"], "font": "sans"}
POST /png    {"tex": "...", "dpi": 220, "color": "#f2f2f7", "bg": null}

Both paths take the same fields. ``note`` and ``define`` repeat in a query string.
"""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from eqlens.render import FormulaError, render

_MAX_BODY = 64 * 1024
_TYPES = {
    "/svg": ("svg", "image/svg+xml"),
    "/png": ("png", "image/png"),
    "/html": ("html", "text/html; charset=utf-8"),
    "/glsl": ("glsl", "text/plain; charset=utf-8"),
}


class Handler(BaseHTTPRequestHandler):
    server_version = "eqlensd/0.2"

    def log_message(self, fmt: str, *args) -> None:
        return

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._json(200, {"ok": True, "service": "eqlensd"})
            return
        if parsed.path in {"/", ""}:
            self._text(
                200,
                "eqlensd\n"
                "GET /health\n"
                "GET /svg?tex=...\n"
                "GET /png?tex=...\n"
                "POST /svg  {\"tex\": \"...\"}\n"
                "POST /png  {\"tex\": \"...\"}\n",
            )
            return
        if parsed.path not in _TYPES:
            self._json(404, {"error": "not found"})
            return
        query = parse_qs(parsed.query)
        tex = query.get("tex", [""])[0]
        self._render(
            parsed.path,
            tex,
            {
                "dpi": _optional_int(query.get("dpi", [None])[0]),
                "color": query.get("color", [None])[0],
                "bg": query.get("bg", [None])[0],
                "legend": query.get("legend", [""])[0].lower() in ("1", "true", "yes"),
                "brief": query.get("brief", [""])[0].lower() in ("1", "true", "yes"),
                "notes": query.get("note", []),
                "define": query.get("define", []),
                "tier": query.get("tier", []),
                "font": query.get("font", [None])[0],
            },
        )

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path not in _TYPES:
            self._json(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length < 0 or length > _MAX_BODY:
            self._json(400, {"error": "body too large"})
            return
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._json(400, {"error": "body must be JSON"})
            return
        if not isinstance(payload, dict):
            self._json(400, {"error": "body must be a JSON object"})
            return
        self._render(parsed.path, str(payload.get("tex", "")), payload)

    def _render(self, path: str, tex: str, fields: dict) -> None:
        fmt, content_type = _TYPES[path]
        dpi, color, bg = fields.get("dpi"), fields.get("color"), fields.get("bg")
        kwargs = {}
        for name in ("notes", "define", "tier", "constant", "shared"):
            value = fields.get(name) or []
            if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                self._json(400, {"error": f"{name} must be a list of strings"})
                return
            kwargs[name] = value
        kwargs["legend"] = fields.get("legend") is True
        kwargs["brief"] = fields.get("brief") is True
        kwargs["tips"] = fields.get("tips") is True
        kwargs["credit"] = fields.get("credit") is not False
        if fields.get("font"):
            kwargs["font"] = str(fields["font"])
        if dpi is not None:
            if not isinstance(dpi, int) or isinstance(dpi, bool):
                self._json(400, {"error": "dpi must be an integer"})
                return
            kwargs["dpi"] = dpi
        if color:
            kwargs["color"] = str(color)
        if bg is not None:
            kwargs["bg"] = None if bg in ("", "transparent", None) else str(bg)
        try:
            data = render(tex, fmt, **kwargs)
        except FormulaError as exc:
            self._json(400, {"error": str(exc)})
            return
        self._bytes(200, content_type, data)

    def _json(self, status: int, payload: dict) -> None:
        self._bytes(status, "application/json", json.dumps(payload).encode("utf-8"))

    def _text(self, status: int, text: str) -> None:
        self._bytes(status, "text/plain; charset=utf-8", text.encode("utf-8"))

    def _bytes(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        # Tells the client this eqlensd draws the ledger, defined symbols, and notes itself.
        self.send_header("X-Eqlens-Card", "1")
        self.end_headers()
        self.wfile.write(body)


def _optional_int(value):
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return value


def serve(host: str, port: int) -> None:
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"eqlensd listening on http://{host}:{port}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="eqlensd", description="Serve math formulas as SVG or PNG on localhost.")
    parser.add_argument("--host", default="127.0.0.1", help="bind address (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    serve(args.host, args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
