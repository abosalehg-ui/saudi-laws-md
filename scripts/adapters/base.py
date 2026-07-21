from __future__ import annotations

from abc import ABC, abstractmethod

from ..schema import LawDocument


class ParseError(Exception):
    """الصفحة لا تطابق البنية المتوقعة للمصدر."""


class BaseAdapter(ABC):
    """الواجهة المشتركة: كل adapter يحوّل HTML مصدره إلى LawDocument موحد."""

    source: str

    @abstractmethod
    def parse(self, html: str, url: str) -> LawDocument:
        ...
