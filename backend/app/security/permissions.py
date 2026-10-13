"""Role → permission resolution (reference data is cached per process)."""
from __future__ import annotations

import threading

from sqlalchemy import select

from app.db.session import system_session
from app.models import Role, RolePermission

_lock = threading.Lock()
_cache: dict[str, frozenset[str]] | None = None
_ranks: dict[str, int] = {}


def _load() -> dict[str, frozenset[str]]:
    global _cache
    with _lock:
        if _cache is None:
            mapping: dict[str, set[str]] = {}
            with system_session() as s:
                for role in s.scalars(select(Role)):
                    mapping.setdefault(role.key, set())
                    _ranks[role.key] = role.rank
                for rp in s.scalars(select(RolePermission)):
                    mapping.setdefault(rp.role_key, set()).add(rp.permission_key)
            _cache = {k: frozenset(v) for k, v in mapping.items()}
        return _cache


def permissions_for_role(role_key: str) -> frozenset[str]:
    return _load().get(role_key, frozenset())


def role_rank(role_key: str) -> int:
    _load()
    return _ranks.get(role_key, 0)


def known_roles() -> list[str]:
    return list(_load())


def all_permissions() -> frozenset[str]:
    return permissions_for_role("platform_super_admin")


def reset_cache() -> None:
    global _cache
    with _lock:
        _cache = None
        _ranks.clear()
