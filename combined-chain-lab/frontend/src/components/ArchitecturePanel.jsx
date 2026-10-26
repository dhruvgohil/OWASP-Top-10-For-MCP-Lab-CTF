// A live pivot map of the attack surface.
//   - Nodes are revealed progressively: only hops a request has actually reached are drawn, and
//     they persist cumulatively for the session (App owns the `unlocked` set). A fresh session
//     collapses the map back to You -> Frontend LLM.
//   - active (a request is in flight): the visible connectors pulse and a data mote flows down.
//   - activePath: the nodes the most recent request touched, given a subtle accent.
//   - breached (a secret / flag has come back to the UI): the MCP-tier path glows red.

// The full pivot chain, in order. Each request lights up a prefix of this chain; `key` matches
// the node keys the backend reports in /api/chat `reached`.
const NODES = [
  {
    key: "you",
    tier: "user",
    title: "You",
    subtitle: "Where your input enters. Everything you send is untrusted.",
    tag: "public",
  },
  {
    key: "frontend",
    tier: "public",
    title: "HelixSupport Assistant — Frontend LLM",
    subtitle: "The public-facing router. No tools of its own — it forwards you deeper.",
    tag: "no tools",
  },
  {
    key: "backend",
    tier: "classified",
    title: "Support Automation Agent — Backend LLM",
    subtitle:
      "An internal automation agent with real tools. It acts on what it's asked to do.",
    tag: "mcp client",
  },
  {
    key: "mcp",
    tier: "tool",
    title: "Support MCP Server",
    subtitle:
      "Exposes tools gated by trust tier — public / user / support / admin. Not every gate is as strict as it looks.",
    tag: "tiered",
  },
  {
    key: "signer",
    tier: "tool",
    title: "Session Signer (internal :9003)",
    subtitle:
      "An internal service that issues session tokens. Reachable only if you know where it lives.",
    tag: "internal",
  },
  {
    key: "board",
    tier: "tool",
    title: "Project Board (admin only)",
    subtitle:
      "Admin-only. It does something with what you give it that goes beyond just storing it.",
    tag: "admin only",
  },
];

function Connector({ active, breached }) {
  return (
    <div className="relative mx-auto h-8 w-px bg-line">
      {active && (
        <>
          <div
            className={`absolute inset-0 ${
              breached ? "bg-breach" : "bg-public"
            } animate-pulseline`}
          />
          <div
            className={`absolute left-1/2 top-0 h-2 w-2 -translate-x-1/2 rounded-full animate-flow ${
              breached ? "bg-breach shadow-[0_0_10px_#FF5C5C]" : "bg-public shadow-[0_0_10px_#3DD8C4]"
            }`}
          />
        </>
      )}
    </div>
  );
}

function Node({ tier, title, subtitle, tag, breached, onPath }) {
  const accent =
    tier === "public"
      ? "text-public border-public/40"
      : tier === "classified"
        ? "text-classified border-classified/40"
        : tier === "tool"
          ? "text-muted border-line"
          : "text-fg border-line";

  const glow =
    breached && tier === "tool"
      ? "border-breach/70 shadow-[0_0_24px_-6px_#FF5C5C]"
      : onPath
        ? "shadow-[0_0_18px_-8px_#3DD8C4]"
        : "";

  return (
    <div className={`rounded-md border bg-panel2/80 px-3.5 py-3 ${accent} ${glow} transition-shadow`}>
      <div className="flex items-center justify-between gap-2">
        <span className="font-display text-sm font-600 text-fg">{title}</span>
        {tag && (
          <span
            className={`font-mono text-[10px] uppercase tracking-widest ${
              breached && tier === "tool" ? "text-breach" : "opacity-80"
            }`}
          >
            {breached && tier === "tool" ? "compromised" : tag}
          </span>
        )}
      </div>
      <p className="mt-1 font-mono text-[11px] leading-relaxed text-muted">{subtitle}</p>
    </div>
  );
}

export default function ArchitecturePanel({ active, breached, unlocked, activePath }) {
  // Guard against an undefined set on first paint (App seeds it, but stay defensive).
  const revealed = unlocked instanceof Set ? unlocked : new Set(["you", "frontend"]);
  const path = Array.isArray(activePath) ? activePath : [];
  const visible = NODES.filter((n) => revealed.has(n.key));

  return (
    <section className="rounded-lg border border-line bg-panel p-5">
      <div className="mb-4 flex items-baseline justify-between">
        <h2 className="eyebrow">Attack surface</h2>
        <span
          className={`font-mono text-[10px] uppercase tracking-widest ${
            breached ? "text-breach animate-blink" : active ? "text-public" : "text-muted"
          }`}
        >
          {breached ? "● secret returned" : active ? "● routing" : "○ idle"}
        </span>
      </div>

      {visible.map((node, i) => (
        <div key={node.key}>
          {i > 0 && <Connector active={active} breached={breached} />}
          <Node
            tier={node.tier}
            title={node.title}
            subtitle={node.subtitle}
            tag={node.tag}
            breached={breached}
            onPath={path.includes(node.key)}
          />
        </div>
      ))}

      <div className="mt-5 border-t border-line pt-4">
        <p className="mb-2 eyebrow">Trust tiers</p>
        <div className="grid grid-cols-2 gap-1.5 font-mono text-[10.5px] text-muted">
          <span><span className="text-public">●</span> public — health / signup / sign-in</span>
          <span><span className="text-classified">●</span> user — tickets / notes</span>
          <span><span className="text-breach">●</span> support — customer &amp; account management</span>
          <span><span className="text-fg">●</span> admin — internal tooling</span>
        </div>
      </div>

      <p className="mt-4 border-t border-line pt-4 font-mono text-[11px] leading-relaxed text-muted">
        <span className="text-breach">Objective:</span> the models themselves won't misbehave —
        the weaknesses are in what the tools trust and how they handle your input. Chain the
        stages in order.
      </p>
    </section>
  );
}
