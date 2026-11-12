"use client";
import { useEffect, useState } from "react";

export type Loadable<T> = { state: "loading" } | { state: "error"; message: string } | { state: "ready"; data: T };

/** Fetch a static API file with explicit loading / error states (no silent fallbacks). */
export function useJson<T>(path: string): Loadable<T> {
  const [v, setV] = useState<Loadable<T>>({ state: "loading" });
  useEffect(() => {
    let alive = true;
    fetch(path, { cache: "no-store" })
      .then(async (r) => {
        if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
        return (await r.json()) as T;
      })
      .then((data) => alive && setV({ state: "ready", data }))
      .catch((e: unknown) => alive && setV({ state: "error", message: e instanceof Error ? e.message : String(e) }));
    return () => {
      alive = false;
    };
  }, [path]);
  return v;
}
