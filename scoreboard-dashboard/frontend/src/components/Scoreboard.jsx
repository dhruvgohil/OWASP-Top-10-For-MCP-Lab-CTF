import { useEffect, useState } from "react";
import { getScoreboard } from "../api.js";

export default function Scoreboard({ currentUser }) {
  const [rows, setRows] = useState(null);
  const [error, setError] = useState(false);

  async function load() {
    try {
      setRows(await getScoreboard());
    } catch {
      setError(true);
    }
  }

  useEffect(() => {
    load();
    const id = setInterval(load, 15000); // light auto-refresh
    return () => clearInterval(id);
  }, []);

  function medal(rank) {
    if (rank === 1) return "text-classified";
    if (rank === 2) return "text-fg";
    if (rank === 3) return "text-public";
    return "text-muted";
  }

  return (
    <section className="rounded-lg border border-line bg-panel p-6">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="eyebrow">Scoreboard · ranked high → low</h2>
        <span className="font-mono text-[11px] text-muted">auto-refresh 15s</span>
      </div>

      {error && (
        <p className="font-mono text-[12px] text-breach">Couldn’t load the scoreboard.</p>
      )}

      {rows && rows.length === 0 && (
        <p className="font-mono text-[12px] text-muted">No players yet. Be the first to score.</p>
      )}

      {rows && rows.length > 0 && (
        <div className="overflow-x-auto scroll-slim">
          <table className="w-full border-collapse text-left font-mono text-[13px]">
            <thead>
              <tr className="text-muted">
                <th className="px-3 py-2 font-medium uppercase tracking-widest">#</th>
                <th className="px-3 py-2 font-medium uppercase tracking-widest">Player</th>
                <th className="px-3 py-2 text-center font-medium uppercase tracking-widest">Flags</th>
                <th className="px-3 py-2 text-right font-medium uppercase tracking-widest">Score</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const isMe = r.username === currentUser;
                return (
                  <tr
                    key={r.username}
                    className={`border-t border-line ${isMe ? "bg-public/5" : ""}`}
                  >
                    <td className={`px-3 py-2.5 font-semibold ${medal(r.rank)}`}>{r.rank}</td>
                    <td className="px-3 py-2.5">
                      <span className={isMe ? "text-public" : "text-fg"}>{r.username}</span>
                      {isMe && (
                        <span className="ml-2 rounded bg-public/15 px-1.5 py-0.5 text-[10px] uppercase tracking-widest text-public">
                          you
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2.5 text-center text-muted">{r.flags_captured}/4</td>
                    <td className="px-3 py-2.5 text-right font-semibold text-classified">{r.score}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
