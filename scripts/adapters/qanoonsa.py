"""Adapter لموقع قانون (qanoonsa.com).

الصفحات مبنية على WordPress: العنوان في h1، والمواد عناوين h2/h3 داخل
entry-content، وسطر "صدر بموجب..." قبل أول مادة، وسطر النشر في أم القرى بعد آخرها.
لا يعرض الموقع سجل تعديلات منفصلًا — النص المعروض هو النسخة الحالية فقط.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from ..arabic_numbers import parse_article_label
from ..schema import Article, LawDocument
from .base import BaseAdapter, ParseError

_ARTICLE_HEADING_RE = re.compile(r"^المادة\s+(.+)$")
_GAZETTE_RE = re.compile(r"ن?ُ?شر\s+في\s+عدد\s+جريدة\s+[أا]م\s+القرى")
_ISSUED_RE = re.compile(r"^صدر\s+بموجب\s*:?\s*(.+)$")
_SECTION_PREFIX_RE = re.compile(r"^(الباب|الفصل)\s+\S+")


class QanoonsaAdapter(BaseAdapter):
    source = "qanoonsa"

    def parse(self, html: str, url: str) -> LawDocument:
        soup = BeautifulSoup(html, "lxml")
        for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form"]):
            tag.decompose()

        h1 = soup.find("h1")
        if h1 is None:
            raise ParseError("لم يُعثر على عنوان الصفحة (h1)")
        title = " ".join(h1.get_text(" ", strip=True).split())

        content = soup.find(class_="entry-content") or soup.find("article") or soup.body or soup

        doc = LawDocument(title=title, source=self.source, source_url=url)
        current: Article | None = None
        current_bab: str | None = None
        current_fasl: str | None = None
        intro: list[str] = []

        for el in content.find_all(["h2", "h3", "h4", "p", "li", "blockquote"]):
            text = " ".join(el.get_text(" ", strip=True).split())
            if not text:
                continue
            if el.name in ("h2", "h3", "h4"):
                m = _ARTICLE_HEADING_RE.match(text)
                if m:
                    label = m.group(1).strip()
                    number_int, is_bis = parse_article_label(label)
                    section = " — ".join(s for s in (current_bab, current_fasl) if s) or None
                    current = Article(
                        number=label,
                        text="",
                        section=section,
                        number_int=number_int,
                        is_bis=is_bis,
                    )
                    doc.articles.append(current)
                elif text.startswith("الباب"):
                    current_bab, current_fasl, current = text, None, None
                elif text.startswith("الفصل"):
                    current_fasl, current = text, None
                else:
                    current = None  # عنوان فرعي آخر لا يتبع نمط المواد
            else:
                if _GAZETTE_RE.search(text):
                    doc.gazette_ref = text
                    continue
                if current is not None:
                    current.text += ("\n\n" if current.text else "") + text
                else:
                    intro.append(text)

        for line in intro:
            m = _ISSUED_RE.match(line)
            if m and doc.issued_by is None:
                doc.issued_by = m.group(1).strip().rstrip(".")

        if not doc.articles:
            raise ParseError("لم يُستخرج أي مادة من الصفحة")
        return doc
