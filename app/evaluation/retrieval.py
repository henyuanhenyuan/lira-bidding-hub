"""检索评测：把 recall@k / MRR 接到真实 docs.search 链路上。

金标语料在 `golden/rag_corpus.jsonl`，查询在 `golden/rag_cases.jsonl`。
相关性用关键词覆盖判定：检索到的切片包含查询期望关键词即算命中。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .. import docs as doc_store, embeddings, retrieval_service
from . import metrics

GOLDEN_DIR = Path(__file__).with_name("golden")
CORPUS_PATH = GOLDEN_DIR / "rag_corpus.jsonl"
CASES_PATH = GOLDEN_DIR / "rag_cases.jsonl"


@dataclass(frozen=True)
class RetrievalCase:
    query: str
    keywords: tuple[str, ...]
    segment: str


@dataclass(frozen=True)
class CorpusDoc:
    title: str
    content: str
    category: str = "policy"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    items = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if text:
                items.append(json.loads(text))
    return items


def load_corpus(path: Path | None = None) -> list[CorpusDoc]:
    return [
        CorpusDoc(
            title=item["title"], content=item["content"],
            category=item.get("category", "policy"),
        )
        for item in _read_jsonl(path or CORPUS_PATH)
    ]


def load_cases(path: Path | None = None) -> list[RetrievalCase]:
    return [
        RetrievalCase(
            query=item["query"],
            keywords=tuple(item.get("expected_keywords") or ()),
            segment=item.get("segment", "policy"),
        )
        for item in _read_jsonl(path or CASES_PATH)
    ]


def seed_corpus(conn, corpus: list[CorpusDoc] | None = None) -> int:
    """按标题去重写入评测语料；embedding provider 变化时重建，保证可检索。"""
    corpus = corpus or load_corpus()
    _, active = embeddings.embed("probe")
    rows = {
        row["title"]: row["id"]
        for row in conn.execute(
            "SELECT id, title FROM doc WHERE source = 'eval:rag'"
        ).fetchall()
    }
    added = 0
    for item in corpus:
        doc_id = rows.get(item.title)
        if doc_id:
            providers = {
                row["embed_provider"]
                for row in conn.execute(
                    "SELECT DISTINCT embed_provider FROM doc_chunk WHERE doc_id = ?",
                    (doc_id,),
                ).fetchall()
            }
            if providers == {active}:
                continue
            doc_store.delete_doc(conn, doc_id)
        doc_store.create_doc(
            conn, title=item.title, content=item.content,
            source="eval:rag", category=item.category,
        )
        added += 1
    return added


def _hit(keywords: tuple[str, ...], content: str) -> bool:
    return any(keyword in content for keyword in keywords)


def evaluate(
    conn,
    cases: list[RetrievalCase] | None = None,
    k: int = 5,
    search=None,
) -> dict[str, Any]:
    """对每条查询跑真实检索，计算关键词召回率与 MRR。"""
    cases = cases or load_cases()
    search = search or (
        lambda query, limit: retrieval_service.search_docs(
            conn, query, limit, rewrite_llm=False
        )
    )
    per_case: list[dict[str, Any]] = []
    recalls: list[float] = []
    ranks: list[float] = []

    for case in cases:
        chunks = search(case.query, k)
        contents = [str(item.get("content") or "") for item in chunks]
        matched = [
            keyword for keyword in case.keywords
            if any(keyword in content for content in contents)
        ]
        recall = round(len(matched) / len(case.keywords), 4) if case.keywords else 0.0
        rank = 0.0
        for index, content in enumerate(contents, start=1):
            if _hit(case.keywords, content):
                rank = round(1 / index, 4)
                break
        recalls.append(recall)
        ranks.append(rank)
        per_case.append(
            {
                "query": case.query, "segment": case.segment,
                "recall": recall, "mrr": rank,
                "matched_keywords": matched,
                "missed_keywords": [kw for kw in case.keywords if kw not in matched],
            }
        )

    return {
        "cases": len(cases),
        "k": k,
        "recall_at_k": metrics.mean(recalls),
        "mrr": metrics.mean(ranks),
        "per_case": per_case,
    }
