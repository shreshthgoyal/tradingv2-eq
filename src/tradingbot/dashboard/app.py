from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer


class DashboardHandler(BaseHTTPRequestHandler):
    payload = {"status": "ok", "message": "tradingbot dashboard"}

    def do_GET(self) -> None:  # noqa: N802
        body = json.dumps(self.payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    server = HTTPServer((host, port), DashboardHandler)
    server.serve_forever()
