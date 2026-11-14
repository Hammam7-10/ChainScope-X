from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    ADMIN = "admin"
    ANALYST = "analyst"
    VIEWER = "viewer"


PERMISSIONS: dict[str, frozenset[Role]] = {
    "analysis.run": frozenset({Role.ADMIN, Role.ANALYST}),
    "analysis.view": frozenset({Role.ADMIN, Role.ANALYST, Role.VIEWER}),
    "findings.view": frozenset({Role.ADMIN, Role.ANALYST, Role.VIEWER}),
    "evidence.view": frozenset({Role.ADMIN, Role.ANALYST, Role.VIEWER}),
    "events.view": frozenset({Role.ADMIN, Role.ANALYST, Role.VIEWER}),
    "policy.modify": frozenset({Role.ADMIN}),
    "policy.deactivate": frozenset({Role.ADMIN}),
    "persistence.reconcile": frozenset({Role.ADMIN, Role.ANALYST}),
    "admin.manage": frozenset({Role.ADMIN}),
}


def has_permission(role: Role | str, permission: str) -> bool:
    try:
        normalized = Role(role)
    except ValueError:
        return False
    return normalized in PERMISSIONS.get(permission, frozenset())
