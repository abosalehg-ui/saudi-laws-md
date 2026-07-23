"""نموذج البيانات الموحد الذي تنتجه جميع الـ adapters قبل التحويل إلى Markdown."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .arabic_numbers import ARTICLE_LABEL_RE


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
    doc_type: str | None = None    # النوع المكتشف: نظام/لائحة/مرسوم/أمر/قرار/اتفاقية/معايير...
    body: str | None = None        # متن الوثائق غير المقسّمة لمواد (أدلة/معايير/جداول)، Markdown جاهز
    etag: str | None = None        # ETag آخر استجابة HTTP، لجلب شرطي لاحق (--check-updates)
    last_modified: str | None = None  # Last-Modified آخر استجابة HTTP، لنفس الغرض


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


# ترتيب بنود القرار (أولا/ثانيا/…)، مصدر وحيد يُبنى منه كل ما يطابق البنود
# (كشف القرار في الـ adapters، تسلسل البنود هنا) تفاديًا لتكرار القائمة
CLAUSE_NAMES = (
    "أولا", "ثانيا", "ثالثا", "رابعا", "خامسا",
    "سادسا", "سابعا", "ثامنا", "تاسعا", "عاشرا",
)
_CLAUSE_ORDER = CLAUSE_NAMES  # اسم داخلي سابق (للوضوح في دوال هذا الملف)
_CLAUSE_RANK = {name: i for i, name in enumerate(_CLAUSE_ORDER)}


def clause_sequence_warnings(doc: LawDocument) -> list[str]:
    """تحقق تسلسل بنود القرار؛ يرصد بندًا يسبق ترتيبه ما قبله (بند مفقود)."""
    if not doc.is_decision:
        return []
    warnings: list[str] = []
    prev_rank = -1
    for art in doc.articles:
        rank = _CLAUSE_RANK.get(art.number.strip())
        if rank is None:
            continue
        if rank != prev_rank + 1:
            expected = _CLAUSE_ORDER[prev_rank + 1] if prev_rank + 1 < len(_CLAUSE_ORDER) else "?"
            warnings.append(
                f"خلل تسلسل البنود: «{art.number}» بلا ما قبله (المتوقع «{expected}»)"
            )
        prev_rank = rank
    return warnings


# أنماط ضجيج واجهة يجب ألا تتسرب إلى متن أي مادة/وثيقة.
# ملاحظة: الأنماط هنا خاصة قدر الإمكان لتفادي مطابقة نص قانوني مشروع —
# «جميع الحقوق» و«رقم المادة» تردان فعلًا في المتون («جميع الحقوق والمزايا»،
# «رقم المادة» كترويسة عمود في جداول التعديلات)، فاستُبدلتا بالصيغة الحرفية
# للضجيج (footer المشاركة/الحقوق) بدل المقطع العام.
_NOISE_PATTERNS = (
    "مشاركة المادة",
    "رابط المادة",
    "النص والرابط",
    "حجم الخط",
    "عدد القراءات",
    "جميع الحقوق محفوظة",
)

# عناوين تشبه أخطاء صيغ جداول بيانات (Excel/Google Sheets) متسرّبة من
# الموقع المصدر نفسه، لا خللًا في الاستخراج — لوحظت حالة "#REF!" فعليًا
_BROKEN_TITLE_RE = re.compile(r"^#(REF|N/A|VALUE|DIV/0|NAME|NULL|NUM)[!?]?$")


def validate_document(doc: LawDocument) -> list[str]:
    """تحقق شامل يعيد قائمة تحذيرات (لا يرفع استثناء).

    يغطي: تسلسل المواد، ضجيج الواجهة، المواد الفارغة، وخلوّ الوثيقة من
    أي محتوى. الغرض رصد أعطال الاستخراج مبكرًا في الاستيراد بالجملة.
    """
    warnings = list(sequence_warnings(doc))
    warnings.extend(clause_sequence_warnings(doc))

    if _BROKEN_TITLE_RE.match(doc.title.strip()):
        warnings.append(f"عنوان يشبه خطأ صيغة جدول بيانات: «{doc.title}»")

    has_content = bool(doc.articles) or bool((doc.body or "").strip())
    if not has_content:
        warnings.append("الوثيقة بلا محتوى: لا مواد ولا متن")

    # حارس بنيوي: وثيقة حُفظت متنًا نثريًا (body) لكنها تحوي عدة عناوين
    # "المادة ..." تعني غالبًا فشلًا في تقطيع المواد — مؤشر مبكر على تغيّر
    # بنية HTML للموقع المصدر، لا وثيقة نثرية بطبيعتها
    if doc.body and not doc.articles:
        if len(ARTICLE_LABEL_RE.findall(doc.body)) >= 2:
            warnings.append(
                "وثيقة نثرية تحوي عدة نصوص «المادة …»؛ يُحتمل فشل تقطيع المواد "
                "(تغيّر بنية المصدر؟)"
            )

    haystacks = [a.text for a in doc.articles]
    if doc.body:
        haystacks.append(doc.body)
    for text in haystacks:
        for pattern in _NOISE_PATTERNS:
            if pattern in text:
                warnings.append(f"بقايا ضجيج واجهة في المتن: «{pattern}»")
                break

    empty = [a.number for a in doc.articles if not a.text.strip()]
    if empty:
        preview = "، ".join(empty[:5])
        more = f" (+{len(empty) - 5})" if len(empty) > 5 else ""
        warnings.append(f"مواد بلا متن: {preview}{more}")

    return warnings
