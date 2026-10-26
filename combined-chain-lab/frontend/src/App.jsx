import { useEffect, useState } from "react";
import ChatWindow from "./components/ChatWindow.jsx";
import ArchitecturePanel from "./components/ArchitecturePanel.jsx";
import ObjectivesPanel from "./components/ObjectivesPanel.jsx";
import { getHealth, resetSession } from "./api.js";

export default function App() {
  const [active, setActive] = useState(false);
  const [breached, setBreached] = useState(false);
  const [health, setHealth] = useState(null);
  const [epoch, setEpoch] = useState(0); // bump to reset the chat transcript
  // Attack-surface reveal: `unlocked` grows cumulatively as requests reach deeper nodes and
  // persists for the session; `activePath` is just the most recent request's path (it pulses).
  // "you" + "frontend" are always present (every message hits the public router).
  const [unlocked, setUnlocked] = useState(() => new Set(["you", "frontend"]));
  const [activePath, setActivePath] = useState([]);

  useEffect(() => {
    getHealth().then(setHealth);
  }, []);

  function onReached(reached) {
    const path = reached && reached.length ? reached : ["you", "frontend"];
    setActivePath(path);
    setUnlocked((prev) => new Set([...prev, "you", "frontend", ...path]));
  }

  async function onNewSession() {
    await resetSession();
    setBreached(false);
    // The map resets with the session (the 'rewind' technique clears server-side memory too).
    setUnlocked(new Set(["you", "frontend"]));
    setActivePath([]);
    setEpoch((e) => e + 1);
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-[1240px] flex-col px-5 py-6 lg:px-8">
      {/* Header */}
      <header className="mb-6 flex flex-col gap-3 border-b border-line pb-5 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="eyebrow mb-1.5">Dhruv-Gohil // security lab · MCP01 + MCP05 + MCP07</p>
          <h1 className="font-display text-2xl font-700 tracking-tight text-fg sm:text-3xl">
            HELIX<span className="text-breach">·</span>CHAIN
          </h1>
          <p className="mt-1.5 max-w-xl text-sm text-muted">
            A single dual-LLM MCP kill-chain: <span className="text-fg">authenticate → leak →
            escalate to support → take over admin → RCE</span>. Each stage's access unlocks the
            next, so the four flags must fall in order. The models behave — the bugs are in the
            MCP server's authorization and its shell sink. Ask me to <span className="text-fg">list
            the tools</span> to get oriented.
          </p>
        </div>
        <div className="flex items-center gap-2 font-mono text-[11px]">
          <span
            className={`h-2 w-2 rounded-full ${
              health ? "bg-public shadow-[0_0_8px_#3DD8C4]" : "bg-breach"
            }`}
          />
          <span className="text-muted">
            {health
              ? `backend up · mcp ${health.mcp_reachable ? "linked" : "down"} · ${health.frontend_model}`
              : "backend unreachable"}
          </span>
        </div>
      </header>

      {/* Main: chat + intel sidebar */}
      <main className="grid flex-1 grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
        <div className="min-w-0 min-h-[560px] lg:h-[calc(100vh-190px)]">
          <ChatWindow
            key={epoch}
            onActivity={setActive}
            onLeak={() => setBreached(true)}
            onReached={onReached}
            onNewSession={onNewSession}
          />
        </div>

        <aside className="flex flex-col gap-6 lg:h-[calc(100vh-190px)] lg:overflow-y-auto lg:pr-1 scroll-slim">
          <ArchitecturePanel
            active={active}
            breached={breached}
            unlocked={unlocked}
            activePath={activePath}
          />
          <ObjectivesPanel />
        </aside>
      </main>
    </div>
  );
}
