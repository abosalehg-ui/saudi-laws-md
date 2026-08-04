"""تحويل LawDocument إلى Markdown موحد الشكل بغض النظر عن المصدر."""

from __future__ import annotations

import re
from pathlib import Path

from .frontmatter import quote as _quote
from .schema import LawDocument

_SOURCE_SITES = {
    "qanoonsa": "قانون (qanoonsa.com)",
    "nezams": "نظام (nezams.com)",
}

UNCATEGORIZED = "غير-مصنف"


def prune_empty_dirs(start: Path, root: Path) -> None:
    """يحذف start وأسلافه طالما فارغين، دون تجاوز root (أداة مسارات مشتركة)."""
    current = start
    try:
        root = root.resolve()
        current = current.resolve()
    except OSError:
        return
    while current != root and root in current.parents:
        try:
            current.rmdir()
        except OSError:
            break
        current = current.parent


def build_note(source: str) -> str:
    site = _SOURCE_SITES.get(source, source)
    return (
        f"نسخة غير رسمية مستخرجة آليًا من موقع {site}. "
        "لا يُعتد بها كمصدر رسمي؛ للتحقق يُرجى الرجوع إلى جريدة أم القرى (uqn.gov.sa) "
        "وبوابة الأنظمة السعودية لدى هيئة الخبراء (laws.boe.gov.sa)."
    )


def format_document(doc: LawDocument) -> str:
    lines = ["---"]
    lines.append(f"title: {_quote(doc.title)}")
    lines.append(f"source: {doc.source}")
    lines.append(f"source_url: {_quote(doc.source_url)}")
    if doc.doc_type:
        lines.append(f"doc_type: {_quote(doc.doc_type)}")
    for key in (
        "issued_by",
        "issued_date",
        "approval_date_hijri",
        "publish_date",
        "gazette_ref",
        "status",
        "category",
    ):
        value = getattr(doc, key)
        if value:
            lines.append(f"{key}: {_quote(value)}")
    for key in ("attachments", "amendments"):
        values = getattr(doc, key)
        if values:
            lines.append(f"{key}: [" + ", ".join(_quote(v) for v in values) + "]")
    for key in ("etag", "last_modified"):
        value = getattr(doc, key)
        if value:
            lines.append(f"{key}: {_quote(value)}")
    if doc.retrieved_at:
        lines.append(f"retrieved_at: {doc.retrieved_at}")
    lines.append(f"note: {_quote(build_note(doc.source))}")
    lines.append("---")
    lines.append("")
    lines.append(f"# {doc.title}")

    # وثيقة غير مقسّمة لمواد: نُدرج المتن الجاهز كما هو
    if not doc.articles and doc.body:
        lines.append("")
        lines.append(doc.body.strip())
        return "\n".join(lines) + "\n"

    current_section: str | None = None
    for art in doc.articles:
        if art.section and art.section != current_section:
            current_section = art.section
            lines.append("")
            lines.append(f"## {art.section}")
        lines.append("")
        heading_text = art.number if doc.is_decision else f"المادة {art.number}"
        # المستوى لكل مادة على حدة: ### تحت باب/فصل (##)، و## لمادة بلا قسم.
        # رفعُ كل المواد إلى ### لمجرد وجود قسم واحد في الوثيقة كان يقفز
        # H1→H3 للمواد السابقة لأول باب، فيكسر التسلسل الهرمي للعناوين
        article_heading = "###" if art.section else "##"
        lines.append(f"{article_heading} {heading_text}")
        lines.append("")
        lines.append(art.text.strip())
        if art.amendment_history:
            lines.append("")
            lines.append("> **تعديلات المادة:**")
            for amendment in art.amendment_history:
                lines.append(f"> - {amendment}")
    return "\n".join(lines) + "\n"


_MAX_FILENAME_BYTES = 200  # هامش أمان تحت حد 255 بايت الشائع لأنظمة الملفات، بعد ترميز UTF-8


def sanitize_filename(name: str) -> str:
    name = re.sub(r'[/\\:*?"<>|]', " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    encoded = name.encode("utf-8")[:_MAX_FILENAME_BYTES]
    name = encoded.decode("utf-8", errors="ignore").strip()
    # اسم مكوَّن من نقاط فقط ("." أو "..") يشير للمجلد نفسه/الأب — يُرفض حتى
    # لا يكتب مسار مُشتق من عنوان/تصنيف غير موثوق خارج مجلد المخرجات (S-1)
    if not name or set(name) <= {"."}:
        return "بدون-عنوان"
    return name


def disambiguated_filename(stem: str, discriminator: str) -> str:
    """«جذع (مميِّز)» مع ضمان بقاء المميِّز كاملًا بعد الاقتطاع.

    sanitize_filename يقتطع من نهاية الاسم، فحين يبلغ الجذع وحده حدَّ الطول
    تضيع لاحقة التمييز كلها ويعود الاسم مطابقًا للاسم المتصادم — وهو ما كان
    يُدخل حلقة _resolve_collision في دوران بلا نهاية. هنا يُقتطع الجذع بقدر
    ما تتطلّبه اللاحقة، فيبقى الناتج مميَّزًا مهما طال العنوان.
    """
    discriminator = sanitize_filename(discriminator)
    tail = f" ({discriminator})"
    budget = _MAX_FILENAME_BYTES - len(tail.encode("utf-8"))
    if budget <= 0:
        # مميِّز أطول من حدّ الاسم كله: يُقتطع هو نفسه ويُستغنى عن الجذع
        return sanitize_filename(discriminator)
    stem = sanitize_filename(stem).encode("utf-8")[:budget]
    stem = stem.decode("utf-8", errors="ignore").strip()
    return sanitize_filename(f"{stem}{tail}")


def output_path(doc: LawDocument, out_dir: Path) -> Path:
    category = sanitize_filename(doc.category) if doc.category else UNCATEGORIZED
    return out_dir / category / f"{sanitize_filename(doc.title)}.md"
