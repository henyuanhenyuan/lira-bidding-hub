"""检索服务：查询改写 + 多跳 + 融合，并为每一步打 trace。

底层仍是 `docs.search_docs`（向量 + 关键词 + RRF + 父子块），
这里只在外层做改写、多跳和可观测，便于单独评测。
"""

from __future__ import annotations

import os
import re
from typing import Any, Callable

from . import agent, docs as doc_store, llm, tracing

RRF_K = 60
STOPWORDS = ("的", "了", "是", "在", "吗", "呢", "什么", "如何", "怎么", "哪些", "为什么", "和", "与")


def _clean(query: str) -> str:
    return re.sub(r"[？?。！!，,；;：:\s]+", " ", query).strip()


def heuristic_variants(query: str) -> list[str]:
    base = _clean(query)
    if not base:
        return []
    trimmed = base
    for word in STOPWORDS:
        trimmed = trimmed.replace(word, " ")
    trimmed = re.sub(r"\s+", " ", trimmed).strip()
    variants: list[str] = []
    if trimmed and trimmed != base:
        variants.append(trimmed)
    # 关键词式变体：取最长的两个片段
    pieces = [piece for piece in trimmed.split(" ") if len(piece) >= 2]
    if len(pieces) >= 2:
        variants.append(" ".join(pieces[:2]))
    return [item for item in dict.fromkeys(variants) if item][:2]


def llm_variants(query: str) -> list[str]:
    if os.getenv("LIRA_QUERY_REWRITE", "on") == "off":
        return []
    if not agent._llm_available():
        return []
    response = llm.complete(
        [
            {
                "role": "system",
                "content": (
                    "把用户问题改写成 2 条更适合知识库检索的查询，"
                    "保留专有名词与数字，每行一条，不要编号，不要解释。"
                ),
            },
            {"role": "user", "content": query},
        ],
        kind="query_rewrite",
        max_tokens=60,
    )
    if response is None:
        return []
    lines = [line.strip(" -•\t") for line in response.text.splitlines()]
    return [line for line in lines if 2 <= len(line) <= 60][:2]


def rewrite_query(query: str, use_llm: bool = True) -> list[str]:
    with tracing.span("retrieval.rewrite", kind="retrieval", query=query[:80]):
        variants = heuristic_variants(query)
        if use_llm:
            variants.extend(llm_variants(query))
        return list(dict.fromkeys(variants))[:3]


def _fuse(
    ranked: list[list[dict[str, Any]]],
    weights: list[float] | None = None,
) -> list[dict[str, Any]]:
    """加权 RRF：原查询权重最高，变体次之，二跳最低。"""
    weights = weights or [1.0] * len(ranked)
    scores: dict[str, float] = {}
    items: dict[str, dict[str, Any]] = {}
    for index, result_list in enumerate(ranked):
        weight = weights[index] if index < len(weights) else 1.0
        for rank, item in enumerate(result_list):
            chunk_id = str(item.get("id"))
            if not chunk_id:
                continue
            scores[chunk_id] = (
                scores.get(chunk_id, 0.0) + weight / (RRF_K + rank + 1)
            )
            items.setdefault(chunk_id, item)
    ordered = sorted(scores, key=lambda key: -scores[key])
    fused = []
    for chunk_id in ordered:
        item = dict(items[chunk_id])
        item["score"] = round(scores[chunk_id], 4)
        fused.append(item)
    return fused


def search_docs(
    conn,
    query: str,
    limit: int = 3,
    *,
    rewrite: bool = True,
    rewrite_llm: bool = True,
    multi_hop: bool = True,
    search: Callable[[str, int], list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    """改写 → 多路召回 → RRF 融合；必要时用首条结果做一次二跳。"""
    search = search or (lambda text, size: doc_store.search_docs(conn, text, size))
    queries = [query] + (rewrite_query(query, use_llm=rewrite_llm) if rewrite else [])

    with tracing.span("retrieval.search", kind="retrieval", queries=len(queries)):
        pool = max(limit * 2, 10)
        ranked = [search(text, pool) for text in queries if text.strip()]
        fused = _fuse(
            [items for items in ranked if items],
            weights=[2.0] + [1.0] * (len(ranked) - 1),
        )

        if multi_hop and fused:
            # 首条结果与问题重合度低时，用其标题/开头再检索一次
            head = fused[0]
            title = str(head.get("doc_title") or "")
            snippet = str(head.get("content") or "")[:40]
            if title and snippet:
                with tracing.span("retrieval.hop2", kind="retrieval", seed=head.get("id")):
                    second = search(f"{title} {snippet}", pool)
                    if second:
                        fused = _fuse([fused, second], weights=[1.0, 0.6])

    return fused[:limit]
