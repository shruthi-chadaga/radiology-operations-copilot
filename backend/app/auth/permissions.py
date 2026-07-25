"""Small composable permission predicates used by domain routes."""

from collections.abc import Callable

from app.auth.models import Role


def require_any_role(*roles: Role) -> Callable[[Role], bool]:
    allowed = frozenset(roles)
    return lambda actual: actual in allowed
