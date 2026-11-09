import { useCallback, useEffect, useRef, useState } from "react";

export function useAsync<T>(
  loader: () => Promise<T>,
  deps: unknown[] = [],
  options: { pollMs?: number | null } = {},
): { data: T | null; error: string | null; loading: boolean; reload: () => void } {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const alive = useRef(true);
  const loaderRef = useRef(loader);
  loaderRef.current = loader;

  const run = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true);
    try {
      const value = await loaderRef.current();
      if (alive.current) {
        setData(value);
        setError(null);
      }
    } catch (err) {
      if (alive.current) setError(err instanceof Error ? err.message : String(err));
    } finally {
      if (alive.current && !quiet) setLoading(false);
    }
  }, []);

  useEffect(() => {
    alive.current = true;
    void run();
    return () => {
      alive.current = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  const pollMs = options.pollMs;
  useEffect(() => {
    if (!pollMs) return;
    const timer = window.setInterval(() => void run(true), pollMs);
    return () => window.clearInterval(timer);
  }, [pollMs, run]);

  return { data, error, loading, reload: () => void run(true) };
}

export function useToast() {
  const [message, setMessage] = useState<{ text: string; tone: "ok" | "warn" | "error" } | null>(null);
  const timer = useRef<number | null>(null);

  const push = useCallback((text: string, tone: "ok" | "warn" | "error" = "ok") => {
    setMessage({ text, tone });
    if (timer.current) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setMessage(null), 3200);
  }, []);

  useEffect(
    () => () => {
      if (timer.current) window.clearTimeout(timer.current);
    },
    [],
  );

  return { message, push };
}
