"""تحويل محدود لعناصر HTML إلى Markdown للوثائق غير المقسّمة لمواد.

يُستخدم للأدلة والمعايير والجداول التي محتواها فقرات وجداول بلا بنية
"المادة ...". التحويل حتمي ويحافظ على النص كما ورد؛ لا تلخيص ولا إعادة صياغة.
"""

from __future__ import annotations

import re

from bs4 import Tag

# بقايا حقول CMS ثنائية اللغة تتسرّب أحيانًا إلى بداية العنوان أو الفقرة
# ("Arabic Full Name: …"، "English صدر في: …"). تعيش هنا لا في adapter
# qanoonsa لأن مسارَي الاستخراج (المواد والمتن النثري) يحتاجانها معًا؛
# تطبيقها في الأول دون الثاني هو ما سرّب 12 وثيقة متنها «English صدر
# بموجب …» إلى المُدوَّنة.
CMS_LABEL_PREFIX_RE = re.compile(r"^(?:Arabic|English)(?:\s+Full\s+Name)?\s*:?\s+")


def clean_text(raw: str) -> str:
    """يوحّد المسافات ويزيل بادئة حقل الـ CMS — التنظيف المشترك لكل كتلة نصّ."""
    return CMS_LABEL_PREFIX_RE.sub("", " ".join(raw.split()))


def _cell_text(cell: Tag) -> str:
    # داخل خلية الجدول نستبدل الأسطر بمسافات ونهرّب أنبوب Markdown
    text = " ".join(cell.get_text(" ", strip=True).split())
    return text.replace("|", "\\|")


def table_to_markdown(table: Tag) -> str:
    """يحوّل جدول HTML إلى جدول Markdown. يفترض الصف الأول ترويسة."""
    rows: list[list[str]] = []
    for tr in table.find_all("tr"):
        cells = tr.find_all(["th", "td"])
        if cells:
            rows.append([_cell_text(c) for c in cells])
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    header, body = rows[0], rows[1:]
    lines = ["| " + " | ".join(header) + " |"]
    lines.append("| " + " | ".join(["---"] * width) + " |")
    for row in body:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def prose_to_markdown(
    content: Tag,
    skip: frozenset[str] = frozenset(),
) -> str:
    """يحوّل محتوى وثيقة غير مقسّمة لمواد إلى Markdown مع الحفاظ على الترتيب.

    ``skip`` مجموعة نصوص فقرات يجب تجاهلها (سطور استُخرجت مسبقًا إلى حقول
    وصفية مثل النشر والاعتماد). العناوين h2/h3/h4 تُصبح ``##`` مباشرة تحت
    عنوان الوثيقة (``#``) — لا ``###`` حتى لا يقفز التسلسل الهرمي مستوى
    (H1→H3) فتتعطل قارئات الشاشة ومولّدات فهرس المحتويات — والجداول
    تُحوَّل، والفقرات والعناصر تبقى كما وردت.
    """
    blocks: list[str] = []
    for el in content.find_all(["h2", "h3", "h4", "p", "li", "blockquote", "table"]):
        if el.name == "table":
            md = table_to_markdown(el)
            if md:
                blocks.append(md)
            continue
        # عناصر مُتداخلة داخل جدول أو li/blockquote يُلتقط نصها ضمن حاويها؛
        # نتجنّب تكرارها (الجدول يعالجه محوّله، والحاوي يُخرِج نصه كاملًا)
        if el.find_parent(["table", "li", "blockquote"]) is not None:
            continue
        text = clean_text(el.get_text(" ", strip=True))
        if not text or text in skip:
            continue
        if el.name in ("h2", "h3", "h4"):
            blocks.append(f"## {text}")
        elif el.name == "li":
            blocks.append(f"- {text}")
        else:
            blocks.append(text)
    return "\n\n".join(blocks)
