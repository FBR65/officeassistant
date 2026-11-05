"""Microsoft Graph: Kalender. Vorbereitet, ohne Mandant nicht prüfbar.

Der Vertrag ist derselbe wie bei ICS (`calendar/ics.py`): Termine eines Zeitraums. Sobald
ein Mandant mit Zustimmung da ist, wird hier `/me/calendarView` aufgerufen und das Ergebnis
in dieselbe Form gebracht. Bis dahin sagt der Adapter, was fehlt.
"""

from __future__ import annotations

from datetime import datetime

import httpx

from officeassistant.calendar.ics import Termin


class GraphNotConfigured(RuntimeError):
    """Ohne App-Registrierung und Zustimmung gibt es keinen Graph-Zugang."""


def termine(
    access_token: str, von: datetime, bis: datetime, client: httpx.Client | None = None
) -> list[Termin]:
    """Termine aus dem Microsoft-Kalender (Graph)."""
    if not access_token:
        raise GraphNotConfigured(
            "Für den Microsoft-Kalender fehlt ein Graph-Token. Das braucht eine "
            "App-Registrierung im Mandanten und die Zustimmung eines Administrators. "
            "Bis dahin lässt sich eine ICS-Adresse als Quelle nutzen."
        )

    client = client or httpx.Client(base_url="https://graph.microsoft.com/v1.0", timeout=20)
    antwort = client.get(
        "/me/calendarView",
        params={
            "startDateTime": von.isoformat(),
            "endDateTime": bis.isoformat(),
            "$select": "subject,start,end,location,attendees,isAllDay,iCalUId",
            "$orderby": "start/dateTime",
        },
        headers={
            "Authorization": f"Bearer {access_token}",
            "Prefer": 'outlook.timezone="UTC"',
            "Accept": "application/json",
        },
    )
    if antwort.status_code >= 400:
        raise GraphNotConfigured(
            f"Graph antwortet mit {antwort.status_code}: {antwort.text[:200]}"
        )

    ergebnis: list[Termin] = []
    for eintrag in antwort.json().get("value", []):
        beginn = _zeit(eintrag.get("start"))
        ende = _zeit(eintrag.get("end"))
        ergebnis.append(
            Termin(
                uid=str(eintrag.get("iCalUId", "")),
                titel=str(eintrag.get("subject", "(ohne Titel)")),
                beginn=beginn,
                ende=ende,
                ort=str((eintrag.get("location") or {}).get("displayName", "")),
                teilnehmer=tuple(
                    str((teil.get("emailAddress") or {}).get("address", ""))
                    for teil in eintrag.get("attendees", [])
                ),
                ganztags=bool(eintrag.get("isAllDay")),
            )
        )
    return ergebnis


def _zeit(wert) -> datetime:
    from datetime import UTC

    roh = str((wert or {}).get("dateTime", ""))
    if not roh:
        return datetime.now(UTC)
    return datetime.fromisoformat(roh.replace("Z", "+00:00")).astimezone(UTC)
