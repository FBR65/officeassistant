"""Werkzeug: Präsentationen erstellen.

Das Werkzeug legt eine Datei an und trägt sie in die Ablage ein. Es sendet nichts und
schreibt in kein Postfach, deshalb braucht es keine Freigabe.

Bilder dürfen aus dem Postfach kommen: entweder als Pfad auf dem Server oder als Verweis
auf eine Nachricht samt Anhangsnamen. Der Bildnachweis bleibt Pflicht.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agno.run.base import RunContext
from agno.tools import tool
from pydantic import BaseModel, Field

from officeassistant.agents.mail_tools import _session
from officeassistant.presentations import builder, proof, rules, store
from officeassistant.settings import Settings


def _zielordner(settings: Settings, user_id: str) -> Path:
    return store.ordner(settings.data_dir, user_id) / "bilder"


def _bild_aus_postfach(session: Any, angaben: dict[str, Any], zielordner: Path) -> Path | None:
    """Anhang aus einer Nachricht holen und ablegen. Gibt den Pfad zurück."""
    kennung = str(angaben.get("nachricht", "")).strip()
    name = str(angaben.get("anhang", "")).strip()
    if not kennung or not name:
        return None
    nachricht = session.provider.get_message(kennung)
    for anhang in getattr(nachricht, "anhaenge", ()):  # Anhänge seit Schema 7
        if anhang.dateiname != name:
            continue
        if not anhang.ist_bild or not anhang.inhalt:
            return None
        zielordner.mkdir(parents=True, exist_ok=True)
        ziel = zielordner / store._sauber(Path(name).name, 60)
        ziel.write_bytes(anhang.inhalt)
        return ziel
    return None


class FolieIn(BaseModel):
    """Eine Folie, wie das Modell sie liefert. Feste Felder, damit nichts geraten wird."""

    titel: str = Field(description="Titel der Folie")
    stichpunkte: list[str] = Field(
        default_factory=list, description="Stichpunkte der Folie, höchstens sechs"
    )
    notiz: str = Field(
        default="", description="Sprechnotiz: was zu sagen ist, mit Zeitangabe. Pflicht."
    )
    tabelle: dict[str, Any] | None = Field(
        default=None, description="Tabelle mit den Feldern kopf und zeilen"
    )
    diagramm: dict[str, Any] | None = Field(
        default=None, description="Diagramm mit den Feldern art, kategorien und reihen"
    )
    bilder: list[dict[str, Any]] = Field(
        default_factory=list, description="Bilder mit pfad oder nachricht und anhang"
    )


@tool
def create_presentation(
    titel: str,
    folien: list[FolieIn],
    untertitel: str = "",
    quelle: str = "",
    quelle_dokument: int = 0,
    run_context: RunContext | None = None,
) -> dict[str, Any]:
    """Erstellt eine PowerPoint-Datei (.pptx) und legt sie in der Ablage ab.

    Richtlinien: 16:9, höchstens sechs Stichpunkte je Folie, höchstens 60 Wörter je Folie,
    Sprechnotiz auf jeder Folie. Eine Designvorlage wird verwendet, wenn sie eingerichtet ist.

    Args:
        titel: Titel der Präsentation.
        folien: Liste von Folien. Jede Folie ist ein Objekt mit `titel`, `stichpunkte`
            (Liste von Zeichenketten), `notiz` (Pflicht, was zu sagen ist), optional
            `tabelle` (mit `kopf` und `zeilen`), `diagramm` (mit `art`, `kategorien`,
            `reihen`) und `bilder` (mit `pfad` oder `nachricht` und `anhang`, dazu
            `beschriftung`).
        untertitel: Untertitel der Titelfolie.
        quelle: Text für die letzte Folie „Quellen"; Pflicht, wenn Bilder verwendet werden.
        quelle_dokument: Nummer eines hochgeladenen Dokuments. Ist sie gesetzt, wird jede
            Folie gegen dessen Text geprüft; nicht belegte Begriffe verhindern die Datei.
    """
    settings = Settings.load()
    beschreibung = {
        "titel": titel,
        "untertitel": untertitel,
        "quelle": quelle,
        "folien": [folie.model_dump() for folie in folien],
    }

    with _session(run_context) as session:
        user_id = session.user_id

        # Bilder aufbereiten: Pfad prüfen oder aus dem Postfach holen.
        for nummer, folie in enumerate(beschreibung["folien"], 1):
            bilder = folie.get("bilder") or []
            if not isinstance(bilder, list):
                return {"fehler": f"Folie {nummer}: `bilder` muss eine Liste sein."}
            for bild in bilder:
                if not isinstance(bild, dict):
                    return {"fehler": f"Folie {nummer}: Jeder Bildeintrag muss ein Objekt sein."}
                if bild.get("pfad"):
                    continue
                try:
                    pfad = _bild_aus_postfach(session, bild, _zielordner(settings, user_id))
                except Exception as fehler:  # noqa: BLE001 - Auskunft statt Absturz
                    return {
                        "fehler": f"Folie {nummer}: Das Bild ließ sich nicht holen: {fehler}",
                        "hinweis": "Prüfen Sie Nachricht und Anhangsnamen mit read_mail.",
                    }
                if pfad is None:
                    return {
                        "fehler": f"Folie {nummer}: Anhang „{bild.get('anhang')}“ ist kein Bild "
                        "oder nicht vorhanden.",
                    }
                bild["pfad"] = str(pfad)

        try:
            deck = rules.deck_aus_dict(beschreibung)
        except rules.RegelVerstoss as fehler:
            return {"fehler": str(fehler)}

        vorlage = Path(settings.presentation_template) if settings.presentation_template else None
        ziel = store.ordner(settings.data_dir, user_id) / store.dateiname(titel)

        # Schutz gegen Wiederholung: erst nachsehen, dann bauen. Sonst überschreibt der
        # zweite Aufruf die Datei des ersten und hinterlässt einen Eintrag ohne Datei.
        erwartete_folien = 1 + len(deck.folien) + (1 if deck.quelle else 0)
        conn = _verbindung(settings)
        try:
            vorhanden = store.gleiche(conn, user_id, deck.titel, erwartete_folien)
        finally:
            conn.close()
        if vorhanden is not None:
            return {
                "erstellt": False,
                "datei": vorhanden.dateiname,
                "folienzahl": vorhanden.folienzahl,
                "ablege": f"/praesentationen (Nummer {vorhanden.id})",
                "hinweis": "Diese Präsentation liegt bereits vor. Werkzeug nicht erneut aufrufen.",
            }

        if quelle_dokument:
            from officeassistant.documents import store as dokumente

            conn_quelle = _verbindung(settings)
            try:
                try:
                    beleg = dokumente.hole(conn_quelle, user_id, int(quelle_dokument))
                except dokumente.DokumentFehler as fehler:
                    return {"fehler": str(fehler)}
                seiten = dokumente.seiten(conn_quelle, beleg.id)
            finally:
                conn_quelle.close()
            # Quellenangabe aus dem Dokument bilden, damit sie nachprüfbar ist.
            seiten_liste = ", ".join(f"{s.nummer}" for s in seiten if s.text)
            angabe = (
                f"Dokument „{beleg.name}“, Seiten {seiten_liste}, Stand "
                f"{beleg.angelegt.astimezone():%d.%m.%Y}"
            )
            # Gibt es schon eine Folie „Quellen", wird die Angabe dort ergänzt, statt eine
            # zweite Quellenfolie anzuhängen.
            vorhandene_quelle = next(
                (
                    folie
                    for folie in deck.folien
                    if "quelle" in folie.titel.lower() or "source" in folie.titel.lower()
                ),
                None,
            )
            if vorhandene_quelle is not None:
                vorhandene_quelle.stichpunkte.append(angabe)
            else:
                deck.quelle = f"{deck.quelle} · {angabe}" if deck.quelle else angabe

            befunde = proof.pruefe(deck, "\n\n".join(seite.text for seite in seiten))
            if befunde:
                return {
                    "fehler": "Nicht im Dokument belegt: "
                    + "; ".join(str(befund) for befund in befunde[:8])
                    + (f" (und {len(befunde) - 8} weitere)" if len(befunde) > 8 else ""),
                    "hinweis": "Entfernen Sie diese Begriffe oder übernehmen Sie die Schreibweise "
                    "aus dem Dokument. Ohne Beleg entsteht keine Datei.",
                }

        try:
            builder.baue(deck, ziel, vorlage=vorlage)
        except rules.RegelVerstoss as fehler:
            return {"fehler": str(fehler)}
        except builder.Bautehler as fehler:
            return {"fehler": str(fehler)}

        gelesen = builder.lies(ziel)

        conn = _verbindung(settings)
        try:
            eintrag = store.anlegen(
                conn,
                settings.data_dir,
                user_id,
                deck.titel,
                ziel,
                int(gelesen["folienzahl"]),
                vorlage.name if vorlage else "",
            )
        finally:
            conn.close()

    return {
        "erstellt": True,
        "datei": eintrag.dateiname,
        "folienzahl": eintrag.folienzahl,
        "groesse_kb": round(eintrag.groesse / 1024),
        "vorlage": eintrag.vorlage or "eingebaute Gestaltung",
        "ablege": f"/praesentationen (Nummer {eintrag.id})",
        "hinweis": "Die Datei ist abgelegt. Werkzeug nicht erneut aufrufen.",
    }


def _verbindung(settings: Settings):
    from officeassistant.store import db

    return db.connect(settings.db_url, autocommit=True)


PRESENTATION_TOOLS = [create_presentation]
