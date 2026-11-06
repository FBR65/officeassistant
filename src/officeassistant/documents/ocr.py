"""Texterkennung über einen OpenAI-kompatiblen Endpunkt.

Vorbild ist DocPipeline: die Seite wird als PNG gezeichnet, base64-kodiert an
`{base_url}/chat/completions` geschickt und das Ergebnis als Text zurückgegeben.
Drei Versuche mit wachsender Wartezeit, damit ein ausgelastetes Modell nicht sofort
aufgibt.
"""

from __future__ import annotations

import base64
import time

import httpx

OCR_PROMPT = (
    "Extrahiere den gesamten Text dieser Seite als Markdown. "
    "Behalte die Lesereihenfolge. Gib nur den Text aus, ohne Kommentare."
)

MAX_VERSUCHE = 3
WIEDERHOLBAR = frozenset({408, 409, 425, 429})


class OcrFehler(RuntimeError):
    """Die Texterkennung ist nicht erreichbar oder hat abgelehnt."""


class OcrClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str = "",
        timeout: float = 180.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._model = model
        self._key = api_key
        self._timeout = timeout
        self._transport = transport

    def _kopf(self) -> dict[str, str]:
        kopf = {"Content-Type": "application/json"}
        if self._key:
            kopf["Authorization"] = f"Bearer {self._key}"
        return kopf

    def _rumpf(self, bild: bytes) -> dict:
        kodiert = base64.b64encode(bild).decode("ascii")
        return {
            "model": self._model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": OCR_PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{kodiert}"},
                        },
                    ],
                }
            ],
            "temperature": 0,
        }

    def text_aus_bild(self, bild: bytes) -> str:
        """Gibt den erkannten Text zurück. Leerer Text ist ein gültiges Ergebnis."""
        letzter_grund = "keine Antwort"
        for versuch in range(1, MAX_VERSUCHE + 1):
            try:
                with httpx.Client(timeout=self._timeout, transport=self._transport) as client:
                    antwort = client.post(
                        f"{self._base}/chat/completions",
                        json=self._rumpf(bild),
                        headers=self._kopf(),
                    )
            except httpx.HTTPError as fehler:
                letzter_grund = f"nicht erreichbar: {fehler}"
            else:
                if antwort.status_code == 200:
                    return _text_aus_antwort(antwort.json())
                if antwort.status_code in WIEDERHOLBAR:
                    letzter_grund = f"ausgelastet (Status {antwort.status_code})"
                else:
                    raise OcrFehler(
                        f"Die Texterkennung hat abgelehnt (Status {antwort.status_code}): "
                        f"{antwort.text[:160]}"
                    )
            if versuch < MAX_VERSUCHE:
                time.sleep(1.0 * versuch)
        raise OcrFehler(f"Die Texterkennung ist fehlgeschlagen: {letzter_grund}")


def _text_aus_antwort(daten: dict) -> str:
    try:
        inhalt = daten["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as fehler:
        raise OcrFehler("Die Texterkennung hat keine verwertbare Antwort geliefert.") from fehler
    if isinstance(inhalt, list):
        # Manche Endpunkte liefern Abschnitte statt einer Zeichenkette.
        inhalt = "".join(
            str(stueck.get("text", "")) for stueck in inhalt if isinstance(stueck, dict)
        )
    return str(inhalt).strip()
