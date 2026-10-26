// Thin fetch wrapper. The session lives in an httpOnly cookie (invisible to JS);
// we only keep the CSRF token in memory and echo it on state-changing requests.

let csrfToken = null;

export function setCsrfToken(token) {
  csrfToken = token || null;
}

async function request(path, { method = "GET", body } = {}) {
  const headers = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  // Send CSRF header on anything that mutates state.
  if (method !== "GET" && csrfToken) headers["X-CSRF-Token"] = csrfToken;

  const res = await fetch(path, {
    method,
    headers,
    credentials: "include", // send/receive the session cookie
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  let data = null;
  const text = await res.text();
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = { detail: text };
    }
  }
  if (!res.ok) {
    const err = new Error(errorMessage(data, res.status));
    err.status = res.status;
    err.data = data;
    throw err;
  }
  return data;
}

// FastAPI returns `detail` as a string for HTTPException but as an array of
// {loc, msg, ...} objects for schema-validation failures (422). Flatten both so
// a rejected email reads as its policy message, not "[object Object]".
function errorMessage(data, status) {
  const detail = data && data.detail;
  if (typeof detail === "string" && detail) return detail;
  if (Array.isArray(detail) && detail.length) {
    const msgs = detail
      .map((d) => (typeof d === "string" ? d : d && d.msg))
      .filter(Boolean)
      // Pydantic prefixes custom ValueErrors with "Value error, ".
      .map((m) => m.replace(/^Value error,\s*/, ""));
    if (msgs.length) return [...new Set(msgs)].join(" · ");
  }
  return `Request failed (${status})`;
}

export const getLab = () => request("/api/lab");
export const getPolicy = () => request("/api/policy");
export const getScoreboard = () => request("/api/scoreboard");
export async function getMe() {
  const data = await request("/api/me");
  // Restore the CSRF token after a page refresh (cookie survived, token didn't).
  if (data && data.csrf_token) setCsrfToken(data.csrf_token);
  return data;
}

export const register = (email, username, password) =>
  request("/api/register", { method: "POST", body: { email, username, password } });

export async function login(identifier, password) {
  const data = await request("/api/login", {
    method: "POST",
    body: { identifier, password },
  });
  setCsrfToken(data.csrf_token);
  return data;
}

export async function logout() {
  try {
    await request("/api/logout", { method: "POST" });
  } finally {
    setCsrfToken(null);
  }
}

export const submitFlag = (flag) =>
  request("/api/submit-flag", { method: "POST", body: { flag } });
