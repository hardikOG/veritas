"use client";

import { useEffect, useState } from "react";
import { getHealth, type HealthResponse } from "@/lib/api";

type Status = "checking" | "up" | "down";

export function HealthBadge() {
  const [status, setStatus] = useState<Status>("checking");
  const [health, setHealth] = useState<HealthResponse | null>(null);

  useEffect(() => {
    let cancelled = false;
    getHealth()
      .then((result) => {
        if (cancelled) return;
        setHealth(result);
        setStatus(result.status === "healthy" ? "up" : "down");
      })
      .catch(() => {
        if (!cancelled) setStatus("down");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const dotClass =
    status === "up"
      ? "bg-emerald-400"
      : status === "down"
        ? "bg-red-400"
        : "bg-neutral-500 animate-pulse";

  const label =
    status === "checking"
      ? "Checking API…"
      : status === "up"
        ? `API live · db ${health?.database} · redis ${health?.redis}`
        : "API unreachable";

  return (
    <div className="flex items-center gap-2 rounded-full border border-neutral-800 bg-neutral-900/60 px-3 py-1 text-xs text-neutral-400">
      <span className={`h-2 w-2 rounded-full ${dotClass}`} />
      {label}
    </div>
  );
}
