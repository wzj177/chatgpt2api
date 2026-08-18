from __future__ import annotations

from collections.abc import Mapping

from contracts.auth import AuthCapabilities, AuthSubject, AuthView
from services.config import config


def _clean(value: object) -> str:
    return str(value or "").strip()


def build_auth_view(app_version: str, identity: Mapping[str, object] | None = None) -> AuthView:
    if identity is None:
        return AuthView(
            authenticated=False,
            version=app_version,
            subject=None,
            capabilities=AuthCapabilities(),
            home_route="/login",
        )

    raw_role = _clean(identity.get("role")).lower()
    role = raw_role if raw_role in {"admin", "user"} else "unknown"
    is_admin = role == "admin"
    subject_id = _clean(identity.get("id")) or "authenticated"
    subject_name = _clean(identity.get("name")) or subject_id
    subject_email = _clean(identity.get("email")) or None
    subject_created_at = _clean(identity.get("created_at")) or None

    return AuthView(
        authenticated=True,
        version=app_version,
        subject=AuthSubject(
            id=subject_id,
            name=subject_name,
            role=role,
            email=subject_email,
            created_at=subject_created_at,
        ),
        capabilities=AuthCapabilities(
            admin_console=is_admin,
            studio=True,
            service_access=role == "user" and config.service_button_enabled,
        ),
        home_route="/" if is_admin else "/studio",
    )
