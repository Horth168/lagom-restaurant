from datetime import datetime

from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.models.enums import Role


def _email(v: str) -> str:
    v = v.strip().lower()
    local, _, domain = v.partition("@")
    if not local or "." not in domain or " " in v or len(v) > 255:
        raise ValueError("Enter a valid email address")
    return v


# Simple check on purpose: strict validators reject valid internal domains (e.g. *.test)
Email = Annotated[str, Field(min_length=3, max_length=255), AfterValidator(_email)]


class LoginIn(BaseModel):
    email: Email
    password: str = Field(min_length=1, max_length=200)


class StaffOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    role: Role
    extra_permissions: list[str]
    is_active: bool
    preferred_language: str
    last_login_at: datetime | None
    created_at: datetime


class MeOut(StaffOut):
    permissions: list[str]


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int
    user: MeOut


class StaffCreate(BaseModel):
    email: Email
    full_name: str = Field(min_length=1, max_length=120)
    role: Role
    password: str = Field(min_length=10, max_length=200)
    extra_permissions: list[str] = []
    preferred_language: str = Field("en", pattern="^(en|km|zh)$")


class StaffUpdate(BaseModel):
    full_name: str | None = Field(None, min_length=1, max_length=120)
    role: Role | None = None
    extra_permissions: list[str] | None = None
    is_active: bool | None = None
    preferred_language: str | None = Field(None, pattern="^(en|km|zh)$")


class PasswordReset(BaseModel):
    new_password: str = Field(min_length=10, max_length=200)


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=10, max_length=200)
