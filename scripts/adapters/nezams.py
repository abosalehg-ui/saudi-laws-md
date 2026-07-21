"""Adapter لموقع نظام (nezams.com).

الصفحة نص شبه متصل يحتاج تنظيفًا قبل التقسيم:
- كتلة أرقام متسلسلة في المقدمة (بقايا widget بحث JS) تُحذف.
- نمط واجهة متكرر بعد كل مادة ("رقم المادة X مشاركة المادة رابط المادة نص
  المادة النص والرابط") يُحذف.
- بلوك "تفاصيل النظام" (بين العنوان وأول مادة) يُفكك إلى حقول وصفية.
- المتن يُقسم بنمط "المادة <ترقيم عربي>"، وجمل التعديل تُنقل إلى
  amendment_history لكل مادة بدل حذفها.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from ..arabic_numbers import ARTICLE_LABEL_RE, parse_article_label
from ..schema import Article, LawDocument
from .base import BaseAdapter, ParseError

_DIGIT_DUMP_RE = re.compile(r"(?:[0-9٠-٩]\s*){15,}")
_UI_NOISE_RE = re.compile(
    r"رقم\s+المادة\s*:?\s*[0-9٠-٩]+\s+مشاركة\s+المادة\s+رابط\s+المادة"
    r"\s+نص\s+المادة(?:\s+النص\s+والرابط)?"
)
_AMEND_RE = re.compile(
    r"(?:تم\s+تعديل\s+هذه\s+المادة\s+بموجب[^.]*\."
    r"|تم\s+بموجب\s+المرسوم\s+الملكي[^.]*?تعديل[^.]*\.)"
)
_SECTION_ORD = (
    r"(?:الأول|الاول|الثاني|الثالث|الرابع|الخامس|السادس|السابع"
    r"|الثامن|التاسع|العاشر|الحادي)(?:\s+عشر)?"
)
_SECTION_RE = re.compile(r"(?:الباب|الفصل)\s+" + _SECTION_ORD)

_DETAILS_HEADER = "تفاصيل النظام"
_FIELD_MAP = {
    "تاريخ النظام": "approval_date_hijri",
    "الاعتماد": "issued_by",
    "تاريخ النشر": "publish_date",
    "النفاذ": "status",
    "الحالة": "status",
    "التصنيف": "category",
    "الملحقات": "attachments",
    "التعديلات": "amendments",
}
_LIST_FIELDS = {"attachments", "amendments"}
_FIELD_LABEL_RE = re.compile(
    "(%s)" % "|".join(sorted(_FIELD_MAP, key=len, reverse=True))
)


def _clean_value(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" :،-\n\t")


def _split_list(value: str) -> list[str]:
    items = [re.sub(r"\s+", " ", line).strip(" :،-•*") for line in value.split("\n")]
    return [item for item in items if item]


class NezamsAdapter(BaseAdapter):
    source = "nezams"

    def parse(self, html: str, url: str) -> LawDocument:
        soup = BeautifulSoup(html, "lxml")
        for tag in soup(
            ["script", "style", "nav", "header", "footer", "aside", "form", "noscript"]
        ):
            tag.decompose()

        h1 = soup.find("h1")
        if h1 is None:
            raise ParseError("لم يُعثر على عنوان الصفحة (h1)")
        title = " ".join(h1.get_text(" ", strip=True).split())

        text = (soup.body or soup).get_text("\n", strip=True)
        text = re.sub(r"[ \t]+", " ", text)
        text = _DIGIT_DUMP_RE.sub(" ", text)
        text = _UI_NOISE_RE.sub(" ", text)

        markers = [
            (m.start(), m.end(), "article", m.group(1)) for m in ARTICLE_LABEL_RE.finditer(text)
        ] + [
            (m.start(), m.end(), "section", m.group(0)) for m in _SECTION_RE.finditer(text)
        ]
        markers.sort()
        if not any(kind == "article" for _, _, kind, _ in markers):
            raise ParseError("لم يُعثر على أي مادة في الصفحة")

        doc = LawDocument(title=title, source=self.source, source_url=url)

        body_start = markers[0][0]
        details_pos = text.find(_DETAILS_HEADER)
        if details_pos != -1 and details_pos < body_start:
            self._parse_details(
                text[details_pos + len(_DETAILS_HEADER): body_start], doc
            )

        current_bab: str | None = None
        current_fasl: str | None = None
        for i, (start, end, kind, payload) in enumerate(markers):
            chunk = text[end: markers[i + 1][0] if i + 1 < len(markers) else len(text)]
            if kind == "section":
                section_title = _clean_value(chunk.split(".")[0])[:100]
                full = f"{payload}: {section_title}" if section_title else payload
                if payload.startswith("الباب"):
                    current_bab, current_fasl = full, None
                else:
                    current_fasl = full
                continue
            amendments = [
                re.sub(r"\s+", " ", m.group(0)).strip() for m in _AMEND_RE.finditer(chunk)
            ]
            article_text = re.sub(r"\s+", " ", _AMEND_RE.sub(" ", chunk)).strip(" :،-")
            number_int, is_bis = parse_article_label(payload)
            doc.articles.append(
                Article(
                    number=re.sub(r"\s+", " ", payload).strip(),
                    text=article_text,
                    section=" — ".join(s for s in (current_bab, current_fasl) if s) or None,
                    number_int=number_int,
                    is_bis=is_bis,
                    amendment_history=amendments,
                )
            )

        if not doc.articles:
            raise ParseError("لم يُستخرج أي مادة من الصفحة")
        return doc

    def _parse_details(self, details: str, doc: LawDocument) -> None:
        labels = list(_FIELD_LABEL_RE.finditer(details))
        for i, m in enumerate(labels):
            value = details[m.end(): labels[i + 1].start() if i + 1 < len(labels) else len(details)]
            field = _FIELD_MAP[m.group(1)]
            if field in _LIST_FIELDS:
                if not getattr(doc, field):
                    setattr(doc, field, _split_list(value.strip(" :\n")))
            elif getattr(doc, field) is None:
                setattr(doc, field, _clean_value(value))
