# HELIXCHAIN Scoreboard Dashboard

A **secure, self-contained** companion dashboard for the
[`combined-chain-lab`](../README.md) (HELIXCHAIN) MCP kill-chain range. Players register,
sign in, read the lab briefing, submit the four flags they capture, and watch a live
scoreboard ranked highest → lowest.

Unlike the lab it tracks, **this dashboard is deliberately hardened** — there is no intended
way to inflate a score or take over another account.

```
┌─────────────┐      /api/* (same-origin proxy)      ┌──────────────┐
│  frontend    │ ───────────────────────────────────▶ │   backend    │
│  nginx :3200 │                                       │ FastAPI :8200│──▶ SQLite (volume)
│  React SPA   │ ◀─── httpOnly signed session cookie ──│  SQLAlchemy  │
└─────────────┘                                       └──────────────┘
```

Ports **3200 / 8200** are chosen so this runs alongside the lab (3100 / 8100 / 8101) without
collisions.

---

## Run

```bash
cd combined-chain-lab/scoreboard-dashboard
cp .env.example .env          # set a strong SESSION_SECRET (see the file)
docker compose up --build
# open http://localhost:3200
```

The dashboard runs **standalone** — the lab does not need to be up. Only the "Open the lab"
button points at `http://localhost:3100`. Scores persist in a Docker volume across restarts.

> Set `SESSION_SECRET` to a long random value in `.env`. Generate one with:
> `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Keep it stable so existing
> logins survive a restart. Set `COOKIE_SECURE=1` if you serve the dashboard over HTTPS.

---

## Registration policy

Only **`@gmail.com`** addresses may register (override with `ALLOWED_EMAIL_DOMAIN`).
The address must also be a syntactically valid one — but it is **never emailed**, so
`test@gmail.com` is a perfectly good lab identity.

Enforcement lives in `backend/app/emailpolicy.py`, which parses the address with
`email_validator` and compares the **normalised ASCII domain for exact equality** — not a
suffix test. So these are all rejected:

| Attempt | Why it fails |
|---------|--------------|
| `a@gmail.com.evil.com` | domain is `gmail.com.evil.com` |
| `a@mail.gmail.com` | subdomain ≠ the domain |
| `a@net-squаre.com` (Cyrillic `а`) | IDNA-normalises to `xn--net-squre-6yh.com` |
| `"x@evil.com"@gmail.com` | quoted local parts rejected |
| `Foo <a@gmail.com>` | display names rejected |
| `a@evil.com,b@gmail.com` | not a single address |

The same function runs in the request schema **and** in `crud.create_user`, which is the only
code path that inserts a user — so a new entry point cannot accidentally skip the check. The
browser does a matching check for fast feedback, but it is advisory: the server decides.
`./scoreboard-admin.sh check-emails` reports any account that would not pass the current policy.

---

## Forgotten passwords

There is **no self-service reset, by design**. Player addresses are fake, so no mail can be
sent, and a "forgot password" form with nothing to verify against would just be a way to take
over someone else's score. An operator resets it instead — the account, its score, and its
captured flags all survive:

```bash
$ ./scoreboard-admin.sh reset-password retr0

User:     retr0 <marcus_holloway@gmail.com>
Score:    10  (flags 1)

New password: ZkGbs-bzcU3-vwREN
(shown once; 1 session(s) revoked)
```

Pass `--password '...'` to choose one yourself, or `--keep-sessions` to leave their existing
logins alive. By default the reset revokes every active session, so the old password (and any
live cookie) stops working immediately.

---

## Managing accounts

Player data lives in the named Docker volume **`scoreboard-data`** (`/data/scoreboard.db`).
That volume is *not* touched by `docker compose down`, `up --build`, or `restart` — which is
why accounts survive a rebuild. `docker compose down -v` is the only thing that erases it, and
it erases **everyone**. To remove specific rows instead, use the admin CLI:

```bash
./scoreboard-admin.sh list                       # id, username, email, score, stages, sessions
./scoreboard-admin.sh delete marcus              # by username (case-insensitive) — prompts first
./scoreboard-admin.sh delete 3 alice@example.com --yes   # by id / email, no prompt
./scoreboard-admin.sh reset-captures marcus      # clear their flags, keep the account
./scoreboard-admin.sh reset-password marcus      # new password, score kept (see above)
./scoreboard-admin.sh check-emails               # accounts outside the allowed domain
./scoreboard-admin.sh backup ./snap.db           # consistent snapshot (see below)
./scoreboard-admin.sh restore ./snap.db          # replace the live DB
./scoreboard-admin.sh logout marcus              # revoke active sessions only
```

Deleting a user cascades to their captures and sessions. The wrapper `exec`s into the running
backend, or spins up a throwaway container on the same volume if the stack is down. It is
shell-only — nothing here is exposed over HTTP. Direct form:

```bash
docker compose exec backend python -m app.manage delete marcus
```

### Backups — do not `cp` the database file

> ⚠️ **`docker compose cp backend:/data/scoreboard.db ...` produces a silently stale backup.**
> The engine runs in **WAL mode**, so recent commits live in `scoreboard.db-wal` until a
> checkpoint folds them into the main file. Copying `scoreboard.db` on its own captures the
> *pre-commit* state — and the result opens cleanly, so nothing looks wrong. Measured on this
> stack, immediately after deleting a user: live DB `1 user`, `cp` of the file `2 users`.

Use the CLI instead — it goes through SQLite's online backup API, which reads through the WAL
and is safe to run while the app is serving:

```bash
./scoreboard-admin.sh backup ./scoreboard-$(date +%F).db     # consistent snapshot
./scoreboard-admin.sh restore ./scoreboard-2026-08-01.db     # replace the live DB (prompts)
```

`restore` also goes through the backup API rather than swapping files: overwriting
`scoreboard.db` on disk would leave the old `-wal`/`-shm` behind for SQLite to replay over your
restored data. Take a snapshot before any bulk `delete`.

---

## Points

Assigned by stage difficulty / number of steps (multiples of 10):

| Stage | Objective | Flag | Points |
|-------|-----------|------|--------|
| 1 | Information disclosure | `FLAG{CHAIN_STATUS_INFO_DISCLOSURE}` | **10** |
| 2 | Signer privilege escalation | `FLAG{CHAIN_SIGNER_PRIVILEGE_ESCALATION}` | **20** |
| 3 | Admin BOLA / confused deputy | `FLAG{CHAIN_ADMIN_BOLA_CONFUSED_DEPUTY}` | **30** |
| 4 | Remote code execution | `FLAG{CHAIN_ADMIN_RCE_COMMAND_INJECTION}` | **40** |

Total **100**. Flag values default to the lab's built-ins and can be overridden with
`FLAG1..FLAG4` in `.env` (keep them in sync with your lab deployment).

---

## Security design

The core requirement is that **no user can modify their score or hijack another account** via
injection, parameter tampering, replay, or any other vector.

| Concern | Mitigation |
|---------|-----------|
| **SQL / NoSQL injection** | 100% SQLAlchemy ORM with bound parameters — no string-built SQL anywhere. Pydantic schemas (parsed email + domain policy, username regex, length caps) validate every input. |
| **Email domain policy** | Registration is limited to a single operator-configured domain, enforced by `emailpolicy.normalise_email()` — a real address parse plus **exact** normalised-ASCII-domain equality (not a suffix match), so lookalike, subdomain, quoted-local, display-name and multi-address payloads are all rejected. The same function guards both the request schema and `crud.create_user`, the only insert path. |
| **Registration race condition** | The check-then-insert critical section runs under a process-wide `asyncio.Lock` (single-threaded, as requested) **and** is backed by DB `UNIQUE(email)` / `UNIQUE(username)` constraints — duplicate accounts are impossible even under a burst of simultaneous signups. Usernames/emails are compared case-insensitively. |
| **Passwords** | bcrypt with per-password salt (passlib). Plaintext is never stored or logged. Login timing is uniform whether or not the account exists (no user enumeration). |
| **Account takeover / IDOR** | The authenticated user is **always** derived from the signed session cookie — never from a client-supplied id. There is no endpoint that acts on another user by id. |
| **Session security** | Opaque 256-bit token stored server-side, delivered in an **httpOnly, SameSite=Lax, signed** cookie. httpOnly ⇒ not readable by JS (XSS can't steal it); signed ⇒ can't be forged; server-side ⇒ logout/expiry invalidate immediately. |
| **CSRF** | Double-submit token issued at login, echoed in an `X-CSRF-Token` header on every state-changing request and verified server-side (constant-time), combined with `SameSite` cookies. |
| **Score integrity** | The flag→points map lives **only** in backend `config.py`. Submitting a flag sends just the flag string; the server matches it in **constant time** (`hmac.compare_digest`) and writes the fixed server-side points. Clients can never send, pick, or edit points. A user's score is a *derived* `SUM(captures.points)` — there is no mutable score column to attack. |
| **Replay for double points** | `UNIQUE(user_id, flag_stage)` — a flag credits a user at most once. Resubmitting returns `already_captured` with 0 extra points. |
| **Parameter tampering** | Request schemas use `extra="forbid"` — any smuggled field (`points`, `user_id`, `score`, `role`, …) is rejected, not ignored. |
| **Brute force / abuse** | In-memory sliding-window rate limits on login (per IP+identifier) and flag submission (per user). |
| **Info leakage** | FastAPI docs/OpenAPI disabled; generic 500s; security headers (`X-Content-Type-Options`, `X-Frame-Options: DENY`, CSP, `Referrer-Policy`) from both nginx and the backend. Scoreboard exposes only username + score (emails stay private). |

---

## API

All under `/api`, same-origin behind the nginx proxy.

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/api/register` | — | `{email, username, password}` → 201 / 409 |
| POST | `/api/login` | — | `{identifier, password}` → sets cookie, returns `{username, csrf_token}` |
| POST | `/api/logout` | cookie + CSRF | invalidate session |
| GET  | `/api/me` | cookie | current user, score, captured stages, CSRF token |
| POST | `/api/submit-flag` | cookie + CSRF | `{flag}` → `{correct, stage, points, already_captured, score}` |
| GET  | `/api/scoreboard` | — | ranked `[{rank, username, score, flags_captured}]` |
| GET  | `/api/lab` | — | lab briefing + URL + stage/points table |
| GET  | `/api/health` | — | liveness |

---

## Layout

```
scoreboard-dashboard/
├── docker-compose.yml        # backend (8200, internal) + frontend (3200)
├── .env.example
├── scoreboard-admin.sh       # operator CLI (list/delete/reset-password/check-emails/…)
├── backend/                  # FastAPI + SQLite (SQLAlchemy)
│   └── app/{config,database,models,schemas,security,emailpolicy,ratelimit,crud,routes,main,manage}.py
└── frontend/                 # React + Vite + Tailwind (lab theme), served by nginx
    └── src/{App,api}.jsx + components/{AuthPanel,LabBriefing,Progress,FlagSubmit,Scoreboard}.jsx
```

> ⚠️ Companion to an intentionally vulnerable training lab, for authorized security education
> only. The **lab** is vulnerable by design; **this dashboard** is not.
