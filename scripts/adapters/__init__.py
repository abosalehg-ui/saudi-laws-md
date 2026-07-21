from urllib.parse import urlparse

from .base import BaseAdapter, ParseError


def detect_source(url: str) -> str | None:
    host = (urlparse(url).hostname or "").lower()
    if host == "qanoonsa.com" or host.endswith(".qanoonsa.com"):
        return "qanoonsa"
    if host == "nezams.com" or host.endswith(".nezams.com"):
        return "nezams"
    return None


def get_adapter(source: str) -> BaseAdapter:
    from .nezams import NezamsAdapter
    from .qanoonsa import QanoonsaAdapter

    adapters = {"qanoonsa": QanoonsaAdapter, "nezams": NezamsAdapter}
    if source not in adapters:
        raise ValueError(f"مصدر غير معروف: {source}")
    return adapters[source]()
