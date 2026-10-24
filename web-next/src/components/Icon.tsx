const PATHS: Record<string, string> = {
  overview: "M4 13h6V4H4v9zm0 7h6v-4H4v4zm10 0h6V11h-6v9zm0-16v5h6V4h-6z",
  events: "M4 18V9m5 9V5m5 13v-6m5 6V8",
  suggestions:
    "M9 18h6M10 21h4M12 3a6 6 0 0 0-4 10c1 1 1 2 1 3h6c0-1 0-2 1-3a6 6 0 0 0-4-10z",
  approvals: "M9 12l2 2 4-4M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0z",
  competitors: "M4 6h16M4 12h16M4 18h10",
  cases: "M4 5h16v14H4zM8 9h8M8 13h5",
  ask: "M12 3v3m0 12v3M3 12h3m12 0h3M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8z",
  import: "M12 3v12m0 0l4-4m-4 4l-4-4M4 17v3h16v-3",
  collection: "M3 12h4l2-6 4 12 2-6h6",
  trace: "M5 19a2 2 0 1 0 0-4 2 2 0 0 0 0 4zM19 9a2 2 0 1 0 0-4 2 2 0 0 0 0 4zM7 17h5a5 5 0 0 0 5-5V9",
  docs: "M6 4h9l3 3v13H6zM9 9h6M9 13h6",
  skills: "M12 3l2.5 5 5.5.8-4 3.9.9 5.5-4.9-2.6-4.9 2.6.9-5.5-4-3.9 5.5-.8z",
  eval: "M4 19V5m0 14h16M7 15l3-4 3 2 4-6",
  outcome: "M12 8v4l3 2M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0z",
  admin: "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 21a8 8 0 0 1 16 0",
  logout: "M15 12H3m0 0l4-4m-4 4l4 4M13 4h6v16h-6",
};

export default function Icon({ name, size = 18 }: { name: string; size?: number }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={PATHS[name] ?? PATHS.overview} />
    </svg>
  );
}
