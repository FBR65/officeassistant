# P0 spike results

Date: 2026-11-05
Host: `/home/speedy/Dokumente/dev/OfficeAssistant`, Python 3.12 (uv), Podman, llama-swap `:8080`
Evidence rule: a spike counts as passed only with the command or artefact quoted below.

| Spike | Result | Evidence |
|---|---|---|
| P0.1 KoliBri in NiceGUI | **PASS** | rendered card/input/button, click and input reached Python, zero console errors, zero external requests |
| P0.2 approval durability (Postgres) | **PASS** | run `PAUSED` → approval row → process killed → restart → still pending → approved → run `COMPLETED`, tool executed once |
| P0.3 LDAP → Keycloak → AgentOS | **PASS**, with three findings | 401 without token, 200 with LDAP user token, 403 with a member token on `/config`, 404 on a foreign session |
| P0.4 tool calling via llama-swap | **PASS for one model, FAIL for another** | `deepseek-v4-pro-qwen3.5-9b`: one tool call in 14.2 s; `gemma-4-12B-TurboQuant`: no tool call, prompt echo, token cap |
| P0.5 Gmail read-only | **PARTIAL / blocked** | peer probe proves Gmail API read works with existing consent (20 headers); our own OAuth client and token store are not authorised yet |
| P0.6 Microsoft Graph | **BLOCKED** | no tenant and no test mailbox |
| P0.7 on-prem Exchange IMAP | **BLOCKED** | no Exchange account |

---

## P0.1 — KoliBri inside NiceGUI

Code: `spikes/p0_1_kolibri/app.py`, vendored assets `static/kolibri/` (52 MB from
`@public-ui/components` 4.5.0 and `@public-ui/theme-default`, self-hosted, no CDN).

Measured in a real browser (Chrome via CDP):

```
kol-button registriert: True
kol-input-text registriert: True
shadow vorhanden: True
fremde Requests: []
fehler: []
state: Eingabe in Python: frank@example.org
```

Bridge events (`spike_events.jsonl`):

```
{"kind": "click", "count": 1, "args": {"label": "Zaehlen"}}
{"kind": "input", "args": {"value": "frank@example.org"}}
```

Three findings that cost time and belong in the UI layer:

1. `kol-card` takes its content in the **default slot**. `slot="content"` renders nothing.
2. `kol-input-text` has **no `value` property**. `getValue()` returns a **Promise**; the
   bridge must `await` it. Reading `el.value` yields `undefined`, which arrives in Python
   as `None`/`{}` without any error.
3. `emitEvent` exists as a global JS function in NiceGUI 4 and carries payloads to
   `ui.on(...)`; the payload arrives at `e.args`.

Verdict: variant A (NiceGUI host, KoliBri views) is viable. No fallback to a KoliBri SPA
is needed.

---

## P0.2 — approval durability on Postgres

Code: `spikes/p0_2_approval/app.py` (Agno 3.1.12, `PostgresDb`, `@approval`,
`@tool(requires_confirmation=True)`), Postgres 16 in Podman on `127.0.0.1:55432`.

Sequence and observed answers:

```
run:200
status = PAUSED
content = I have tools to execute, but I need confirmation.

GET /approvals?status=pending  -> 200
id dd67a710-… | archive_message | {'message_id': 'M-42'} | run a4c0d005-…

[kill uvicorn, start it again]

GET /approvals?status=pending  -> 200, same row still pending
executed.log                   -> does not exist  (tool really did not run)

POST /approvals/dd67a710-…/resolve {"status":"approved","resolved_by":"frank"} -> 200
POST /agents/p02-agent/runs/a4c0d005-…/continue                                 -> 200
status = COMPLETED
content = Die Mail mit der ID M-42 wurde erfolgreich archiviert.
executed.log -> "archived M-42"
```

Findings:

- The approval survives a process restart on Postgres. The original SQLite doubt (R2) is
  settled: Postgres is the right default, not a fallback.
- The API is asymmetric and must be implemented exactly like this:
  `POST /agents/{id}/runs` takes **multipart/form-data**, `POST /agents/{id}/runs/{run_id}/continue`
  takes **form-urlencoded**, `POST /approvals/{id}/resolve` takes **JSON**.
- Resolving alone does not continue the run; the UI must call `continue` after a decision.

---

## P0.3 — LDAP → Keycloak → AgentOS

Code: `spikes/p0_3_iam/` (`realm-oa.json` import, `add_mappers.py`, `member_client.py`,
`app.py`), containers `oa-ldap` (osixia/openldap 1.5.0, users alice/bob),
`oa-kc` (Keycloak 26.0.8, realm `oa`), AgentOS on `:7789` with
`authorization=True`, `user_isolation=True`, `JWT_JWKS_FILE=/tmp/oa_jwks.json`.

Observed:

```
ohne Token:            401
fake-Token:            401
alice (member) /agents: 200
alice run -> status COMPLETED, session f0ad0af7-…
alice liest eigene:    200
bob liest fremde:      404
bob /sessions:         []        (leer)
member-Token /config, /eval-runs, /traces: 403
```

Findings:

1. **LDAP federation needs attribute mappers.** A user-storage provider imported without
   the `user-attribute-ldap-mapper` set queries the directory with an empty
   returning-attribute list; Keycloak then fails with
   `User returned from LDAP has null username! … attributes from LDAP: {}`.
   Reproduced on two different LDAP servers (bitnami, osixia), fixed by adding the four
   mappers (username↔uid, email↔mail, firstName↔cn, lastName↔sn). The production realm
   export must contain them.
2. **`cryptography` is required for RS256.** Without it every JWKS key fails to parse and
   AgentOS refuses to start with "At least one JWT verification key or JWKS file is
   required" — a misleading message for a missing dependency.
3. **`AuthorizationConfig(jwks_file=…)` did not reach the validator** in 3.1.12; the
   environment variable `JWT_JWKS_FILE` works. Configure the path by environment.
4. **`agent_os:admin` bypasses per-user isolation.** With an admin token, bob could read
   alice's session (200) and list it. With a member token the same request is 404 and the
   list is empty. Consequence for the design: `owner`/`admin` roles must be rare and
   audited; every member token carries narrow scopes only.

LDAP→AD readiness: the mapping table (SPEC 5.3.1) is exactly what was configured here;
switching to AD changes the vendor preset and the login attribute, not the code.

---

## P0.4 — tool calling through llama-swap

Code: `spikes/p0_4_toolcall/probe.py`. One request, one tool, no prompt tuning.

`deepseek-v4-pro-qwen3.5-9b`:

```
latency_s  : 14.2
finish     : tool_calls
tool_calls : [{"type":"function","function":{"name":"get_inbox_count",
              "arguments":"{\"account\":\"frank@example.org\"}"}}]
verdict    : PASS
```

`gemma-4-12B-TurboQuant`:

```
tool_calls : []
content    : "…<|im_start|>user…<|im_start|>assistant…" (prompt echo, repeated)
prompt_tokens: 40        <- the tools array never reached the chat template
completion_tokens: 300   <- stopped by max_tokens
verdict    : FAIL
```

Interpretation: the entry is served without tool support (Jinja template not applied),
and the model does not compensate for it. It is not usable for a tool-bearing role.

Consequence: `deepseek-v4-pro-qwen3.5-9b` is the candidate for the tool-bearing roles.
`gemma-4-12B-TurboQuant` needs a server-side `--jinja` / template fix before it can be
considered again — that is a llama-swap configuration change and a separate approval.

---

## P0.5 — Gmail read-only (partial)

Verified through the peer `hermesbot` (192.168.178.72), which holds an existing Google
consent:

- Gmail API path: OAuth refresh works, `users.messages.list` + `get(format=metadata)`
  returns 20 messages with `Message-ID`, e.g. `id 1a1a13d2679f74c7`, Google Developers,
  `Tue, 03 Nov 2026 03:48:21 -0800`.
- IMAP path: `SELECT` read-only, 14 headers in INBOX, same first message.
- Granted scopes include `gmail.readonly`, `gmail.modify`, `gmail.send`, plus Drive,
  Docs, Sheets, Contacts, Calendar.

What this does **not** prove: our own token store, our own OAuth client and the refresh
across a restart on this host. That needs a Google Cloud OAuth client (Desktop app type)
and one consent per mailbox. Until then P0.5 stays partial.

Also noted from the peer: that mailbox holds ~20 messages in total. Paging, history sync
and cursor tests need synthetic test data.

---

## Environment left behind

| What | State |
|---|---|
| `oa-pg-test` (Postgres 16, `:55432`) | stopped after the run |
| `oa-ldap`, `oa-kc` (Podman network `oa-net`) | stopped after the run |
| `llama-swapel` | untouched, models unloaded |
| Spikes | `spikes/p0_1_kolibri`, `p0_2_approval`, `p0_3_iam`, `p0_4_toolcall` |

Restart commands are in the header of each spike file.
