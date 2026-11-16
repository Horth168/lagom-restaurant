from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.deps import CurrentStaff, get_current_staff
from app.core.permissions import permissions_for
from app.core.rate_limit import client_ip, limiter
from app.core.security import create_access_token, hash_password, password_problems, verify_password
from app.db import get_db
from app.models import User
from app.models.base import utcnow
from app.schemas.staff import LoginIn, MeOut, PasswordChange, TokenOut
from app.services.audit import audit

router = APIRouter(prefix="/api/auth", tags=["auth"])


def me_out(user: User) -> MeOut:
    fields = {f: getattr(user, f) for f in MeOut.model_fields if f != "permissions"}
    return MeOut(**fields, permissions=sorted(permissions_for(user.role, user.extra_permissions)))


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    s = get_settings()
    email = body.email.lower().strip()
    # Limit both per IP and per account, to slow down password guessing
    limiter.check(f"login-ip:{client_ip(request)}", s.login_rate_limit_per_minute, 60)
    limiter.check(f"login-email:{email}", s.login_rate_limit_per_minute, 300)

    user = db.scalar(select(User).where(func.lower(User.email) == email))
    if not verify_password(body.password, user.password_hash if user else None) or not user:
        audit(db, "auth.login_failed", "user", details={"email": email}, request=request)
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email or password is incorrect.")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account has been deactivated.")

    user.last_login_at = utcnow()
    audit(db, "auth.login", "user", user.id, user_id=user.id, request=request)
    db.commit()
    return TokenOut(
        access_token=create_access_token(user.id, user.token_version),
        expires_in_minutes=s.access_token_minutes,
        user=me_out(user),
    )


@router.get("/me", response_model=MeOut)
def me(staff: CurrentStaff = Depends(get_current_staff)):
    return me_out(staff.user)


class MeUpdate(BaseModel):
    preferred_language: str = Field(pattern="^(en|km|zh)$")


@router.patch("/me", response_model=MeOut)
def update_me(body: MeUpdate, staff: CurrentStaff = Depends(get_current_staff), db: Session = Depends(get_db)):
    """Staff choose their own language; the app opens in it next time they sign in."""
    user = db.get(User, staff.id)
    user.preferred_language = body.preferred_language
    db.commit()
    return me_out(user)


@router.post("/change-password", status_code=204)
def change_password(
    body: PasswordChange,
    request: Request,
    staff: CurrentStaff = Depends(get_current_staff),
    db: Session = Depends(get_db),
):
    user = db.get(User, staff.id)
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect.")
    if problems := password_problems(body.new_password):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, " ".join(problems))
    user.password_hash = hash_password(body.new_password)
    user.token_version += 1  # sign out other devices
    audit(db, "auth.password_changed", "user", user.id, user_id=user.id, request=request)
    db.commit()
