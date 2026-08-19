"""فحص صحة مُدوَّنة laws/ الملتزمة (لا الاستيراد اللحظي فقط).

بينما ``validate_document`` يفحص وثيقة لحظة سحبها، لا شيء يفحص آلاف الملفات
المخزَّنة بعد ذلك. هذا السكربت يعيد فحصها من القرص ويصنّف النتائج إلى:

- **أخطاء صلبة** (تُفشل CI): عنوان معطوب (``#REF!`` ونحوه)، غياب حقل إلزامي
  (title/source_url)، بقايا ضجيج واجهة في المتن، فقرات متتالية مكرّرة
  (أثر ازدواج الاستخراج) — كلها أعطال استخراج لا خلاف تحريري فيها.
- **تحذيرات** (تُطبع ولا تُفشل): تصنيف ناقص، تصنيف لا يطابق اسم المجلد،
  خلل تسلسل المواد، مواد فارغة — قد يكون بعضها مشروعًا (فجوة حقيقية في
  الترقيم، وثيقة بلا مجال موضوعي).

الاستخدام:
    python -m scripts.lint_corpus laws            # فحص، رمز خروج ≠0 عند خطأ صلب
    python -m scripts.lint_corpus laws --strict    # يُفشل عند أي تحذير أيضًا
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from .arabic_numbers import parse_article_label
from .formatter import MAX_FILES_PER_DIR, UNCATEGORIZED, category_dir
from .frontmatter import read_field
from .schema import (
    BROKEN_TITLE_RE,
    CONTENT_INCOMPLETE,
    INCOMPLETE_BODY_NOTE,
    MIN_BODY_CHARS,
    NOISE_PATTERNS,
)
from .schema import LawDocument as _Doc
from .status import VALID_STATUSES

_ARTICLE_HEADING_RE = re.compile(r"^#{2,3}\s+المادة\s+(.+?)\s*$", re.MULTILINE)
_PARA_SPLIT_RE = re.compile(r"\n\s*\n")
_REQUIRED_FIELDS = ("title", "source_url")


def _body_after_front_matter(text: str) -> str:
    m = re.match(r"\A---\n.*?\n---\n(.*)", text, re.S)
    return m.group(1) if m else text


def _article_sequence_errors(body: str) -> list[str]:
    """تسلسل المواد من عناوين Markdown (تحذيرات لا أخطاء صلبة)."""
    labels = _ARTICLE_HEADING_RE.findall(body)
    warnings: list[str] = []
    prev: int | None = None
    for label in labels:
        number_int, is_bis = parse_article_label(label)
        if number_int is None:
            continue
        if is_bis:
            continue
        if prev is not None and number_int != prev + 1:
            warnings.append(f"خلل تسلسل: بعد {prev} جاءت {number_int}")
        prev = number_int
    return warnings


def _duplicate_paragraph(body: str) -> bool:
    paras = [p.strip() for p in _PARA_SPLIT_RE.split(body) if p.strip()]
    for a, b in zip(paras, paras[1:], strict=False):
        if a == b and len(a) > 25 and not a.startswith(("#", "|", ">", "-")):
            return True
    return False


def lint_file(path: Path, out_dir: Path) -> tuple[list[str], list[str]]:
    """يعيد (أخطاء صلبة، تحذيرات) لملف واحد."""
    text = path.read_text(encoding="utf-8")
    errors: list[str] = []
    warnings: list[str] = []

    for field in _REQUIRED_FIELDS:
        if not read_field(text, field):
            errors.append(f"حقل إلزامي ناقص: {field}")

    title = read_field(text, "title") or ""
    if BROKEN_TITLE_RE.match(title.strip()):
        errors.append(f"عنوان معطوب: «{title}»")

    body = _body_after_front_matter(text)
    # وثيقة بلا أي متن بعد عنوانها (front matter + # عنوان فقط) عطلُ استخراجٍ
    # صامت — validate_document يرصده لحظة السحب، لكن لا شيء كان يرصده في
    # المُدوَّنة المُلتزَمة، فتراكمت 132 وثيقة جوفاء مرّت عبر CI بصمت
    content = re.sub(r"^\s*#\s.*$", "", body, count=1, flags=re.MULTILINE).strip()
    content_status = read_field(text, "content_status")
    if not content:
        errors.append("وثيقة بلا متن: front matter وعنوان فقط")
    elif (
        len(content) < MIN_BODY_CHARS or content == INCOMPLETE_BODY_NOTE
    ) and content_status != CONTENT_INCOMPLETE:
        # وثيقة جوفاء غير معلَّمة: إمّا عطل استخراج (يجب إصلاحه) وإمّا صفحة
        # مصدر بلا نصّ (يجب تعليمها content_status: ناقص صراحةً). الحالتان
        # تستوجبان تدخّلًا، فهي خطأ صلب لا تحذير — وإلا تسرّبت بصمت كما حدث
        errors.append(
            f"متن جوفاء ({len(content)} < {MIN_BODY_CHARS} محرفًا) بلا "
            f"content_status: {CONTENT_INCOMPLETE}"
        )
    elif (
        content_status == CONTENT_INCOMPLETE
        and len(content) >= MIN_BODY_CHARS
        and content != INCOMPLETE_BODY_NOTE
    ):
        warnings.append("معلَّمة content_status: ناقص رغم أن لها متنًا كاملًا؛ أزِل العلامة")

    status = read_field(text, "status")
    if status and status not in VALID_STATUSES:
        errors.append(
            f"قيمة status خارج المجموعة المغلقة: «{status}» "
            f"(المسموح: {'، '.join(sorted(VALID_STATUSES))})"
        )

    for pattern in NOISE_PATTERNS:
        if pattern in body:
            errors.append(f"ضجيج واجهة في المتن: «{pattern}»")
            break
    if _duplicate_paragraph(body):
        errors.append("فقرات متتالية مكرّرة (أثر ازدواج استخراج)")

    category = read_field(text, "category")
    # الوجهة المتوقّعة تُحسب بنفس دالة الاستيراد (بما فيها تقسيم مجلدات
    # النوع حسب السنة)، لا بمقارنة اسم المجلد الأخير وحده — وإلا عُدّت كل
    # وثيقة في laws/قرار/<سنة>/ مخالِفة لتصنيفها
    expected_dir = category_dir(
        _Doc(
            title="",
            source="",
            source_url="",
            category=category,
            issued_date=read_field(text, "issued_date"),
            approval_date_hijri=read_field(text, "approval_date_hijri"),
            gazette_ref=read_field(text, "gazette_ref"),
        )
    )
    actual_dir = path.parent.relative_to(out_dir)
    if actual_dir.parts[0] == UNCATEGORIZED and category:
        warnings.append("مصنَّف لكنه في غير-مصنف")
    elif category and actual_dir != expected_dir:
        warnings.append(f"التصنيف «{category}» يتوقّع المجلد «{expected_dir}» لا «{actual_dir}»")
    elif not category and actual_dir.parts[0] != UNCATEGORIZED:
        warnings.append("بلا حقل category رغم وجوده في مجلد مصنَّف")

    warnings.extend(_article_sequence_errors(body))
    return errors, warnings


def _oversized_dirs(out_dir: Path) -> list[str]:
    """مجلدات تجاوزت الحدّ المقروء.

    عارض الملفات في GitHub يقطع عرض المجلد عند 1000 عنصر، فما زاد عنها
    يصير غير قابل للوصول بالتصفّح أصلًا. الحدّ هنا أقلّ من ذلك بهامش،
    ليصل الإنذار قبل أن تُفقد أي وثيقة من العرض.
    """
    oversized = []
    for path in sorted(out_dir.rglob("*")):
        if not path.is_dir():
            continue
        count = sum(1 for f in path.glob("*.md") if f.name != "README.md")
        if count > MAX_FILES_PER_DIR:
            oversized.append(f"{path}: {count} ملفًا (الحدّ {MAX_FILES_PER_DIR})")
    return oversized


def lint_corpus(out_dir: Path) -> tuple[int, dict[Path, list[str]], dict[Path, list[str]]]:
    # README.md وثائق توضيحية للمجلد لا وثائق نظام؛ تُستثنى من الفحص
    files = [p for p in sorted(out_dir.rglob("*.md")) if p.name != "README.md"]
    errors: dict[Path, list[str]] = {}
    warnings: dict[Path, list[str]] = {}
    for path in files:
        e, w = lint_file(path, out_dir)
        if e:
            errors[path] = e
        if w:
            warnings[path] = w
    oversized = _oversized_dirs(out_dir)
    if oversized:
        warnings[out_dir] = [f"مجلد أكبر من الحدّ المقروء — {item}" for item in oversized]
    return len(files), errors, warnings


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.lint_corpus",
        description="فحص صحة مُدوَّنة laws/ الملتزمة",
    )
    parser.add_argument("out", nargs="?", default="laws", help="مجلد المخرجات (افتراضي: laws)")
    parser.add_argument("--strict", action="store_true", help="اعتبار التحذيرات أخطاءً مُفشِلة")
    parser.add_argument("--warnings", action="store_true", help="طباعة التحذيرات أيضًا")
    args = parser.parse_args(argv)

    total, errors, warnings = lint_corpus(Path(args.out))
    print(f"فُحص {total} ملفًا.", file=sys.stderr)

    if errors:
        print(f"\nأخطاء صلبة في {len(errors)} ملفًا:", file=sys.stderr)
        for path, msgs in errors.items():
            print(f"  {path}", file=sys.stderr)
            for m in msgs:
                print(f"    - {m}", file=sys.stderr)

    warn_count = sum(len(v) for v in warnings.values())
    if warnings and (args.warnings or args.strict):
        print(f"\nتحذيرات ({warn_count}) في {len(warnings)} ملفًا:", file=sys.stderr)
        for path, msgs in warnings.items():
            print(f"  {path}", file=sys.stderr)
            for m in msgs:
                print(f"    - {m}", file=sys.stderr)
    elif warnings:
        print(f"تحذيرات: {warn_count} (شغّل بـ --warnings لعرضها)", file=sys.stderr)

    if errors:
        return 1
    if args.strict and warnings:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(run())
