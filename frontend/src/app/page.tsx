import { AskPanel } from "@/components/AskPanel";
import { HealthBadge } from "@/components/HealthBadge";
import { SearchPanel } from "@/components/SearchPanel";

export default function Home() {
  return (
    <div className="min-h-full bg-neutral-950 text-neutral-100">
      <div className="mx-auto max-w-3xl px-6 py-16">
        <header className="mb-10">
          <div className="mb-4 flex items-center justify-between">
            <h1 className="text-2xl font-semibold tracking-tight">Veritas</h1>
            <HealthBadge />
          </div>
          <p className="text-sm leading-relaxed text-neutral-400">
            A self-verifying RAG engine. Hybrid retrieval (BM25 + dense vector search,
            fused with RRF) feeds an answer stage that re-embeds and checks every
            claim against the specific source chunk it cites — unsupported claims are
            stripped, and if too many fail, the answer is withheld entirely rather
            than shown degraded.
          </p>
        </header>

        <main className="space-y-6">
          <AskPanel />
          <SearchPanel />
        </main>

        <footer className="mt-10 text-xs text-neutral-600">
          API and worker run separately on Render; this UI is a standalone static
          client.
        </footer>
      </div>
    </div>
  );
}
