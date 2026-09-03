"""
缓存键生成器

提供 URL 标准化与哈希计算，用于视频缓存去重。原源码随缓存子系统重构丢失，
此处按 tests/test_video_key_generator 的契约重建：
- normalize_url(url)  -> scheme/netloc 小写、其余不变
- compute_url_hash(url) -> sha256 hex（长度 64）
"""

import hashlib
from urllib.parse import urlparse, urlunparse


class CacheKeyGenerator:
    """生成稳定、可去重的缓存键。"""

    @staticmethod
    def normalize_url(url: str) -> str:
        """标准化 URL：小写 scheme 与 netloc，路径/查询/片段保持原样。"""
        if not url:
            return ""
        p = urlparse(url)
        return urlunparse(
            (p.scheme.lower(), p.netloc.lower(), p.path, p.params, p.query, p.fragment)
        )

    @classmethod
    def compute_url_hash(cls, url: str) -> str:
        """返回 URL 的 sha256 十六进制哈希（64 字符），相同 URL 稳定一致。"""
        return hashlib.sha256(cls.normalize_url(url).encode("utf-8")).hexdigest()
