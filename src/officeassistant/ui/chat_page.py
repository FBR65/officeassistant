"""Seite „Chat": Mattermost lesen und schreiben, ohne das Programm zu wechseln.

Der Verlauf wird alle fünf Sekunden nachgeladen. Gesendet wird per Klick — der Mensch
drückt, nicht das Modell.
"""

from __future__ import annotations

from urllib.parse import quote

from nicegui import ui
from starlette.requests import Request
from starlette.responses import RedirectResponse

from officeassistant.connectors.base import ConnectorError
from officeassistant.connectors.mattermost import MattermostConnector
from officeassistant.settings import Settings
from officeassistant.store import db
from officeassistant.store.connections import ConnectionError_, ConnectionStore
from officeassistant.ui import auth, layout

SETTINGS = Settings.load()
TAKT_SEKUNDEN = 5


def _mattermost(user_id: str) -> MattermostConnector:
    conn = db.connect(SETTINGS.db_url, autocommit=True)
    try:
        verbindung = ConnectionStore(conn, SETTINGS.token_key).one(user_id, "mattermost")
    finally:
        conn.close()
    return MattermostConnector(verbindung)


def _kanaele(user_id: str) -> tuple[str, list[dict[str, str]]]:
    """Kanalverzeichnis als HTML und als Liste."""
    try:
        kanaele = _mattermost(user_id).channels(limit=40)
    except (ConnectionError_, ConnectorError) as fehler:
        return f"<p>{fehler}</p>", []

    if not kanaele:
        return "<p>Keine Kanäle gefunden.</p>", []

    zeilen = "".join(
        f"""
        <li style="margin:0.2rem 0">
          <a href="/chat?kanal={quote(kanal['id'])}" style="color:inherit">
            #{kanal['name']}
          </a>
        </li>
        """
        for kanal in kanaele
    )
    return f'<ul style="margin:0;padding-left:1.1rem">{zeilen}</ul>', kanaele


def _verlauf_html(connector: MattermostConnector, kanal: str) -> str:
    """Nachrichten eines Kanals als HTML; wird im Takt neu erzeugt."""
    try:
        posts = connector.posts(kanal, limit=40)
    except ConnectorError as fehler:
        return f"<p>{fehler}</p>"

    if not posts:
        return '<p style="color:#777">Noch keine Nachrichten in diesem Kanal.</p>'

    bloecke = []
    for post in posts:
        text = post["text"].replace("&", "&amp;").replace("<", "&lt;").replace("\n", "<br>")
        wer = post["user"][:8]
        bloecke.append(
            f"""
            <div style="margin:0 0 0.6rem 0">
              <span style="color:#555;font-size:0.85em">{wer}</span><br>{text}
            </div>
            """
        )
    return '<div style="max-height:26rem;overflow-y:auto">' + "".join(bloecke) + "</div>"


def _karte(titel: str, inhalt: str) -> str:
    return f'<kol-card _label="{titel}">{inhalt}</kol-card>'


def _eingabe(kanal: str) -> str:
    return f"""
    <form method="post" action="/chat/senden"
          style="display:flex;flex-direction:column;gap:0.5rem">
      <input type="hidden" name="kanal" value="{kanal}">
      <kol-textarea data-name="text" _label="Nachricht" _rows="2"></kol-textarea>
      <kol-button _label="Senden" _variant="primary"></kol-button>
    </form>
    """


@ui.page("/chat")
async def chat_page(request: Request) -> None:
    layout.head(request)
    user = auth.identity(request, SETTINGS)
    if user is None:
        ui.navigate.to("/login")
        return

    kanal = request.query_params.get("kanal", "")
    meldung = request.query_params.get("meldung", "")

    with layout.content():
        layout.app_frame("Chat", user.name or user.email)
        layout.nav("/chat")
        if meldung:
            layout.banner(meldung)

        kanaele_html, kanaele = _kanaele(user.subject)
        if not kanal and kanaele:
            kanal = kanaele[0]["id"]

        if not kanal:
            layout.card("Kanäle", kanaele_html)
            layout.card(
                "Chat",
                "<p>Keine Anbindung. Auf der Seite <a href='/anbindungen'>Anbindungen</a> "
                "den Dienst „Mattermost“ verbinden.</p>",
            )
            return

        try:
            connector = _mattermost(user.subject)
        except ConnectionError_ as fehler:
            layout.card("Chat", f"<p>{fehler}</p>")
            return

        layout.card("Kanäle", kanaele_html)

        # Der Verlauf steht in einer Karte; der Timer tauscht den Karteninhalt.
        verlauf = ui.html(
            _karte("Verlauf", _verlauf_html(connector, kanal)), sanitize=False
        ).classes("w-full")

        layout.card("Nachricht schreiben", _eingabe(kanal))

        def _neu() -> None:
            verlauf.set_content(_karte("Verlauf", _verlauf_html(connector, kanal)))

        ui.timer(TAKT_SEKUNDEN, _neu)


async def senden(request: Request):
    user = auth.identity(request, SETTINGS)
    if user is None:
        return RedirectResponse("/login", status_code=303)

    form = await request.form()
    kanal = str(form.get("kanal", "")).strip()
    text = str(form.get("text", "")).strip()
    if not kanal or not text:
        return RedirectResponse(
            f"/chat?kanal={quote(kanal)}&meldung={quote('Bitte einen Text eingeben')}",
            status_code=303,
        )

    try:
        _mattermost(user.subject).post(text, kanal)
    except (ConnectionError_, ConnectorError) as fehler:
        return RedirectResponse(
            f"/chat?kanal={quote(kanal)}&meldung={quote('Nicht gesendet: ' + str(fehler))}",
            status_code=303,
        )

    return RedirectResponse(f"/chat?kanal={quote(kanal)}", status_code=303)


def register(app) -> None:
    app.add_route("/chat/senden", senden, methods=["POST"], name="chat_send")
