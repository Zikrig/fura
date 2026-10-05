from __future__ import annotations

from enum import Enum

from app.config import Settings
from app.db.repo import Repo


class Role(str, Enum):
    ADMIN = "admin"
    MANAGER = "manager"
    GUARD = "guard"
    NONE = "none"


def resolve_role(user_id: int, settings: Settings, repo: Repo) -> Role:
    if user_id in settings.ADMIN_USER_IDS:
        return Role.ADMIN
    staff = repo.get_staff(user_id)
    if not staff:
        return Role.NONE
    if staff.role == Role.MANAGER.value:
        return Role.MANAGER
    if staff.role == Role.GUARD.value:
        return Role.GUARD
    return Role.NONE


def can_use_bot(role: Role) -> bool:
    return role in {Role.ADMIN, Role.MANAGER, Role.GUARD}


def can_manage_managers(role: Role) -> bool:
    return role == Role.ADMIN


def can_manage_directory(role: Role) -> bool:
    return role in {Role.ADMIN, Role.MANAGER}
