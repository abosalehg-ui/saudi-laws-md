"""نقطة الدخول: يحدد المصدر من الرابط ويستدعي الـ adapter المناسب ثم يكتب الناتج.

أمثلة:
    python -m scripts.main https://nezams.com/نظام-العمل/
    python -m scripts.main --from-file urls.txt --out laws
    python -m scripts.main --html page.html --source nezams --url https://nezams.com/...
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

from .adapters import detect_source, get_adapter
from .adapters.base import ParseError
from .classify import classify_doc_type
from .fetch import Fetcher, FetchError
from .formatter import format_document, output_path
from .schema import validate_document

FAILED_LOG = Path("logs/failed.txt")
DONE_LOG = Path("logs/done.txt")


def log_failure(target: str, reason: str) -> None:
    FAILED_LOG.parent.mkdir(parents=True, exist_ok=True)
    with FAILED_LOG.open("a", encoding="utf-8") as f:
        f.write(f"{datetime.now().isoformat(timespec='seconds')}\t{target}\t{reason}\n")


def log_done(url: str, log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(url + "\n")


def load_done(log_path: Path) -> set[str]:
    if not log_path.exists():
        return set()
    return {
        line.strip()
        for line in log_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


def process_html(html: str, url: str, source: str, args: argparse.Namespace) -> Path:
    doc = get_adapter(source).parse(html, url)
    doc.retrieved_at = date.today().isoformat()
    doc.doc_type = classify_doc_type(doc.title, url, doc.is_decision)
    if args.category:
        doc.category = args.category
    for warning in validate_document(doc):
        print(f"تحذير [{doc.title}]: {warning}", file=sys.stderr)
    path = output_path(doc, Path(args.out))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(format_document(doc), encoding="utf-8")
    if doc.body:
        unit = "وثيقة نصية"
        count = ""
    else:
        unit = "بند" if doc.is_decision else "مادة"
        count = f"{len(doc.articles)} "
    print(f"[{doc.doc_type}] {count}{unit} ← {path}")
    return path


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.main",
        description="تحويل صفحات الأنظمة السعودية (qanoonsa.com / nezams.com) إلى Markdown موحد",
    )
    parser.add_argument("urls", nargs="*", help="روابط الصفحات المراد سحبها")
    parser.add_argument("--from-file", help="ملف يحوي رابطًا في كل سطر")
    parser.add_argument("--html", help="ملف HTML محلي (وضع بدون شبكة)")
    parser.add_argument("--source", choices=["qanoonsa", "nezams"], help="المصدر عند استخدام --html")
    parser.add_argument("--url", default="", help="الرابط الأصلي عند استخدام --html")
    parser.add_argument("--out", default="laws", help="مجلد المخرجات (افتراضي: laws)")
    parser.add_argument("--category", help="فرض تصنيف محدد بدل المستخرج من الصفحة")
    parser.add_argument("--delay", type=float, default=1.5, help="التأخير بين الطلبات بالثواني")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="تخطّي الروابط المسجّلة في logs/done.txt (لاستئناف الاستيراد عبر جلسات)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="حد أقصى لعدد الروابط الجديدة المعالَجة في هذه الدفعة ثم التوقف",
    )
    args = parser.parse_args(argv)

    if args.html:
        source = args.source or detect_source(args.url)
        if not source:
            parser.error("مع ‎--html يجب تحديد ‎--source أو ‎--url برابط معروف المصدر")
        try:
            process_html(
                Path(args.html).read_text(encoding="utf-8"), args.url, source, args
            )
        except (ParseError, OSError) as exc:
            log_failure(args.html, str(exc))
            print(f"فشل: {args.html}: {exc}", file=sys.stderr)
            return 1
        return 0

    urls = list(args.urls)
    if args.from_file:
        lines = Path(args.from_file).read_text(encoding="utf-8").splitlines()
        urls += [line.strip() for line in lines if line.strip() and not line.startswith("#")]
    if not urls:
        parser.error("لم يُمرر أي رابط (أو استخدم --html لملف محلي)")

    done = load_done(DONE_LOG) if args.resume else set()

    fetcher = Fetcher(delay=args.delay)
    failures = 0
    processed = 0
    skipped = 0
    for url in urls:
        if args.resume and url in done:
            skipped += 1
            continue
        if args.limit is not None and processed >= args.limit:
            print(
                f"بلغت الدفعة حدّها ({args.limit})؛ توقّف. المتبقي يُعالَج في تشغيل لاحق.",
                file=sys.stderr,
            )
            break
        source = detect_source(url)
        if not source:
            log_failure(url, "مصدر غير معروف")
            print(f"تخطي: مصدر غير معروف: {url}", file=sys.stderr)
            failures += 1
            continue
        try:
            html = fetcher.get(url)
            process_html(html, url, source, args)
        except (FetchError, ParseError, OSError) as exc:
            log_failure(url, str(exc))
            print(f"فشل: {url}: {exc}", file=sys.stderr)
            failures += 1
        else:
            processed += 1
            if args.resume:
                log_done(url, DONE_LOG)
    if args.resume and skipped:
        print(f"تُخطّي {skipped} رابطًا مكتملًا سابقًا.", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(run())
