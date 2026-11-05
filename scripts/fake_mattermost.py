"""Kleiner Mattermost-Ersatz für Prüfungen ohne echten Server.

Beantwortet nur die Aufrufe, die die Chat-Seite braucht:
GET /api/v4/users/me/teams, GET …/teams/{id}/channels, GET …/channels/{id}/posts,
POST …/posts. Start:

    uv run python scripts/fake_mattermost.py 8065
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

KANAELE = [
    {"id": "kanal-allgemein", "name": "allgemein"},
    {"id": "kanal-buero", "name": "buero"},
]
POSTS: dict[str, list[dict[str, str]]] = {
    "kanal-allgemein": [
        {
            "id": "p1",
            "user_id": "u-alice",
            "message": "Guten Morgen. Das Postfach ist angebunden.",
            "create_at": "1",
        },
        {
            "id": "p2",
            "user_id": "u-bob",
            "message": "Der Kalender läuft über ICS.",
            "create_at": "2",
        },
    ],
    "kanal-buero": [],
}


class Handler(BaseHTTPRequestHandler):
    def _sende(self, daten: object, status: int = 200) -> None:
        roh = json.dumps(daten).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(roh)))
        self.end_headers()
        self.wfile.write(roh)

    def do_GET(self) -> None:  # noqa: N802 - Vorgabe des Moduls
        pfad = urlparse(self.path).path
        if pfad == "/api/v4/users/me/teams":
            self._sende([{"id": "team-1", "display_name": "Büro"}])
        elif pfad == "/api/v4/users/me/teams/team-1/channels":
            self._sende(KANAELE)
        elif pfad.startswith("/api/v4/channels/") and pfad.endswith("/posts"):
            kennung = pfad.split("/")[4]
            posts = POSTS.get(kennung, [])
            self._sende(
                {
                    "order": [post["id"] for post in reversed(posts)],
                    "posts": {post["id"]: post for post in posts},
                }
            )
        else:
            self._sende({"message": "nicht gefunden"}, 404)

    def do_POST(self) -> None:  # noqa: N802 - Vorgabe des Moduls
        pfad = urlparse(self.path).path
        laenge = int(self.headers.get("Content-Length", "0"))
        daten = json.loads(self.rfile.read(laenge) or b"{}")

        if pfad == "/api/v4/posts":
            kanal = str(daten.get("channel_id", ""))
            text = str(daten.get("message", ""))
            neu = {
                "id": f"p{len(POSTS.get(kanal, [])) + 1}-{int(datetime.now(UTC).timestamp())}",
                "user_id": "u-alice",
                "message": text,
                "create_at": str(int(datetime.now(UTC).timestamp())),
            }
            POSTS.setdefault(kanal, []).append(neu)
            self._sende(neu, 201)
        elif pfad == "/api/v4/teams/search":
            self._sende([{"id": "team-1", "display_name": "Büro"}])
        else:
            self._sende({"message": "nicht gefunden"}, 404)

    def log_message(self, *args) -> None:  # leise bleiben
        return


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8065
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
