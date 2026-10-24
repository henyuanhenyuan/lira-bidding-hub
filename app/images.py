from __future__ import annotations

import hashlib
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

# CDN 常见的尺寸/裁剪/压缩参数，不改变图片内容本身
_NOISE_PARAMS = {
    "w", "h", "width", "height", "quality", "q", "format", "fmt", "fit",
    "resize", "crop", "thumbnail", "thumb", "size", "scale", "dpr",
}
_NOISE_PREFIXES = ("x-oss-", "x-cos-", "image", "img", "aliyun", "tfs")


def _is_noise(key: str) -> bool:
    k = key.lower()
    return k in _NOISE_PARAMS or any(k.startswith(p) for p in _NOISE_PREFIXES)


def normalize_url(url: str) -> str:
    """去掉 CDN 变换参数，避免同一张图换尺寸就判定为主图更换。"""
    raw = (url or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    if not parsed.scheme:
        return raw
    kept = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
            if not _is_noise(k)]
    return urlunparse((
        parsed.scheme.lower(),
        parsed.netloc.lower(),
        parsed.path.rstrip("/"),
        "",
        urlencode(kept),
        "",
    ))


def fingerprint(url: str) -> str:
    norm = normalize_url(url)
    if not norm:
        return ""
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:32]


def fp_of(observation: dict) -> str:
    """优先用采集端给的图片哈希，否则对 URL 归一化后取指纹。"""
    explicit = (observation.get("main_image_hash") or "").strip()
    if explicit:
        return explicit
    return fingerprint(observation.get("main_image_url") or "")
