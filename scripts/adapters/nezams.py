"""Adapter لموقع نظام (nezams.com).

البنية الحقيقية للصفحة بنيوية بالكامل (بخلاف ما افترضته النسخة الأولى):
- كل مادة داخل ``li.subject``: العنوان في ``h4`` ("المادة الأولى")، والنص في
  ``div.content``، ورقمها في ``span.numbe-s``، وأزرار المشاركة في
  ``div.subject-share`` (تُحذف).
- بلوك "تفاصيل النظام" جدول داخل ``div.content-sy``: كل صف تسمية/قيمة
  (تاريخ النظام، الإعتماد، تاريخ النشر، النفاد، التصنيف، التعديلات، الملحقات).
- ديباجة المرسوم الملكي في ``div.desc-ohter`` قبل قائمة المواد (لا تُستخرج).
- جمل التعديل ترد سطرًا مستقلًا داخل نص المادة بصيغة
  "تم بموجب المرسوم الملكي رقم (م/…) وتاريخ …هـ تعديل المادة (…)، لتكون بالنص الآتي:"
  وتُنقل إلى amendment_history مع إبقاء النص الجديد المقتبس في متن المادة.
- لا يعرض الموقع عناوين الأبواب/الفصول عناصر مستقلة (وردت فقط داخل جمل
  التعديل)، لذا يبقى حقل section فارغًا لهذا المصدر.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from ..arabic_numbers import parse_article_label
from ..schema import Article, LawDocument
from .base import BaseAdapter, ParseError

_ARTICLE_LABEL_RE = re.compile(r"^المادة\s+(.+)$")
_AMEND_LINE_RE = re.compile(
    r"^تم\s+(?:بموجب\s+(?:المرسوم\s+الملكي|قرار)\s.*?(?:تعديل|إلغاء|إضافة)"
    r"|(?:تعديل|إلغاء|إضافة)\s+هذه\s+المادة\s+بموجب).*$"
)
_FIELD_MAP = {
    "تاريخ النظام": "approval_date_hijri",
    "الاعتماد": "issued_by",
    "الإعتماد": "issued_by",
    "تاريخ النشر": "publish_date",
    "النفاذ": "status",
    "النفاد": "status",  # هكذا تُكتب التسمية فعليًا في الموقع
    "الحالة": "status",
    "التصنيف": "category",
    "الملحقات": "attachments",
    "التعديلات": "amendments",
}
_LIST_FIELDS = {"attachments", "amendments"}


def _clean_line(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" :،–—-")


class NezamsAdapter(BaseAdapter):
    source = "nezams"

    def parse(self, html: str, url: str) -> LawDocument:
        soup = BeautifulSoup(html, "lxml")

        h1 = soup.find("h1")
        if h1 is None:
            raise ParseError("لم يُعثر على عنوان الصفحة (h1)")
        title = " ".join(h1.get_text(" ", strip=True).split())

        doc = LawDocument(title=title, source=self.source, source_url=url)
        self._parse_details(soup, doc)

        items = soup.select("li.subject")
        if not items:
            raise ParseError("لم يُعثر على أي مادة في الصفحة (li.subject)")

        for li in items:
            heading = li.find(["h4", "h3", "h2"])
            content = li.find("div", class_="content")
            if heading is None or content is None:
                continue
            label_text = " ".join(heading.get_text(" ", strip=True).split())
            m = _ARTICLE_LABEL_RE.match(label_text)
            label = m.group(1).strip() if m else label_text

            lines = [
                " ".join(line.split())
                for line in content.get_text("\n", strip=True).split("\n")
            ]
            amendments: list[str] = []
            body: list[str] = []
            for line in lines:
                if not line:
                    continue
                if _AMEND_LINE_RE.match(line):
                    amendments.append(line)
                else:
                    body.append(line)

            number_int, is_bis = parse_article_label(label)
            doc.articles.append(
                Article(
                    number=label,
                    text="\n\n".join(body).strip(),
                    number_int=number_int,
                    is_bis=is_bis,
                    amendment_history=amendments,
                )
            )

        if not doc.articles:
            raise ParseError("لم يُستخرج أي مادة من الصفحة")
        return doc

    def _parse_details(self, soup: BeautifulSoup, doc: LawDocument) -> None:
        heading = soup.find(class_="heading-system-single")
        block = heading.find_next_sibling("div") if heading else None
        table = block.find("table") if block else soup.find("table")
        if table is None:
            return
        for row in table.find_all("tr"):
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                continue
            label = _clean_line(cells[0].get_text(" ", strip=True))
            field = _FIELD_MAP.get(label)
            if field is None:
                continue
            lines = [
                _clean_line(line)
                for line in cells[1].get_text("\n", strip=True).split("\n")
            ]
            lines = [line for line in lines if line]
            if not lines:
                continue
            if field in _LIST_FIELDS:
                if not getattr(doc, field):
                    setattr(doc, field, lines)
            elif getattr(doc, field) is None:
                setattr(doc, field, "؛ ".join(lines).rstrip("."))
