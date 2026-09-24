"""نموذج البيانات الموحد الذي تنتجه جميع الـ adapters قبل التحويل إلى Markdown."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .arabic_numbers import ARTICLE_LABEL_RE
from .frontmatter import read_field


@dataclass
class Article:
    number: str  # التسمية كما وردت: "الأولى"، "التاسعة والسبعون مكرر"...
    text: str
    section: str | None = None  # عنوان الباب/الفصل الذي تنتمي له المادة (إن وُجد)
    number_int: int | None = None  # الرقم التسلسلي المشتق، للتحقق فقط ولا يظهر في الناتج
    is_bis: bool = False  # مادة "مكرر"
    amendment_history: list[str] = field(default_factory=list)


@dataclass
class LawDocument:
    title: str
    source: str  # "qanoonsa" أو "nezams"
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
    is_decision: bool = False  # قرار (أولا/ثانيا/...) بلا مواد، بدل نظام كامل
    issued_date: str | None = None  # تاريخ صدور القرار كما ورد ("صدر في: ...")
    doc_type: str | None = None  # النوع المكتشف: نظام/لائحة/مرسوم/أمر/قرار/اتفاقية/معايير...
    body: str | None = None  # متن الوثائق غير المقسّمة لمواد (أدلة/معايير/جداول)، Markdown جاهز
    etag: str | None = None  # ETag آخر استجابة HTTP، لجلب شرطي لاحق (--check-updates)
    last_modified: str | None = None  # Last-Modified آخر استجابة HTTP، لنفس الغرض
    status_note: str | None = None  # نصّ الحالة الأصلي حين يحمل تفاصيل (جهة الإلغاء والنظام البديل)
    issued_date_hijri: str | None = None  # تاريخ الإصدار الهجري ISO قابل للفرز (1443-10-04)
    publish_date_gregorian: str | None = None  # تاريخ النشر الميلادي ISO قابل للفرز
    content_status: str | None = None  # "ناقص" للوثيقة التي لا نصّ لها في المصدر نفسه
    dropped_items: int = 0  # عناصر مادة أسقطها الـ adapter لقالب غير متوقَّع (للتحقق فقط)

    @classmethod
    def from_front_matter(cls, text: str) -> LawDocument:
        """وثيقة وصفية (بلا مواد ولا متن) من front matter ملف مُلتزَم.

        تكفي لإعادة حساب النوع والتصنيف والمسار (``category_dir``/``output_path``)
        بنفس دوال الاستيراد — فلا تبني كل أداة صيانة نسختها من هذه الحقول.
        """
        return cls(
            title=read_field(text, "title") or "",
            source=read_field(text, "source") or "",
            source_url=read_field(text, "source_url") or "",
            doc_type=read_field(text, "doc_type"),
            category=read_field(text, "category"),
            issued_date=read_field(text, "issued_date"),
            approval_date_hijri=read_field(text, "approval_date_hijri"),
            gazette_ref=read_field(text, "gazette_ref"),
            content_status=read_field(text, "content_status"),
        )


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
                warnings.append(f"مادة مكررة برقم {art.number_int} لا تلي أصلها (السابقة: {prev})")
            continue
        if prev is not None and art.number_int != prev + 1:
            warnings.append(f"خلل في التسلسل: بعد المادة {prev} جاءت المادة {art.number_int}")
        prev = art.number_int
    return warnings


# ترتيب بنود القرار (أولا/ثانيا/…)، مصدر وحيد يُبنى منه كل ما يطابق البنود
# (كشف القرار في الـ adapters، تسلسل البنود هنا) تفاديًا لتكرار القائمة
CLAUSE_NAMES = (
    "أولا",
    "ثانيا",
    "ثالثا",
    "رابعا",
    "خامسا",
    "سادسا",
    "سابعا",
    "ثامنا",
    "تاسعا",
    "عاشرا",
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
            warnings.append(f"خلل تسلسل البنود: «{art.number}» بلا ما قبله (المتوقع «{expected}»)")
        prev_rank = rank
    return warnings


# أنماط ضجيج واجهة يجب ألا تتسرب إلى متن أي مادة/وثيقة.
# ملاحظة: الأنماط هنا خاصة قدر الإمكان لتفادي مطابقة نص قانوني مشروع —
# «جميع الحقوق» و«رقم المادة» تردان فعلًا في المتون («جميع الحقوق والمزايا»،
# «رقم المادة» كترويسة عمود في جداول التعديلات)، فاستُبدلتا بالصيغة الحرفية
# للضجيج (footer المشاركة/الحقوق) بدل المقطع العام.
NOISE_PATTERNS = (
    "مشاركة المادة",
    "رابط المادة",
    "النص والرابط",
    "حجم الخط",
    "عدد القراءات",
    "جميع الحقوق محفوظة",
    # زر تبديل اللغة ملتصقًا بسطر وصفي: توقيع صفحات qanoonsa التي تُعيد
    # نشر وثيقة بلا متنها، فلا يبقى في المتن سوى هذا السطر — وثيقة جوفاء
    # تمرّ كأنها وثيقة نثرية صحيحة. رُصدت بصيغتين: «صدر في» و«صدر بموجب»
    "English صدر في",
    "English صدر بموجب",
)

#: الحدّ الأدنى لطول متن وثيقة تُعدّ ذات محتوى حقيقي (بالمحارف، بعد العنوان).
#: دونه تكون الوثيقة «جوفاء»: سطر تاريخ إصدار، أو كلمة «تحميل»، أو بقايا
#: واجهة — وكلها رُصدت فعلًا في المُدوَّنة. القيمة مضبوطة تحت أقصر متن
#: مشروع لوحظ (أمر ملكي بتعيين/إعفاء) وفوق كل الحالات الجوفاء المرصودة.
MIN_BODY_CHARS = 120

#: قيمة ``content_status`` للوثيقة التي لا نصّ لها في المصدر نفسه (لا خلل
#: استخراج): تُحفظ ببياناتها الوصفية وتُعلَّم صراحةً حتى يمكن ترشيحها.
CONTENT_INCOMPLETE = "ناقص"

#: متن بديل للوثيقة التي لا نصّ لها في المصدر. أصدق من ترك بقايا واجهة
#: («English صدر بموجب …»، «تحميل») تبدو للقارئ نصًّا قانونيًا مبتورًا.
INCOMPLETE_BODY_NOTE = (
    "> **النصّ غير متاح آليًا.** المصدر يعرض البيانات الوصفية أعلاه دون نصّ "
    "الوثيقة (النصّ لديه في مرفق). للاطلاع على النصّ الكامل يُرجى الرجوع إلى "
    "رابط المصدر أعلاه أو إلى جريدة أم القرى."
)

#: نصوص متن لا تحمل أي محتوى قانوني: بقايا واجهة، وأخطاء صيغ جداول
#: بيانات متسرّبة من المصدر، وتسميات أزرار. وثيقة كل متنها من هذا يُستبدَل
#: متنها بـ INCOMPLETE_BODY_NOTE.
UNINFORMATIVE_BODY_LINES = frozenset({"تحميل", "التحميل", "اضغط هنا", "English"})


# سطر يعِد بجدول («… وفق الجدول الآتي:») — يجب أن يليه جدول Markdown.
# «المرفق» مستثنى عمدًا: الجدول المرفق وثيقة مستقلة غالبًا لا جزء من المتن.
_TABLE_PROMISE_RE = re.compile(
    r"^(?!\|)[^\n]*(?:الجدول|الجداول)\s+(?:الآتي|الاتي|التالي|الآتية|التالية)[^\n]*:[ \t]*$",
    re.MULTILINE,
)


def missing_table_lines(text: str) -> list[str]:
    """أسطر تعِد بجدول («الجدول الآتي:») ولا يليها جدول Markdown.

    هذا توقيع عطل الاستخراج الذي كان يُسقط جداول المواد بصمت: مادة تنتهي
    بنقطتين ثم تنتقل مباشرة إلى الفقرة أو المادة التالية.
    """
    missing = []
    for m in _TABLE_PROMISE_RE.finditer(text):
        if not text[m.end() :].lstrip().startswith("|"):
            missing.append(m.group(0).strip())
    return missing


def body_length(doc: LawDocument) -> int:
    """طول المحتوى الفعلي للوثيقة بالمحارف (مواد + متن نثري)."""
    total = sum(len(a.text.strip()) for a in doc.articles)
    return total + len((doc.body or "").strip())


# عناوين تشبه أخطاء صيغ جداول بيانات (Excel/Google Sheets) متسرّبة من
# الموقع المصدر نفسه، لا خللًا في الاستخراج — لوحظت حالة "#REF!" فعليًا
BROKEN_TITLE_RE = re.compile(r"^#(REF|N/A|VALUE|DIV/0|NAME|NULL|NUM)[!?]?$")


def validate_document(doc: LawDocument) -> list[str]:
    """تحقق شامل يعيد قائمة تحذيرات (لا يرفع استثناء).

    يغطي: تسلسل المواد، ضجيج الواجهة، المواد الفارغة، وخلوّ الوثيقة من
    أي محتوى. الغرض رصد أعطال الاستخراج مبكرًا في الاستيراد بالجملة.
    """
    warnings = list(sequence_warnings(doc))
    warnings.extend(clause_sequence_warnings(doc))

    if BROKEN_TITLE_RE.match(doc.title.strip()):
        warnings.append(f"عنوان يشبه خطأ صيغة جدول بيانات: «{doc.title}»")

    has_content = bool(doc.articles) or bool((doc.body or "").strip())
    if not has_content:
        warnings.append("الوثيقة بلا محتوى: لا مواد ولا متن")

    # حارس بنيوي: وثيقة حُفظت متنًا نثريًا (body) لكنها تحوي عدة عناوين
    # "المادة ..." تعني غالبًا فشلًا في تقطيع المواد — مؤشر مبكر على تغيّر
    # بنية HTML للموقع المصدر، لا وثيقة نثرية بطبيعتها
    if doc.body and not doc.articles:
        if len(ARTICLE_LABEL_RE.findall(doc.body)) >= 2:
            warnings.append("وثيقة نثرية تحوي عدة نصوص «المادة …»؛ يُحتمل فشل تقطيع المواد (تغيّر بنية المصدر؟)")

    haystacks = [a.text for a in doc.articles]
    if doc.body:
        haystacks.append(doc.body)
    for text in haystacks:
        for pattern in NOISE_PATTERNS:
            if pattern in text:
                warnings.append(f"بقايا ضجيج واجهة في المتن: «{pattern}»")
                break

    if has_content and body_length(doc) < MIN_BODY_CHARS and doc.content_status is None:
        warnings.append(
            f"متن أقصر من الحد الأدنى ({body_length(doc)} < {MIN_BODY_CHARS} محرفًا): "
            "يُحتمل أن الصفحة بلا نصّ (مرفق PDF) أو أن الاستخراج فشل"
        )

    for text in haystacks:
        for line in missing_table_lines(text):
            warnings.append(f"سطر يعِد بجدول لا يليه جدول (يُحتمل إسقاط جدول): «{line[:80]}»")

    if doc.dropped_items:
        warnings.append(f"أُسقط {doc.dropped_items} عنصر مادة بقالب غير متوقَّع (بلا عنوان أو متن)")

    empty = [a.number for a in doc.articles if not a.text.strip()]
    if empty:
        preview = "، ".join(empty[:5])
        more = f" (+{len(empty) - 5})" if len(empty) > 5 else ""
        warnings.append(f"مواد بلا متن: {preview}{more}")

    return warnings
