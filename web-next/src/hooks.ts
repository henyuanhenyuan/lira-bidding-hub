import { useCallback, useEffect, useRef, useState } from "react";

export function useAsync<T>(loader: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await loader());
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, deps);

  useEffect(() => {
    void reload();
  }, [reload]);

  return { data, error, loading, reload };
}

const EVENT_KINDS = ["event", "approval", "ingest", "agent"];

export function useStreamBridge(): void {
  useEffect(() => {
    if (!("EventSource" in window)) return;
    const source = new EventSource("/api/stream");
    const listeners: [string, EventListener][] = EVENT_KINDS.map((kind) => [
      kind,
      () =>
        window.dispatchEvent(
          new CustomEvent("lira:stream", { detail: { kind } }),
        ),
    ]);
    listeners.forEach(([kind, fn]) => source.addEventListener(kind, fn));
    return () => {
      listeners.forEach(([kind, fn]) => source.removeEventListener(kind, fn));
      source.close();
    };
  }, []);
}

export function useStreamEvent(kinds: string[], handler: (kind: string) => void): void {
  const ref = useRef(handler);
  ref.current = handler;

  useEffect(() => {
    const listener = (event: Event) => {
      const kind = (event as CustomEvent<{ kind: string }>).detail?.kind;
      if (kind && kinds.includes(kind)) ref.current(kind);
    };
    window.addEventListener("lira:stream", listener as EventListener);
    return () => window.removeEventListener("lira:stream", listener as EventListener);
  }, [kinds.join("|")]);
}
