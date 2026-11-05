"""Gemeinsames Gerüst der Oberfläche: KoliBri laden, Kopfzeile, Navigation.

Regeln aus P0.1:
* KoliBri-Assets liegen lokal unter `/kolibri` (kein CDN).
* `kol-card` nimmt Inhalt im Default-Slot.
* Ereignisse werden über `emitEvent` an Python gegeben, Werte über `getValue()`
  (liefert eine Promise).
"""

from __future__ import annotations

from contextlib import contextmanager

from nicegui import ui

from officeassistant.ui import auth

# Nach Aufgaben gruppiert, nicht nach Bauart. „Verwalten" erscheint nur für Verwaltung.
NAV_GRUPPEN = [
    (
        "Arbeiten",
        [
            ("Übersicht", "/"),
            ("Post", "/post"),
            ("Chat", "/chat"),
            ("Kalender", "/kalender"),
        ],
    ),
    (
        "Assistent",
        [
            ("Aufträge", "/auftraege"),
            ("Freigaben", "/freigaben"),
            ("Routinen", "/routinen"),
            ("Gedächtnis", "/gedaechtnis"),
            ("Aktivität", "/aktivitaet"),
        ],
    ),
    (
        "Verwalten",
        [
            ("Postfächer", "/postfaecher"),
            ("Anbindungen", "/anbindungen"),
        ],
    ),
]

# Für Seiten, die noch die flache Liste erwarten.
NAV = [eintrag for _, eintraege in NAV_GRUPPEN for eintrag in eintraege]

# Das Thema wird aus der Sitzung gelesen. Umgeschaltet wird derzeit nicht: das BWSt-Paket
# liefert ohne seine Schrift- und Icon-Assets eine ungestylte Seite (Versuch am 05.11.2026).
THEME_KEY = "thema"
THEMES = {
    "default": "Standard",
    "bwst": "BWSt (vorbereitet, nicht freigegeben)",
}

KOLIBRI_HEAD = """
<script type="module">
  import { register } from '/kolibri/components/index.js';
  import { defineCustomElements } from '/kolibri/components/loader/index.js';
  import { DEFAULT } from '/kolibri/theme-__THEMA__.mjs';

  await register(DEFAULT, defineCustomElements);

  const bind = (root) => {
    root.querySelectorAll('[data-emit]').forEach((el) => {
      if (el.dataset.bound) return;
      el.dataset.bound = '1';
      const event = el.dataset.emit;
      const read = async () => {
        if (typeof el.getValue === 'function') {
          const v = await el.getValue();
          return typeof v === 'string' ? v : '';
        }
        return el.value ?? '';
      };
      const send = async (type) => emitEvent(event, { type, value: await read() });
      el.addEventListener('click', () => send('click'));
      el.addEventListener('input', () => send('input'));
      el.addEventListener('change', () => send('change'));
    });
  };

  const start = () => {
    bind(document);
    new MutationObserver(() => bind(document)).observe(document.body, {
      childList: true,
      subtree: true,
    });
    window.kolibriReady = true;
  };
  start();


</script>
"""


FORM_SCRIPT = """
<script>
  // Ein Klick auf einen KoliBri-Knopf schickt sein Formular ab. KoliBri-Felder liegen
  // im Shadow DOM und werden vom Formular nicht erfasst; ihre Werte werden vorher in
  // versteckte Felder geschrieben. Welches Feld wohin gehört, steht in `data-name`.
  // KoliBri-Knöpfe sind keine <button>-Elemente und lösen kein Absenden aus.
  window.oaSubmit = async function (btn) {
    const form = btn.closest('form');
    if (!form) return;

    const festesFeld = btn.getAttribute('data-feld');
    if (festesFeld !== null) {
      const ziel = form.elements[festesFeld];
      if (ziel) ziel.value = btn.getAttribute('data-wert') || '';
    }

    const felder = form.querySelectorAll('kol-input-text, kol-textarea, kol-select, kol-input-email');
    for (const feld of felder) {
      const name = feld.getAttribute('data-name');
      if (!name) continue;
      let wert = '';
      try {
        wert = typeof feld.getValue === 'function' ? await feld.getValue() : '';
      } catch (e) {
        wert = '';
      }
      if (wert && typeof wert === 'object') wert = wert.value;
      let versteckt = form.querySelector('input[type=hidden][name="' + name + '"]');
      if (!versteckt) {
        versteckt = document.createElement('input');
        versteckt.type = 'hidden';
        versteckt.name = name;
        form.appendChild(versteckt);
      }
      versteckt.value = wert === null || wert === undefined ? '' : String(wert);
    }
    form.requestSubmit();
  };

  // KoliBri setzt beim Laden inline "visibility: hidden !important" und nimmt es nicht
  // immer zurück. Dann ist ein Knopf sichtbar, aber nicht anklickbar (Klick geht an das
  // Element dahinter). Deshalb wird die Sperre entfernt, sobald sie auftaucht.
  const freigeben = () => {
    document.querySelectorAll('kol-card, kol-button, kol-input-text, kol-textarea, kol-heading, kol-alert, kol-select')
      .forEach((el) => {
        if (el.style && el.style.getPropertyValue('visibility')) {
          el.style.removeProperty('visibility');
        }
      });
  };
  document.addEventListener('DOMContentLoaded', freigeben);
  new MutationObserver(freigeben).observe(document.body, {
    childList: true, subtree: true, attributes: true, attributeFilter: ['style'],
  });
  setInterval(freigeben, 500);

  // Inline-Attribute (onclick="…") führt diese Seite nicht aus. Formular-Knöpfe werden
  // deshalb angemeldet, und Navigationsknöpfe tragen ihr Ziel in `data-href`.
  const bindButtons = () => {
    document.querySelectorAll('kol-button').forEach((btn) => {
      if (btn.dataset.oaBound) return;
      btn.dataset.oaBound = '1';
      if (btn.hasAttribute('data-href')) {
        btn.addEventListener('click', () => {
          window.location.href = btn.getAttribute('data-href');
        });
      } else if (btn.closest('form')) {
        btn.addEventListener('click', () => window.oaSubmit(btn));
      }
    });
  };

  document.addEventListener('DOMContentLoaded', bindButtons);
  new MutationObserver(bindButtons).observe(document.body, {childList: true, subtree: true});
  bindButtons();
</script>
"""


def head(request=None) -> None:
    """Kopf der Seite; das Thema kommt aus der Sitzung (Standard oder BWSt)."""
    thema = "default"
    if request is not None and "session" in request.scope:
        gewaehlt = str(request.session.get(THEME_KEY, "default"))
        if gewaehlt in THEMES:
            thema = gewaehlt
    ui.add_head_html(KOLIBRI_HEAD.replace("__THEMA__", thema))
    ui.add_body_html(FORM_SCRIPT)


@contextmanager
def content():
    """Einheitlicher Rahmen: zentriert, mit Rand, nie am Fensterrand klebend."""
    with ui.column().classes("w-full max-w-4xl mx-auto px-6 py-8 gap-4"):
        yield


def banner(text: str) -> None:
    """Hinweiszeile im Stil der Bibliothek, ohne eigene Schrift oder Farben."""
    ui.html(
        f'<kol-alert _label="Hinweis" _type="info" _variant="card">{text}</kol-alert>',
        sanitize=False,
    ).classes("w-full")


def app_frame(title: str, user_name: str) -> None:
    """Kopfzeile mit Anwendungstitel, angemeldetem Nutzer und Abmeldung."""
    ui.html(
        f"""
        <header style="display:flex;align-items:center;justify-content:space-between;
                       gap:1rem;padding:1rem 0;border-bottom:1px solid #d0d0d0">
          <kol-heading _label="{title}" _level="1"></kol-heading>
          <div style="display:flex;align-items:center;gap:1rem">
            <span>{user_name}</span>
            <kol-button _label="Abmelden" _variant="secondary" data-href="/logout"></kol-button>
          </div>
        </header>
        """,
        sanitize=False,
    ).classes("w-full")


def nav(active: str = "") -> None:
    """Navigation in drei Gruppen; die aktuelle Seite ist hervorgehoben.

    Die Zahl offener Freigaben steht am Eintrag „Freigaben", der Eintrag „Verwaltung"
    erscheint nur für Verwaltung. Beides wird hier ermittelt, damit jede Seite es ohne
    Zutun zeigt.
    """
    offene, ist_admin = _nav_lage()
    teile = []
    for gruppe, eintraege in NAV_GRUPPEN:
        if gruppe == "Verwalten" and ist_admin:
            eintraege = [*eintraege, ("Verwaltung", "/verwaltung")]
        knoepfe = []
        for label, href in eintraege:
            zahl = f" ({offene})" if href == "/freigaben" and offene else ""
            knoepfe.append(
                f'<kol-button _label="{label}{zahl}"{_active(href, active)} '
                f'data-href="{href}" style="white-space:nowrap"></kol-button>'
            )
        teile.append(
            f'<div style="display:flex;align-items:center;gap:0.5rem;flex-wrap:wrap">'
            f'<span style="color:#555;font-size:0.85em;min-width:5.5rem">{gruppe}</span>'
            f'{"".join(knoepfe)}</div>'
        )
    ui.html(
        f'<nav style="display:flex;flex-direction:column;gap:0.5rem;padding:0.75rem 0;'
        f'border-bottom:1px solid #e0e0e0">{"".join(teile)}</nav>',
        sanitize=False,
    ).classes("w-full")


def _nav_lage() -> tuple[int, bool]:
    """Zahl offener Freigaben und Verwaltungsrecht des angemeldeten Nutzers."""
    try:
        from officeassistant.settings import Settings
        from officeassistant.store import db, dashboard
        from officeassistant.store.users import UserStore

        anfrage = ui.context.client.request
        settings = Settings.load()
        user = auth.identity(anfrage, settings)
        if user is None:
            return 0, False
        conn = db.connect(settings.db_url, autocommit=True)
        try:
            eigener = UserStore(conn).get(user.subject)
            return (
                dashboard.offene_freigaben(conn, user.subject),
                bool(eigener and eigener.is_admin),
            )
        finally:
            conn.close()
    except Exception:  # noqa: BLE001 - Navigation darf nie die Seite verhindern
        return 0, False


def _active(href: str, active: str) -> str:
    return ' _variant="primary"' if href == active else ""


def card(title: str, body_html: str) -> None:
    ui.html(f'<kol-card _label="{title}">{body_html}</kol-card>', sanitize=False).classes(
        "w-full"
    )
