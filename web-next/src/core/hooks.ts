import { useCallback, useEffect, useRef, useState } from "react";

export function useAsync<T>(loader: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const alive = useRef(true);
  const $loader = useRef(loader);
  $loader.current = loader;

  const reload = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const value = await $loader.current();
      if (alive.current) setData(value);
    } catch (err) {
      if (alive.current) {
        setError(err instanceof Error ? err.message : "加载失败");
      }
    } finally {
      if (alive.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    alive.current = true;
    void reload();
    return () => {
      alive.current = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return { data, error, loading, reload };
}

export function useToast() {
  const [message, setMessage] = useState("");
  const timer = useRef<number | undefined>(undefined);
  const show = useCallback((text: string) => {
    setMessage(text);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setMessage(""), 3200);
  }, []);
  return { message, show };
}
