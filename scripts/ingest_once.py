"""Einmaliger Empfänger für Zugangsdaten von einem Peer (nur im LAN, kurze Laufzeit).

Nimmt genau eine POST-Anfrage an, schreibt den Inhalt in eine Datei mit Rechten 600 und
beendet sich. Kein Weiterleiten, kein Protokollieren des Inhalts.
"""

from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

TOKEN = os.environ.get("INGEST_TOKEN", "")
MODE = os.environ.get("INGEST_MODE", "json")  # json | gpg
TARGET = os.environ.get("INGEST_TARGET", "/tmp/oa_ingest.json")
PORT = int(os.environ.get("INGEST_PORT", "8091"))


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - Signatur des Basismoduls
        if self.path == f"/ping/{TOKEN}":
            self._answer(200, {"ok": True})
        else:
            self._answer(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802 - Signatur des Basismoduls
        if self.path != f"/ingest/{TOKEN}":
            self._answer(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        if not body:
            self._answer(400, {"error": "leerer Inhalt"})
            return
        if MODE == "gpg":
            # Verschlüsselter Inhalt: unverändert ablegen, Entschlüsselung erfolgt danach.
            with open(TARGET, "wb") as fh:
                fh.write(body)
            os.chmod(TARGET, 0o600)
            self._answer(200, {"ok": True, "bytes": len(body), "mode": "gpg"})
            raise SystemExit(0)
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            self._answer(400, {"error": "kein JSON"})
            return
        if not isinstance(parsed, dict):
            self._answer(400, {"error": "Objekt erwartet"})
            return
        with open(TARGET, "w", encoding="utf-8") as fh:
            json.dump(parsed, fh)
        os.chmod(TARGET, 0o600)
        self._answer(200, {"ok": True, "keys": sorted(parsed.keys())})
        # Nach dem Schreiben beenden (kein Dauerbetrieb).
        raise SystemExit(0)

    def _answer(self, code: int, payload: dict) -> None:
        raw = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, fmt: str, *args) -> None:
        # Keine Inhalte, nur Pfad und Status.
        sys.stderr.write("ingest: " + fmt % args + "\n")


if __name__ == "__main__":
    if not TOKEN:
        print("INGEST_TOKEN fehlt", file=sys.stderr)
        raise SystemExit(2)
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"bereit auf :{PORT}, Ziel {TARGET}", flush=True)
    server.serve_forever()
