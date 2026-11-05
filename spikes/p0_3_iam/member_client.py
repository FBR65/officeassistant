"""Create a second Keycloak client whose tokens carry narrow scopes (no agent_os:admin).

Needed because an admin-scoped token legitimately bypasses per-user ownership gates;
the isolation proof must run with an ordinary member token.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request

KC = "http://127.0.0.1:8180"
REALM = "oa"
CLIENT = "oa-ui-member"
SCOPES = ["agents:read", "agents:*:run", "sessions:read", "sessions:write", "runs:read"]


def admin_token() -> str:
    form = urllib.parse.urlencode(
        {
            "grant_type": "password",
            "client_id": "admin-cli",
            "username": "admin",
            "password": "adminpw",
        }
    ).encode()
    req = urllib.request.Request(
        KC + "/realms/master/protocol/openid-connect/token", data=form
    )
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())["access_token"]


def call(method, path, token, data=None):
    req = urllib.request.Request(KC + path, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, data=body, timeout=30) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()[:300]


def main() -> None:
    tok = admin_token()
    status, existing = call("GET", f"/admin/realms/{REALM}/clients?clientId={CLIENT}", tok)
    if existing:
        print("client exists:", existing[0]["id"])
        cid = existing[0]["id"]
    else:
        payload = {
            "clientId": CLIENT,
            "secret": "membersecret",
            "publicClient": False,
            "directAccessGrantsEnabled": True,
            "standardFlowEnabled": False,
            "protocolMappers": [
                {
                    "name": "agno-scopes-member",
                    "protocol": "openid-connect",
                    "protocolMapper": "oidc-hardcoded-claim-mapper",
                    "config": {
                        "claim.name": "scopes",
                        "claim.value": json.dumps(SCOPES),
                        "jsonType.label": "JSON",
                        "access.token.claim": "true",
                        "id.token.claim": "false",
                        "userinfo.token.claim": "false",
                    },
                }
            ],
        }
        status, body = call("POST", f"/admin/realms/{REALM}/clients", tok, payload)
        print("create client:", status, body if status >= 300 else "")
        _, existing = call("GET", f"/admin/realms/{REALM}/clients?clientId={CLIENT}", tok)
        cid = existing[0]["id"]

    # ensure the mapper exists (import may have skipped it)
    _, mappers = call("GET", f"/admin/realms/{REALM}/clients/{cid}/protocol-mappers/models", tok)
    if not any(m["protocolMapper"] == "oidc-hardcoded-claim-mapper" for m in mappers):
        status, body = call(
            "POST",
            f"/admin/realms/{REALM}/clients/{cid}/protocol-mappers/models",
            tok,
            {
                "name": "agno-scopes-member",
                "protocol": "openid-connect",
                "protocolMapper": "oidc-hardcoded-claim-mapper",
                "config": {
                    "claim.name": "scopes",
                    "claim.value": json.dumps(SCOPES),
                    "jsonType.label": "JSON",
                    "access.token.claim": "true",
                    "id.token.claim": "false",
                    "userinfo.token.claim": "false",
                },
            },
        )
        print("mapper:", status, body if status >= 300 else "")
    print("client id:", cid, "| scopes:", SCOPES)


if __name__ == "__main__":
    main()
