"""تطبيع حقول الروابط في ملفات laws/ الحالية إلى الصيغة القانونية (urls.py).

خلفية: مُرِّرت الروابط تاريخيًا بترميزين (مُرمَّز عربي مقروء) حسب دفعة
الاستيراد، فانقسمت هوية الوثيقة الواحدة. هذا السكربت يعيد كتابة ``source_url``
و``also_available_from`` إلى الصيغة القانونية، ويُسقط من ``also_available_from``
أي رابط يساوي رابط الملف نفسه (ربط ذاتي نشأ من اختلاف الترميز).

لا يمسّ المتن ولا بقية الحقول. يُشغَّل مرة واحدة بعد اعتماد urls.py، ثم يبقى
متاحًا للصيانة (تشغيله بعدها لا يغيّر شيئًا — idempotent).

الاستخدام:
    python -m scripts.canonicalize_urls laws            # تنفيذ فعلي
    python -m scripts.canonicalize_urls laws --dry-run   # معاينة بلا كتابة
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .formatter import atomic_write
from .frontmatter import read_field, read_list_field, set_field, set_list_field
from .urls import canonical_url

_LIST_FIELD = "also_available_from"


def _canonical_siblings(urls: list[str], own: str) -> list[str]:
    """الروابط المطبَّعة بلا الرابط الذاتي وبلا تكرار (يحفظ الترتيب)."""
    seen: set[str] = set()
    result: list[str] = []
    for url in urls:
        canonical = canonical_url(url)
        if canonical == own or canonical in seen:  # ربط ذاتي أو مكرر → يُسقَط
            continue
        seen.add(canonical)
        result.append(canonical)
    return result


def canonicalize_file(path: Path, dry_run: bool = False) -> tuple[bool, bool]:
    """يعيد (سيتغيّر/تغيّر source_url، ... also_available_from) لملف واحد.

    مع ``dry_run`` يحسب التغييرات دون كتابة — بنفس المنطق لا بنسخة ثانية
    منه، فلا تنحرف المعاينة عن التنفيذ.
    """
    text = path.read_text(encoding="utf-8")
    changed_src = changed_aaf = False

    raw_src = read_field(text, "source_url")
    own = canonical_url(raw_src) if raw_src else ""
    if raw_src and own != raw_src:
        text = set_field(text, "source_url", own)
        changed_src = True

    old_list = read_list_field(text, _LIST_FIELD)
    if old_list:
        new_list = _canonical_siblings(old_list, own)
        if new_list != old_list:
            text = set_list_field(text, _LIST_FIELD, new_list)
            changed_aaf = True

    if (changed_src or changed_aaf) and not dry_run:
        atomic_write(path, text)
    return changed_src, changed_aaf


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.canonicalize_urls",
        description="تطبيع حقول الروابط في laws/ إلى الصيغة القانونية",
    )
    parser.add_argument("out", nargs="?", default="laws", help="مجلد المخرجات (افتراضي: laws)")
    parser.add_argument("--dry-run", action="store_true", help="معاينة بلا كتابة")
    args = parser.parse_args(argv)

    src_changed = aaf_changed = 0
    for path in sorted(Path(args.out).rglob("*.md")):
        if path.name == "README.md":  # فهرس مجلد مُولَّد لا وثيقة نظام
            continue
        changed_src, changed_aaf = canonicalize_file(path, dry_run=args.dry_run)
        if not (changed_src or changed_aaf):
            continue
        if args.dry_run:
            tags = [
                name for name, flag in (("source_url", changed_src), (_LIST_FIELD, changed_aaf))
                if flag
            ]
            print(f"سيُطبَّع [{'، '.join(tags)}]: {path}")
        src_changed += int(changed_src)
        aaf_changed += int(changed_aaf)

    verb = "سيُطبَّع" if args.dry_run else "طُبِّع"
    print(f"{verb} source_url: {src_changed} ملفًا", file=sys.stderr)
    print(f"{verb} also_available_from: {aaf_changed} ملفًا", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(run())
