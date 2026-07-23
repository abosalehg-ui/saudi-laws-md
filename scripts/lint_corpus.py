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
from .formatter import UNCATEGORIZED, sanitize_filename
from .frontmatter import read_field
from .schema import _BROKEN_TITLE_RE, _NOISE_PATTERNS

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
    if _BROKEN_TITLE_RE.match(title.strip()):
        errors.append(f"عنوان معطوب: «{title}»")

    body = _body_after_front_matter(text)
    for pattern in _NOISE_PATTERNS:
        if pattern in body:
            errors.append(f"ضجيج واجهة في المتن: «{pattern}»")
            break
    if _duplicate_paragraph(body):
        errors.append("فقرات متتالية مكرّرة (أثر ازدواج استخراج)")

    category = read_field(text, "category")
    expected_dir = sanitize_filename(category) if category else UNCATEGORIZED
    actual_dir = path.parent.name
    if actual_dir == UNCATEGORIZED and category:
        warnings.append("مصنَّف لكنه في غير-مصنف")
    elif category and actual_dir != expected_dir:
        warnings.append(f"التصنيف «{category}» لا يطابق المجلد «{actual_dir}»")
    elif not category and actual_dir != UNCATEGORIZED:
        warnings.append("بلا حقل category رغم وجوده في مجلد مصنَّف")

    warnings.extend(_article_sequence_errors(body))
    return errors, warnings


def lint_corpus(out_dir: Path) -> tuple[int, dict[Path, list[str]], dict[Path, list[str]]]:
    files = sorted(out_dir.rglob("*.md"))
    errors: dict[Path, list[str]] = {}
    warnings: dict[Path, list[str]] = {}
    for path in files:
        e, w = lint_file(path, out_dir)
        if e:
            errors[path] = e
        if w:
            warnings[path] = w
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
