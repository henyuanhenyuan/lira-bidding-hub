import type { Guardrail, SuggestionStatus } from "./types";

export const TYPE_TEXT: Record<string, string> = {
  price_drop: "价格下降",
  price_rise: "价格上升",
  band_breach: "价格带击穿",
  source_switch: "采集源切换",
  title_change: "标题变化",
  image_change: "主图更换",
  review_spike: "评论异动",
};

export const ACTION_TEXT: Record<string, string> = {
  follow: "跟进调价",
  hold: "先观察",
  adjust_coupon: "投券对冲",
  join_promo: "报名活动",
  no_action: "不行动",
};

export const STATUS_TEXT: Record<SuggestionStatus, string> = {
  pending: "待提交",
  submitted: "待审批",
  approved: "已批准",
  executed: "已执行",
  accepted: "已采纳",
  rejected: "已驳回",
  cancelled: "已取消",
  holdout: "实验中",
};

export const GUARDRAIL_TEXT: Record<Guardrail, string> = {
  ok: "护栏通过",
  warning: "接近毛利下限",
  blocked: "毛利护栏拦截",
  unknown: "缺成本数据",
};

export const WF_TEXT: Record<string, string> = {
  submit: "提交",
  approve: "批准",
  reject: "驳回",
  execute: "执行",
  cancel: "取消",
};

export const ROLE_TEXT: Record<string, string> = {
  admin: "管理员",
  manager: "主管",
  member: "运营",
};

export const STEP_KIND_TEXT: Record<string, string> = {
  context: "上下文",
  plan: "计划",
  tool: "工具",
  analysis: "归因",
  verify: "校验",
  critic: "复核",
  fallback: "回退",
  suggestion: "建议",
  finalize: "完成",
  error: "错误",
};
