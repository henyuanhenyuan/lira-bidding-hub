export function formatTs(value?: string | null, withYear = false): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", {
    year: withYear ? "numeric" : undefined,
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function timeAgo(value?: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const diff = Date.now() - date.getTime();
  const future = diff < 0;
  const minutes = Math.abs(diff) / 60000;
  if (minutes < 1) return "刚刚";
  const text =
    minutes < 60
      ? `${Math.round(minutes)} 分钟`
      : minutes < 1440
        ? `${Math.round(minutes / 60)} 小时`
        : `${Math.round(minutes / 1440)} 天`;
  return future ? `${text}后` : `${text}前`;
}

export function money(value?: number | null): string {
  if (value === null || value === undefined) return "—";
  return `¥${value.toFixed(2)}`;
}

export function percent(value?: number | null, digits = 0): string {
  if (value === null || value === undefined) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}
