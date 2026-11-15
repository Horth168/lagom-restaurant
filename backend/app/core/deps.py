"""FastAPI dependencies for authentication and permissions."""
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.permissions import permissions_for
from app.core.security import decode_access_token
from app.db import get_db
from app.models import User

_bearer = HTTPBearer(auto_error=False)


@dataclass
class CurrentStaff:
    user: User
    permissions: set[str]

    @property
    def id(self) -> int:
        return self.user.id

    def can(self, perm: str) -> bool:
        return perm in self.permissions


def user_from_token(db: Session, token: str | None) -> User | None:
    if not token:
        return None
    payload = decode_access_token(token)
    if not payload:
        return None
    user = db.get(User, int(payload["sub"]))
    if not user or not user.is_active or user.token_version != payload.get("ver"):
        return None
    return user


def get_current_staff(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> CurrentStaff:
    user = user_from_token(db, creds.credentials if creds else None)
    if not user:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Please sign in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    staff = CurrentStaff(user=user, permissions=permissions_for(user.role, user.extra_permissions))
    request.state.staff = staff
    return staff


def require(*perms: str, any_of: bool = False):
    """Require all (default) or any of the given permissions."""

    def _dep(staff: CurrentStaff = Depends(get_current_staff)) -> CurrentStaff:
        ok = any(staff.can(p) for p in perms) if any_of else all(staff.can(p) for p in perms)
        if not ok:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have permission to do this.")
        return staff

    return _dep
