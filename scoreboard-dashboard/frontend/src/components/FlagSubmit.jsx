import { useState } from "react";
import { submitFlag } from "../api.js";

export default function FlagSubmit({ onResult }) {
  const [flag, setFlag] = useState("");
  const [result, setResult] = useState(null); // {correct, stage, points, already_captured}
  const [error, setError] = useState(null);
  const [checking, setChecking] = useState(false);

  async function onSubmit(e) {
    e.preventDefault();
    if (!flag.trim() || checking) return;
    setChecking(true);
    setResult(null);
    setError(null);
    try {
      const res = await submitFlag(flag.trim());
      setResult(res);
      if (res.correct && !res.already_captured) setFlag("");
      await onResult?.(); // refresh score/progress
    } catch (err) {
      setError(err.message || "Couldn’t reach the verifier.");
    } finally {
      setChecking(false);
    }
  }

  const borderColor =
    result?.correct
      ? "border-public"
      : result || error
        ? "border-breach"
        : "border-line";

  return (
    <section className="rounded-lg border border-line bg-panel p-5">
      <h2 className="eyebrow mb-3">Capture the flag</h2>
      <form onSubmit={onSubmit} className="flex flex-col gap-3">
        <input
          value={flag}
          onChange={(e) => setFlag(e.target.value)}
          placeholder="FLAG{...}"
          spellCheck={false}
          className={`w-full rounded-md border bg-panel2 px-3 py-2.5 font-mono text-sm text-fg outline-none transition-colors placeholder:text-muted/60 focus:border-public ${borderColor}`}
        />
        <button
          type="submit"
          disabled={checking || !flag.trim()}
          className="rounded-md bg-public/15 px-4 py-2.5 font-mono text-sm font-medium uppercase tracking-widest text-public transition-colors hover:bg-public/25 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {checking ? "Verifying…" : "Submit flag"}
        </button>
      </form>

      {result?.correct && result.already_captured && (
        <p className="mt-3 font-mono text-[12px] text-classified">
          ✓ Correct — stage {result.stage}, but you already captured this one (no extra points).
        </p>
      )}
      {result?.correct && !result.already_captured && (
        <p className="mt-3 font-mono text-[12px] text-public">
          ✓ Stage {result.stage} captured · +{result.points} points!
        </p>
      )}
      {result && !result.correct && (
        <p className="mt-3 font-mono text-[12px] text-breach">
          ✗ Not a valid flag. Keep working the chain.
        </p>
      )}
      {error && <p className="mt-3 font-mono text-[12px] text-breach">{error}</p>}
    </section>
  );
}
