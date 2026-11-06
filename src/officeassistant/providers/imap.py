"""IMAP/SMTP-Adapter für Exchange on-prem und beliebige IMAP-Server.

Grenzen von IMAP, die dieser Adapter nicht versteckt:

* Kein Kalender. `list_events`, `create_event`, `move_event` werfen `NotSupported`.
* Keine Labels im Sinne von Gmail. Ein Label ist hier ein Ordner; `apply_label` legt ihn
  bei Bedarf an und kopiert die Nachricht hinein.
* Entwürfe liegen im Ordner `Drafts`, gesendete Nachrichten werden nach `Sent` kopiert.
* Eine Nachricht wird über `Ordner|UID` angesprochen, weil eine UID nur je Ordner gilt.
"""

from __future__ import annotations

import base64
import email
import imaplib
import re
import smtplib
import ssl
from dataclasses import dataclass, replace, field
from datetime import UTC, datetime
from email.header import decode_header, make_header
from email.message import EmailMessage, Message
from email.utils import parsedate_to_datetime

from officeassistant.providers.base import (
    Attachment,
    DraftRef,
    Event,
    Message as MailMessage,
    MessageHeader,
    SendResult,
)
from officeassistant.providers.text import html_to_text


class NotSupported(RuntimeError):
    """Der Anbieter kann diese Aufgabe nicht leisten (IMAP: kein Kalender)."""


def _anriss(roh: bytes) -> str:
    """Erste Zeilen eines Nachrichtenteils als einzeiliger Anriss.

    Manche Absender kodieren den Text base64. Ungefiltert stünde dann ein Zeichensalat
    in der Übersicht, deshalb wird ein erkennbar kodierter Block einmal entschlüsselt.
    """
    if not roh:
        return ""
    text = roh.decode("utf-8", "replace")
    for trenner in ("\r\n\r\n", "\n\n"):
        if trenner in text:
            text = text.split(trenner, 1)[1]
            break

    verdichtet = "".join(text.split())
    if len(verdichtet) > 40 and re.fullmatch(r"[A-Za-z0-9+/=]+", verdichtet):
        try:
            text = base64.b64decode(verdichtet + "=" * (-len(verdichtet) % 4)).decode(
                "utf-8", "replace"
            )
        except (ValueError, TypeError):
            pass

    zeilen = [zeile.strip() for zeile in text.splitlines() if zeile.strip()]
    return " ".join(zeilen)[:200]


MAX_ANHANG = 10 * 1024 * 1024


class ImapError(RuntimeError):
    """IMAP- oder SMTP-Aufruf ist fehlgeschlagen."""


@dataclass(frozen=True, slots=True)
class ImapConfig:
    address: str
    host: str
    port: int = 993
    user: str = ""
    password: str = ""
    ssl: bool = True
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_security: str = "starttls"  # "starttls" | "ssl" | "none"
    drafts_folder: str = "Drafts"
    sent_folder: str = "Sent"
    archive_folder: str = "Archive"
    trash_folder: str = "Trash"
    inbox_folder: str = "INBOX"
    display_name: str = ""
    timeout: int = 30

    def __post_init__(self) -> None:
        if not self.address or "@" not in self.address:
            raise ValueError("IMAP: Adresse fehlt oder enthält kein @")
        if not self.host:
            raise ValueError("IMAP: Server fehlt")

    @property
    def smtp_address(self) -> str:
        return self.smtp_host or self.host

    @property
    def from_header(self) -> str:
        """Absenderzeile: mit Namen, wenn einer hinterlegt ist."""
        name = self.display_name.strip()
        if not name:
            return self.address
        return f"{name} <{self.address}>"

    # Gmail über App-Kennwort: die Server sind fest, nur das Kennwort kommt vom Nutzer.
    GMAIL = {
        "host": "imap.gmail.com",
        "port": 993,
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 587,
        "smtp_security": "starttls",
        "ssl": True,
    }

    @classmethod
    def gmail(cls, address: str, payload: dict) -> ImapConfig:
        """Gmail mit App-Kennwort; Server und Ports sind fest vorgegeben."""
        kennwort = str(payload.get("password", "")).strip()
        if not kennwort:
            raise ValueError(
                "Für Gmail fehlt das App-Kennwort. Es entsteht bei Google unter "
                "myaccount.google.com/apppasswords (Zwei-Faktor-Anmeldung nötig)."
            )
        return cls(
            address=address,
            user=str(payload.get("user", "") or address),
            password=kennwort,
            display_name=str(payload.get("display_name", "")),
            **cls.GMAIL,
        )

    @classmethod
    def from_tokens(cls, address: str, payload: dict) -> ImapConfig:
        """Zugangsdaten aus dem verschlüsselten Speicher; fehlende Felder benennen."""
        fehlend = [
            name
            for name in ("host", "user", "password")
            if not str(payload.get(name, "")).strip()
        ]
        if fehlend:
            raise ValueError(
                "IMAP: folgende Angaben fehlen: " + ", ".join(fehlend)
            )
        return cls(
            address=address,
            host=str(payload["host"]),
            port=int(payload.get("port", 993)),
            user=str(payload["user"]),
            password=str(payload["password"]),
            ssl=str(payload.get("ssl", "true")).lower() in ("1", "true", "ja", "yes"),
            smtp_host=str(payload.get("smtp_host", "")),
            smtp_port=int(payload.get("smtp_port", 587)),
            smtp_security=str(payload.get("smtp_security", "starttls")),
            drafts_folder=str(payload.get("drafts_folder", "Drafts")),
            sent_folder=str(payload.get("sent_folder", "Sent")),
            archive_folder=str(payload.get("archive_folder", "Archive")),
            trash_folder=str(payload.get("trash_folder", "Trash")),
            inbox_folder=str(payload.get("inbox_folder", "INBOX")),
            display_name=str(payload.get("display_name", "")),
        )


@dataclass
class ImapProvider:
    """Erfüllt den MailProvider-Vertrag, soweit IMAP ihn hergibt."""

    config: ImapConfig
    _cache: dict[str, list[str]] = field(default_factory=dict, repr=False)

    # --- Verbindungen ---------------------------------------------------------
    def _imap(self) -> imaplib.IMAP4:
        if self.config.ssl:
            conn: imaplib.IMAP4 = imaplib.IMAP4_SSL(
                self.config.host, self.config.port, timeout=self.config.timeout
            )
        else:
            conn = imaplib.IMAP4(
                self.config.host, self.config.port, timeout=self.config.timeout
            )
        conn.login(self.config.user, self.config.password)
        return conn

    def _smtp(self):
        if self.config.smtp_security == "ssl":
            return smtplib.SMTP_SSL(
                self.config.smtp_address, self.config.smtp_port, timeout=self.config.timeout
            )
        client = smtplib.SMTP(
            self.config.smtp_address, self.config.smtp_port, timeout=self.config.timeout
        )
        if self.config.smtp_security == "starttls":
            client.starttls(context=ssl.create_default_context())
        return client

    @property
    def address(self) -> str:
        return self.config.address

    # --- Ordner ---------------------------------------------------------------
    def list_folders(self) -> list[str]:
        with self._imap() as conn:
            typ, data = conn.list()
            if typ != "OK":
                raise ImapError("Ordnerliste nicht abrufbar")
            ordner: list[str] = []
            for zeile in data or []:
                text = zeile.decode("utf-8", "replace") if isinstance(zeile, bytes) else str(zeile)
                treffer = re.search(r'"([^"]*)"\s*$', text)
                if treffer:
                    ordner.append(treffer.group(1))
            return ordner

    def _ensure_folder(self, conn: imaplib.IMAP4, name: str) -> str:
        """Ordner anlegen, wenn er fehlt; gibt den tatsächlichen Namen zurück."""
        typ, data = conn.list()
        vorhanden = []
        for zeile in data or []:
            text = zeile.decode("utf-8", "replace") if isinstance(zeile, bytes) else str(zeile)
            treffer = re.search(r'"([^"]*)"\s*$', text)
            if treffer:
                vorhanden.append(treffer.group(1))
        for ordner in vorhanden:
            if ordner.lower() == name.lower() or ordner.lower().endswith("/" + name.lower()):
                return ordner
        conn.create(name)
        return name

    def _select(self, conn: imaplib.IMAP4, folder: str) -> str:
        typ, _ = conn.select(f'"{folder}"', readonly=False)
        if typ != "OK":
            raise ImapError(f"Ordner '{folder}' nicht auswählbar")
        return folder

    # --- Nachrichten ----------------------------------------------------------
    @staticmethod
    def _split_id(provider_id: str) -> tuple[str, str]:
        if "|" not in provider_id:
            raise ValueError(f"Ungültige Nachrichtenkennung: {provider_id}")
        folder, uid = provider_id.split("|", 1)
        return folder, uid

    @staticmethod
    def _header_value(raw: bytes | str | None) -> str:
        if raw is None:
            return ""
        text = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
        try:
            return str(make_header(decode_header(text))).strip()
        except Exception:  # noqa: BLE001 - kaputte Kodierung darf nicht abstürzen
            return text.strip()

    def search(
        self, query: str, since: datetime | None = None, limit: int = 20
    ) -> list[MessageHeader]:
        # Suchbegriffe gehen als UTF-8-Bytes hinaus: imaplib kodiert Zeichenketten
        # sonst mit ASCII und bricht bei Umlauten ab.
        kriterien: list[bytes] = [b"ALL"]
        if since is not None:
            kriterien.append(f'SINCE {since.strftime("%d-%b-%Y")}'.encode("ascii"))

        with self._imap() as conn:
            folder = self._select(conn, self.config.inbox_folder)
            typ, data = conn.uid("search", None, *kriterien)  # type: ignore[arg-type]
            if typ != "OK":
                raise ImapError("Suche fehlgeschlagen")
            uids = (data[0] or b"").split()
            if not uids:
                return []

            # Freitext wird hier gefiltert, nicht vom Server gesucht: IMAP-SEARCH
            # vergleicht Kopfzeilen im Rohzustand, Betreffs mit Umlauten stehen dort
            # aber als =?utf-8?…?= und würden nie treffen.
            # Kopfzeilen zuerst, ohne Text: der Server liefert die Teile in beliebiger
            # Reihenfolge, deshalb wird jedes Teil über seine UID zugeordnet.
            felder = "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE MESSAGE-ID)])"
            typ, roh = conn.uid("fetch", b",".join(uids[-max(limit * 3, 30):]).decode(), felder)
            if typ != "OK":
                raise ImapError("Kopfzeilen nicht abrufbar")

            ergebnis: list[MessageHeader] = []
            for teil in roh or []:
                if not isinstance(teil, tuple) or len(teil) < 2:
                    continue
                uid_treffer = re.search(rb"UID (\d+)", teil[0])
                if not uid_treffer:
                    continue
                uid = uid_treffer.group(1).decode()
                nachricht = email.message_from_bytes(teil[1])
                empfangen = self._parse_date(nachricht.get("Date"))
                ergebnis.append(
                    MessageHeader(
                        provider_id=f"{folder}|{uid}",
                        thread_id=self._header_value(nachricht.get("Message-ID")) or uid,
                        sender=self._header_value(nachricht.get("From")),
                        subject=self._header_value(nachricht.get("Subject")),
                        received_at=empfangen,
                        labels=(),
                        snippet="",
                    )
                )
            ergebnis.sort(key=lambda h: h.received_at, reverse=True)
            anrisse = self._anrisse(conn, folder, ergebnis[: max(limit, 10)])
            ergebnis = [
                replace(kopf, snippet=anrisse.get(kopf.provider_id.split("|")[-1], ""))
                if anrisse.get(kopf.provider_id.split("|")[-1])
                else kopf
                for kopf in ergebnis
            ]

        worte = [w.lower() for w in re.split(r"\s+", query or "") if w]
        if not worte:
            return ergebnis[:limit]

        treffer = [
            kopf
            for kopf in ergebnis
            if all(
                wort in f"{kopf.subject} {kopf.sender}".lower() for wort in worte
            )
        ]
        if treffer:
            return treffer[:limit]

        # Kein Treffer im Kopf: Körper der jüngsten Nachrichten prüfen.
        for kopf in ergebnis[:25]:
            try:
                inhalt = self.get_message(kopf.provider_id).body_text
            except (ImapError, ValueError):
                continue
            if all(wort in inhalt.lower() for wort in worte):
                treffer.append(kopf)
                if len(treffer) >= limit:
                    break
        return treffer

    def _anrisse(
        self, conn: IMAP4_SSL, folder: str, koepfe: list[MessageHeader]
    ) -> dict[str, str]:
        """Erste Zeilen des Textes je UID. Ein eigener Abruf: nur so ist die Zuordnung sicher."""
        if not koepfe:
            return {}
        uids = [kopf.provider_id.split("|")[-1] for kopf in koepfe]
        typ, roh = conn.uid(
            "fetch", ",".join(uids), "(BODY.PEEK[TEXT]<0.300>)"
        )
        if typ != "OK":
            return {}
        anrisse: dict[str, str] = {}
        for teil in roh or []:
            if not isinstance(teil, tuple) or len(teil) < 2:
                continue
            treffer = re.search(rb"UID (\d+)", teil[0])
            if treffer:
                anrisse[treffer.group(1).decode()] = _anriss(teil[1])
        return anrisse

    @staticmethod
    def _parse_date(wert: str | None) -> datetime:
        if not wert:
            return datetime.now(UTC)
        try:
            return parsedate_to_datetime(wert).astimezone(UTC)
        except (TypeError, ValueError):
            return datetime.now(UTC)

    def get_message(self, provider_id: str) -> MailMessage:
        folder, uid = self._split_id(provider_id)
        with self._imap() as conn:
            self._select(conn, folder)
            typ, data = conn.uid("fetch", uid, "(RFC822)")
            if typ != "OK" or not data:
                raise ImapError(f"Nachricht {provider_id} nicht abrufbar")
            roh = next((teil[1] for teil in data if isinstance(teil, tuple)), None)
            roh = bytes(roh) if roh is not None else None
            if roh is None:
                raise ImapError(f"Nachricht {provider_id} ohne Inhalt")

        nachricht = email.message_from_bytes(roh)  # type: ignore[arg-type]
        text, html = self._bodies(nachricht)
        header = MessageHeader(
            provider_id=provider_id,
            thread_id=self._header_value(nachricht.get("Message-ID")) or uid,
            sender=self._header_value(nachricht.get("From")),
            subject=self._header_value(nachricht.get("Subject")),
            received_at=self._parse_date(nachricht.get("Date")),
            labels=(),
            snippet=text[:140].replace("\n", " "),
        )
        return MailMessage(
            header=header,
            body_text=text,
            body_html=html,
            to=self._addresses(nachricht.get("To")),
            cc=self._addresses(nachricht.get("Cc")),
            anhaenge=self._anhaenge(nachricht),
        )

    def _anhaenge(self, nachricht: Message) -> tuple[Attachment, ...]:
        """Anhänge lesen. Große Anhänge werden nur mit Namen und Größe geführt."""
        gefunden: list[Attachment] = []
        for teil in nachricht.walk():
            if teil.is_multipart():
                continue
            if teil.get_content_disposition() != "attachment":
                continue
            dateiname = self._header_value(teil.get_filename()) or "anhang"
            roh = teil.get_payload(decode=True) or b""
            groesse = len(roh)
            gefunden.append(
                Attachment(
                    dateiname=dateiname,
                    art=teil.get_content_type(),
                    groesse=groesse,
                    inhalt=roh if groesse <= MAX_ANHANG else b"",
                )
            )
        return tuple(gefunden)

    def _addresses(self, wert: str | None) -> tuple[str, ...]:
        if not wert:
            return ()
        return tuple(
            teil.split("<")[-1].rstrip(">").strip()
            for teil in str(wert).split(",")
            if teil.strip()
        )

    def _bodies(self, nachricht: Message) -> tuple[str, str | None]:
        text = ""
        html: str | None = None
        for teil in nachricht.walk():
            if teil.is_multipart():
                continue
            art = teil.get_content_type()
            if teil.get_content_disposition() == "attachment":
                continue
            if art == "text/plain" and not text:
                text = self._decode(teil)
            elif art == "text/html" and html is None:
                html = self._decode(teil)
        if not text and html:
            text = html_to_text(html)
        return text, html

    @staticmethod
    def _decode(teil: Message) -> str:
        try:
            inhalt = teil.get_payload(decode=True) or b""
        except Exception:  # noqa: BLE001
            return ""
        zeichensatz = teil.get_content_charset() or "utf-8"
        try:
            return inhalt.decode(zeichensatz, "replace")
        except LookupError:
            return inhalt.decode("utf-8", "replace")

    # --- Entwürfe und Senden --------------------------------------------------
    def create_draft(
        self,
        to: tuple[str, ...],
        subject: str,
        body: str,
        reply_to: str | None = None,
    ) -> DraftRef:
        nachricht = EmailMessage()
        nachricht["From"] = self.config.from_header
        nachricht["To"] = ", ".join(to)
        nachricht["Subject"] = subject
        if reply_to:
            nachricht["In-Reply-To"] = reply_to
            nachricht["References"] = reply_to
        nachricht.set_content(body)

        with self._imap() as conn:
            folder = self._ensure_folder(conn, self.config.drafts_folder)
            typ, data = conn.append(
                f'"{folder}"', "\\Draft", imaplib.Time2Internaldate(datetime.now(UTC)),
                nachricht.as_bytes(),
            )
            if typ != "OK":
                raise ImapError("Entwurf konnte nicht abgelegt werden")
            uid = ""
            antwort = data[0].decode("utf-8", "replace") if data and data[0] else ""
            treffer = re.search(r"APPENDUID \d+ (\d+)", antwort)
            if treffer:
                uid = treffer.group(1)
            if not uid:
                uid = self._find_by_message_id(conn, folder, str(nachricht["Message-ID"] or ""))
        return DraftRef(provider_id=f"{folder}|{uid}", to=to, subject=subject)

    def _find_by_message_id(self, conn: imaplib.IMAP4, folder: str, message_id: str) -> str:
        if not message_id:
            return ""
        self._select(conn, folder)
        typ, data = conn.uid(  # type: ignore[arg-type]
            "search", None, f'HEADER Message-ID "{message_id}"'
        )
        if typ != "OK" or not data or not data[0]:
            return ""
        return data[0].split()[-1].decode()

    def send_draft(self, draft_id: str) -> SendResult:
        folder, uid = self._split_id(draft_id)
        with self._imap() as conn:
            self._select(conn, folder)
            typ, data = conn.uid("fetch", uid, "(RFC822)")
            if typ != "OK" or not data:
                raise ImapError(f"Entwurf {draft_id} nicht gefunden")
            roh = next((teil[1] for teil in data if isinstance(teil, tuple)), None)
            roh = bytes(roh) if roh is not None else None
            if roh is None:
                raise ImapError(f"Entwurf {draft_id} ohne Inhalt")

        nachricht = email.message_from_bytes(roh)  # type: ignore[arg-type]
        empfaenger = [
            teil.split("<")[-1].rstrip(">").strip()
            for teil in str(nachricht.get("To", "")).split(",")
            if teil.strip()
        ]
        if not empfaenger:
            raise ImapError("Entwurf ohne Empfänger")

        with self._smtp() as client:
            if self.config.smtp_security == "starttls" or self.config.smtp_security == "ssl":
                client.login(self.config.user, self.config.password)
            client.send_message(nachricht, from_addr=self.config.address, to_addrs=empfaenger)

        # Entwurf nach Gesendet verschieben; ein Duplikat im Entwurfsordner bleibt sonst.
        with self._imap() as conn:
            self._select(conn, folder)
            ziel = self._ensure_folder(conn, self.config.sent_folder)
            conn.uid("copy", uid, f'"{ziel}"')
            conn.uid("store", uid, "+FLAGS", "(\\Deleted)")
            conn.expunge()

        return SendResult(
            provider_id=draft_id,
            thread_id=self._header_value(nachricht.get("Message-ID")) or draft_id,
            sent_at=datetime.now(UTC),
        )

    # --- Kennzeichnen, Lesen, Ablegen ----------------------------------------
    def apply_label(self, provider_id: str, label: str) -> None:
        """IMAP kennt keine Labels: der Name wird zum Ordner, die Nachricht kopiert."""
        folder, uid = self._split_id(provider_id)
        with self._imap() as conn:
            self._select(conn, folder)
            ziel = self._ensure_folder(conn, label)
            typ, _ = conn.uid("copy", uid, f'"{ziel}"')
            if typ != "OK":
                raise ImapError(f"Label '{label}' konnte nicht gesetzt werden")

    def mark_read(self, provider_id: str) -> None:
        self._flag(provider_id, "+FLAGS", "(\\Seen)")

    def mark_unread(self, provider_id: str) -> None:
        self._flag(provider_id, "-FLAGS", "(\\Seen)")

    def _flag(self, provider_id: str, operation: str, flags: str) -> None:
        folder, uid = self._split_id(provider_id)
        with self._imap() as conn:
            self._select(conn, folder)
            typ, _ = conn.uid("store", uid, operation, flags)
            if typ != "OK":
                raise ImapError(f"Merker {flags} nicht setzbar")

    def archive(self, provider_id: str) -> None:
        self._move(provider_id, self.config.archive_folder)

    def delete(self, provider_id: str, permanent: bool = False) -> None:
        if permanent:
            folder, uid = self._split_id(provider_id)
            with self._imap() as conn:
                self._select(conn, folder)
                conn.uid("store", uid, "+FLAGS", "(\\Deleted)")
                conn.expunge()
            return
        self._move(provider_id, self.config.trash_folder)

    def _move(self, provider_id: str, ziel: str) -> None:
        folder, uid = self._split_id(provider_id)
        with self._imap() as conn:
            self._select(conn, folder)
            ordner = self._ensure_folder(conn, ziel)
            typ, _ = conn.uid("copy", uid, f'"{ordner}"')
            if typ != "OK":
                raise ImapError(f"Verschieben nach '{ordner}' fehlgeschlagen")
            conn.uid("store", uid, "+FLAGS", "(\\Deleted)")
            conn.expunge()

    # --- Kalender: von IMAP nicht abgedeckt ----------------------------------
    def list_events(self, start: datetime, end: datetime) -> list[Event]:
        raise NotSupported(
            "IMAP kennt keinen Kalender. Für Termine Exchange Online über Graph anbinden."
        )

    def create_event(
        self,
        subject: str,
        start: datetime,
        end: datetime,
        attendees: tuple[str, ...] = (),
        body: str = "",
    ) -> Event:
        raise NotSupported(
            "IMAP kennt keinen Kalender. Für Termine Exchange Online über Graph anbinden."
        )

    def move_event(self, provider_id: str, start: datetime, end: datetime) -> Event:
        raise NotSupported(
            "IMAP kennt keinen Kalender. Für Termine Exchange Online über Graph anbinden."
        )
