"""API routes. All under /api, same-origin with the SPA.

Security invariants enforced here:
- The authenticated user is ALWAYS derived from the signed session cookie,
  never from a request field → no IDOR / account-takeover path.
- State-changing requests require a matching CSRF token header.
- Flag matching is constant-time; points come only from the server-side table.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy.orm import Session as OrmSession

from . import config, crud, emailpolicy, ratelimit, security
from .database import get_db
from .models import Session, User
from .schemas import (
    FlagInfo,
    FlagSubmitRequest,
    FlagSubmitResponse,
    LabResponse,
    LoginRequest,
    LoginResponse,
    MeResponse,
    PolicyResponse,
    RegisterRequest,
    ScoreRow,
)

router = APIRouter(prefix="/api")

_LAB_SUMMARY = (
    "HELIXCHAIN is a single dual-LLM MCP kill-chain that fuses three OWASP-MCP "
    "weaknesses into one ordered attack: authenticate → leak → escalate to "
    "support → take over admin → RCE. Each stage's access unlocks the next, so "
    "the four flags must fall in order. The models behave — every flaw lives in "
    "the MCP server's authorization decisions and one shell sink. Capture each "
    "flag in the lab's chat, then submit it here for points."
)


# --- Helpers -----------------------------------------------------------------


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _current_session(request: Request, db: OrmSession) -> Session | None:
    raw = request.cookies.get(config.SESSION_COOKIE_NAME)
    if not raw:
        return None
    token = security.unsign_cookie(raw)
    if not token:
        return None
    return crud.get_valid_session(db, token)


def require_session(request: Request, db: OrmSession = Depends(get_db)) -> Session:
    sess = _current_session(request, db)
    if sess is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return sess


def require_csrf(sess: Session, x_csrf_token: str | None) -> None:
    if not x_csrf_token or not security.constant_time_eq(x_csrf_token, sess.csrf_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token")


def _set_session_cookie(response: Response, session_token: str) -> None:
    response.set_cookie(
        key=config.SESSION_COOKIE_NAME,
        value=security.sign_cookie(session_token),
        max_age=config.SESSION_TTL_SECONDS,
        httponly=True,
        secure=config.COOKIE_SECURE,
        samesite=config.COOKIE_SAMESITE,
        path="/",
    )


# --- Public ------------------------------------------------------------------


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/lab", response_model=LabResponse)
def lab_info() -> LabResponse:
    return LabResponse(
        name=config.LAB_NAME,
        url=config.LAB_URL,
        summary=_LAB_SUMMARY,
        stages=[FlagInfo(stage=f.stage, name=f.name, points=f.points) for f in config.FLAGS],
        total_points=config.TOTAL_POINTS,
    )


@router.get("/policy", response_model=PolicyResponse)
def policy() -> PolicyResponse:
    return PolicyResponse(
        email_domain=config.ALLOWED_EMAIL_DOMAIN,
        password_min_length=config.PASSWORD_MIN_LEN,
    )


@router.get("/scoreboard", response_model=list[ScoreRow])
def get_scoreboard(db: OrmSession = Depends(get_db)) -> list[ScoreRow]:
    return [ScoreRow(**row) for row in crud.scoreboard(db)]


# --- Auth --------------------------------------------------------------------


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, db: OrmSession = Depends(get_db)) -> dict:
    try:
        user = await crud.create_user(
            db, email=payload.email, username=payload.username, password=payload.password
        )
    except emailpolicy.InvalidEmail as exc:
        # Unreachable via HTTP (the schema already ran the same check), but the
        # CRUD layer is authoritative — surface its verdict as a 422 rather than
        # letting a future caller turn a policy violation into a 500.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except crud.DuplicateUser:
        # Generic message — do not reveal whether it was the email or username.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That username or email is already registered.",
        )
    return {"username": user.username}


@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: OrmSession = Depends(get_db),
) -> LoginResponse:
    rl_key = f"login:{_client_ip(request)}:{payload.identifier.strip().lower()}"
    if not ratelimit.check(rl_key, config.LOGIN_MAX_ATTEMPTS, config.LOGIN_WINDOW_SECONDS):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Try again later.",
        )

    user = crud.get_user_by_identifier(db, payload.identifier)
    # Always run a verify to keep timing uniform whether or not the user exists.
    dummy_hash = "$2b$12$" + "." * 53
    valid = security.verify_password(payload.password, user.password_hash if user else dummy_hash)
    if not user or not valid:
        # Identical error for unknown-user and bad-password → no enumeration.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials.",
        )

    sess = crud.create_session(db, user)
    _set_session_cookie(response, sess.token)
    return LoginResponse(username=user.username, csrf_token=sess.csrf_token)


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    x_csrf_token: str | None = Header(default=None),
    db: OrmSession = Depends(get_db),
) -> dict:
    sess = _current_session(request, db)
    if sess is not None:
        require_csrf(sess, x_csrf_token)
        crud.delete_session(db, sess.token)
    response.delete_cookie(config.SESSION_COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me", response_model=MeResponse)
def me(sess: Session = Depends(require_session), db: OrmSession = Depends(get_db)) -> MeResponse:
    user: User = sess.user
    score = crud.user_score(db, user.id)
    return MeResponse(
        username=user.username,
        score=score,
        captured_stages=crud.user_captured_stages(db, user.id),
        total_points=config.TOTAL_POINTS,
        csrf_token=sess.csrf_token,
    )


# --- Flag submission ---------------------------------------------------------


@router.post("/submit-flag", response_model=FlagSubmitResponse)
def submit_flag(
    payload: FlagSubmitRequest,
    sess: Session = Depends(require_session),
    x_csrf_token: str | None = Header(default=None),
    db: OrmSession = Depends(get_db),
) -> FlagSubmitResponse:
    require_csrf(sess, x_csrf_token)

    user: User = sess.user
    rl_key = f"submit:{user.id}"
    if not ratelimit.check(rl_key, config.SUBMIT_MAX_ATTEMPTS, config.SUBMIT_WINDOW_SECONDS):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many submissions. Slow down.",
        )

    submitted = payload.flag.strip()
    # Constant-time match against the authoritative flag table.
    matched = None
    for f in config.FLAGS:
        if security.constant_time_eq(submitted, f.value):
            matched = f
            break

    if matched is None:
        return FlagSubmitResponse(correct=False, score=crud.user_score(db, user.id))

    newly = crud.record_capture(db, user.id, matched.stage, matched.points)
    return FlagSubmitResponse(
        correct=True,
        stage=matched.stage,
        points=matched.points if newly else 0,
        already_captured=not newly,
        score=crud.user_score(db, user.id),
    )
