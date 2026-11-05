"""Isolationstest: Wird ein KoliBri-Knopf in einer kol-card unsichtbar?

Zwei Formulare, eines in einer kol-card, eines ohne. Beide schreiben ihren Knopf in
den Seitentitel, wenn sie abgeschickt wurden.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from nicegui import app, ui
from starlette.requests import Request
from starlette.responses import PlainTextResponse

HERE = Path(__file__).parent
app.add_static_files("/kolibri", str(HERE.parent / "p0_1_kolibri" / "static" / "kolibri"))

HEAD = """
<script type="module">
  import { register } from '/kolibri/components/index.js';
  import { defineCustomElements } from '/kolibri/components/loader/index.js';
  import { DEFAULT } from '/kolibri/theme-default.mjs';
  await register(DEFAULT, defineCustomElements);
</script>
"""


@ui.page("/")
def index() -> None:
    ui.add_head_html(HEAD)
    ui.add_body_html(
        """
        <script>
          window.oaSubmit = async function (btn) {
            const form = btn.closest('form');
            const feld = form.querySelector('kol-input-text');
            const wert = feld && typeof feld.getValue === 'function' ? await feld.getValue() : '';
            const hidden = form.querySelector('input[type=hidden]');
            if (hidden) hidden.value = wert || '';
            form.requestSubmit();
          };
          // Klick auf einen KoliBri-Knopf: über composedPath, damit es auch dann
          // greift, wenn der Host selbst nicht getroffen wird.
          document.addEventListener('click', (ev) => {
            const pfad = ev.composedPath ? ev.composedPath() : [];
            const knopf = pfad.find((el) => el && el.tagName === 'KOL-BUTTON');
            if (!knopf) return;
            const form = knopf.closest('form');
            if (!form) return;
            ev.preventDefault();
            window.oaSubmit(knopf);
          }, true);
          // KoliBri setzt beim Laden inline "visibility: hidden !important" und nimmt es
          // nicht immer zurück; dann ist der Knopf sichtbar, aber nicht anklickbar.
          const freigeben = () => {
            document.querySelectorAll('kol-card, kol-button, kol-input-text, kol-textarea, kol-heading')
              .forEach((el) => {
                if (el.style && el.style.getPropertyValue('visibility')) {
                  el.style.removeProperty('visibility');
                }
              });
          };
          document.addEventListener('DOMContentLoaded', freigeben);
          new MutationObserver(freigeben).observe(document.body, {childList: true, subtree: true, attributes: true, attributeFilter: ['style']});
          setInterval(freigeben, 500);

          const bind = () => document.querySelectorAll('form kol-button').forEach((b) => {
            if (b.dataset.oaBound) return;
            b.dataset.oaBound = '1';
            b.addEventListener('click', () => window.oaSubmit(b));
          });
          document.addEventListener('DOMContentLoaded', bind);
          new MutationObserver(bind).observe(document.body, {childList: true, subtree: true});
          bind();
        </script>
        """
    )

    # 1) Formular IN einer KoliBri-Karte
    ui.html(
        """
        <kol-card _label="In der Karte">
          <form method="post" action="/gesendet">
            <kol-input-text _label="Feld A"></kol-input-text>
            <input type="hidden" name="wert" id="a">
            <kol-button _label="Senden A"></kol-button>
          </form>
        </kol-card>
        """,
        sanitize=False,
    )

    # 2) Formular OHNE Karte
    ui.html(
        """
        <div style="margin-top:2rem">
          <form method="post" action="/gesendet">
            <kol-input-text _label="Feld B"></kol-input-text>
            <input type="hidden" name="wert" id="b">
            <kol-button _label="Senden B"></kol-button>
          </form>
        </div>
        """,
        sanitize=False,
    )


@app.post("/gesendet")
async def gesendet(request: Request):
    form = await request.form()
    return PlainTextResponse(f"angekommen: {form.get('wert')!r}")


if __name__ in {"__main__", "__mp_main__"}:
    ui.run(host="127.0.0.1", port=8098, reload=False, show=False)
