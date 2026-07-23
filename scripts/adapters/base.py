from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from ..schema import LawDocument


class ParseError(Exception):
    """الصفحة لا تطابق البنية المتوقعة للمصدر."""


class BaseAdapter(ABC):
    """الواجهة المشتركة: كل adapter يحوّل HTML مصدره إلى LawDocument موحد.

    كل adapter يعلن بياناته الوصفية (المصدر، المضيفات، خريطة الموقع) هنا
    كصفات صنف؛ فتُشتق منها كل الجداول (detect_source، السماح بالمضيف،
    فهرس الخرائط) من نقطة تسجيل واحدة — إضافة مصدر ثالث = صنف واحد جديد.
    """

    source: ClassVar[str]
    hosts: ClassVar[tuple[str, ...]] = ()
    sitemap_index: ClassVar[str] = ""

    @abstractmethod
    def parse(self, html: str, url: str) -> LawDocument:
        ...
