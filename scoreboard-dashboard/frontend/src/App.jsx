import { useCallback, useEffect, useState } from "react";
import AuthPanel from "./components/AuthPanel.jsx";
import LabBriefing from "./components/LabBriefing.jsx";
import Progress from "./components/Progress.jsx";
import FlagSubmit from "./components/FlagSubmit.jsx";
import Scoreboard from "./components/Scoreboard.jsx";
import { getMe, logout } from "./api.js";

export default function App() {
  const [me, setMe] = useState(null); // {username, score, captured_stages, total_points}
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState("dashboard"); // "dashboard" | "scoreboard"

  const refreshMe = useCallback(async () => {
    try {
      const data = await getMe();
      setMe(data);
      return data;
    } catch {
      setMe(null);
      return null;
    }
  }, []);

  useEffect(() => {
    refreshMe().finally(() => setLoading(false));
  }, [refreshMe]);

  async function onLoggedIn() {
    await refreshMe();
    setView("dashboard");
  }

  async function onLogout() {
    await logout();
    setMe(null);
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-[1180px] flex-col px-5 py-6 lg:px-8">
      <header className="mb-6 flex flex-col gap-3 border-b border-line pb-5 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="eyebrow mb-1.5">Dhruv-Gohil // security lab · scoreboard</p>
          <h1 className="font-display text-2xl font-bold tracking-tight text-fg sm:text-3xl">
            HELIX<span className="text-breach">·</span>CHAIN
            <span className="ml-2 align-middle font-mono text-sm font-medium uppercase tracking-[0.2em] text-muted">
              scoreboard
            </span>
          </h1>
          <p className="mt-1.5 max-w-xl text-sm text-muted">
            Capture the four flags in the HELIXCHAIN lab, submit them here for points, and
            climb the ranking. Points scale with each stage's difficulty.
          </p>
        </div>

        {me && (
          <div className="flex items-center gap-3 font-mono text-[12px]">
            <span className="text-muted">
              <span className="text-public">●</span> {me.username} · {me.score} pts
            </span>
            <button
              onClick={onLogout}
              className="rounded-md border border-line px-3 py-1.5 uppercase tracking-widest text-muted transition-colors hover:border-breach hover:text-breach"
            >
              Sign out
            </button>
          </div>
        )}
      </header>

      {loading ? (
        <div className="flex flex-1 items-center justify-center font-mono text-sm text-muted">
          Loading…
        </div>
      ) : !me ? (
        <main className="grid flex-1 grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_400px]">
          <LabBriefing />
          <AuthPanel onLoggedIn={onLoggedIn} />
        </main>
      ) : (
        <>
          <nav className="mb-5 flex gap-2 font-mono text-[12px]">
            <TabButton active={view === "dashboard"} onClick={() => setView("dashboard")}>
              Dashboard
            </TabButton>
            <TabButton active={view === "scoreboard"} onClick={() => setView("scoreboard")}>
              Scoreboard
            </TabButton>
          </nav>

          {view === "dashboard" ? (
            <main className="grid flex-1 grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_400px]">
              <LabBriefing />
              <div className="flex flex-col gap-6">
                <Progress me={me} />
                <FlagSubmit onResult={refreshMe} />
              </div>
            </main>
          ) : (
            <main className="flex-1">
              <Scoreboard currentUser={me.username} />
            </main>
          )}
        </>
      )}

      <footer className="mt-8 border-t border-line pt-4 font-mono text-[10.5px] leading-relaxed text-muted">
      </footer>
    </div>
  );
}

function TabButton({ active, onClick, children }) {
  return (
    <button
      onClick={onClick}
      className={`rounded-md border px-4 py-2 uppercase tracking-widest transition-colors ${
        active
          ? "border-public bg-public/10 text-public"
          : "border-line text-muted hover:border-fg hover:text-fg"
      }`}
    >
      {children}
    </button>
  );
}
