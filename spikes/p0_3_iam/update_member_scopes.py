"""Mitglieds-Scopes am laufenden Keycloak ergänzen (Testclient `oa-ui-member`)."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request

KC = "http://127.0.0.1:8180"
REALM = "oa"
CLIENT = "oa-ui-member"
SCOPES = [
    "agents:read",
    "agents:*:run",
    "sessions:read",
    "sessions:write",
    "runs:read",
    "approvals:read",
    "approvals:write",
]


def admin_token() -> str:
    form = urllib.parse.urlencode(
        {"grant_type": "password", "client_id": "admin-cli", "username": "admin",
         "password": "adminpw"}
    ).encode()
    req = urllib.request.Request(
        KC + "/realms/master/protocol/openid-connect/token", data=form
    )
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())["access_token"]


def call(method: str, path: str, token: str, data=None):
    req = urllib.request.Request(KC + path, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, data=body, timeout=30) as resp:
        raw = resp.read()
        return resp.status, (json.loads(raw) if raw else None)


def main() -> None:
    tok = admin_token()
    _, clients = call("GET", f"/admin/realms/{REALM}/clients?clientId={CLIENT}", tok)
    client_id = clients[0]["id"]
    _, mappers = call(
        "GET", f"/admin/realms/{REALM}/clients/{client_id}/protocol-mappers/models", tok
    )
    for mapper in mappers:
        if mapper["config"].get("claim.name") == "scopes":
            mapper["config"]["claim.value"] = json.dumps(SCOPES)
            status, _ = call(
                "PUT",
                f"/admin/realms/{REALM}/clients/{client_id}/protocol-mappers/models/{mapper['id']}",
                tok,
                mapper,
            )
            print("mapper aktualisiert:", status, SCOPES)


if __name__ == "__main__":
    main()
