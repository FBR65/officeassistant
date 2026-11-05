"""Add the standard LDAP attribute mappers to the oa realm.

The realm import created the user-storage provider but no LDAP mappers. Without
mappers the user query carries an empty returning-attribute list, JNDI asks the
server for no attributes at all, and Keycloak fails with
"User returned from LDAP has null username".
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request

KC = "http://127.0.0.1:8180"
REALM = "oa"


def call(method: str, path: str, token: str | None = None, data: dict | None = None):
    req = urllib.request.Request(KC + path, method=method)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, data=body, timeout=30) as resp:
        raw = resp.read()
        return resp.status, (json.loads(raw) if raw else None)


def token() -> str:
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


MAPPERS = [
    ("username", "uid"),
    ("email", "mail"),
    ("firstName", "cn"),
    ("lastName", "sn"),
]


def main() -> None:
    tok = token()
    _, comps = call("GET", f"/admin/realms/{REALM}/components?type=org.keycloak.storage.UserStorageProvider", tok)
    provider_id = comps[0]["id"]
    print("provider:", provider_id)

    _, existing = call(
        "GET",
        f"/admin/realms/{REALM}/components?parent={provider_id}&type=org.keycloak.storage.ldap.mappers.LDAPStorageMapper",
        tok,
    )
    have = {c["config"].get("user.model.attribute", [None])[0] for c in existing}
    print("existing mappers:", have)

    for model_attr, ldap_attr in MAPPERS:
        if model_attr in have:
            print("skip", model_attr)
            continue
        payload = {
            "name": f"{model_attr}-mapper",
            "providerId": "user-attribute-ldap-mapper",
            "providerType": "org.keycloak.storage.ldap.mappers.LDAPStorageMapper",
            "parentId": provider_id,
            "config": {
                "user.model.attribute": [model_attr],
                "ldap.attribute": [ldap_attr],
                "read.only": ["true"],
                "always.read.value.from.ldap": ["true"],
                "is.mandatory.in.ldap": ["false"],
            },
        }
        status, _ = call("POST", f"/admin/realms/{REALM}/components", tok, payload)
        print(f"create {model_attr} -> {status}")

    _, after = call(
        "GET",
        f"/admin/realms/{REALM}/components?parent={provider_id}&type=org.keycloak.storage.ldap.mappers.LDAPStorageMapper",
        tok,
    )
    print("now:", [(c["name"], c["config"]["user.model.attribute"]) for c in after])


if __name__ == "__main__":
    main()
