"""يعيد تصنيف ملفات laws/ الحالية وفق منطق classify.py الحالي، دون إعادة سحب من الشبكة.

خلفية المشكلة: منطق التصنيف (classify.py) تطوّر عبر تاريخ الاستيراد
(تبسيط التصنيف، الرجوع لنوع الوثيقة عند غياب تصنيف الموقع، توسعة كشف
"قرار")، لكن الملفات التي كُتبت بمنطق أقدم لم تُعَد معالجتها. النتيجة:
مجلدات تصنيف شبه مكرّرة (خطأ إملائي/همزة/ترتيب كلمات) وتكدّس غير مبرَّر
في laws/غير-مصنف. هذا السكربت يعيد حساب doc_type وcategory من العنوان
والحقول الموجودة فعليًا في كل ملف، وينقل الملف عند اختلاف الناتج.

التعديل يقتصر على سطري doc_type وcategory في الـ front matter وموقع
الملف على القرص؛ لا يُعاد توليد أي محتوى آخر (المتن، بقية الحقول) تفاديًا
لأي فرق تنسيق غير مقصود عن الأصل.

الاستخدام:
    python -m scripts.reclassify laws            # تنفيذ فعلي
    python -m scripts.reclassify laws --dry-run   # معاينة بلا كتابة
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from .classify import classify_doc_type, resolve_category
from .formatter import atomic_write, output_path, prune_empty_dirs
from .frontmatter import read_field, set_field, unquote
from .schema import CLAUSE_NAMES, LawDocument

_TITLE_RE = re.compile(r'^title:\s*"((?:[^"\\]|\\.)*)"\s*$', re.MULTILINE)
_CLAUSE_HEADING_RE = re.compile(
    rf"^#{{2,3}}\s*({'|'.join(CLAUSE_NAMES)})ً?\s*$", re.MULTILINE
)


def _detect_is_decision(body: str) -> bool:
    return bool(_CLAUSE_HEADING_RE.search(body))


def plan_move(path: Path, out_dir: Path) -> tuple[Path, str | None, str | None] | None:
    """يحسب الوجهة الجديدة لملف واحد؛ يعيد None إن تعذّرت قراءة الحقول اللازمة."""
    text = path.read_text(encoding="utf-8")
    m_title = _TITLE_RE.search(text)
    if not m_title:
        return None
    title = unquote(m_title.group(1))
    source_url = read_field(text, "source_url") or ""
    old_doc_type = read_field(text, "doc_type")
    old_category = read_field(text, "category")

    is_decision = _detect_is_decision(text)
    new_doc_type = classify_doc_type(title, source_url, is_decision)
    new_category = resolve_category(old_category, new_doc_type)

    # الوجهة تُحسب بنفس دالة الاستيراد لا بنسخة ثانية من منطق المسار، وإلا
    # اختلفت عنها بصمت (مثل تقسيم مجلدات النوع حسب السنة) فأعاد كل استيراد
    # لاحق الملفات إلى مسارها القديم
    new_path = output_path(
        LawDocument(
            title=title,
            source=read_field(text, "source") or "",
            source_url=source_url,
            category=new_category,
            issued_date=read_field(text, "issued_date"),
            approval_date_hijri=read_field(text, "approval_date_hijri"),
            gazette_ref=read_field(text, "gazette_ref"),
        ),
        out_dir,
    )

    changed_doc_type = new_doc_type if new_doc_type != old_doc_type else None
    changed_category = new_category if new_category != old_category else None
    return new_path, changed_doc_type, changed_category


def reclassify(out_dir: Path, dry_run: bool = False) -> tuple[int, int, list[str]]:
    """يعيد تصنيف كل ملفات out_dir. يعيد (منقول، بلا تغيير، تعارضات غير محلولة)."""
    moved = 0
    unchanged = 0
    conflicts: list[str] = []
    touched_dirs: set[Path] = set()

    for path in sorted(out_dir.rglob("*.md")):
        if path.name == "README.md":  # فهرس مجلد مُولَّد لا وثيقة نظام
            continue
        result = plan_move(path, out_dir)
        if result is None:
            continue
        new_path, changed_doc_type, changed_category = result
        if new_path == path and changed_doc_type is None and changed_category is None:
            unchanged += 1
            continue
        if new_path != path and new_path.exists():
            conflicts.append(f"{path} ← يوجد ملف آخر مسبقًا في {new_path}")
            continue

        text = path.read_text(encoding="utf-8")
        if changed_doc_type is not None:
            text = set_field(text, "doc_type", changed_doc_type)
        if changed_category is not None:
            text = set_field(text, "category", changed_category)

        moved += 1
        if dry_run:
            if new_path != path:
                print(f"نقل: {path} → {new_path}")
            else:
                print(f"تحديث حقول فقط: {path}")
            continue

        if new_path != path:
            # الكتابة أولًا ثم الحذف: العكس يفقد الوثيقة إن فشلت الكتابة
            atomic_write(new_path, text)
            path.unlink()
            touched_dirs.add(path.parent)
        else:
            atomic_write(path, text)

    if not dry_run:
        for d in touched_dirs:
            prune_empty_dirs(d, out_dir)

    return moved, unchanged, conflicts


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.reclassify",
        description="إعادة تصنيف ملفات laws/ الحالية وفق منطق classify.py الحالي",
    )
    parser.add_argument("out", nargs="?", default="laws", help="مجلد المخرجات (افتراضي: laws)")
    parser.add_argument("--dry-run", action="store_true", help="معاينة التغييرات بلا كتابة")
    args = parser.parse_args(argv)

    out_dir = Path(args.out)
    moved, unchanged, conflicts = reclassify(out_dir, dry_run=args.dry_run)
    print(f"{'سيُنقل/يُحدَّث' if args.dry_run else 'نُقل/حُدِّث'}: {moved}", file=sys.stderr)
    print(f"بلا تغيير: {unchanged}", file=sys.stderr)
    if conflicts:
        print(f"تعارضات غير محلولة (تُركت كما هي): {len(conflicts)}", file=sys.stderr)
        for c in conflicts:
            print(f"  - {c}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(run())
