"""نقطة الدخول: يحدد المصدر من الرابط ويستدعي الـ adapter المناسب ثم يكتب الناتج.

أمثلة:
    python -m scripts.main https://nezams.com/نظام-العمل/
    python -m scripts.main --from-file urls.txt --out laws
    python -m scripts.main --html page.html --source nezams --url https://nezams.com/...
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date, datetime
from pathlib import Path

from .adapters import detect_source, get_adapter
from .adapters.base import ParseError
from .classify import classify_doc_type, resolve_category
from .discover import discover
from .fetch import Fetcher, FetchError
from .formatter import format_document, output_path
from .report import RunResult, build_summary
from .schema import LawDocument, validate_document

FAILED_LOG = Path("logs/failed.txt")
DONE_LOG = Path("logs/done.txt")
SUMMARY_FILE = Path("logs/summary.md")


def log_failure(target: str, reason: str) -> None:
    FAILED_LOG.parent.mkdir(parents=True, exist_ok=True)
    with FAILED_LOG.open("a", encoding="utf-8") as f:
        f.write(f"{datetime.now().isoformat(timespec='seconds')}\t{target}\t{reason}\n")


def log_done(url: str, log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(url + "\n")


_SOURCE_URL_RE = re.compile(r'^source_url:\s*"?(.*?)"?\s*$', re.MULTILINE)


def load_done_from_output(out_dir: Path) -> set[str]:
    """يستنتج الروابط المنجَزة من ملفات المخرجات نفسها (حقل source_url).

    هذه هي حالة الاستئناف الدائمة: بما أن مجلد laws/ يُلتزَم في git بينما
    logs/ متجاهَل، فإن مسح المخرجات المُلتزَمة يجعل --resume يعمل حتى في
    جلسة جديدة تستنسخ المستودع من الصفر (كحالة الـ Routine).
    """
    done: set[str] = set()
    if not out_dir.exists():
        return done
    for md in out_dir.rglob("*.md"):
        try:
            head = "\n".join(md.read_text(encoding="utf-8").splitlines()[:15])
        except OSError:
            continue
        match = _SOURCE_URL_RE.search(head)
        if match and match.group(1):
            done.add(match.group(1))
    return done


def load_done(log_path: Path) -> set[str]:
    if not log_path.exists():
        return set()
    return {
        line.strip()
        for line in log_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


def process_html(
    html: str, url: str, source: str, args: argparse.Namespace
) -> tuple[LawDocument, list[str]]:
    doc = get_adapter(source).parse(html, url)
    doc.retrieved_at = date.today().isoformat()
    doc.doc_type = classify_doc_type(doc.title, url, doc.is_decision)
    doc.category = args.category or resolve_category(doc.category, doc.doc_type)
    warnings = validate_document(doc)
    for warning in warnings:
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
    return doc, warnings


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.main",
        description="تحويل صفحات الأنظمة السعودية (qanoonsa.com / nezams.com) إلى Markdown موحد",
    )
    parser.add_argument("urls", nargs="*", help="روابط الصفحات المراد سحبها")
    parser.add_argument(
        "--discover",
        metavar="SOURCES",
        help="اكتشاف الروابط من الخرائط مباشرةً (qanoonsa و/أو nezams مفصولة بفاصلة)",
    )
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
    parser.add_argument(
        "--include-updates",
        action="store_true",
        help="مع --discover: إدراج صفحات تعديلات المواد المفردة (nezams)",
    )
    parser.add_argument(
        "--report",
        nargs="?",
        const=str(SUMMARY_FILE),
        help="كتابة تقرير ملخّص للتشغيلة (افتراضيًا logs/summary.md)",
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

    fetcher = Fetcher(delay=args.delay)

    urls = list(args.urls)
    if args.from_file:
        lines = Path(args.from_file).read_text(encoding="utf-8").splitlines()
        urls += [line.strip() for line in lines if line.strip() and not line.startswith("#")]
    if args.discover:
        sources = [s.strip() for s in args.discover.split(",") if s.strip()]
        for source in sources:
            print(f"اكتشاف روابط {source}…", file=sys.stderr)
            try:
                found = discover(source, fetcher, include_updates=args.include_updates)
            except (FetchError, ValueError) as exc:
                print(f"فشل اكتشاف {source}: {exc}", file=sys.stderr)
                continue
            print(f"{source}: {len(found)} رابط", file=sys.stderr)
            urls += found
    if not urls:
        parser.error("لم يُمرر أي رابط (استخدم روابط مباشرة أو --from-file أو --discover أو --html)")

    # حالة الاستئناف = سجل الجلسة (logs/done.txt) ∪ ما هو مُلتزَم في المخرجات
    done: set[str] = set()
    if args.resume:
        done = load_done(DONE_LOG) | load_done_from_output(Path(args.out))

    failures = 0
    processed = 0
    skipped = 0
    results: list[RunResult] = []
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
            results.append(RunResult(url=url, status="failed", reason="مصدر غير معروف"))
            continue
        try:
            html = fetcher.get(url)
            doc, warnings = process_html(html, url, source, args)
        except (FetchError, ParseError, OSError) as exc:
            log_failure(url, str(exc))
            print(f"فشل: {url}: {exc}", file=sys.stderr)
            failures += 1
            results.append(RunResult(url=url, status="failed", reason=str(exc)))
        else:
            processed += 1
            results.append(RunResult(
                url=url, status="ok", title=doc.title,
                doc_type=doc.doc_type, warnings=warnings,
            ))
            if args.resume:
                log_done(url, DONE_LOG)
    if args.resume and skipped:
        print(f"تُخطّي {skipped} رابطًا مكتملًا سابقًا.", file=sys.stderr)
    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(build_summary(results, skipped=skipped), encoding="utf-8")
        print(f"التقرير ← {report_path}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(run())
