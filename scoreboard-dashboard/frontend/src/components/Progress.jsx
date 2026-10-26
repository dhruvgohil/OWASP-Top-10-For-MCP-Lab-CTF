const STAGES = [
  { stage: 1, label: "Information disclosure" },
  { stage: 2, label: "Signer privilege escalation" },
  { stage: 3, label: "Admin BOLA / confused deputy" },
  { stage: 4, label: "Remote code execution" },
];

export default function Progress({ me }) {
  const captured = new Set(me?.captured_stages ?? []);
  const count = captured.size;

  return (
    <section className="rounded-lg border border-line bg-panel p-5">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="eyebrow">Your progress</h2>
        <span className="font-mono text-[12px] text-muted">
          <span className="text-public">{me?.score ?? 0}</span> / {me?.total_points ?? 0} pts ·{" "}
          {count}/4 flags
        </span>
      </div>

      <ul className="flex flex-col gap-2">
        {STAGES.map((s) => {
          const done = captured.has(s.stage);
          return (
            <li
              key={s.stage}
              className={`flex items-center gap-3 rounded-md border px-3 py-2.5 font-mono text-[12px] ${
                done ? "border-public/40 bg-public/5" : "border-line bg-panel2"
              }`}
            >
              <span
                className={`flex h-5 w-5 items-center justify-center rounded-full text-[11px] ${
                  done ? "bg-public/20 text-public" : "bg-line/40 text-muted"
                }`}
              >
                {done ? "✓" : s.stage}
              </span>
              <span className={done ? "text-fg" : "text-muted"}>{s.label}</span>
              <span className={`ml-auto ${done ? "text-public" : "text-muted/60"}`}>
                {done ? "captured" : "locked"}
              </span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
