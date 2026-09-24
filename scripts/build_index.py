"""يبني فهرسًا آليًا (index.json) وفهارس تصفّح (README.md) لمُدوَّنة laws/.

ثلاثة مخرجات مُولَّدة كلها من نفس المسح:

1. ``index.json`` — مدخل لكل وثيقة (عنوان، نوع، تصنيف، حالة، مصدر، رابط،
   تواريخ آلية، مسار) لأدوات البحث وRAG دون مسح آلاف الملفات. مرتّب حسب
   المسار لتقليل ضجيج الفروق في git.
2. ``laws/<تصنيف>/README.md`` — فهرس تصفّح لكل مجلد: جدول بالعناوين
   والأنواع والتواريخ والروابط. بدونه يجد من يفتح المجلد جدارًا من مئات
   أسماء الملفات بلا أي دليل.
3. عدّاد الوثائق في ``README.md`` الجذر بين علامتين، فلا يتقادم يدويًا.

الاستخدام:
    python -m scripts.build_index laws --out index.json
    python -m scripts.build_index laws --check   # يتحقق أن كل ما سبق محدَّث (لـ CI)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from .classify import VALID_TYPES
from .formatter import UNCATEGORIZED, atomic_write
from .frontmatter import read_field, read_list_field

_FIELDS = (
    "title",
    "doc_type",
    "category",
    "status",
    "status_note",
    "source",
    "source_url",
    "issued_date_hijri",
    "publish_date_gregorian",
    "content_status",
)


def build_index(out_dir: Path) -> list[dict]:
    entries: list[dict] = []
    for path in sorted(out_dir.rglob("*.md")):
        if path.name == "README.md":  # وثيقة توضيحية للمجلد لا وثيقة نظام
            continue
        text = path.read_text(encoding="utf-8")
        entry = {"path": path.as_posix()}
        for field in _FIELDS:
            value = read_field(text, field)
            if value:
                entry[field] = value
        also = read_list_field(text, "also_available_from")
        if also:
            entry["also_available_from"] = also
        entries.append(entry)
    return entries


def _serialize(entries: list[dict]) -> str:
    return json.dumps(entries, ensure_ascii=False, indent=2) + "\n"


_ROOT_README = Path("README.md")
_COUNT_START = "<!-- corpus-count -->"
_COUNT_END = "<!-- /corpus-count -->"
_COUNT_RE = re.compile(re.escape(_COUNT_START) + r".*?" + re.escape(_COUNT_END), re.S)

_INCOMPLETE_MARK = "◐"


def _cell(value: str) -> str:
    """يهرّب أنبوب Markdown داخل خلية الجدول."""
    return value.replace("|", "\\|")


def directory_readme(directory: Path, entries: list[dict]) -> str:
    """فهرس تصفّح لمجلد واحد: جدول مرتّب بالعنوان."""
    rows = sorted(entries, key=lambda e: e.get("title", ""))
    incomplete = sum(1 for e in rows if e.get("content_status"))
    lines = [
        f"# {directory.name}",
        "",
        f"{len(rows)} وثيقة في هذا المجلد. فهرس مُولَّد آليًا (`python -m scripts.build_index`) — لا يُحرَّر يدويًا.",
        "",
    ]
    if incomplete:
        lines += [
            f"> {incomplete} وثيقة معلَّمة بـ {_INCOMPLETE_MARK}: المصدر يعرض "
            "بياناتها الوصفية دون نصّها (النصّ في مرفق لدى الموقع الأصل).",
            "",
        ]
    lines += [
        "| الوثيقة | النوع | التاريخ الهجري | الحالة | المصدر |",
        "| --- | --- | --- | --- | --- |",
    ]
    for entry in rows:
        name = Path(entry["path"]).name
        title = _cell(entry.get("title", name))
        mark = f" {_INCOMPLETE_MARK}" if entry.get("content_status") else ""
        lines.append(
            f"| [{title}{mark}](<{name}>) "
            f"| {_cell(entry.get('doc_type', '—'))} "
            f"| {entry.get('issued_date_hijri', '—')} "
            f"| {_cell(entry.get('status', '—'))} "
            f"| [{entry.get('source', '—')}]({entry.get('source_url', '')}) |"
        )
    return "\n".join(lines) + "\n"


def subfolder_readme(directory: Path, counts: dict[str, int]) -> str:
    """فهرس مجلد وسيط (لا وثائق فيه مباشرةً، بل مجلدات فرعية): اسم كل فرع وعدده.

    بدونه يفتح القارئ ``laws/قرار/`` فيجد أسماء سنوات بلا عدد ولا دليل.
    """
    total = sum(counts.values())
    lines = [
        f"# {directory.name}",
        "",
        f"{total} وثيقة موزّعة على {len(counts)} مجلدًا فرعيًا. فهرس مُولَّد آليًا "
        "(`python -m scripts.build_index`) — لا يُحرَّر يدويًا.",
        "",
        "| المجلد | عدد الوثائق |",
        "| --- | --- |",
    ]
    for name in sorted(counts):
        lines.append(f"| [{_cell(name)}](<{name}/README.md>) | {counts[name]} |")
    return "\n".join(lines) + "\n"


def directory_readmes(entries: list[dict], out_dir: Path | None = None) -> dict[Path, str]:
    """يجمع الفهارس المطلوبة لكل مجلد يحوي وثائق، ولكل مجلد وسيط فوقه."""
    by_dir: dict[Path, list[dict]] = {}
    for entry in entries:
        by_dir.setdefault(Path(entry["path"]).parent, []).append(entry)
    readmes = {d / "README.md": directory_readme(d, rows) for d, rows in by_dir.items()}
    if out_dir is None:
        return readmes
    # المجلدات الوسيطة: أسلاف مجلدات الوثائق دون مجلد المخرجات نفسه، وليس
    # فيها وثائق مباشرة (فهرسها جدول مجلدات فرعية لا جدول وثائق)
    subfolders: dict[Path, dict[str, int]] = {}
    for directory, rows in by_dir.items():
        child = directory
        for parent in directory.parents:
            if parent == out_dir or out_dir not in parent.parents:
                break
            counts = subfolders.setdefault(parent, {})
            counts[child.name] = counts.get(child.name, 0) + len(rows)
            child = parent
    for directory, counts in subfolders.items():
        if directory not in by_dir:
            readmes[directory / "README.md"] = subfolder_readme(directory, counts)
    return readmes


_BROWSE_START = "<!-- browse -->"
_BROWSE_END = "<!-- /browse -->"
_BROWSE_RE = re.compile(re.escape(_BROWSE_START) + r".*?" + re.escape(_BROWSE_END), re.S)


def browse_section(entries: list[dict], out_dir: Path) -> str:
    """جدولا تصفّح لمجلدات المستوى الأول: حسب المجال، وحسب نوع الوثيقة.

    المُدوَّنة تجمع محورين في مستوى واحد — مجلدات مجال (``أنظمة الصحة``)
    ومجلدات نوع (``لائحة``، ``قرار``) لوثائق لم يصنّفها مصدرها — فيُفصلان
    هنا صراحةً حتى يعرف القارئ أين يبحث.
    """
    counts: dict[str, int] = {}
    for entry in entries:
        parts = Path(entry["path"]).relative_to(out_dir).parts
        if len(parts) > 1:
            counts[parts[0]] = counts.get(parts[0], 0) + 1
    type_dirs = VALID_TYPES | {UNCATEGORIZED}
    groups = (
        ("حسب المجال", sorted(n for n in counts if n not in type_dirs)),
        ("حسب نوع الوثيقة (وثائق لم يحدّد مصدرها مجالًا)", sorted(n for n in counts if n in type_dirs)),
    )
    lines = [
        _BROWSE_START,
        "",
        f"{sum(counts.values()):,} وثيقة. جدولان مُولَّدان آليًا (`python -m scripts.build_index`).",
    ]
    for heading, names in groups:
        if not names:
            continue
        lines += ["", f"### {heading}", "", "| المجلد | عدد الوثائق |", "| --- | --- |"]
        lines += [f"| [{_cell(n)}](<{n}/README.md>) | {counts[n]:,} |" for n in names]
    lines += ["", _BROWSE_END]
    return "\n".join(lines)


def out_readme_with_browse(text: str, entries: list[dict], out_dir: Path) -> str:
    """يحدّث قسم التصفّح بين العلامتين في README مجلد المخرجات (إن وُجدتا)."""
    return _BROWSE_RE.sub(lambda _: browse_section(entries, out_dir), text)


def root_readme_with_count(text: str, count: int) -> str:
    """يحدّث عدّاد الوثائق بين العلامتين في README الجذر (إن وُجدتا)."""
    return _COUNT_RE.sub(f"{_COUNT_START}{count:,}{_COUNT_END}", text)


def _generated_files(entries: list[dict], index_path: Path, out_dir: Path) -> dict[Path, str]:
    """كل الملفات المُولَّدة ومحتواها المتوقّع — مصدر واحد للكتابة والتحقق."""
    files: dict[Path, str] = {index_path: _serialize(entries)}
    files.update(directory_readmes(entries, out_dir))
    out_readme = out_dir / "README.md"
    if out_readme.exists():
        current = out_readme.read_text(encoding="utf-8")
        updated = out_readme_with_browse(current, entries, out_dir)
        if updated != current:
            files[out_readme] = updated
    if _ROOT_README.exists():
        current = _ROOT_README.read_text(encoding="utf-8")
        updated = root_readme_with_count(current, len(entries))
        if updated != current:
            files[_ROOT_README] = updated
    return files


def _orphan_readmes(out_dir: Path, generated: dict[Path, str]) -> list[Path]:
    """فهارس مجلدات لم تعد لها وثائق (نُقلت كلها) — تُحذف بدل أن تتقادم."""
    return [path for path in sorted(out_dir.rglob("README.md")) if path not in generated and path.parent != out_dir]


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.build_index",
        description="بناء فهرس index.json لمُدوَّنة laws/",
    )
    parser.add_argument("out", nargs="?", default="laws", help="مجلد المخرجات (افتراضي: laws)")
    parser.add_argument("--out-file", default="index.json", help="ملف الفهرس (افتراضي: index.json)")
    parser.add_argument(
        "--check",
        action="store_true",
        help="التحقق أن الفهرس محدَّث دون كتابته (رمز خروج ≠0 إن تغيّر) — لـ CI",
    )
    args = parser.parse_args(argv)

    entries = build_index(Path(args.out))
    index_path = Path(args.out_file)
    generated = _generated_files(entries, index_path, Path(args.out))

    if args.check:
        stale = [
            path
            for path, payload in generated.items()
            if (path.read_text(encoding="utf-8") if path.exists() else "") != payload
        ]
        # فهرس مجلد بقي بعد نقل آخر وثائقه = ملف مُولَّد يتيم يجب حذفه
        orphans = _orphan_readmes(Path(args.out), generated)
        if stale or orphans:
            for path in stale + orphans:
                print(f"  {path}", file=sys.stderr)
            print(
                f"ملفات مُولَّدة غير محدَّثة؛ شغّل: python -m scripts.build_index {args.out}",
                file=sys.stderr,
            )
            return 1
        print(
            f"{index_path} و{len(generated) - 1} فهرس مجلد محدَّثة ({len(entries)} وثيقة).",
            file=sys.stderr,
        )
        return 0

    for path, payload in generated.items():
        atomic_write(path, payload)
    for path in _orphan_readmes(Path(args.out), generated):
        path.unlink()
    print(
        f"كُتب {index_path} و{len(generated) - 1} فهرس مجلد ({len(entries)} وثيقة).",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(run())
