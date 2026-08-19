"use client";

import { useState, type FormEvent } from "react";
import { ApiError, search, type SearchResult } from "@/lib/api";

export function SearchPanel() {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<SearchResult[] | null>(null);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!query.trim() || loading) return;
    setLoading(true);
    setError(null);
    setResults(null);
    try {
      const response = await search(query.trim());
      setResults(response.results);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="rounded-xl border border-neutral-800 bg-neutral-900/40 p-6">
      <h2 className="text-lg font-medium text-neutral-100">Search</h2>
      <p className="mt-1 text-sm text-neutral-400">
        Hybrid retrieval — BM25 keyword search and dense vector search, fused with
        Reciprocal Rank Fusion.
      </p>

      <form onSubmit={onSubmit} className="mt-4 flex gap-2">
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search the ingested documents…"
          className="flex-1 rounded-lg border border-neutral-700 bg-neutral-950 px-3 py-2 text-sm text-neutral-100 placeholder:text-neutral-500 focus:border-neutral-500 focus:outline-none"
        />
        <button
          type="submit"
          disabled={loading || !query.trim()}
          className="rounded-lg bg-neutral-100 px-4 py-2 text-sm font-medium text-neutral-900 transition hover:bg-white disabled:cursor-not-allowed disabled:opacity-40"
        >
          {loading ? "Searching…" : "Search"}
        </button>
      </form>

      {error && <p className="mt-4 text-sm text-red-400">{error}</p>}

      {results && results.length === 0 && (
        <p className="mt-4 text-sm text-neutral-500">No matching chunks.</p>
      )}

      {results && results.length > 0 && (
        <ul className="mt-5 space-y-3">
          {results.map((result) => (
            <li
              key={result.chunk_id}
              className="rounded-lg border border-neutral-800 bg-neutral-950 px-4 py-3"
            >
              <p className="text-sm text-neutral-200">{result.content}</p>
              <div className="mt-2 flex flex-wrap gap-3 text-xs text-neutral-500">
                <span>score: {result.score.toFixed(3)}</span>
                {result.bm25_rank !== null && <span>bm25 rank: {result.bm25_rank}</span>}
                {result.dense_rank !== null && <span>dense rank: {result.dense_rank}</span>}
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
