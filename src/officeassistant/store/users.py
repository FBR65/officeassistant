"""Nutzer, Rollen und die Prüfung, ob jemand auf fremde Daten zugreifen darf."""

from __future__ import annotations

from dataclasses import dataclass

import psycopg

ROLES = ("owner", "admin", "member")


@dataclass(frozen=True, slots=True)
class AppUser:
    id: str
    email: str
    display_name: str
    role: str
    active: bool

    @property
    def is_admin(self) -> bool:
        return self.role in ("owner", "admin")


class UserStore:
    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def upsert(
        self,
        user_id: str,
        email: str,
        display_name: str = "",
        role: str = "member",
    ) -> AppUser:
        if role not in ROLES:
            raise ValueError(f"Unbekannte Rolle: {role}")
        with self._conn.transaction():
            row = self._conn.execute(
                """
                INSERT INTO app_user (id, email, display_name, role)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE
                    SET email = excluded.email,
                        display_name = excluded.display_name,
                        updated_at = now()
                RETURNING id, email, display_name, role, active
                """,
                (user_id, email, display_name, role),
            ).fetchone()
        return _user(row)

    def all_users(self) -> list[AppUser]:
        rows = self._conn.execute(
            """
            SELECT id, email, display_name, role, active FROM app_user
            ORDER BY role, email
            """
        ).fetchall()
        return [_user(row) for row in rows]

    def set_role(self, user_id: str, role: str) -> None:
        if role not in ROLES:
            raise ValueError(f"Unbekannte Rolle: {role}")
        with self._conn.transaction():
            self._conn.execute(
                "UPDATE app_user SET role = %s, updated_at = now() WHERE id = %s",
                (role, user_id),
            )

    def set_active(self, user_id: str, active: bool) -> None:
        with self._conn.transaction():
            self._conn.execute(
                "UPDATE app_user SET active = %s, updated_at = now() WHERE id = %s",
                (active, user_id),
            )

    def get(self, user_id: str) -> AppUser | None:
        row = self._conn.execute(
            "SELECT id, email, display_name, role, active FROM app_user WHERE id = %s",
            (user_id,),
        ).fetchone()
        return _user(row) if row else None

    def require(self, user_id: str) -> AppUser:
        user = self.get(user_id)
        if user is None:
            raise PermissionError(f"Unbekannter Nutzer: {user_id}")
        if not user.active:
            raise PermissionError(f"Nutzer ist deaktiviert: {user_id}")
        return user

    def ensure_self(self, actor_id: str, target_user_id: str) -> None:
        """Zugriff auf eigene Daten; fremde Daten nur für Administratorrollen."""
        if actor_id == target_user_id:
            return
        actor = self.require(actor_id)
        if not actor.is_admin:
            raise PermissionError(
                f"Zugriff auf fremde Daten abgewiesen: {actor_id} -> {target_user_id}"
            )


def _user(row: dict) -> AppUser:
    return AppUser(
        id=row["id"],
        email=row["email"],
        display_name=row["display_name"],
        role=row["role"],
        active=row["active"],
    )
