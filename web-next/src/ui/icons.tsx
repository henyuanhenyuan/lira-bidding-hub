const PATHS: Record<string, string> = {
  control: "M4 13h4l2.5-7 3 12 2.5-5H20",
  bidding: "M12 3v4m0 10v4M5 12H3m18 0h-2M6.3 6.3 4.9 4.9m14.2 1.4 1.4-1.4M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8Z",
  agents: "M8 8h8v8H8zM12 3v5m0 8v5M3 12h5m8 0h5",
  sources: "M4 7c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3Zm0 5c0 1.7 3.6 3 8 3s8-1.3 8-3M4 7v10c0 1.7 3.6 3 8 3s8-1.3 8-3V7",
  eval: "M4 19V5m0 14h16M8 15l3-4 3 2 4-6",
  settings: "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm8-3a8 8 0 0 1-.2 1.8l2 1.5-2 3.4-2.3-.9a8 8 0 0 1-3 1.7L14 22h-4l-.5-2.5a8 8 0 0 1-3-1.7l-2.3.9-2-3.4 2-1.5A8 8 0 0 1 4 12",
  screen: "M3 5h18v11H3zM8 20h8m-4-4v4",
  logout: "M15 12H3m12 0-4-4m4 4-4 4M13 4h6v16h-6",
  chevron: "m9 6 6 6-6 6",
  refresh: "M20 11a8 8 0 1 0-.7 4.4M20 5v6h-6",
  check: "m5 13 4 4L19 7",
  close: "M6 6l12 12M18 6 6 18",
  upload: "M12 16V4m0 0L7 9m5-5 5 5M4 17v3h16v-3",
  play: "M7 5l12 7-12 7z",
  bell: "M6 9a6 6 0 1 1 12 0c0 5 2 6 2 6H4s2-1 2-6Zm4 9a2 2 0 0 0 4 0",
  plus: "M12 5v14M5 12h14",
  spark: "M12 3v3m0 12v3M5.6 5.6l2.1 2.1m8.6 8.6 2.1 2.1M3 12h3m12 0h3M5.6 18.4l2.1-2.1m8.6-8.6 2.1-2.1",
  arrow: "M5 12h14m-6-6 6 6-6 6",
  filter: "M4 6h16M7 12h10m-7 6h4",
  globe: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Zm-9-9h18M12 3c2.5 2.4 3.8 5.4 3.8 9s-1.3 6.6-3.8 9c-2.5-2.4-3.8-5.4-3.8-9S9.5 5.4 12 3Z",
  cpu: "M9 9h6v6H9zM4 9h5M4 15h5m6-6h5m-5 6h5M9 4v5m6-5v5M9 15v5m6-5v5",
  clock: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Zm0-13v5l3 2",
  plug: "M9 3v6m6-6v6M7 9h10v3a5 5 0 0 1-10 0zM12 17v4",
};

export function Icon({ name, size = 18, className = "" }: { name: string; size?: number; className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <path d={PATHS[name] || PATHS.spark} />
    </svg>
  );
}
