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
from ..htmlmd import clean_text, prose_to_markdown
from ..schema import CLAUSE_NAMES, Article, LawDocument
from .base import BaseAdapter, ParseError

_ARTICLE_HEADING_RE = re.compile(r"^المادة\s+(.+)$")
_CLAUSE_HEADING_RE = re.compile(rf"^({'|'.join(CLAUSE_NAMES)})ً?$")
_GAZETTE_RE = re.compile(r"ن?ُ?شر\s+في\s+عدد\s+جريدة\s+[أا]م\s+القرى")
_ISSUED_RE = re.compile(r"^صدر\s+بموجب\s*:?\s*(.+)$")
_ISSUED_DATE_RE = re.compile(r"^صدر\s+في\s*:?\s*(.+)$")
_SIGNER_RE = re.compile(r"^(رئيس|نائب رئيس)\s+مجلس\s+الوزراء$")


class _ArticleCollector:
    """آلة حالة تقطيع صفحة qanoonsa إلى مواد/بنود/متن.

    استُخرجت من ``parse`` لأنها كانت تحمل خمسة متغيّرات حالة متشابكة
    (المادة الجارية، الباب، الفصل، البنود، الديباجة) داخل حلقة واحدة —
    أصعب موضع في الملف على القراءة والتعديل. هنا كلٌّ منها صفة مُسمّاة،
    ومدخلات الحلقة سطران فقط: عنوان أو فقرة.
    """

    def __init__(self, doc: LawDocument):
        self.doc = doc
        self.clauses: list[Article] = []
        self.intro: list[str] = []
        # السطور التي هُضمت في حقول وصفية (تاريخ الإصدار، النشر)؛ تُستبعَد
        # من المتن النثري وإلا خرجت وثيقة «متنها سطر تاريخ» (191 حالة)
        self.extracted: list[str] = []
        self._current: Article | None = None
        self._bab: str | None = None
        self._fasl: str | None = None

    def feed_heading(self, text: str) -> None:
        article = _ARTICLE_HEADING_RE.match(text)
        clause = _CLAUSE_HEADING_RE.match(text) if not article else None
        if article:
            label = article.group(1).strip()
            number_int, is_bis = parse_article_label(label)
            section = " — ".join(s for s in (self._bab, self._fasl) if s) or None
            self._current = Article(
                number=label, text="", section=section,
                number_int=number_int, is_bis=is_bis,
            )
            self.doc.articles.append(self._current)
        elif clause:
            self._current = Article(number=clause.group(1), text="")
            self.clauses.append(self._current)
        elif text.startswith("الباب"):
            self._bab, self._fasl, self._current = text, None, None
        elif text.startswith("الفصل"):
            self._fasl, self._current = text, None
        else:
            self._current = None  # عنوان فرعي آخر لا يتبع نمط المواد أو البنود

    def feed_paragraph(self, text: str) -> None:
        if _GAZETTE_RE.search(text):
            self.doc.gazette_ref = text
            self.extracted.append(text)
            return
        issued_date = _ISSUED_DATE_RE.match(text)
        if issued_date:
            self.doc.issued_date = issued_date.group(1).strip()
            self.extracted.append(text)
            return
        if _SIGNER_RE.match(text):
            return
        if self._current is not None:
            self._current.text += ("\n\n" if self._current.text else "") + text
        else:
            self.intro.append(text)


class QanoonsaAdapter(BaseAdapter):
    source = "qanoonsa"
    hosts = ("qanoonsa.com",)
    sitemap_index = "https://qanoonsa.com/wp-sitemap.xml"

    def parse(self, html: str, url: str) -> LawDocument:
        soup = BeautifulSoup(html, "lxml")
        # الـ h1 يقع داخل header.entry-header في قالب WordPress، فيُلتقط قبل حذف الأغلفة
        h1 = soup.find("h1")
        if h1 is None:
            raise ParseError("لم يُعثر على عنوان الصفحة (h1)")
        title = clean_text(h1.get_text(" ", strip=True))

        for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form"]):
            tag.decompose()

        content = soup.find(class_="entry-content") or soup.find("article") or soup.body or soup

        doc = LawDocument(title=title, source=self.source, source_url=url)
        collector = _ArticleCollector(doc)
        for el in content.find_all(["h2", "h3", "h4", "p", "li", "blockquote"]):
            # عنصر متداخل داخل li/blockquote يُلتقط نصه كاملًا ضمن حاويه؛
            # معالجته ثانيةً هنا تُكرّر النص في المتن (نمط مطابق لتجاهل
            # عناصر الجدول في htmlmd.prose_to_markdown)
            if el.find_parent(["li", "blockquote"]) is not None:
                continue
            text = clean_text(el.get_text(" ", strip=True))
            if not text:
                continue
            if el.name in ("h2", "h3", "h4"):
                collector.feed_heading(text)
            else:
                collector.feed_paragraph(text)
        clauses, intro, extracted_lines = collector.clauses, collector.intro, collector.extracted

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
            skip = {"English", *extracted_lines}
            for line in intro:
                if _ISSUED_RE.match(line):
                    skip.add(line)
            body = prose_to_markdown(content, skip=frozenset(skip))
            if not body.strip():
                raise ParseError("لم يُستخرج أي مادة أو بند أو متن من الصفحة")
            doc.body = body
        return doc
