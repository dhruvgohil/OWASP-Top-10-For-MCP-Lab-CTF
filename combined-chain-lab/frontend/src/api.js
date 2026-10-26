// Backend base URL. In Docker the frontend is served on host :3100 and the browser reaches
// the backend on the host at :8100 (ports remapped so this lab can run alongside the source
// labs). Override with VITE_API_BASE at build time if needed.
// const API_BASE = import.meta.env.VITE_API_BASE || "http://host.docker.internal:8100";
const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8100";
// const API_BASE = import.meta.env.VITE_API_BASE || "http://100.64.138.60:8100";

// A stable per-browser session id so the backend can keep this chat's auth/session memory
// across turns. "New session" rotates it (the 'rewind / start a new session' technique).
function newSessionId() {
  const id = "sess-" + Math.random().toString(36).slice(2) + Date.now().toString(36);
  localStorage.setItem("helix_session_id", id);
  return id;
}

export function getSessionId() {
  return localStorage.getItem("helix_session_id") || newSessionId();
}

export function rotateSessionId() {
  return newSessionId();
}

// A STABLE per-browser tenant id that partitions this participant's lab world (tickets,
// notes, admin account, board) on the server. Unlike the session id, "New session" (↺) does
// NOT rotate it -- so a poisoned note survives the stage-3 rewind and stays visible to the
// support agent. Cleared only by clearing browser storage / using a different browser.
function getTenantId() {
  let id = localStorage.getItem("helix_tenant_id");
  if (!id) {
    id = "tnt-" + Math.random().toString(36).slice(2) + Date.now().toString(36);
    localStorage.setItem("helix_tenant_id", id);
  }
  return id;
}

async function postJSON(path, body) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`Request failed (${res.status})`);
  }
  return res.json();
}

export function sendChat(message) {
  return postJSON("/api/chat", {
    message,
    session_id: getSessionId(),
    tenant_id: getTenantId(),
  });
}

// Clear this session's server-side memory, then rotate to a fresh id.
export async function resetSession() {
  try {
    await postJSON("/api/reset", { session_id: getSessionId() });
  } catch {
    // Non-fatal: rotating the id below still starts a clean conversation.
  }
  return rotateSessionId();
}

export async function getHealth() {
  try {
    const res = await fetch(`${API_BASE}/api/health`);
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}
