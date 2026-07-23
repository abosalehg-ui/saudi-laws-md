"""سجل المصادر: نقطة التسجيل الوحيدة لكل adapters.

إضافة مصدر ثالث = صنف adapter جديد يعلن (source, hosts, sitemap_index) ثم
إدراجه في ``ADAPTERS`` — وتُشتق منه تلقائيًا detect_source والسماح بالمضيف
وفهرس الخرائط (discover.py)، بلا تعديل عدة مواضع متفرقة.
"""

from __future__ import annotations

from urllib.parse import urlparse

from .base import BaseAdapter
from .nezams import NezamsAdapter
from .qanoonsa import QanoonsaAdapter

ADAPTERS: tuple[type[BaseAdapter], ...] = (QanoonsaAdapter, NezamsAdapter)
_BY_SOURCE: dict[str, type[BaseAdapter]] = {a.source: a for a in ADAPTERS}


def _host_matches(host: str, allowed: str) -> bool:
    return host == allowed or host.endswith("." + allowed)


def detect_source(url: str) -> str | None:
    host = (urlparse(url).hostname or "").lower()
    for adapter in ADAPTERS:
        if any(_host_matches(host, h) for h in adapter.hosts):
            return adapter.source
    return None


def get_adapter(source: str) -> BaseAdapter:
    try:
        return _BY_SOURCE[source]()
    except KeyError:
        raise ValueError(f"مصدر غير معروف: {source}") from None
