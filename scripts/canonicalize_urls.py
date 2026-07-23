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
import re
import sys
from pathlib import Path

from .frontmatter import read_field, set_field, set_list_field, unquote
from .urls import canonical_url

_LIST_FIELD_RE = re.compile(r'^also_available_from:\s*\[(.*?)\]\s*$', re.MULTILINE)


def _extract_list(text: str) -> list[str]:
    m = _LIST_FIELD_RE.search(text)
    if not m or not m.group(1).strip():
        return []
    return [unquote(v.strip().strip('"')) for v in m.group(1).split(",")]


def canonicalize_file(path: Path) -> tuple[bool, bool]:
    """يعيد (تغيّر source_url، تغيّر also_available_from) لملف واحد."""
    text = path.read_text(encoding="utf-8")
    changed_src = changed_aaf = False

    raw_src = read_field(text, "source_url")
    own = canonical_url(raw_src) if raw_src else ""
    if raw_src and own != raw_src:
        text = set_field(text, "source_url", own)
        changed_src = True

    old_list = _extract_list(text)
    if old_list:
        seen: set[str] = set()
        new_list: list[str] = []
        for u in old_list:
            cu = canonical_url(u)
            if cu == own or cu in seen:  # ربط ذاتي أو مكرر → يُسقَط
                continue
            seen.add(cu)
            new_list.append(cu)
        if new_list != old_list:
            text = set_list_field(text, "also_available_from", new_list)
            changed_aaf = True

    if (changed_src or changed_aaf):
        path.write_text(text, encoding="utf-8")
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
        text = path.read_text(encoding="utf-8")
        raw_src = read_field(text, "source_url")
        own = canonical_url(raw_src) if raw_src else ""
        will_src = bool(raw_src) and own != raw_src
        old_list = _extract_list(text)
        new_list, seen = [], set()
        for u in old_list:
            cu = canonical_url(u)
            if cu == own or cu in seen:
                continue
            seen.add(cu)
            new_list.append(cu)
        will_aaf = bool(old_list) and new_list != old_list

        if not (will_src or will_aaf):
            continue
        if args.dry_run:
            tags = []
            if will_src:
                tags.append("source_url")
            if will_aaf:
                tags.append("also_available_from")
            print(f"سيُطبَّع [{'، '.join(tags)}]: {path}")
        else:
            cs, ca = canonicalize_file(path)
            will_src, will_aaf = cs, ca
        src_changed += int(will_src)
        aaf_changed += int(will_aaf)

    verb = "سيُطبَّع" if args.dry_run else "طُبِّع"
    print(f"{verb} source_url: {src_changed} ملفًا", file=sys.stderr)
    print(f"{verb} also_available_from: {aaf_changed} ملفًا", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(run())
