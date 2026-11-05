# OfficeAssistant — Specification (v0.2, decisions applied)

Status: **draft v0.2 — decisions Q1–Q6 applied, no code written, P0 not started**
Date: 2026-11-05
Repository: `/home/speedy/Dokumente/dev/OfficeAssistant` (empty `uv` scaffold, `uv_build`, Python 3.12)
License target: MIT (private use)

## Change log

| Version | Change |
|---|---|
| 0.1 | initial draft, six open questions |
| 0.2 | Q1 model = OpenAI-compatible endpoint; Q2 UI = variant A; Q3 both Exchange paths mandatory; Q4 Podman; Q5 multi-user with IAM; Q6 all three routines; integration scope fixed (excluded / desirable) |
| 0.3 | Q7 identity = LDAP now, Active Directory later (must stay possible without code change); Q8 model endpoint = the local llama-swap instance |
| 0.5 | Q9 = Variante B: Freigaben löst ein Dienstkonto mit `agent_os:admin`; der Mensch steht in `resolution_data`. P1 und P2 (Testanbieter) umgesetzt — siehe `p1-results.md`, `p2-results.md` |
| 0.11 | Gmail angebunden über IMAP mit App-Kennwort (Abweichung: kein OAuth) — siehe `p2-1-gmail-results.md` |
| 0.10 | Arbeitsseiten `/post`, `/chat`, `/kalender`: Postfach lesen und Entwurf, Mattermost mit 5-Sekunden-Takt, Kalender aus ICS mit Graph-Vorbereitung — siehe `arbeitsseiten-results.md` |
| 0.9 | Anbindungen (Jira, Confluence, Mattermost, SharePoint, OneNote, Webex) samt Seite `/anbindungen`; Skype abgeschaltet. P5.5 Proben gegen Einschleusung; P6 Nachweistabelle — siehe `connections-results.md`, `p6-evidence.md` |
| 0.8 | P4.2–P4.4 mit Zeitgeber (systemd-Nutzerdienst) und Seite `/routinen` — siehe `docs/specs/p4-results.md` |
| 0.7 | P4.1 umgesetzt (Team mit vier Rollen), P4.5 bereits in P2 belegt — siehe `docs/specs/p4-results.md` |
| 0.6 | P3.5 umgesetzt (IMAP/SMTP gegen GreenMail geprüft), P3.6 teilweise; P3.1–P3.4 warten auf ein Entra-Konto — siehe `docs/specs/p3-results.md` |
| 0.4 | P0 executed: results in `docs/specs/p0-results.md`; P0.1–P0.4 passed, P0.5 partial (needs our own OAuth client), P0.6/P0.7 blocked (no accounts); four constraints from the spikes folded in (5.3.1, 5.6, 5.7, 9) |

---

## 1. Decisions (binding for v1)

| # | Decision | Consequence in this spec |
|---|---|---|
| Q1 | Model access through an **OpenAI-compatible endpoint**, provider chosen by the operator | `agno.models.openai.like.OpenAILike(id, api_key, base_url)`; no provider-specific code, no hard-coded vendor |
| Q2 | **Variant A**: NiceGUI hosts the app, KoliBri supplies the components, JS bridge to Python | Flet is out; no Quasar widgets in user views; KoliBri assets self-hosted |
| Q3 | **Both** Microsoft paths must work: Exchange Online via Graph **and** on-prem Exchange via IMAP/SMTP | Graph adapter and IMAP adapter are both v1 scope, both with tests |
| Q4 | Deployment with **Podman** (rootless quadlets) | one quadlet per service, `podman secret`, no host network, no docker-compose |
| Q5 | **Multi-user with IAM** | OIDC login, JWT against AgentOS, `user_isolation=True`, per-user mailbox credentials, per-user approvals and audit |
| Q6 | All three routines: morning briefing, inbox triage, meeting prep | P4 delivers three routines, not one |
| Q7 | Identity: **LDAP now, Active Directory later**, which must remain reachable by configuration only | Keycloak with LDAP user federation in front of AgentOS; AD is a vendor-preset and attribute-mapping change, no code change (5.3) |
| Q9 | Freigaben löst ein **Dienstkonto** (Variante B), nicht das Mitglied selbst | Agno sperrt die Auflösung für Nicht-Administratoren bei `user_isolation=True`; das Dienstkonto trägt `agent_os:admin`, liegt nur im UI-Prozess, der Mensch erscheint in `resolution_data.entschieden_von` |
| Q8 | Model endpoint: **the local llama-swap instance** (`127.0.0.1:8080`, OpenAI-compatible) | `base_url` points at llama-swap, model id is configuration, tool calling must be proven per model (P0.4) |
| — | Not needed: iOS, Slack, Telegram, WhatsApp, Google Workspace (Docs/Drive/Sheets), Notion, HubSpot, Linear, Zoom | no tasks; adapter slots stay closed |
| — | Desirable later: Skype, Mattermost, OneNote, Webex, Jira, Confluence, SharePoint | **umgesetzt als Anbindungen** (P3.7): Adapter für Jira, Confluence, Mattermost, SharePoint, OneNote, Webex; Skype ist abgeschaltet — siehe `docs/specs/connections-results.md` |

---

## 2. Goal and scope

On-premise, multi-user office assistant that reads mailboxes and calendars, does
recurring work unattended, and never sends or writes without a trust setting.

**In v1:** Gmail, Microsoft 365 / Exchange Online (Graph), on-prem Exchange (IMAP/SMTP),
calendar, three routines, approval inbox, activity log, multi-user login with roles.

**Out of v1:** every integration in the "not needed" list, mobile apps, voice,
multi-tenant SaaS operation, document search over drives (the knowledge base covers mail
and calendar content only).

---

## 3. Facts base (read 2026-11-05)

### 3.1 Town (town.com) — capability inventory

| Capability | Source |
|---|---|
| Named assistant ("Townie") with its own mailbox `name@town.com`; usable via web app, e-mail, iOS, Slack, Telegram, WhatsApp | `town.com/docs` |
| Connects Google Workspace (Gmail, Calendar, Docs, Drive, Sheets), Slack, Notion, HubSpot, Linear, Jira, Airtable, Dropbox, GitHub, Zoom, Calendly, … plus custom tools via MCP | `town.com/docs` |
| **Routines**: recurring jobs in natural language, on a trigger or a schedule | `town.com/docs/features/routines` |
| Stock routine library (Morning Briefing, Auto-inbox triage, Meeting Briefing) — "not templates, they learn how you work" | `town.com/docs/features/routines` |
| Custom routines are built in conversation, not via a form | `town.com/docs/features/routines` |
| **Trust dial per routine and per tool**: `read-only` / `approval-required` / `autonomous`, mixable inside one routine | `town.com/docs/features/routines` |
| Learning from corrections: people, projects, writing voice; visible "wiki"; no instruction files | `town.com/product` |
| Tasks / "Need to Know" follow-up list; every action visible in an activity view | `town.com/docs` |
| Team layer: shared routines and skills ("Powers"), per-teammate permissions | `town.com/product` |
| Own browser for work outside integrations | `town.com/product` |
| SOC 2 Type 2, DPA, no training on customer data | `town.com/product` |

**Notable gap:** Town's documented integration list has Google Workspace and
Microsoft-adjacent tools, but **no Exchange/Outlook mail integration**. That gap is where
this project sits.

### 3.2 Frameworks and interfaces

| Item | Fact | Source |
|---|---|---|
| Agno | 3.1.12 (PyPI), Python `>=3.9` | pypi.org |
| OpenAI-compatible models | `OpenAILike(id=…, api_key=…, base_url=…)`, inherits `OpenAIChat` | `docs.agno.com/models/providers/openai-like` |
| AgentOS | FastAPI runtime: REST + SSE, sessions, memory, knowledge, background execution, scheduler, approvals, JWT/RBAC, MCP/A2A/AG-UI | `docs.agno.com/agent-os/introduction` |
| AgentOS auth | modes `jwt` / `security_key` / `none`; `authorization=True` enforces scopes; tokens may come from "a third-party identity provider like WorkOS, Auth0, or Okta"; `JWT_VERIFICATION_KEY` or `JWT_JWKS_FILE` | `docs.agno.com/agent-os/security/overview` |
| AgentOS isolation | `user_isolation=True` scopes user-owned data to the caller's user ID; roles Owner / Administrator / Member / custom | `docs.agno.com/agent-os/security/authorization/overview` |
| Approvals | `@approval` + `@tool(requires_confirmation=True)`; DB-backed record; pause/resume; `type="audit"` non-blocking | `docs.agno.com/agent-os/approvals/overview` |
| Scheduler | `AgentOS(scheduler=True)`, cron, run history, `SchedulerTools` | `docs.agno.com/agent-os/scheduler/overview` |
| Gmail toolkit | read/search/send/label; OAuth; **token stored under a shared provider identity (`google`, no user ID)** | `docs.agno.com/tools/toolkits/social/gmail` |
| E-mail toolkit | `EmailTools` — Gmail SMTP app password, **send only** | `docs.agno.com/tools/toolkits/social/email` |
| Microsoft mail | no Graph toolkit in the Agno toolkit index → own adapter | `docs.agno.com/tools/toolkits/overview` |
| EWS | Exchange Online EWS retired and blocked from **2026-10-01**; migration path is Graph | IBM support, UiPath migration guide |
| Skype | consumer Skype retired **2025-05-05**; Skype for Business Online retired **2021-07-31** | Microsoft support |
| OneNote | Graph `/onenote/*` (notebooks, sections, pages) | learn.microsoft.com/graph |
| Mattermost | REST API + bot accounts with personal access tokens | docs.mattermost.com |
| Webex | REST API, bot tokens; bots see only DMs and @mentions | developer.webex.com |
| Keycloak | User Federation "sync users from LDAP and Active Directory servers"; Kerberos bridge for SSO | `keycloak.org/docs/latest/server_admin` |
| llama-swap (host) | `llama-swapel`, `ghcr.io/mostlygeek/llama-swap:unified-cuda`, `:8080`, OpenAI-compatible `/v1/models`, 14 entries listed 2026-11-05 | `podman ps`, `curl :8080/v1/models` |
| KoliBri | v4, EUPL-1.2, Stencil web components, WCAG 2.2 / BITV 2.0, `_`-prefixed props, `register(theme, defineCustomElements)`, themes Default/BWSt/Desy/ECL/KERN | `public-ui.github.io/en/docs/get-started/first-steps` |
| NiceGUI | 4.0.0, Python `>=3.11`, FastAPI + WebSocket, `ui.html`, `ui.add_head_html`, generic JS events, `native=True` (pywebview) | nicegui.io docs |
| Flet | 1.0.5, Flutter canvas, no DOM → KoliBri only inside a WebView island (`flet-webview`) | `flet.dev/docs` |

### 3.3 What the linked Gemini answer gets right and wrong

Right: a self-hosted stack of local inference + agent framework + accessible frontend is
feasible; Agno fits; own Python tools for mail protocols are the usual route.

Wrong or unusable for production:
- `AutoGPT / BabyAGI` are research toys, not an operations platform.
- "OpenCoesion / Localized Open Government Bots" — no verifiable project.
- It implies Agno ships mail tooling for Exchange/Outlook. It does not.
- It omits the constraint that decides the frontend: KoliBri are HTML web components,
  Flet is a Flutter canvas.

---

## 4. UI: NiceGUI as host, KoliBri as component layer (Q2 = variant A)

Flet is rejected: KoliBri are HTML custom elements, Flet renders a Flutter canvas without
DOM. KoliBri inside a Flet `WebView` would be a foreign island with its own focus order —
that contradicts the accessibility requirement.

| | Flet 1.0.5 | NiceGUI 4.0.0 |
|---|---|---|
| Rendering | Flutter canvas | real DOM in the browser |
| KoliBri | only inside a WebView island | in-page, shared theme and focus order |
| JS interop | no DOM access | `run_javascript`, generic events |
| Delivery | native binaries | browser, ASGI behind reverse proxy |

Variant A rules:

1. Every user-facing view is a KoliBri composition, injected with `ui.html`.
2. `kol-*` events (click, input change, dialog close) travel over a thin JS bridge to
   Python handlers; the bridge is one module with its own tests.
3. Quasar widgets are not used in user views. Permitted exceptions: `ui.notify` and the
   transient loading spinner, until replaced by `kol-toast` / `kol-spinner`.
4. KoliBri packages are vendored from npm and served from `/static/kolibri/`.
   No CDN call in production.
5. Theme is registered once per page load; Default and BWSt are selectable.

Cost accepted: two event models (KoliBri custom events, NiceGUI websocket state) must be
kept in sync. P0.1 proves this before any feature work.

---

## 5. Architecture (v0.2)

Multi-user changes the v0.1 sketch in one important way: the NiceGUI process no longer
runs the agents in-process. It becomes a frontend for the AgentOS API, so authentication,
isolation and audit have exactly one owner.

```
                  Browser (KoliBri UI, German, WCAG/BITV target)
                                  │ HTTPS
┌─────────────────────────────────┴─────────────────────────────────────────────┐
│ quadlet: officeassistant-ui      (NiceGUI 4, FastAPI/ASGI)                    │
│  · OIDC login (authlib) → session cookie; JWT for AgentOS per user            │
│  · KoliBri views via ui.html; JS bridge kol-* → Python                        │
│  · /static/kolibri/*  (vendored, no CDN)                                      │
│  · REST/SSE client for AgentOS, one JWT per user                              │
└─────────────────────────────────┬─────────────────────────────────────────────┘
                                  │ Bearer JWT with scopes
┌─────────────────────────────────┴─────────────────────────────────────────────┐
│ quadlet: officeassistant-api     (Agno 3.1 / AgentOS)                         │
│  authorization=True, JWKS from IdP, user_isolation=True                       │
│  Team "office": Leader + Triage / Drafting / Scheduling / Research            │
│  Scheduler (3 routines) · Approvals · Sessions · Memory · Knowledge           │
└──────┬──────────────────────────────────┬─────────────────────────────────────┘
       │                                  │
┌──────┴───────────────┐   ┌──────────────┴─────────────────────────────────────┐
│ quadlet: …-db        │   │ Provider layer (own code, per-user credentials)   │
│ PostgreSQL 16        │   │  GmailAdapter  (Gmail API, OAuth per user)        │
│ + pgvector           │   │  GraphAdapter  (Graph, OAuth per user)            │
│ sessions, memory,    │   │  ImapAdapter   (IMAP4 + SMTP STARTTLS)            │
│ approvals, audit,    │   │  tokens encrypted, key from podman secret         │
│ knowledge            │   └───────────────────────────────────────────────────┘
└──────────────────────┘
┌──────────────────────────────┐
│ quadlet: keycloak (optional) │  OIDC issuer; any OIDC provider works
└──────────────────────────────┘
```

### 5.1 Provider interface

| Method | Kind | v1 default trust |
|---|---|---|
| `list_folders` / `search` / `get_message` / `list_events` | read | allowed |
| `create_draft` | draft | allowed (inert object) |
| `apply_label` / `mark_read` | write | `approval-required` |
| `create_event` / `move_event` | write | `approval-required` |
| `send_draft` | write | **approval only, no autonomy** |
| `archive` | write | `approval-required` |
| `delete(permanent=True)` | destructive | **approval only** |

Agents never see credentials. Each tool call receives the adapter instance of the
calling user.

### 5.2 Why our own token store, not Agno's Google store

The Agno Gmail toolkit keeps the Google token under a single shared provider identity:
"`google`, with no user ID; an agent's `user_id` does not choose a separate mailbox."
With several users that mixes mailboxes. Therefore:

- the provider layer owns OAuth tokens, keyed by `(user_id, provider, account)`,
  encrypted with a key from `podman secret`;
- AgentOS `user_isolation=True` isolates sessions, memory and approvals. It does **not**
  isolate third-party tokens; the architecture must not pretend otherwise.

### 5.3 IAM model (Q5, Q7)

| Layer | Mechanism |
|---|---|
| Login | OIDC authorization-code flow in the UI process against Keycloak; Keycloak authenticates the user against the **directory** (LDAP now, Active Directory later) |
| Directory | Keycloak User Federation (LDAP): connection URL, bind DN, base DN, user/group object classes, attribute mapping are **configuration**, not code |
| API auth | JWT bearer to AgentOS, verified via `JWT_VERIFICATION_KEY` or `JWT_JWKS_FILE` |
| Roles | `owner` (all), `admin` (users, trust policy, integrations), `member` (own mailbox, own routines, own approvals) |
| Role source | directory group → Keycloak role mapping (group names configurable) |
| Data isolation | `user_isolation=True` plus `user_id` on every own table, every query filtered |
| Approvals | a member sees and resolves only their own; no member resolves another member's approval |
| Audit | append-only, `actor` taken from the verified JWT subject, never from client input |

#### 5.3.1 Why LDAP now and Active Directory later is one configuration change

Active Directory is an LDAP directory. It differs in vendor preset and attributes, not
in protocol:

| Setting | OpenLDAP (now) | Active Directory (later) |
|---|---|---|
| Vendor preset in Keycloak | Other | `Active Directory` |
| Login attribute | `uid` / `mail` | `sAMAccountName` / `userPrincipalName` |
| Group membership | `memberOf` or group `member` | `memberOf` (nested groups need the AD preset) |
| Transport | LDAPS 636 | LDAPS 636, or Kerberos/SPNEGO for desktop SSO |

So: no application code touches the directory. The application sees only an OIDC
identity with `sub`, `email`, `name` and roles. Switching to AD changes Keycloak
settings; the platform, the database and the tests stay unchanged.

**Proven in P0.3** against osixia/openldap with two users: login, JWT with `scopes`,
AgentOS `authorization=True`, `user_isolation=True`, 401 without token, 403 with a narrow
token on `/config`, 404 on a foreign session (see `p0-results.md`).

Two configuration facts that make or break it:

1. The LDAP user-storage provider **must** arrive with the four attribute mappers
   (username↔uid, email↔mail, firstName↔cn, lastName↔sn). Without them Keycloak queries
   the directory with an empty attribute list and fails with
   `User returned from LDAP has null username … attributes from LDAP: {}`. The realm
   export in `deploy/` therefore contains the mappers, not just the provider.
2. The JWKS path reaches AgentOS through `JWT_JWKS_FILE`; passing
   `AuthorizationConfig(jwks_file=…)` alone did not take effect in Agno 3.1.12.

Rejected alternative: the UI binds directly against LDAP and mints its own JWT. Fewer
components, but then we own password handling, session lifetime, MFA and lockout
policy — and Kerberos SSO against AD would need a broker anyway. Not chosen.


### 5.4 Trust model (Town parity)

`read-only` / `approval-required` / `autonomous`, per tool and per routine, default
`approval-required`. `send_draft` and `delete(permanent=True)` are fixed to approval in
v1 for every role.

### 5.5 Data model

| Table | Key columns |
|---|---|
| `app_user` | id (IdP `sub`), email, display name, role, active |
| `mail_account` | user_id, provider (`gmail`/`graph`/`imap`), address, token_ref, scopes, status |
| `message_cache` | account_id, provider_id, thread_id, from, subject, received_at, labels |
| `event_cache` | account_id, provider_id, start, end, subject, organizer |
| `task` | user_id, source, title, state, due_at, links |
| `routine` | user_id, name, cron, prompt, trust, enabled, last_run_id |
| `run` | user_id, agent_id, started_at, ended_at, tokens, outcome |
| `approval` | user_id, run_id, tool, payload, decision, decided_at |
| `audit` | user_id, tool, args_hash, result_code, ts (append-only) |
| `memory_entry` | user_id, kind (person/project/voice), text, source, editable |

PostgreSQL 16 with pgvector is the default (multi-user plus durable approvals).

### 5.6 Security baseline

1. Least-privilege scopes: Gmail `gmail.modify` (not `mail.google.com`), Graph
   `Mail.ReadWrite` + `Calendars.ReadWrite` + `offline_access`; read-only mode uses
   `gmail.readonly` / `Mail.Read`.
2. Tokens encrypted at rest; key from podman secret; never logged, never in the repo.
3. `send` and `delete(permanent)` are approval-only for every role.
4. Audit append-only, one row per tool call, with the prompt hash.
5. Model endpoint is operator-configured; mail bodies leave the host only if the
   operator points the endpoint outside. The operator guide states this.
6. KoliBri assets self-hosted; no external requests from the UI.

### 5.7 Model layer (Q8: llama-swap)

The agents talk to the local llama-swap instance, which offers one OpenAI-compatible
surface for every model it serves:

```
base_url = http://127.0.0.1:8080/v1     (host)  /  http://llama-swap:8080/v1  (podman net)
model_id = <entry from /v1/models>
api_key  = any non-empty string (llama-swap ignores it)
```

Observed on this host, 2026-11-05: the container `llama-swapel`
(`ghcr.io/mostlygeek/llama-swap:unified-cuda`, port 8080) lists 14 entries, all
`unloaded`, including `deepseek-v4-pro-qwen3.5-9b`, `gemma-4-12B-TurboQuant`,
`Qwen2.5-Coder-7B-Instruct-heretic`, `LFM3-1.7B`, the embedding models
`bge-m3-gguf` / `nomic-embed-text-v2-moe` and the OCR/vision entries.

Two consequences:

1. **"Listed in `/v1/models`" proves the config parsed, not that the model can drive an
   agent.** Tool calling needs a chat template with tool support and a server started
   with the Jinja template; a model without it answers in prose and Agno never gets a
   tool call. P0.4 proved this the hard way: `deepseek-v4-pro-qwen3.5-9b` emitted exactly
   one tool call in 14.2 s, while `gemma-4-12B-TurboQuant` ignored the `tools` array
   entirely (`prompt_tokens: 40`), echoed the prompt and hit the token cap.
2. **Model and role are configuration.** One id per role (`roles.leader`,
   `roles.drafting`, `roles.triage`), all pointing at llama-swap. Swapping a model is a
   config change, never a code change. A model that cannot emit tool calls is not used
   for a tool-bearing role.

Embeddings for the knowledge base use a separate llama-swap entry; no model is loaded
in-process.

---

## 6. Deployment (Podman, rootless quadlets) — Q4

| Unit | Content |
|---|---|
| `officeassistant-db.container` | postgres:16 + pgvector, volume `oa-db`, secret `pg-password` |
| `officeassistant-api.container` | AgentOS image, `PublishPort=127.0.0.1:7777`, secrets `jwt-verify`, `token-key`, `model-api-key` |
| `officeassistant-ui.container` | NiceGUI image, `PublishPort=127.0.0.1:8080`, OIDC environment, no DB access |
| `keycloak.container` | optional reference IdP, own volume, LDAP federation configured to the directory |
| — (external) | `llama-swapel` is **not** part of this deployment; the API container reaches it through the host gateway or a shared podman network. One dependency, documented in the operator guide |
| `oa.network` | podman network; UI reaches API by service name only |

Rules: `Containerfile` per image, pinned tags, healthchecks, `AutoUpdate=no`, no
`--privileged`, logging to journald, no secrets in `Exec`/`Environment` where
`Secret=` is possible.

---

## 7. Phases and tasks

One commit per task. TDD per `old-coder` (RED → GREEN → REFACTOR → GAUNTLET → EVIDENCE).
`uv` only. UI strings German, code and docs English.

### P0 — Spikes (gate for all later work)

| # | Task | Acceptance |
|---|---|---|
| P0.1 | KoliBri inside NiceGUI, vendored assets: `kol-button`, `kol-input-text`, `kol-card`; click and change reach a Python handler | counter increments in Python, input value arrives, no console error, no external request (devtools) |
| P0.2 | AgentOS approval durability on **Postgres**: pause, restart container, resolve, resume | pending approval survives restart, run resumes, audit row exists |
| P0.3 | Keycloak with **LDAP user federation**, AD-compatible settings: login, JWT with roles, AgentOS `authorization=True`, `user_isolation=True`; user A cannot read user B's session | 401 without token, 403 with wrong scope, isolation test passes, directory settings documented as a table (5.3.1) |
| P0.4 | `OpenAILike` against llama-swap: list `/v1/models`, pick one chat model, one tool, one call | the model emits exactly one tool call and the parsed result returns. If it answers in prose, the model is not usable for tool roles — report it, do not patch the prompt until it pretends |
| P0.5 | Gmail read-only with our own token store (not the Agno shared identity), 20 headers, refresh after restart | headers in JSON, refresh works, token encrypted |
| P0.6 | Graph read-only via device code: 20 messages + calendar window | parity with P0.5, scopes documented |
| P0.7 | IMAP/SMTP against an on-prem Exchange test account | 20 headers, one draft, limits documented |

**Executed 2026-11-05 — results in `docs/specs/p0-results.md`:** P0.1, P0.2, P0.4 passed;
P0.3 passed with three findings (LDAP mappers, `cryptography`, admin-scope bypass);
P0.5 partial (peer-verified Gmail read, our own OAuth client missing); P0.6 and P0.7
blocked (no test tenant, no Exchange account).

P0 ends with a short written report per spike. No P1 work before that report.

### P1 — Skeleton and IAM

| # | Task | Files | Acceptance |
|---|---|---|---|
| P1.1 | Dependencies and lock | `pyproject.toml`, `uv.lock` | `uv sync` clean |
| P1.2 | Settings (pydantic-settings): `model.base_url`, `roles.*.model_id`, DB URL, OIDC issuer/client, directory settings, crypto key | `src/officeassistant/settings.py` | missing value → clear German error, never a silent default |
| P1.3 | Provider protocol + fake adapter | `providers/base.py`, `tests/fakes.py` | protocol enforced |
| P1.4 | Postgres schema + migration runner | `store/schema.py`, `store/migrate.py` | fresh DB → all tables; rerun idempotent |
| P1.5 | User repository + role check | `store/users.py` | member cannot read a foreign row |
| P1.6 | Encrypted token store (Fernet, key from secret) | `store/tokens.py` | round-trip; wrong key → error, no partial write |
| P1.7 | Audit writer | `store/audit.py` | 2 calls → 2 rows |
| P1.8 | AgentOS app with `authorization=True`, `user_isolation=True` | `api/main.py` | boots, `/health` 200, unauthenticated 401 |
| P1.9 | NiceGUI shell: login, logout, KoliBri loader, German navigation | `ui/app.py`, `static/kolibri/` | login → app; logout clears session |
| P1.10 | Containerfiles, three quadlets, network | `deploy/` | quadlets start, UI only on loopback |

**Status 2026-11-05: P1.1–P1.9 erledigt und geprüft**, P1.10 gebaut und als Abbild
gestartet (siehe `docs/specs/p1-results.md`). Abweichung: die JWT-Prüfung läuft über
`Authorization(jwks_file=…)` aus `agno.os.authz`; `AuthorizationConfig` ist in 3.1.12
abgekündigt und reichte die JWKS-Datei nicht durch.

### P2 — Gmail end to end (per user)

| # | Task | Acceptance |
|---|---|---|
| P2.1 | OAuth connect flow, account list, disconnect | token written, disconnect deletes it, audit row |
| P2.2 | `search` + `get_message` normalized | body text without HTML |
| P2.3 | `create_draft` + `send_draft` with `@approval` | draft in Gmail; send after approval only |
| P2.4 | Label/archive tools with trust levels | read-only blocks; approval-required pauses |
| P2.5 | Tools wired with the caller's adapter | "was liegt heute an" picks read tools |

**Status 2026-11-05: P2.2–P2.5 erledigt** (Testanbieter `fake`), P2.1 teilweise — siehe
`docs/specs/p2-results.md`. Der echte Gmail-Anbieter wartet auf den OAuth-Client.

### P3 — Microsoft paths (both, Q3)

| # | Task | Acceptance |
|---|---|---|
| P3.1 | `GraphAdapter` auth (device code, refresh, several accounts) | refresh without browser, two accounts separate |
| P3.2 | Graph search / get_message | parity with P2.2 on the same data |
| P3.3 | Graph create_draft / send_draft | parity with P2.3 |
| P3.4 | Graph calendar read + create_event behind approval | event visible in Outlook |
| P3.5 | `ImapAdapter` search/get/draft via IMAP/SMTP | parity where IMAP allows; limits documented |
| P3.6 | Provider selection per account in the UI | one user with Gmail and Exchange in parallel |

**Status 2026-11-05: P3.5 erledigt und gegen einen echten IMAP-Server geprüft** (8 Tests
gegen GreenMail, dazu ein Agentenlauf gegen das Postfach). P3.6 teilweise: Auswahl
`imap`/`fake` wirkt, Gmail fehlt noch. P3.1–P3.4 nicht begonnen (kein Entra-Konto) —
siehe `docs/specs/p3-results.md`.

### P4 — Agents, routines, approvals (Q6: all three routines)

| # | Task | Acceptance |
|---|---|---|
| P4.1 | Team: Leader + Triage, Drafting, Scheduling, Research; German instructions | routing test passes |
| P4.2 | Routine *Morgenbriefing* (cron 08:00): calendar, mail needing action, open tasks | run history success, output in app and as mail |
| P4.3 | Routine *Inbox-Triage* (labels only; `autonomous` allowed by policy) | labels applied, audit rows |
| P4.4 | Routine *Meeting-Vorbereitung* (30 min before each event) | one note per event, empty days skipped |
| P4.5 | Approval inbox: list per user, payload preview, approve/reject, resume | decision resolves the run; foreign approval not resolvable |
| P4.6 | Routine editor in plain language (prompt + cron + trust) | created routine appears in the scheduler and fires |
| P4.7 | Memory from corrections, visible and editable list | next draft honours it, other users unaffected |
| P4.8 | Activity view per user: runs, tool calls, tokens | matches audit table |

**Status 2026-11-05:**

* P4.1 erledigt — Team aus Leitung und vier Rollen, kein Senden in einer Rolle, zwei Läufe.
* P4.2 erledigt — Morgenbriefing, vom Zeitgeber gestartet, Ergebnis auf `/routinen`.
* P4.3 teilweise — Triage liest und ordnet; Kennzeichnen mit Freigabe noch nicht geübt.
* P4.4 erledigt ohne Kalender — IMAP kennt keinen Kalender, der Lauf sagt das.
* P4.5 erledigt — siehe `p2-results.md`.
* P4.6 erledigt — Editor auf `/routinen`: anlegen, ändern, abschalten, löschen; Befugnis je Routine wählbar (`read`/`label`/`draft`), nie `send`. Abweichung: Zeitplan in Alltagssprache statt Cron-Ausdruck (Q: kein Cron für Bürokräfte).

* P4.7 erledigt — Gedächtnis je Nutzer, Werkzeug `remember`, Seite `/gedaechtnis`.
* P4.8 erledigt ohne Tokenzählung — Seite `/aktivitaet`.

Einzelheiten: `docs/specs/p4-results.md`.

### P5 — Accessibility and delivery

| # | Task | Acceptance |
|---|---|---|
| P5.1 | KoliBri coverage of all views (table, form, dialog) | no Quasar widget in user views except notifications |
| P5.2 | Keyboard pass, focus order, form errors announced | manual checklist filled |
| P5.3 | Theme switch Default / BWSt | whole UI follows, no reload error |
| P5.4 | Admin area: users, roles, trust policy, integrations | every change audited |
| P5.5 | Prompt-injection test set (mail text tries to trigger send) | no send without approval in any case |
| P5.6 | README + operator guide: OIDC setup, Gmail OAuth app, Entra app, quadlets, backup | a second person installs from it |

### P6 — Evidence

Per SPEC line: `requirement | implemented | test | evidence`. Anything not implemented
stays marked "prepared, not implemented".

---

## 8. Open points

| # | Point | Why it matters | Proposed default |
|---|---|---|---|
| O1 | ~~OIDC provider~~ — answered: LDAP now, AD later, Keycloak as broker (Q7) | closed | — |
| O2 | ~~Model endpoint~~ — answered: llama-swap (Q8) | closed | — |
| O3 | Which llama-swap entry serves which agent role? | P0.4 needs one chat model per role; the catalog holds 14 entries, none proven for tool calling | probe in P0.4, choose by measurement, never by size |
| O4 | Directory instance for the P0.3 spike: a local OpenLDAP test container, or an existing LDAP/AD reachable from this host? | P0.3 needs a bind target | local OpenLDAP container with two test users |
| O5 | Gmail and Graph test accounts (addresses, tenant) | P0.5 / P0.6 need real mailboxes | provided by Frank at P0 start |

---

## 9. Risks

| # | Risk | Mitigation |
|---|---|---|
| R1 | KoliBri + NiceGUI event bridge (custom element events, re-render) | P0.1 gates all work; fallback is a KoliBri SPA against the AgentOS API |
| R2 | Agno Gmail token is one shared identity → mailbox mixing across users | own per-user token store (5.2), proven in P0.5 |
| R3 | Graph registration needs tenant admin consent | document consent; device code for the pilot |
| R4 | On-prem Exchange may have IMAP disabled by policy | P0.7 proves it early; escalate before P3.5 if blocked |
| R5 | Two styling systems on one page (KoliBri + Quasar reset) | `kol-*` only in user views |
| R6 | Prompt injection from mail bodies triggering writes | write tools gated, `send` never autonomous, P5.5 test set |
| R7 | Rootless Podman + Postgres volume permissions | dedicated `User=` in the quadlet, tested in P1.10 |
| R8 | JWT clock skew or JWKS rotation breaks login | JWKS cache, 60 s leeway, documented |
| R9 | Audit integrity in multi-user operation | actor from verified JWT subject, server-side only |
| R10 | No chat model in the local catalog is proven to emit tool calls; without them no agent can act | P0.4 measures one model per role; a model that fails is reported, not patched into pretending. Fallback: a tool-capable model added to the llama-swap config (own approval, own step) |
| R11 | A local OpenLDAP test proves nothing about Active Directory (nested groups, `sAMAccountName`, Kerberos SSO) | keep the mapping in Keycloak configuration, record the AD column of 5.3.1 as *prepared, not tested* until a real AD is reachable |
| R12 | An `agent_os:admin` token bypasses per-user isolation (measured in P0.3: a foreign session was readable) | `owner`/`admin` roles are rare, named and audited; member tokens carry narrow scopes (`agents:read`, `agents:*:run`, `sessions:read|write`); the UI never stores an admin token in a user session |
| R13 | Missing `cryptography` makes every RS256 JWKS key unparsable, and AgentOS reports it as "no verification key" | `cryptography` is a hard dependency; a startup self-test checks that the JWKS yields at least one key |

---

## Appendix A — Desirable integrations (outside v1)

| Wish | Feasible? | API / note |
|---|---|---|
| **Skype** | **No** | Consumer Skype retired 2025-05-05, Skype for Business Online 2021-07-31. Substitute: Microsoft Teams (Graph) or Mattermost |
| Mattermost | yes | REST API, bot account with personal access token; self-hosted, good on-prem fit |
| OneNote | yes | Graph `/onenote/notebooks`, `/sections`, `/pages`; delegated `Notes.ReadWrite` |
| Webex | yes | REST API, bot token; bots see DMs and @mentions only |
| Jira | yes | REST API v3 (Cloud) / v2 (Data Center); token per user |
| Confluence | yes | REST API; same token model as Jira |
| SharePoint | yes | Graph `/sites`, `/drives`, `/lists`; delegated scopes, tenant consent |

Rule: each integration is a new adapter behind the same tool contract, with its own
trust level and its own audit rows. None of them enters v1.

## Appendix B — Excluded by decision

iOS app, Slack, Telegram, WhatsApp, Google Workspace beyond Gmail and Calendar, Notion,
HubSpot, Linear, Zoom. No tasks, no adapter stubs, no placeholders in the UI.

---

## 10. What this specification deliberately does not do

- No code in this document, no scaffolding changes before approval (rule 1).
- No claim of BITV conformance until P5.1/P5.2 evidence exists.
- No estimate of duration.
