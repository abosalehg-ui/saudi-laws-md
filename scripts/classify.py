"""كشف نوع الوثيقة القانونية من عنوانها (وأحيانًا رابطها).

الأنواع مبنية على البادئات الفعلية الملاحظة في عناوين الموقعين:
نظام، لائحة، مرسوم ملكي، أمر ملكي، قرار، اتفاقية، معايير/دليل، تعديل.
الكشف مبني على مطابقة نصية حتمية لا على استدلال لغوي، حتى يكون قابلًا
للتحقق ومستقرًا عبر الدفعات.
"""

from __future__ import annotations

import re
from urllib.parse import unquote, urlparse

# النوع → أنماط بادئة العنوان (تُطبَّق بالترتيب؛ أول تطابق يفوز)
_TITLE_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("مرسوم ملكي", re.compile(r"^مرسوم\s+ملكي")),
    ("أمر ملكي", re.compile(r"^أمر\s+ملكي")),
    ("قرار", re.compile(r"^قرار\b")),
    ("اتفاقية", re.compile(r"^(اتفاقية|مذكرة\s+تفاهم|بروتوكول)\b")),
    ("لائحة", re.compile(r"^(اللائحة|لائحة|قواعد|الدليل|دليل)\b")),
    ("معايير", re.compile(r"^(معايير|جدول|اشتراطات|ضوابط|مواصفات)\b")),
    ("نظام", re.compile(r"^(نظام|تنظيم)\b")),
]

# مسار "تحديثات الأنظمة" في nezams: تعديل مادة مفردة لا نظام كامل
_UPDATE_URL_RE = re.compile(r"تحديثات[-\s]*الأنظمة|/nezam_update|تحديثات-الانظمة")

VALID_TYPES = {
    "نظام", "لائحة", "مرسوم ملكي", "أمر ملكي",
    "قرار", "اتفاقية", "معايير", "تعديل", "أخرى",
}


def classify_doc_type(title: str, url: str = "", is_decision: bool = False) -> str:
    """يرجع نوع الوثيقة من عنوانها (وربما رابطها).

    - صفحات تحديثات nezams تُصنَّف "تعديل" مهما كان العنوان.
    - القرارات (بنية أولا/ثانيا) تُصنَّف حسب العنوان أولًا؛ فإن لم يُطابق
      نمطًا معروفًا رُدّت "قرار".
    - ما لا يطابق أي نمط يُرد "أخرى".
    """
    decoded = unquote(urlparse(url).path) if url else ""
    if _UPDATE_URL_RE.search(decoded):
        return "تعديل"

    normalized = " ".join(title.split())
    for doc_type, pattern in _TITLE_RULES:
        if pattern.search(normalized):
            return doc_type

    if is_decision:
        return "قرار"
    return "أخرى"
