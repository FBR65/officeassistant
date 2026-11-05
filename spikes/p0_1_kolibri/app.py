"""P0.1 — KoliBri web components inside NiceGUI, self-hosted, events reach Python.

Acceptance (from the SPEC):
  * kol-button and kol-input-text render
  * a click and an input change arrive in Python
  * no console error, no external request

Run: uv run python spikes/p0_1_kolibri/app.py
Then open http://127.0.0.1:8099 and watch the log file ./spike_events.jsonl
"""

from __future__ import annotations

import json
from pathlib import Path

from nicegui import app, ui

HERE = Path(__file__).parent
EVENTS = HERE / "spike_events.jsonl"

app.add_static_files("/kolibri", str(HERE / "static" / "kolibri"))

HEAD = """
<script type="module">
  import { register } from '/kolibri/components/index.js';
  import { defineCustomElements } from '/kolibri/components/loader/index.js';
  import { DEFAULT } from '/kolibri/theme-default.mjs';

  await register(DEFAULT, defineCustomElements);

  const bind = (root) => {
    root.querySelectorAll('kol-button').forEach((el) => {
      if (el.dataset.bound) return;
      el.dataset.bound = '1';
      el.addEventListener('click', () => emitEvent('kol_click', { label: el.getAttribute('_label') }));
    });
    root.querySelectorAll('kol-input-text').forEach((el) => {
      if (el.dataset.bound) return;
      el.dataset.bound = '1';
      // KoliBri v4: getValue() liefert eine Promise, kein Property
      const read = async () => {
        const v = typeof el.getValue === 'function' ? await el.getValue() : el.value;
        return typeof v === 'string' ? v : '';
      };
      el.addEventListener('input', async () => emitEvent('kol_input', { value: await read() }));
      el.addEventListener('change', async () => emitEvent('kol_input', { value: await read() }));
    });
  };

  const start = () => {
    bind(document);
    new MutationObserver(() => bind(document)).observe(document.body, { childList: true, subtree: true });
    window.kolibriReady = true;
  };
  start();
</script>
"""


def record(kind: str, payload: dict) -> None:
    with EVENTS.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"kind": kind, **payload}, ensure_ascii=False) + "\n")


@ui.page("/")
def index() -> None:
    ui.add_head_html(HEAD)
    clicks = {"n": 0}

    with ui.column().classes("p-8 gap-6"):
        ui.html(
            """
            <kol-card _label="P0.1 KoliBri in NiceGUI">
              <div style="display:flex;flex-direction:column;gap:1rem">
                <kol-input-text _label="Postfach" _placeholder="name@example.org" _type="text"></kol-input-text>
                <kol-button _label="Zaehlen" _variant="primary"></kol-button>
              </div>
            </kol-card>
            <p id="python-state" style="margin-top:1rem">noch kein Ereignis</p>
            """,
            sanitize=False,
        ).classes("w-full")

    def on_click(e) -> None:
        clicks["n"] += 1
        record("click", {"count": clicks["n"], "args": e.args})
        ui.run_javascript(
            f"document.getElementById('python-state').textContent = 'Klick in Python angekommen: {clicks['n']}'"
        )

    def on_input(e) -> None:
        record("input", {"args": e.args})
        ui.run_javascript(
            "document.getElementById('python-state').textContent = 'Eingabe in Python: ' + "
            f"{json.dumps(str(((e.args or {}).get('value') if isinstance(e.args, dict) else e.args)))}"
        )

    ui.on("kol_click", on_click)
    ui.on("kol_input", on_input)


if __name__ in {"__main__", "__mp_main__"}:
    EVENTS.write_text("", encoding="utf-8")
    ui.run(host="127.0.0.1", port=8099, title="P0.1 KoliBri", reload=False, show=False)
