"""نموذج البيانات الموحد الذي تنتجه جميع الـ adapters قبل التحويل إلى Markdown."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Article:
    number: str                    # التسمية كما وردت: "الأولى"، "التاسعة والسبعون مكرر"...
    text: str
    section: str | None = None     # عنوان الباب/الفصل الذي تنتمي له المادة (إن وُجد)
    number_int: int | None = None  # الرقم التسلسلي المشتق، للتحقق فقط ولا يظهر في الناتج
    is_bis: bool = False           # مادة "مكرر"
    amendment_history: list[str] = field(default_factory=list)


@dataclass
class LawDocument:
    title: str
    source: str                    # "qanoonsa" أو "nezams"
    source_url: str
    issued_by: str | None = None
    approval_date_hijri: str | None = None
    publish_date: str | None = None
    gazette_ref: str | None = None
    status: str | None = None
    category: str | None = None
    attachments: list[str] = field(default_factory=list)
    amendments: list[str] = field(default_factory=list)  # تعديلات على مستوى النظام (تظهر في تفاصيل nezams)
    articles: list[Article] = field(default_factory=list)
    retrieved_at: str | None = None
    is_decision: bool = False      # قرار (أولا/ثانيا/...) بلا مواد، بدل نظام كامل
    issued_date: str | None = None  # تاريخ صدور القرار كما ورد ("صدر في: ...")


def sequence_warnings(doc: LawDocument) -> list[str]:
    """تحقق من تسلسل أرقام المواد؛ يعيد تحذيرات (لا يفشل) عند الفجوات أو تعذر التحويل.

    لا ينطبق على القرارات: بنودها (أولا/ثانيا/...) ليست مرقّمة تسلسليًا كالمواد.
    """
    if doc.is_decision:
        return []
    warnings: list[str] = []
    prev: int | None = None
    for art in doc.articles:
        if art.number_int is None:
            warnings.append(f"تعذر تحويل رقم المادة إلى عدد: «{art.number}»")
            continue
        if art.is_bis:
            if prev is not None and art.number_int != prev:
                warnings.append(
                    f"مادة مكررة برقم {art.number_int} لا تلي أصلها (السابقة: {prev})"
                )
            continue
        if prev is not None and art.number_int != prev + 1:
            warnings.append(
                f"خلل في التسلسل: بعد المادة {prev} جاءت المادة {art.number_int}"
            )
        prev = art.number_int
    return warnings
