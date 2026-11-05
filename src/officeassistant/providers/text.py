"""Text-Aufbereitung für Mailinhalte.

Mailkörper sind unvertrauenswürdige Eingaben. Der Adapter liefert reinen Text; HTML
wird nicht an das Modell gegeben, sondern vorher in Text überführt.
"""

from __future__ import annotations

import re

_TAG = re.compile(r"<[^>]+>")
_SCRIPT_STYLE = re.compile(r"<(script|style)\b.*?</\1>", re.IGNORECASE | re.DOTALL)
_WHITESPACE = re.compile(r"[ \t\r\f\v]+")
_BLANK_LINES = re.compile(r"\n{3,}")
_ENTITIES = {
    "&nbsp;": " ",
    "&amp;": "&",
    "&lt;": "<",
    "&gt;": ">",
    "&quot;": '"',
    "&#39;": "'",
    "&apos;": "'",
}


def html_to_text(html: str) -> str:
    """HTML in lesbaren Text überführen, ohne Struktur zu erfinden."""
    without_blocks = _SCRIPT_STYLE.sub(" ", html)
    with_breaks = re.sub(r"<br\s*/?>", "\n", without_blocks, flags=re.IGNORECASE)
    with_breaks = re.sub(r"</p\s*>", "\n\n", with_breaks, flags=re.IGNORECASE)
    text = _TAG.sub("", with_breaks)
    for entity, replacement in _ENTITIES.items():
        text = text.replace(entity, replacement)
    text = _WHITESPACE.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    text = _BLANK_LINES.sub("\n\n", text)
    return text.strip()
