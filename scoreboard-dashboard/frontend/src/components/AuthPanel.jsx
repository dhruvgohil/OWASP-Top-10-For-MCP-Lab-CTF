import { useEffect, useState } from "react";
import { getPolicy, login, register } from "../api.js";

const USERNAME_RE = /^[A-Za-z0-9_-]{3,20}$/;
// Conservative local-part shape. This is a UX nicety only — the server runs the
// real, stricter check (app/emailpolicy.py) and is the only thing that decides.
const LOCAL_PART_RE = /^[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+(\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*$/;
const DEFAULT_DOMAIN = "gmail.com";

export default function AuthPanel({ onLoggedIn }) {
  const [mode, setMode] = useState("login"); // "login" | "register"
  const [identifier, setIdentifier] = useState(""); // login
  const [email, setEmail] = useState(""); // register
  const [username, setUsername] = useState(""); // register
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);
  // Read the domain from the server so the hint stays true if the operator
  // overrides ALLOWED_EMAIL_DOMAIN.
  const [domain, setDomain] = useState(DEFAULT_DOMAIN);

  useEffect(() => {
    let cancelled = false;
    getPolicy()
      .then((p) => {
        if (!cancelled && p?.email_domain) setDomain(p.email_domain);
      })
      .catch(() => {
        /* keep the default hint; the server still enforces the real rule */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  function switchMode(next) {
    setMode(next);
    setError(null);
    setNotice(null);
    setPassword("");
  }

  async function onSubmit(e) {
    e.preventDefault();
    if (busy) return;
    setError(null);
    setNotice(null);

    if (mode === "register") {
      const trimmedEmail = email.trim();
      const at = trimmedEmail.lastIndexOf("@");
      const local = at > 0 ? trimmedEmail.slice(0, at) : "";
      const emailDomain = at > 0 ? trimmedEmail.slice(at + 1).toLowerCase() : "";
      if (emailDomain !== domain || !LOCAL_PART_RE.test(local)) {
        setError(`Enter a valid email address ending in @${domain}`);
        return;
      }
      if (!USERNAME_RE.test(username)) {
        setError("Username must be 3–20 chars: letters, numbers, _ or - only.");
        return;
      }
      if (password.length < 8) {
        setError("Password must be at least 8 characters.");
        return;
      }
    }

    setBusy(true);
    try {
      if (mode === "register") {
        await register(email.trim(), username.trim(), password);
        setNotice("Account created. You can sign in now.");
        setMode("login");
        setIdentifier(username.trim());
        setPassword("");
      } else {
        await login(identifier.trim(), password);
        await onLoggedIn?.();
      }
    } catch (err) {
      setError(err.message || "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  const inputCls =
    "w-full rounded-md border border-line bg-panel2 px-3 py-2.5 font-mono text-sm text-fg outline-none transition-colors placeholder:text-muted/60 focus:border-public";

  return (
    <section className="rounded-lg border border-line bg-panel p-6">
      <div className="mb-5 flex gap-2 font-mono text-[12px]">
        <button
          onClick={() => switchMode("login")}
          className={`rounded-md px-3 py-1.5 uppercase tracking-widest transition-colors ${
            mode === "login" ? "bg-public/15 text-public" : "text-muted hover:text-fg"
          }`}
        >
          Sign in
        </button>
        <button
          onClick={() => switchMode("register")}
          className={`rounded-md px-3 py-1.5 uppercase tracking-widest transition-colors ${
            mode === "register" ? "bg-public/15 text-public" : "text-muted hover:text-fg"
          }`}
        >
          Register
        </button>
      </div>

      <h2 className="eyebrow mb-4">
        {mode === "login" ? "Access your dashboard" : "Create an account"}
      </h2>

      <form onSubmit={onSubmit} className="flex flex-col gap-3">
        {mode === "register" ? (
          <>
            <label className="flex flex-col gap-1">
              <span className="font-mono text-[10.5px] uppercase tracking-widest text-muted">Email</span>
              <input
                type="email"
                required
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder={`you@${domain}`}
                className={inputCls}
              />
              <span className="font-mono text-[10.5px] text-muted">
                Must be an @{domain} address. It is never emailed — nothing is sent to it.
              </span>
            </label>
            <label className="flex flex-col gap-1">
              <span className="font-mono text-[10.5px] uppercase tracking-widest text-muted">Username</span>
              <input
                required
                autoComplete="username"
                spellCheck={false}
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="3–20 chars · a-z 0-9 _ -"
                className={inputCls}
              />
            </label>
          </>
        ) : (
          <label className="flex flex-col gap-1">
            <span className="font-mono text-[10.5px] uppercase tracking-widest text-muted">
              Username or email
            </span>
            <input
              required
              autoComplete="username"
              spellCheck={false}
              value={identifier}
              onChange={(e) => setIdentifier(e.target.value)}
              placeholder="your username or email"
              className={inputCls}
            />
          </label>
        )}

        <label className="flex flex-col gap-1">
          <span className="font-mono text-[10.5px] uppercase tracking-widest text-muted">Password</span>
          <input
            type="password"
            required
            autoComplete={mode === "register" ? "new-password" : "current-password"}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder={mode === "register" ? "at least 8 characters" : "••••••••"}
            className={inputCls}
          />
        </label>

        <button
          type="submit"
          disabled={busy}
          className="mt-1 rounded-md bg-public/15 px-4 py-2.5 font-mono text-sm font-medium uppercase tracking-widest text-public transition-colors hover:bg-public/25 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {busy ? "Working…" : mode === "login" ? "Sign in" : "Create account"}
        </button>

        {mode === "login" && (
          // No self-service reset by design: lab addresses are fake, so no mail
          // can be sent and any "forgot password" form would just be a way to
          // take over someone else's score.
          <p className="font-mono text-[10.5px] leading-relaxed text-muted">
            Forgot your password? Ask the lab organiser to reset it — your score and
            captured flags are kept.
          </p>
        )}
      </form>

      {error && <p className="mt-3 font-mono text-[12px] text-breach">✗ {error}</p>}
      {notice && <p className="mt-3 font-mono text-[12px] text-public">✓ {notice}</p>}
    </section>
  );
}
