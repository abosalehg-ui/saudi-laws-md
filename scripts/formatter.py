"""تحويل LawDocument إلى Markdown موحد الشكل بغض النظر عن المصدر."""

from __future__ import annotations

import re
from pathlib import Path

from .schema import LawDocument

_SOURCE_SITES = {
    "qanoonsa": "قانون (qanoonsa.com)",
    "nezams": "نظام (nezams.com)",
}

UNCATEGORIZED = "غير-مصنف"


def build_note(source: str) -> str:
    site = _SOURCE_SITES.get(source, source)
    return (
        f"نسخة غير رسمية مستخرجة آليًا من موقع {site}. "
        "لا يُعتد بها كمصدر رسمي؛ للتحقق يُرجى الرجوع إلى جريدة أم القرى (uqn.gov.sa) "
        "وبوابة الأنظمة السعودية لدى هيئة الخبراء (laws.boe.gov.sa)."
    )


def _quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def format_document(doc: LawDocument) -> str:
    lines = ["---"]
    lines.append(f"title: {_quote(doc.title)}")
    lines.append(f"source: {doc.source}")
    lines.append(f"source_url: {_quote(doc.source_url)}")
    for key in (
        "issued_by",
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
    if doc.retrieved_at:
        lines.append(f"retrieved_at: {doc.retrieved_at}")
    lines.append(f"note: {_quote(build_note(doc.source))}")
    lines.append("---")
    lines.append("")
    lines.append(f"# {doc.title}")

    has_sections = any(a.section for a in doc.articles)
    article_heading = "###" if has_sections else "##"
    current_section: str | None = None
    for art in doc.articles:
        if art.section and art.section != current_section:
            current_section = art.section
            lines.append("")
            lines.append(f"## {art.section}")
        lines.append("")
        lines.append(f"{article_heading} المادة {art.number}")
        lines.append("")
        lines.append(art.text.strip())
        if art.amendment_history:
            lines.append("")
            lines.append("> **تعديلات المادة:**")
            for amendment in art.amendment_history:
                lines.append(f"> - {amendment}")
    return "\n".join(lines) + "\n"


def sanitize_filename(name: str) -> str:
    name = re.sub(r'[/\\:*?"<>|]', " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:150] or "بدون-عنوان"


def output_path(doc: LawDocument, out_dir: Path) -> Path:
    category = sanitize_filename(doc.category) if doc.category else UNCATEGORIZED
    return out_dir / category / f"{sanitize_filename(doc.title)}.md"
