export function money(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `¥${value.toLocaleString("zh-CN", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}`;
}

export function pct(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

export function signedPct(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const text = `${Math.abs(value * 100).toFixed(digits)}%`;
  return value > 0 ? `+${text}` : value < 0 ? `-${text}` : "0.0%";
}

export function num(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toLocaleString("zh-CN");
}

export function compact(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  if (Math.abs(value) >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (Math.abs(value) >= 1_000) return `${(value / 1_000).toFixed(1)}k`;
  return String(value);
}

export function timeAgo(iso: string | null | undefined): string {
  if (!iso) return "—";
  const ts = new Date(iso).getTime();
  if (Number.isNaN(ts)) return "—";
  const diff = Date.now() - ts;
  const min = Math.floor(diff / 60000);
  if (min < 1) return "刚刚";
  if (min < 60) return `${min} 分钟前`;
  const hour = Math.floor(min / 60);
  if (hour < 24) return `${hour} 小时前`;
  const day = Math.floor(hour / 24);
  if (day < 30) return `${day} 天前`;
  return new Date(iso).toLocaleDateString("zh-CN");
}

export function clock(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function shortDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("zh-CN", { month: "2-digit", day: "2-digit" });
}

export const SEVERITY_TEXT: Record<string, string> = {
  L1: "轻微",
  L2: "关注",
  L3: "高危",
};

export const ACTION_TEXT: Record<string, string> = {
  adjust_price: "调价",
  hold: "维持",
  raise_price: "提价",
  match_band: "贴合区间",
  undercut: "跟降",
  follow: "跟随",
  match: "对标",
  manual_review: "人工复核",
};

export const STATUS_TEXT: Record<string, string> = {
  pending: "待处理",
  submitted: "待审批",
  approved: "已批准",
  rejected: "已驳回",
  executed: "已执行",
  auto_closed: "自动归档",
  accepted: "已采纳",
  cancelled: "已撤回",
  exception: "待确认",
  succeeded: "成功",
  failed: "失败",
  running: "运行中",
  ok: "正常",
  error: "异常",
};

export const STRATEGY_TEXT: Record<string, string> = {
  follow: "跟随竞品",
  undercut: "低于竞品",
  match_band: "贴合区间",
  hold: "锁定价格",
};

export function severityClass(sev: string | null | undefined): string {
  if (sev === "L3") return "sev l3";
  if (sev === "L2") return "sev l2";
  return "sev l1";
}
