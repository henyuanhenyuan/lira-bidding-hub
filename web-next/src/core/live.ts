import { useEffect, useRef, useState } from "react";

export type LiveKind = "agent" | "autopilot" | "event" | "approval" | string;

export interface LiveEvent {
  id: number;
  kind: LiveKind;
  at: string;
  data: Record<string, unknown>;
}

type Listener = (event: LiveEvent) => void;

let source: EventSource | null = null;
let listeners = new Set<Listener>();
let buffer: LiveEvent[] = [];
let status: "idle" | "open" | "closed" = "idle";
const statusListeners = new Set<(s: string) => void>();

function emitStatus(next: string) {
  status = next as typeof status;
  statusListeners.forEach((fn) => fn(next));
}

function ensureSource() {
  if (source && source.readyState !== EventSource.CLOSED) return;
  source = new EventSource("/api/stream");
  const kinds = ["agent", "autopilot", "event", "approval"];
  source.onopen = () => emitStatus("open");
  source.onerror = () => emitStatus("closed");
  kinds.forEach((kind) => {
    source!.addEventListener(kind, (raw) => {
      try {
        const payload = JSON.parse((raw as MessageEvent).data) as LiveEvent;
        buffer = [payload, ...buffer].slice(0, 120);
        listeners.forEach((fn) => fn(payload));
      } catch {
        /* ignore malformed frames */
      }
    });
  });
}

export function useLive(limit = 20) {
  const [events, setEvents] = useState<LiveEvent[]>([]);
  const [connected, setConnected] = useState(status === "open");
  const limitRef = useRef(limit);
  limitRef.current = limit;

  useEffect(() => {
    ensureSource();
    setEvents(buffer.slice(0, limitRef.current));

    const listener: Listener = (event) => {
      setEvents((prev) => [event, ...prev].slice(0, limitRef.current));
    };
    const onStatus = (s: string) => setConnected(s === "open");
    listeners.add(listener);
    statusListeners.add(onStatus);
    setConnected(status === "open");

    return () => {
      listeners.delete(listener);
      statusListeners.delete(onStatus);
    };
  }, []);

  return { events, connected };
}

export function useInterval(callback: () => void, ms: number | null) {
  const saved = useRef(callback);
  saved.current = callback;
  useEffect(() => {
    if (ms === null) return;
    const timer = window.setInterval(() => saved.current(), ms);
    return () => window.clearInterval(timer);
  }, [ms]);
}
