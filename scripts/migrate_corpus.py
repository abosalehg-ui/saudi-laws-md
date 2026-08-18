"""هجرة الملفات القائمة في laws/ إلى العقد الجديد للبيانات الوصفية.

مقابل ``reclassify`` (يعيد حساب التصنيف والمسار) و``canonicalize_urls``
(يوحّد صيغة الروابط)، هذا السكربت يعالج **حقول** الـ front matter التي
تغيّر عقدها:

1. ``status`` من نصّ حرّ إلى قيمة من مجموعة مغلقة، مع نقل التفاصيل إلى
   ``status_note`` (انظر ``status.py``).
2. اشتقاق ``issued_date_hijri`` و``publish_date_gregorian`` بصيغة ISO
   قابلة للفرز من الحقول النصية القائمة، دون المساس بالنصّ الأصلي.
3. تعليم الوثيقة الجوفاء بـ ``content_status: ناقص``.

عن النقطة الثالثة: 197 وثيقة في المُدوَّنة متنها أقصر من الحد الأدنى —
تحقّقنا بجلب صفحاتها أن **المصدر نفسه لا يعرض لها نصًّا** (النصّ في مرفق
PDF)، فليست عطل استخراج. لا تُحذف (بياناتها الوصفية ورابطها لهما قيمة)
ولا تُترك بلا علامة (تبدو حينها كنصّ نظام مبتور)، بل تُعلَّم صراحةً
فيمكن ترشيحها من ``index.json`` ويمرّرها ``lint_corpus`` بوعي.

يُشغَّل مرة بعد اعتماد العقد الجديد، ويبقى للصيانة — تشغيله ثانيةً لا
يغيّر شيئًا (idempotent).

الاستخدام:
    python -m scripts.migrate_corpus laws            # تنفيذ فعلي
    python -m scripts.migrate_corpus laws --dry-run   # معاينة بلا كتابة
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

from .dates import parse_gregorian, parse_hijri
from .formatter import atomic_write
from .frontmatter import read_field, set_field
from .schema import (
    BROKEN_TITLE_RE,
    CONTENT_INCOMPLETE,
    INCOMPLETE_BODY_NOTE,
    MIN_BODY_CHARS,
    NOISE_PATTERNS,
    UNINFORMATIVE_BODY_LINES,
)
from .status import VALID_STATUSES, normalize_status

_TITLE_LINE_RE = re.compile(r"^\s*#\s.*$", re.MULTILINE)
_FRONT_MATTER_RE = re.compile(r"\A---\n.*?\n---\n(.*)", re.S)


def body_text(text: str) -> str:
    """متن الوثيقة بعد الـ front matter وسطر العنوان — ما يُقاس طوله."""
    m = _FRONT_MATTER_RE.match(text)
    return _TITLE_LINE_RE.sub("", m.group(1) if m else text, count=1).strip()


def _is_uninformative(line: str) -> bool:
    """سطر لا يحمل محتوى قانونيًا: بقايا واجهة، أو خطأ صيغة جدول بيانات."""
    stripped = line.strip()
    return (
        not stripped
        or stripped in UNINFORMATIVE_BODY_LINES
        or bool(BROKEN_TITLE_RE.match(stripped))
        or any(pattern in stripped for pattern in NOISE_PATTERNS)
    )


def replace_uninformative_body(text: str) -> tuple[str, bool]:
    """يستبدل متنًا كلّه بقايا واجهة بملاحظة صريحة أن النصّ غير متاح.

    ترك «English صدر بموجب …» أو «تحميل» متنًا لوثيقة يجعلها تبدو نصًّا
    قانونيًا مبتورًا؛ الملاحظة الصريحة تقول للقارئ ما الحاصل فعلًا.
    """
    m = _FRONT_MATTER_RE.match(text)
    if not m:
        return text, False
    body = m.group(1)
    title_match = _TITLE_LINE_RE.search(body)
    if not title_match:
        return text, False
    rest = body[title_match.end():]
    lines = [ln for ln in rest.split("\n") if ln.strip()]
    if not lines or not all(_is_uninformative(ln) for ln in lines):
        return text, False
    if rest.strip() == INCOMPLETE_BODY_NOTE:
        return text, False
    head = text[: m.start(1)] + body[: title_match.end()]
    return f"{head}\n\n{INCOMPLETE_BODY_NOTE}\n", True


def migrate_text(text: str) -> tuple[str, list[str]]:
    """يعيد (النصّ بعد الهجرة، أسماء الحقول التي تغيّرت)."""
    changed: list[str] = []

    text, replaced = replace_uninformative_body(text)
    if replaced:
        changed.append("body")

    raw_status = read_field(text, "status")
    if raw_status and raw_status not in VALID_STATUSES:
        status, note = normalize_status(raw_status)
        text = set_field(text, "status", status)
        text = set_field(text, "status_note", note)
        changed.append("status")

    hijri = parse_hijri(read_field(text, "issued_date")) or parse_hijri(
        read_field(text, "approval_date_hijri")
    )
    if hijri and read_field(text, "issued_date_hijri") != hijri:
        text = set_field(text, "issued_date_hijri", hijri)
        changed.append("issued_date_hijri")

    gregorian = parse_gregorian(read_field(text, "publish_date")) or parse_gregorian(
        read_field(text, "gazette_ref")
    )
    if gregorian and read_field(text, "publish_date_gregorian") != gregorian:
        text = set_field(text, "publish_date_gregorian", gregorian)
        changed.append("publish_date_gregorian")

    # الملاحظة البديلة أطول من الحدّ، لكنها ليست محتوى — وإلا لرُفعت علامة
    # النقص عن الوثائق التي وُضعت لها الملاحظة أصلًا
    body = body_text(text)
    hollow = len(body) < MIN_BODY_CHARS or body == INCOMPLETE_BODY_NOTE
    marked = read_field(text, "content_status") == CONTENT_INCOMPLETE
    if hollow != marked:
        text = set_field(text, "content_status", CONTENT_INCOMPLETE if hollow else None)
        changed.append("content_status")

    return text, changed


def migrate(out_dir: Path, dry_run: bool = False) -> tuple[int, Counter[str]]:
    """يهاجر كل ملفات out_dir؛ يعيد (عدد الملفات المتغيّرة، عدّاد الحقول)."""
    touched = 0
    fields: Counter[str] = Counter()
    for path in sorted(out_dir.rglob("*.md")):
        if path.name == "README.md":  # فهرس مجلد مُولَّد لا وثيقة نظام
            continue
        text = path.read_text(encoding="utf-8")
        new_text, changed = migrate_text(text)
        if not changed:
            continue
        touched += 1
        fields.update(changed)
        if dry_run:
            print(f"{path} ← {'، '.join(changed)}")
        else:
            atomic_write(path, new_text)
    return touched, fields


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.migrate_corpus",
        description="هجرة حقول laws/ إلى العقد الجديد (الحالة، التواريخ الآلية، الوثائق الناقصة)",
    )
    parser.add_argument("out", nargs="?", default="laws", help="مجلد المخرجات (افتراضي: laws)")
    parser.add_argument("--dry-run", action="store_true", help="معاينة بلا كتابة")
    args = parser.parse_args(argv)

    touched, fields = migrate(Path(args.out), dry_run=args.dry_run)
    verb = "سيُحدَّث" if args.dry_run else "حُدِّث"
    print(f"{verb}: {touched} ملفًا", file=sys.stderr)
    for field, count in fields.most_common():
        print(f"  {field}: {count}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(run())
