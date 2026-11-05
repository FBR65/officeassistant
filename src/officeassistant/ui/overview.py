"""Startseite: der Arbeitsstand auf einen Blick.

Vier Blöcke, jeder mit Zahlen und einem Weg zur Detailseite: Termine des Tages, offene
Entscheidungen, die letzten Läufe, Auffälligkeiten. Jeder Block nennt den Grund, wenn er
leer ist — eine leere Fläche sagt nichts.
"""

from __future__ import annotations

from nicegui import ui
from starlette.requests import Request
from starlette.responses import Response

from officeassistant.settings import Settings
from officeassistant.store import dashboard, db
from officeassistant.ui import auth, layout

SETTINGS = Settings.load()


def _zeit(datum) -> str:
    return f"{datum.astimezone():%d.%m. %H:%M}"


def _termine(block: dict) -> str:
    if block["termin_hinweis"]:
        return f'<p>{block["termin_hinweis"]}</p>'
    zeilen = "".join(
        f'<tr><td style="padding:0.25rem 1rem 0.25rem 0;white-space:nowrap">{t.zeit}</td>'
        f'<td style="padding:0.25rem 1rem 0.25rem 0">{t.titel}</td>'
        f'<td style="padding:0.25rem 0;color:#555">{t.ort}</td></tr>'
        for t in block["termine"]
    )
    return f'<table style="border-collapse:collapse;width:100%">{zeilen}</table>'


def _freigaben(block: dict) -> str:
    anzahl = int(block["freigaben"])
    if anzahl == 0:
        return '<p>Nichts wartet auf Sie. <a href="/freigaben">Freigaben</a></p>'
    wort = "Freigabe wartet" if anzahl == 1 else "Freigaben warten"
    return (
        f'<p><strong>{anzahl} {wort}</strong> auf Ihre Entscheidung. '
        f'<a href="/freigaben">Jetzt entscheiden</a></p>'
    )


def _laeufe(block: dict) -> str:
    if not block["laeufe"]:
        return '<p>Noch kein Auftrag gelaufen. <a href="/auftraege">Ersten Auftrag erteilen</a></p>'
    zeilen = []
    for lauf in block["laeufe"]:
        text = lauf.anfang or "keine Antwort"
        zeilen.append(
            f'<tr><td style="padding:0.25rem 1rem 0.25rem 0;white-space:nowrap">{_zeit(lauf.zeit)}</td>'
            f'<td style="padding:0.25rem 1rem 0.25rem 0;white-space:nowrap">{lauf.stand}</td>'
            f'<td style="padding:0.25rem 0">{text}</td></tr>'
        )
    return (
        f'<table style="border-collapse:collapse;width:100%">{"".join(zeilen)}</table>'
        '<p><a href="/aktivitaet">Alle Läufe</a></p>'
    )


def _auffaellig(block: dict) -> str:
    punkte: list[str] = []
    if block["fehler"]:
        punkte.append(
            f'{block["fehler"]} Läufe sind in den letzten 24 Stunden gescheitert. '
            '<a href="/aktivitaet">Ansehen</a>'
        )
    punkte.extend(block["routinen"])
    if not punkte:
        return '<p>Keine Auffälligkeit.</p>'
    eintraege = "".join(f"<li>{punkt}</li>" for punkt in punkte)
    return f"<ul style=\"margin:0;padding-left:1.2rem\">{eintraege}</ul>"


@ui.page("/")
async def index(request: Request) -> Response | None:
    layout.head(request)
    user = auth.identity(request, SETTINGS)

    with layout.content():
        if user is None:
            ui.html(
                """
                <kol-card _label="Anmeldung erforderlich">
                  <p>Bitte melden Sie sich mit Ihrem Verzeichniskonto an.</p>
                  <kol-button _label="Anmelden" _variant="primary" data-href="/login"></kol-button>
                </kol-card>
                """,
                sanitize=False,
            ).classes("w-full")
            return None

        conn = db.connect(SETTINGS.db_url, autocommit=True)
        try:
            block = dashboard.alle_zahlen(conn, user.subject, SETTINGS.token_key)
        finally:
            conn.close()

        layout.app_frame("OfficeAssistant", user.name or user.email)
        layout.nav("/")

        layout.card("Heute", _termine(block))
        layout.card("Wartet auf Sie", _freigaben(block))
        layout.card("Zuletzt gelaufen", _laeufe(block))
        layout.card("Auffällig", _auffaellig(block))
        return None
