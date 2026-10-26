"""Pydantic request/response models.

Requests use strict schemas: `extra="forbid"` means any unexpected field (a
smuggled `points`, `user_id`, `score`, `role`, ...) is rejected outright rather
than silently ignored — closing the parameter-tampering vector at the door.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .config import EMAIL_MAX_LEN, PASSWORD_MAX_LEN, PASSWORD_MIN_LEN, USERNAME_PATTERN
from .emailpolicy import InvalidEmail, normalise_email


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RegisterRequest(_StrictModel):
    # Plain `str` + our own validator rather than pydantic's EmailStr: EmailStr
    # would accept any valid address, and we need the domain gate applied by the
    # same function every other write path uses. The value stored downstream is
    # this validator's normalised output, so the check cannot be sidestepped by
    # sending a differently-cased or oddly-formatted variant.
    email: str = Field(max_length=EMAIL_MAX_LEN)
    username: str = Field(pattern=USERNAME_PATTERN)
    password: str = Field(min_length=PASSWORD_MIN_LEN, max_length=PASSWORD_MAX_LEN)

    @field_validator("email")
    @classmethod
    def _check_email_policy(cls, v: str) -> str:
        try:
            return normalise_email(v)
        except InvalidEmail as exc:
            raise ValueError(str(exc)) from exc

    @field_validator("username")
    @classmethod
    def _normalise_username(cls, v: str) -> str:
        return v.strip()


class LoginRequest(_StrictModel):
    # Accept either a username or an email in one field.
    identifier: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=PASSWORD_MAX_LEN)


class FlagSubmitRequest(_StrictModel):
    flag: str = Field(min_length=1, max_length=256)


# --- Responses ---------------------------------------------------------------


class PublicUser(BaseModel):
    username: str


class MeResponse(BaseModel):
    username: str
    score: int
    captured_stages: list[int]
    total_points: int
    # Returned so the SPA can restore its CSRF token after a page refresh
    # (the session cookie survives; the in-memory token does not).
    csrf_token: str


class LoginResponse(BaseModel):
    username: str
    csrf_token: str


class FlagSubmitResponse(BaseModel):
    correct: bool
    stage: int | None = None
    points: int = 0
    already_captured: bool = False
    score: int


class ScoreRow(BaseModel):
    rank: int
    username: str
    score: int
    flags_captured: int


class FlagInfo(BaseModel):
    stage: int
    name: str
    points: int


class PolicyResponse(BaseModel):
    """Public registration rules, so the SPA's hints match what the server
    actually enforces even when the operator overrides ALLOWED_EMAIL_DOMAIN.
    Advisory only — the server remains the sole authority."""

    email_domain: str
    password_min_length: int


class LabResponse(BaseModel):
    name: str
    url: str
    summary: str
    stages: list[FlagInfo]
    total_points: int
