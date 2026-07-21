"""يكشف الوثائق المزدوجة (العنوان نفسه في أكثر من ملف) عبر laws/ ويربط بينها.

الازدواج ينشأ من سحب نفس الوثيقة من كلا المصدرين (qanoonsa وnezams)، أو من
إعادة سحب نفس الرابط بعد تغيّر عنوانه/تصنيفه على الموقع دون أن يُحذف
الملف القديم يدويًا. لا يدمج هذا السكربت الملفات ولا يحذف أيًا منها —
دمج تلقائي لوثيقتين قد يكون خاطئًا (عنوانان متطابقان صدفة لوثيقتين
مختلفتين فعليًا)، فالخيار الأكثر أمانًا هو الإبقاء على الملفين وربطهما
صراحةً عبر حقل also_available_from (قائمة روابط النسخ الأخرى) ليعرف
القارئ أن نسخة أخرى موجودة، دون حسم أيّهما "الصحيحة".

الاستخدام:
    python -m scripts.audit_duplicates laws            # تنفيذ فعلي
    python -m scripts.audit_duplicates laws --dry-run   # معاينة بلا كتابة
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

from .frontmatter import read_field, set_list_field, unquote

_FIELD = "also_available_from"
_LIST_FIELD_RE = re.compile(r'^also_available_from:\s*\[(.*?)\]\s*$', re.MULTILINE)


def find_duplicate_groups(out_dir: Path) -> dict[str, list[Path]]:
    """يجمع مسارات الملفات حسب العنوان؛ يعيد فقط المجموعات التي تضم أكثر من ملف."""
    by_title: dict[str, list[Path]] = defaultdict(list)
    for path in sorted(out_dir.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        title = read_field(text, "title")
        if title is None:
            continue
        by_title[unquote(title)].append(path)
    return {title: paths for title, paths in by_title.items() if len(paths) > 1}


def annotate_duplicates(out_dir: Path, dry_run: bool = False) -> tuple[int, int]:
    """يضيف/يحدّث حقل also_available_from لكل ملف ضمن مجموعة مزدوجة.

    يعيد (عدد المجموعات، عدد الملفات المُحدَّثة).
    """
    groups = find_duplicate_groups(out_dir)
    files_touched = 0
    for paths in groups.values():
        urls = {}
        for path in paths:
            text = path.read_text(encoding="utf-8")
            urls[path] = read_field(text, "source_url") or ""
        for path in paths:
            siblings = sorted(u for p, u in urls.items() if p != path and u)
            if not siblings:
                continue
            text = path.read_text(encoding="utf-8")
            if _extract_list(text) == siblings:
                continue
            new_text = set_list_field(text, _FIELD, siblings)
            files_touched += 1
            if dry_run:
                print(f"سيُحدَّث: {path} ← يرتبط بـ {len(siblings)} نسخة أخرى")
                continue
            path.write_text(new_text, encoding="utf-8")
    return len(groups), files_touched


def _extract_list(text: str) -> list[str]:
    m = _LIST_FIELD_RE.search(text)
    if not m:
        return []
    body = m.group(1).strip()
    if not body:
        return []
    return [unquote(v.strip().strip('"')) for v in body.split(",")]


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.audit_duplicates",
        description="كشف الوثائق المزدوجة العنوان في laws/ وربطها عبر also_available_from",
    )
    parser.add_argument("out", nargs="?", default="laws", help="مجلد المخرجات (افتراضي: laws)")
    parser.add_argument("--dry-run", action="store_true", help="معاينة بلا كتابة")
    args = parser.parse_args(argv)

    out_dir = Path(args.out)
    group_count, touched = annotate_duplicates(out_dir, dry_run=args.dry_run)
    print(f"مجموعات مزدوجة العنوان: {group_count}", file=sys.stderr)
    print(f"{'سيُحدَّث' if args.dry_run else 'حُدِّث'}: {touched} ملفًا", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(run())
