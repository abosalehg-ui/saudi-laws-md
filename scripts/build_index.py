"""يبني فهرسًا آليًا (index.json) لكل وثائق laws/ من بياناتها الوصفية.

يفتح المُدوَّنة لأدوات البحث وRAG دون مسح آلاف الملفات: كل مدخل يحمل
العنوان والنوع والتصنيف والحالة والمصدر والرابط والمسار النسبي. المخرجات
مرتّبة حسب المسار لتقليل ضجيج الفروق في git بين التشغيلات.

الاستخدام:
    python -m scripts.build_index laws --out index.json
    python -m scripts.build_index laws --check   # يتحقق أن index.json محدَّث (لـ CI)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from .frontmatter import read_field, unquote

_LIST_FIELD_RE = re.compile(r'^also_available_from:\s*\[(.*?)\]\s*$', re.MULTILINE)
_FIELDS = ("title", "doc_type", "category", "status", "source", "source_url")


def _also_available(text: str) -> list[str]:
    m = _LIST_FIELD_RE.search(text)
    if not m or not m.group(1).strip():
        return []
    return [unquote(v.strip().strip('"')) for v in m.group(1).split(",")]


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
        also = _also_available(text)
        if also:
            entry["also_available_from"] = also
        entries.append(entry)
    return entries


def _serialize(entries: list[dict]) -> str:
    return json.dumps(entries, ensure_ascii=False, indent=2) + "\n"


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.build_index",
        description="بناء فهرس index.json لمُدوَّنة laws/",
    )
    parser.add_argument("out", nargs="?", default="laws", help="مجلد المخرجات (افتراضي: laws)")
    parser.add_argument("--out-file", default="index.json", help="ملف الفهرس (افتراضي: index.json)")
    parser.add_argument(
        "--check", action="store_true",
        help="التحقق أن الفهرس محدَّث دون كتابته (رمز خروج ≠0 إن تغيّر) — لـ CI",
    )
    args = parser.parse_args(argv)

    entries = build_index(Path(args.out))
    payload = _serialize(entries)
    index_path = Path(args.out_file)

    if args.check:
        current = index_path.read_text(encoding="utf-8") if index_path.exists() else ""
        if current != payload:
            print(
                f"{index_path} غير محدَّث؛ شغّل: python -m scripts.build_index {args.out}",
                file=sys.stderr,
            )
            return 1
        print(f"{index_path} محدَّث ({len(entries)} وثيقة).", file=sys.stderr)
        return 0

    index_path.write_text(payload, encoding="utf-8")
    print(f"كُتب {index_path} ({len(entries)} وثيقة).", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(run())
