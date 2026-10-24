from __future__ import annotations

import hashlib
import logging
import math
import os

import httpx

from . import config

log = logging.getLogger(__name__)

EMBED_MODEL = os.getenv("LIRA_EMBED_MODEL", "bge-m3")
HASH_DIM = 256


def _normalize(v: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / norm for x in v]


def _hash_embed(text: str, dim: int = HASH_DIM) -> list[float]:
    """离线兜底：字符 n-gram 哈希。没有模型也能检索，只是语义精度差。"""
    vec = [0.0] * dim
    chars = list(text or "")
    grams = chars[:] + ["".join(chars[i : i + 2]) for i in range(len(chars) - 1)]
    for g in grams:
        h = hashlib.md5(g.encode("utf-8")).digest()
        idx = int.from_bytes(h[:4], "big") % dim
        sign = 1.0 if h[4] % 2 == 0 else -1.0
        vec[idx] += sign
    return _normalize(vec)


def ollama_available() -> bool:
    try:
        return httpx.get(f"{config.OLLAMA_URL}/api/tags", timeout=1.0).status_code == 200
    except Exception:
        return False


def embed(text: str) -> tuple[list[float], str]:
    """返回 (向量, 提供方)。Ollama 不可用时自动退回哈希向量。"""
    if config.LLM_ENABLED != "off":
        try:
            r = httpx.post(
                f"{config.OLLAMA_URL}/api/embed",
                json={"model": EMBED_MODEL, "input": text},
                timeout=10.0,
            )
            if r.status_code == 200:
                emb = r.json().get("embeddings", [[]])[0]
                if emb:
                    return _normalize(emb), f"ollama:{EMBED_MODEL}"
        except Exception as exc:
            log.warning("embedding fallback to hash: %s", exc)
    return _hash_embed(text), "hash:256"
