"""Adapter لموقع قانون (qanoonsa.com).

الصفحات مبنية على WordPress: العنوان في h1، والمواد عناوين h2/h3 داخل
entry-content، وسطر "صدر بموجب..." قبل أول مادة، وسطر النشر في أم القرى بعد آخرها.
لا يعرض الموقع سجل تعديلات منفصلًا — النص المعروض هو النسخة الحالية فقط.

بعض الصفحات (مثل /p/516402/) ليست نصّ نظام بل نصّ قرار مجلس وزراء: لا تحوي
"المادة ..." بل بنودًا مرقّمة "أولا"/"ثانيا"/... تحت عنوان "يقرر ما يلي"،
وتُختم بتوقيع "رئيس مجلس الوزراء" وسطر "صدر في: ...". تُعامَل هذه كوثيقة
قرار (is_decision) بدل نظام إذا لم تحوِ الصفحة أي مادة.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from ..arabic_numbers import parse_article_label
from ..htmlmd import prose_to_markdown
from ..schema import Article, LawDocument
from .base import BaseAdapter, ParseError

_ARTICLE_HEADING_RE = re.compile(r"^المادة\s+(.+)$")
_CLAUSE_HEADING_RE = re.compile(
    r"^(أولا|ثانيا|ثالثا|رابعا|خامسا|سادسا|سابعا|ثامنا|تاسعا|عاشرا)ً?$"
)
_GAZETTE_RE = re.compile(r"ن?ُ?شر\s+في\s+عدد\s+جريدة\s+[أا]م\s+القرى")
_ISSUED_RE = re.compile(r"^صدر\s+بموجب\s*:?\s*(.+)$")
_ISSUED_DATE_RE = re.compile(r"^صدر\s+في\s*:?\s*(.+)$")
_SIGNER_RE = re.compile(r"^(رئيس|نائب رئيس)\s+مجلس\s+الوزراء$")


class QanoonsaAdapter(BaseAdapter):
    source = "qanoonsa"

    def parse(self, html: str, url: str) -> LawDocument:
        soup = BeautifulSoup(html, "lxml")
        # الـ h1 يقع داخل header.entry-header في قالب WordPress، فيُلتقط قبل حذف الأغلفة
        h1 = soup.find("h1")
        if h1 is None:
            raise ParseError("لم يُعثر على عنوان الصفحة (h1)")
        title = " ".join(h1.get_text(" ", strip=True).split())

        for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form"]):
            tag.decompose()

        content = soup.find(class_="entry-content") or soup.find("article") or soup.body or soup

        doc = LawDocument(title=title, source=self.source, source_url=url)
        clauses: list[Article] = []
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
                cm = _CLAUSE_HEADING_RE.match(text) if not m else None
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
                elif cm:
                    current = Article(number=cm.group(1), text="")
                    clauses.append(current)
                elif text.startswith("الباب"):
                    current_bab, current_fasl, current = text, None, None
                elif text.startswith("الفصل"):
                    current_fasl, current = text, None
                else:
                    current = None  # عنوان فرعي آخر لا يتبع نمط المواد أو البنود
            else:
                if _GAZETTE_RE.search(text):
                    doc.gazette_ref = text
                    continue
                if _ISSUED_DATE_RE.match(text):
                    doc.issued_date = _ISSUED_DATE_RE.match(text).group(1).strip()
                    continue
                if _SIGNER_RE.match(text):
                    continue
                if current is not None:
                    current.text += ("\n\n" if current.text else "") + text
                else:
                    intro.append(text)

        for line in intro:
            m = _ISSUED_RE.match(line)
            if m and doc.issued_by is None:
                doc.issued_by = m.group(1).strip().rstrip(".")

        if not doc.articles and clauses:
            doc.is_decision = True
            doc.articles = clauses

        if not doc.articles:
            # وثيقة غير مقسّمة لمواد (دليل/معايير/جدول): نحفظ متنها كـ Markdown
            # بدل رفعها كفشل، مع تجاهل السطور التي استُخرجت إلى حقول وصفية.
            skip = {"English"}
            if doc.gazette_ref:
                skip.add(doc.gazette_ref)
            for line in intro:
                if _ISSUED_RE.match(line):
                    skip.add(line)
            body = prose_to_markdown(content, skip=frozenset(skip))
            if not body.strip():
                raise ParseError("لم يُستخرج أي مادة أو بند أو متن من الصفحة")
            doc.body = body
        return doc
