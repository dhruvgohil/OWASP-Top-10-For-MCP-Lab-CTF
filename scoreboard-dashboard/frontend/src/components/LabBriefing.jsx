import { useEffect, useState } from "react";
import { getLab } from "../api.js";

export default function LabBriefing() {
  const [lab, setLab] = useState(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    getLab().then(setLab).catch(() => setError(true));
  }, []);

  return (
    <section className="rounded-lg border border-line bg-panel p-6">
      <p className="eyebrow mb-2">The lab · MCP01 + MCP05 + MCP07</p>
      <h2 className="font-display text-xl font-semibold tracking-tight text-fg">
        {lab ? lab.name : "HELIXCHAIN"} — sequential MCP kill-chain
      </h2>

      <p className="mt-3 text-sm leading-relaxed text-muted">
        {lab
          ? lab.summary
          : "A single dual-LLM MCP kill-chain: authenticate → leak → escalate → take over admin → RCE."}
      </p>

      {/* Stage / points table */}
      <div className="mt-5 overflow-hidden rounded-md border border-line">
        <table className="w-full border-collapse text-left font-mono text-[12px]">
          <thead>
            <tr className="bg-panel2 text-muted">
              <th className="px-3 py-2 font-medium uppercase tracking-widest">Stage</th>
              <th className="px-3 py-2 font-medium uppercase tracking-widest">Objective</th>
              <th className="px-3 py-2 text-right font-medium uppercase tracking-widest">Points</th>
            </tr>
          </thead>
          <tbody>
            {(lab?.stages ?? []).map((s) => (
              <tr key={s.stage} className="border-t border-line">
                <td className="px-3 py-2 text-muted">#{s.stage}</td>
                <td className="px-3 py-2 text-fg">{s.name}</td>
                <td className="px-3 py-2 text-right text-classified">{s.points}</td>
              </tr>
            ))}
            {lab && (
              <tr className="border-t border-line bg-panel2/60">
                <td className="px-3 py-2 text-muted" colSpan={2}>
                  Total available
                </td>
                <td className="px-3 py-2 text-right text-public">{lab.total_points}</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <a
        href={lab?.url || "http://10.13.254.254:3100"}
        target="_blank"
        rel="noopener noreferrer"
        className="mt-5 inline-flex items-center gap-2 rounded-md border border-public/50 bg-public/10 px-4 py-2.5 font-mono text-sm font-medium uppercase tracking-widest text-public transition-colors hover:bg-public/20"
      >
        Open the lab ↗
        <span className="font-normal normal-case tracking-normal text-public/70">
          {lab?.url || "http://10.13.254.254:3100"}
        </span>
      </a>

      {error && (
        <p className="mt-3 font-mono text-[11px] text-breach">
          Couldn’t reach the backend for live lab details — showing defaults.
        </p>
      )}
    </section>
  );
}
