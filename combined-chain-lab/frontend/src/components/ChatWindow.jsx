import { useEffect, useRef, useState } from "react";
import { sendChat } from "../api.js";

const GREETING = {
  role: "assistant",
  text: "Hi, I'm the HelixSupport Assistant. I can sign you up, log you in, open and track support tickets, and get them resolved through our automation team. New here? Ask me to \"list the available tools\" and I'll show you what the support system can do at your current access level.",
};

function containsFlag(text) {
  return /FLAG\{[^}]*\}/i.test(text || "");
}

function Bubble({ msg }) {
  const isUser = msg.role === "user";
  const leaked = !isUser && containsFlag(msg.text);

  return (
    <div className={`flex min-w-0 ${isUser ? "justify-end" : "justify-start"}`}>
      <div className="min-w-0 max-w-[80%]">
        <div
          className={`mb-1 font-mono text-[10px] uppercase tracking-widest ${
            isUser ? "text-right text-muted" : leaked ? "text-breach" : "text-public"
          }`}
        >
          {isUser ? "you" : leaked ? "helixsupport // leak" : "helixsupport"}
        </div>
        <div
          className={`overflow-x-auto whitespace-pre-wrap break-words [overflow-wrap:anywhere] rounded-lg border px-3.5 py-2.5 text-sm leading-relaxed ${
            isUser
              ? "border-line bg-panel2 text-fg"
              : leaked
                ? "border-breach/60 bg-breach/10 text-fg shadow-[0_0_24px_-8px_#FF5C5C]"
                : "border-line bg-panel text-fg"
          }`}
        >
          {msg.text}
        </div>
      </div>
    </div>
  );
}

export default function ChatWindow({ onActivity, onLeak, onReached, onNewSession }) {
  const [messages, setMessages] = useState([GREETING]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, loading]);

  async function onSend(e) {
    e.preventDefault();
    const text = input.trim();
    if (!text || loading) return;

    setMessages((m) => [...m, { role: "user", text }]);
    setInput("");
    setLoading(true);
    onActivity?.(true);

    try {
      const { reply, reached } = await sendChat(text);
      setMessages((m) => [...m, { role: "assistant", text: reply }]);
      // Reveal the attack-surface nodes this request actually reached (cumulative in App).
      onReached?.(reached || []);
      if (containsFlag(reply)) onLeak?.();
    } catch {
      setMessages((m) => [
        ...m,
        { role: "assistant", text: "Connection to the assistant failed. Is the backend up?" },
      ]);
    } finally {
      setLoading(false);
      onActivity?.(false);
    }
  }

  return (
    <section className="flex h-full min-h-0 flex-col rounded-lg border border-line bg-panel">
      <header className="flex items-center justify-between border-b border-line px-5 py-3">
        <div className="flex items-center gap-2.5">
          <span className="h-2 w-2 rounded-full bg-public shadow-[0_0_8px_#3DD8C4]" />
          <span className="font-display text-sm font-600">HelixSupport Chat</span>
          <span className="eyebrow">public channel</span>
        </div>
        <button
          onClick={() => {
            onNewSession?.();
            setMessages([GREETING]);
          }}
          className="font-mono text-[10px] uppercase tracking-widest text-muted transition-colors hover:text-public"
          title="Clear this session's memory and start fresh (the 'rewind' technique)"
        >
          ↺ new session
        </button>
      </header>

      <div ref={scrollRef} className="scroll-slim flex-1 space-y-4 overflow-y-auto px-5 py-5">
        {messages.map((msg, i) => (
          <Bubble key={i} msg={msg} />
        ))}
        {loading && (
          <div className="flex items-center gap-2 font-mono text-[11px] text-muted">
            <span className="inline-flex gap-1">
              <span className="h-1.5 w-1.5 animate-blink rounded-full bg-public" />
            </span>
            routing through the automation agent…
          </div>
        )}
      </div>

      <form onSubmit={onSend} className="border-t border-line p-3">
        <div className="flex items-end gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) onSend(e);
            }}
            rows={2}
            placeholder="Message HelixSupport…  (Enter to send, Shift+Enter for newline)"
            className="scroll-slim min-h-[44px] flex-1 resize-none rounded-md border border-line bg-panel2 px-3 py-2 text-sm text-fg outline-none placeholder:text-muted/60 focus:border-public"
          />
          <button
            type="submit"
            disabled={loading || !input.trim()}
            className="h-[44px] rounded-md bg-public/15 px-5 font-mono text-sm font-500 uppercase tracking-widest text-public transition-colors hover:bg-public/25 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Send
          </button>
        </div>
      </form>
    </section>
  );
}
