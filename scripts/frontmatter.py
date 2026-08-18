"""أدوات خفيفة لقراءة/تعديل حقل واحد داخل front matter، دون تفسير YAML كامل.

يُستخدم من سكربتات الصيانة (reclassify.py، audit_duplicates.py) التي تعدّل
حقلًا أو حقلين فقط في ملفات موجودة مسبقًا، وتريد ترك بقية الملف (المتن،
بقية الحقول) بلا لمس. main.py يحتفظ بنسخته الخاصة من قراءة source_url
لأنها على مسار ساخن (تُفحص لكل ملف في كل تشغيلة).
"""

from __future__ import annotations

import re

_FRONT_MATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.S)


_LIST_VALUE_RE = re.compile(r'"((?:[^"\\]|\\.)*)"')


def read_list_field(text: str, field: str) -> list[str]:
    """يقرأ حقل قائمة (``field: ["a", "b"]``) من كتلة الـ front matter فقط.

    مقابل ``set_list_field``؛ وُجد سابقًا مكرّرًا حرفيًا في ثلاثة سكربتات
    (build_index، audit_duplicates، canonicalize_urls) فجُمع هنا.
    القيم تُقرأ بمطابقة السلاسل المقتبسة لا بالتقسيم على الفاصلة، حتى لا
    تنكسر قيمة تحوي فاصلة داخلها.
    """
    m = _FRONT_MATTER_RE.match(text)
    block = m.group(1) if m else text
    row = re.search(rf"^{re.escape(field)}:\s*\[(.*)\]\s*$", block, re.MULTILINE)
    if not row or not row.group(1).strip():
        return []
    return [unquote(v) for v in _LIST_VALUE_RE.findall(row.group(1))]


def read_field(text: str, field: str) -> str | None:
    """يقرأ قيمة حقل نصي مفرد (غير قائمة) من كتلة الـ front matter فقط.

    مقصور على الكتلة (لا كامل النص) حتى لا يلتقط سطرًا في المتن يبدأ بالحقل
    نفسه (وثيقة تقتبس نموذجًا أو جدولًا)، توحيدًا للعقد مع set_field.
    """
    fm = _FRONT_MATTER_RE.match(text)
    block = fm.group(1) if fm else text
    m = re.search(rf'^{re.escape(field)}:\s*"?(.*?)"?\s*$', block, re.MULTILINE)
    return m.group(1) if m and m.group(1) else None


def quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def unquote(value: str) -> str:
    return value.replace('\\"', '"').replace("\\\\", "\\")


def _sub_literal(pattern: re.Pattern[str], replacement: str, text: str) -> str:
    """استبدال أول تطابق بنصّ **حرفي**.

    ``re.sub`` يفسّر الشرطة العكسية في سلسلة الاستبدال (``\\\\`` تصير ``\\``،
    و``\\g<1>`` تصير مرجعًا)، وقيمنا مهرَّبة أصلًا بـ ``quote`` — فتمريرها
    نصًّا يفكّ مستوى هروب كامل ويكسر عقد الـ front matter (قيمة تنتهي
    بشرطة عكسية كانت تُنتج اقتباسًا مهرَّبًا يبتلع نهاية السطر). تمرير
    دالة يوقف هذا التفسير.
    """
    return pattern.sub(lambda _: replacement, text, count=1)


def set_field(text: str, field: str, value: str | None) -> str:
    """يستبدل/يحذف/يضيف حقلًا نصيًا مفردًا، مقصورًا على كتلة الـ front matter."""
    m = _FRONT_MATTER_RE.match(text)
    if not m:
        return text
    block = m.group(1)
    field_re = re.compile(rf'^{re.escape(field)}:\s*"?(?:.*?)"?\s*$', re.MULTILINE)
    if value:
        line = f"{field}: {quote(value)}"
        new_block = (
            _sub_literal(field_re, line, block) if field_re.search(block) else block + "\n" + line
        )
    elif field_re.search(block):
        new_block = "\n".join(ln for ln in block.split("\n") if not field_re.match(ln))
    else:
        new_block = block
    return text[: m.start(1)] + new_block + text[m.end(1):]


def set_list_field(text: str, field: str, values: list[str]) -> str:
    """يستبدل/يحذف/يضيف حقل قائمة (["a", "b"])، مقصورًا على كتلة الـ front matter."""
    m = _FRONT_MATTER_RE.match(text)
    if not m:
        return text
    block = m.group(1)
    field_re = re.compile(rf"^{re.escape(field)}:\s*\[.*?\]\s*$", re.MULTILINE)
    if values:
        line = f"{field}: [" + ", ".join(quote(v) for v in values) + "]"
        new_block = (
            _sub_literal(field_re, line, block) if field_re.search(block) else block + "\n" + line
        )
    elif field_re.search(block):
        new_block = "\n".join(ln for ln in block.split("\n") if not field_re.match(ln))
    else:
        new_block = block
    return text[: m.start(1)] + new_block + text[m.end(1):]
