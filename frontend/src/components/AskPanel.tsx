"use client";

import { useState, type FormEvent } from "react";
import { ApiError, ask, type AskResponse } from "@/lib/api";

export function AskPanel() {
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AskResponse | null>(null);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!question.trim() || loading) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      setResult(await ask(question.trim()));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="rounded-xl border border-neutral-800 bg-neutral-900/40 p-6">
      <h2 className="text-lg font-medium text-neutral-100">Ask</h2>
      <p className="mt-1 text-sm text-neutral-400">
        Every claim in the answer is verified against its cited source chunk. If too
        many claims fail verification, Veritas refuses to answer rather than guess.
      </p>

      <form onSubmit={onSubmit} className="mt-4 flex gap-2">
        <input
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="Ask a question about the ingested documents…"
          className="flex-1 rounded-lg border border-neutral-700 bg-neutral-950 px-3 py-2 text-sm text-neutral-100 placeholder:text-neutral-500 focus:border-neutral-500 focus:outline-none"
        />
        <button
          type="submit"
          disabled={loading || !question.trim()}
          className="rounded-lg bg-neutral-100 px-4 py-2 text-sm font-medium text-neutral-900 transition hover:bg-white disabled:cursor-not-allowed disabled:opacity-40"
        >
          {loading ? "Asking…" : "Ask"}
        </button>
      </form>

      {error && <p className="mt-4 text-sm text-red-400">{error}</p>}

      {result && (
        <div className="mt-5 space-y-3">
          {result.refused ? (
            <div className="rounded-lg border border-amber-900/60 bg-amber-950/30 px-4 py-3 text-sm text-amber-300">
              <span className="font-medium">Refused.</span> Not enough of the answer
              was supported by the cited sources to show it with confidence.
            </div>
          ) : (
            <div className="rounded-lg border border-neutral-800 bg-neutral-950 px-4 py-3 text-sm leading-relaxed text-neutral-200">
              {result.answer}
            </div>
          )}

          <div className="flex flex-wrap items-center gap-3 text-xs text-neutral-500">
            <span>confidence: {(result.confidence * 100).toFixed(0)}%</span>
            <span>latency: {result.latency_ms}ms</span>
            <span>citations: {result.citations.length}</span>
          </div>

          {result.citations.length > 0 && (
            <ul className="space-y-1 text-xs text-neutral-500">
              {result.citations.map((citation) => (
                <li key={citation.chunk_id} className="font-mono">
                  chunk {citation.chunk_id.slice(0, 8)} · similarity{" "}
                  {citation.similarity.toFixed(2)}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}
