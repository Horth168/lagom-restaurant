"""Staff accounts: create, edit, deactivate, reset passwords."""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import CurrentStaff, require
from app.core.permissions import ALL_PERMISSIONS, OWNER_ONLY, ROLE_PERMISSIONS
from app.core.security import hash_password, password_problems
from app.db import get_db
from app.models import User
from app.models.enums import Role
from app.schemas.staff import PasswordReset, StaffCreate, StaffOut, StaffUpdate
from app.services.audit import audit

router = APIRouter(prefix="/api/staff", tags=["staff"])


def _check_can_assign(actor: CurrentStaff, role: Role | None, extra: list[str] | None) -> None:
    is_owner = actor.user.role == Role.OWNER
    if role == Role.OWNER and not is_owner:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the owner can create or promote owners.")
    if extra:
        unknown = [p for p in extra if p not in ALL_PERMISSIONS]
        if unknown:
            raise HTTPException(422, f"Unknown permissions: {unknown}")
        if not is_owner and (set(extra) & OWNER_ONLY or not set(extra) <= actor.permissions):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You cannot give permissions you do not have.")


def _active_owner_count(db: Session) -> int:
    return db.scalar(select(func.count()).where(User.role == Role.OWNER, User.is_active.is_(True)))


@router.get("/roles")
def roles(_: CurrentStaff = Depends(require("staff.manage"))):
    return {
        "roles": {r.value: sorted(p) for r, p in ROLE_PERMISSIONS.items()},
        "permissions": ALL_PERMISSIONS,
    }


@router.get("", response_model=list[StaffOut])
def list_staff(db: Session = Depends(get_db), _: CurrentStaff = Depends(require("staff.manage"))):
    return db.scalars(select(User).order_by(User.is_active.desc(), User.full_name)).all()


@router.post("", response_model=StaffOut, status_code=201)
def create_staff(
    body: StaffCreate,
    request: Request,
    db: Session = Depends(get_db),
    actor: CurrentStaff = Depends(require("staff.manage")),
):
    _check_can_assign(actor, body.role, body.extra_permissions)
    if problems := password_problems(body.password):
        raise HTTPException(422, " ".join(problems))
    email = body.email.lower().strip()
    if db.scalar(select(User.id).where(func.lower(User.email) == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists.")
    user = User(
        email=email,
        full_name=body.full_name.strip(),
        role=body.role,
        password_hash=hash_password(body.password),
        extra_permissions=body.extra_permissions,
        preferred_language=body.preferred_language,
    )
    db.add(user)
    db.flush()
    audit(db, "staff.created", "user", user.id, actor.id, {"role": body.role, "email": email}, request)
    db.commit()
    return user


@router.patch("/{user_id}", response_model=StaffOut)
def update_staff(
    user_id: int,
    body: StaffUpdate,
    request: Request,
    db: Session = Depends(get_db),
    actor: CurrentStaff = Depends(require("staff.manage")),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Staff member not found.")
    if user.role == Role.OWNER and actor.user.role != Role.OWNER:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the owner can edit an owner account.")
    _check_can_assign(actor, body.role, body.extra_permissions)

    changes = body.model_dump(exclude_unset=True)
    if user.id == actor.id and (changes.get("is_active") is False or ("role" in changes and changes["role"] != user.role)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot deactivate or change the role of your own account.")
    losing_owner = user.role == Role.OWNER and (
        changes.get("is_active") is False or ("role" in changes and changes["role"] != Role.OWNER)
    )
    if losing_owner and _active_owner_count(db) <= 1:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "LAGOM must always have at least one active owner.")

    for field, value in changes.items():
        setattr(user, field, value)
    if "is_active" in changes or "role" in changes or "extra_permissions" in changes:
        user.token_version += 1  # force sign-in again with the new permissions
    audit(db, "staff.updated", "user", user.id, actor.id, {k: str(v) for k, v in changes.items()}, request)
    db.commit()
    return user


@router.post("/{user_id}/reset-password", status_code=204)
def reset_password(
    user_id: int,
    body: PasswordReset,
    request: Request,
    db: Session = Depends(get_db),
    actor: CurrentStaff = Depends(require("staff.manage")),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Staff member not found.")
    if user.role == Role.OWNER and actor.user.role != Role.OWNER:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the owner can reset an owner's password.")
    if problems := password_problems(body.new_password):
        raise HTTPException(422, " ".join(problems))
    user.password_hash = hash_password(body.new_password)
    user.token_version += 1
    audit(db, "staff.password_reset", "user", user.id, actor.id, request=request)
    db.commit()
