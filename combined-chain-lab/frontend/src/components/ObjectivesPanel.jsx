// The four staged objectives. Each shows only a brief, non-revealing hint — participants work
// out which tool/technique applies. Flag submission is handled by the separate scoreboard.

const STAGES = [
  {
    n: 1,
    title: "Information disclosure",
    detail: "Make the service disclose more about itself than it should.",
  },
  {
    n: 2,
    title: "Escalate to support",
    detail: "Trade what leaked for a higher trust level than you signed up with (it needs exact format).",
  },
  {
    n: 3,
    title: "Take over admin",
    detail: "Get the system to hand you its most privileged account via it's ticket.",
  },
  {
    n: 4,
    title: "Remote code execution",
    detail: "Tools → RCE → root flag.",
  },
];

export default function ObjectivesPanel() {
  return (
    <section className="rounded-lg border border-line bg-panel p-5">
      <div className="mb-3 flex items-baseline justify-between">
        <h2 className="eyebrow">Objectives</h2>
      </div>
      <ol className="flex flex-col gap-3">
        {STAGES.map((s) => (
          <li key={s.n}>
            <p className="text-sm text-fg">
              <span className="font-mono text-muted">{s.n}.</span> {s.title}
            </p>
            <p className="mt-0.5 text-[11.5px] leading-relaxed text-muted">{s.detail}</p>
          </li>
        ))}
      </ol>
    </section>
  );
}
