-- Schema des OfficeAssistant (eigene Tabellen; Sitzungen, Läufe und Freigaben
-- verwaltet AgentOS in derselben Datenbank über seine eigenen Tabellen).

CREATE TABLE IF NOT EXISTS schema_version (
    version     integer PRIMARY KEY,
    applied_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS app_user (
    id            text PRIMARY KEY,              -- IdP-sub
    email         text NOT NULL,
    display_name  text NOT NULL DEFAULT '',
    role          text NOT NULL DEFAULT 'member'
                  CHECK (role IN ('owner', 'admin', 'member')),
    active        boolean NOT NULL DEFAULT true,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS mail_account (
    id           bigserial PRIMARY KEY,
    user_id      text NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    provider     text NOT NULL CHECK (provider IN ('gmail', 'graph', 'imap')),
    address      text NOT NULL,
    scopes       text[] NOT NULL DEFAULT '{}',
    status       text NOT NULL DEFAULT 'active'
                 CHECK (status IN ('active', 'expired', 'revoked')),
    created_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, address)
);

-- Version 2: Testanbieter `fake` zulassen (nur für Tests und Vorführungen).
ALTER TABLE mail_account DROP CONSTRAINT IF EXISTS mail_account_provider_check;
ALTER TABLE mail_account ADD CONSTRAINT mail_account_provider_check
    CHECK (provider IN ('gmail', 'graph', 'imap', 'fake'));

CREATE TABLE IF NOT EXISTS tool_policy (
    user_id  text NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    tool     text NOT NULL,
    level    text NOT NULL CHECK (level IN ('read-only', 'approval-required', 'autonomous')),
    PRIMARY KEY (user_id, tool)
);

CREATE TABLE IF NOT EXISTS credential (
    account_id   bigint PRIMARY KEY REFERENCES mail_account(id) ON DELETE CASCADE,
    ciphertext   bytea NOT NULL,
    updated_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS task (
    id          bigserial PRIMARY KEY,
    user_id     text NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    source      text NOT NULL DEFAULT '',
    title       text NOT NULL,
    state       text NOT NULL DEFAULT 'open'
                CHECK (state IN ('open', 'done', 'dropped')),
    due_at      timestamptz,
    links       jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS routine (
    id           bigserial PRIMARY KEY,
    user_id      text NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    name         text NOT NULL,
    cron         text NOT NULL,
    prompt       text NOT NULL,
    trust        text NOT NULL DEFAULT 'approval-required'
                 CHECK (trust IN ('read-only', 'approval-required', 'autonomous')),
    enabled      boolean NOT NULL DEFAULT true,
    last_run_id  text,
    created_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, name)
);

CREATE TABLE IF NOT EXISTS memory_entry (
    id          bigserial PRIMARY KEY,
    user_id     text NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    kind        text NOT NULL CHECK (kind IN ('person', 'project', 'voice', 'other')),
    text        text NOT NULL,
    source      text NOT NULL DEFAULT '',
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audit (
    id           bigserial PRIMARY KEY,
    user_id      text NOT NULL,
    tool         text NOT NULL,
    args_hash    text NOT NULL,
    result_code  text NOT NULL,
    ts           timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS audit_user_ts_idx ON audit (user_id, ts DESC);

-- Das Protokoll ist nur anhängend: Ändern und Löschen werden abgewiesen.
CREATE OR REPLACE FUNCTION audit_reject_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit is append-only';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS audit_no_update ON audit;
CREATE TRIGGER audit_no_update
    BEFORE UPDATE OR DELETE ON audit
    FOR EACH ROW EXECUTE FUNCTION audit_reject_mutation();

INSERT INTO schema_version (version) VALUES (1)
    ON CONFLICT (version) DO NOTHING;
INSERT INTO schema_version (version) VALUES (2)
    ON CONFLICT (version) DO NOTHING;

-- Sitzungen der Oberfläche: der Browser hält nur die Kennung, die Token liegen
-- verschlüsselt hier. Ein Cookie mit drei JWT wäre größer als die 4096-Byte-Grenze.
CREATE TABLE IF NOT EXISTS ui_session (
    sid          text PRIMARY KEY,
    subject      text NOT NULL,
    email        text NOT NULL,
    name         text NOT NULL,
    tokens       bytea NOT NULL,
    expires_at   timestamptz NOT NULL,
    seen_at      timestamptz NOT NULL DEFAULT now(),
    created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ui_session_expires_idx ON ui_session (expires_at);

INSERT INTO schema_version (version) VALUES (3)
    ON CONFLICT (version) DO NOTHING;

-- Ergebnis eines Routine-Laufs. `output` ist der Text, den der Agent geliefert hat;
-- `status` sagt, ob der Lauf durchlief, auf eine Freigabe wartet oder scheiterte.
CREATE TABLE IF NOT EXISTS routine_run (
    id          bigserial PRIMARY KEY,
    routine_id  bigint NOT NULL REFERENCES routine(id) ON DELETE CASCADE,
    user_id     text NOT NULL,
    status      text NOT NULL CHECK (status IN ('running', 'completed', 'paused', 'failed')),
    output      text NOT NULL DEFAULT '',
    error       text NOT NULL DEFAULT '',
    started_at  timestamptz NOT NULL DEFAULT now(),
    ended_at    timestamptz
);

CREATE INDEX IF NOT EXISTS routine_run_routine_idx ON routine_run (routine_id, started_at DESC);

INSERT INTO schema_version (version) VALUES (4)
    ON CONFLICT (version) DO NOTHING;

-- Was eine Routine tun darf. Ohne Angabe: nur lesen. Senden ist in keiner Stufe enthalten.
ALTER TABLE routine ADD COLUMN IF NOT EXISTS scope text NOT NULL DEFAULT 'read';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'routine_scope_check'
    ) THEN
        ALTER TABLE routine
            ADD CONSTRAINT routine_scope_check
            CHECK (scope IN ('read', 'label', 'draft'));
    END IF;
END $$;

INSERT INTO schema_version (version) VALUES (5)
    ON CONFLICT (version) DO NOTHING;

-- Anbindungen je Nutzer (Jira, Confluence, Mattermost, …). Zugangsschlüssel liegen
-- verschlüsselt; die Spalte `kind` sagt, welcher Adapter zuständig ist.
CREATE TABLE IF NOT EXISTS connection (
    id          bigserial PRIMARY KEY,
    user_id     text NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    kind        text NOT NULL,
    base_url    text NOT NULL DEFAULT '',
    label       text NOT NULL DEFAULT '',
    ciphertext  bytea,
    created_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, kind, base_url)
);

INSERT INTO schema_version (version) VALUES (6)
    ON CONFLICT (version) DO NOTHING;

-- Erzeugte Präsentationen. Die Datei liegt im Datenverzeichnis; hier stehen Kennzahlen
-- für die Liste und die Zuordnung zum Nutzer.
CREATE TABLE IF NOT EXISTS presentation (
    id          bigserial PRIMARY KEY,
    user_id     text NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    titel       text NOT NULL,
    dateiname   text NOT NULL,
    pfad        text NOT NULL,
    folienzahl  integer NOT NULL DEFAULT 0,
    groesse     bigint NOT NULL DEFAULT 0,
    vorlage     text NOT NULL DEFAULT '',
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_presentation_user ON presentation (user_id, created_at DESC);

INSERT INTO schema_version (version) VALUES (7)
    ON CONFLICT (version) DO NOTHING;

-- Hochgeladene Dokumente und der je Seite gelesene Text.
CREATE TABLE IF NOT EXISTS document (
    id          bigserial PRIMARY KEY,
    user_id     text NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    name        text NOT NULL,
    pfad        text NOT NULL,
    seitenzahl  integer NOT NULL DEFAULT 0,
    zeichen     integer NOT NULL DEFAULT 0,
    per_ocr     integer NOT NULL DEFAULT 0,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS document_page (
    id          bigserial PRIMARY KEY,
    document_id bigint NOT NULL REFERENCES document(id) ON DELETE CASCADE,
    nummer      integer NOT NULL,
    text        text NOT NULL DEFAULT '',
    verfahren   text NOT NULL DEFAULT 'textlayer',
    hinweis     text NOT NULL DEFAULT '',
    UNIQUE (document_id, nummer)
);

CREATE INDEX IF NOT EXISTS idx_document_user ON document (user_id, created_at DESC);

INSERT INTO schema_version (version) VALUES (8)
    ON CONFLICT (version) DO NOTHING;
