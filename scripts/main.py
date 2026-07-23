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
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from urllib.parse import unquote, urlparse

from .adapters import detect_source, get_adapter
from .adapters.base import ParseError
from .classify import classify_doc_type, resolve_category
from .discover import discover
from .fetch import Fetcher, FetchError
from .formatter import format_document, output_path, sanitize_filename
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
_ETAG_RE = re.compile(r'^etag:\s*"?(.*?)"?\s*$', re.MULTILINE)
_LAST_MODIFIED_RE = re.compile(r'^last_modified:\s*"?(.*?)"?\s*$', re.MULTILINE)
_HEAD_LINES = 25  # هامش يكفي كل حقول الـ front matter الحالية حتى retrieved_at/note
# عنوان مادة في متن Markdown (## أو ### المادة ...)، لكشف أن ملفًا قائمًا يحوي مواد
_ARTICLE_HEADING_MD_RE = re.compile(r"^#{2,3}\s*المادة\s", re.MULTILINE)


def _read_source_url(path: Path) -> str | None:
    """يقرأ source_url من رأس ملف مخرجات موجود (أو None إن تعذّر)."""
    try:
        head = "\n".join(path.read_text(encoding="utf-8").splitlines()[:_HEAD_LINES])
    except OSError:
        return None
    match = _SOURCE_URL_RE.search(head)
    return match.group(1) if match and match.group(1) else None


def _file_has_articles(path: Path) -> bool:
    try:
        return bool(_ARTICLE_HEADING_MD_RE.search(path.read_text(encoding="utf-8")))
    except OSError:
        return False


def _disambiguate_path(path: Path, url: str) -> Path:
    """يشتق اسمًا مميزًا عند تصادم المسار مع وثيقة أخرى، من آخر مقطع في الرابط.

    لـ qanoonsa هذا معرّف المنشور (p/516403 ← 516403)، ولـ nezams اسم
    المقالة (slug) — كلاهما فريد لكل وثيقة، فالنتيجة حتمية وقابلة للتكرار.
    """
    segments = [s for s in urlparse(url).path.split("/") if s]
    disc = unquote(segments[-1]) if segments else "نسخة"
    return path.with_name(sanitize_filename(f"{path.stem} ({disc})") + path.suffix)


def _resolve_collision(path: Path, source_url: str) -> Path:
    """يعيد مسارًا آمنًا للكتابة: يتجنّب طمس وثيقة أخرى تتصادم في الاسم.

    الكتابة فوق ملف قائم مسموحة فقط إن كان لنفس source_url (تحديث في مكانه).
    إن كان لوثيقة مختلفة (تصادم عنوان بعد الاقتطاع، أو نفس العنوان من
    المصدرين) يُشتق اسم مميز؛ ويُكرَّر عند تصادم نادر متتالٍ.
    """
    if not path.exists() or _read_source_url(path) == source_url:
        return path
    candidate = _disambiguate_path(path, source_url)
    counter = 2
    while candidate.exists() and _read_source_url(candidate) != source_url:
        stem = _disambiguate_path(path, source_url).stem
        candidate = candidate.with_name(sanitize_filename(f"{stem} {counter}") + path.suffix)
        counter += 1
    return candidate


@dataclass
class OutputEntry:
    """ما يُستنتج من ملف مخرجات موجود لرابط مصدر واحد."""

    path: Path
    etag: str | None = None
    last_modified: str | None = None


def build_source_index(out_dir: Path) -> dict[str, OutputEntry]:
    """يبني فهرس source_url ← بيانات الملف الحالي لكل مخرجات out_dir.

    يُستخدم لغرضين: تثبيت هوية الوثيقة على source_url بدل مسارها المُشتق
    (عنوان/تصنيف)، إذ يتغيّر هذا المسار مع تطوّر منطق التصنيف — وبدون هذا
    الفهرس تتراكم نسخ يتيمة في مسارات قديمة (انظر process_html) — وتزويد
    الجلب الشرطي (--check-updates) بآخر ETag/Last-Modified معروفين.
    """
    index: dict[str, OutputEntry] = {}
    if not out_dir.exists():
        return index
    for md in out_dir.rglob("*.md"):
        try:
            head = "\n".join(md.read_text(encoding="utf-8").splitlines()[:_HEAD_LINES])
        except OSError:
            continue
        match = _SOURCE_URL_RE.search(head)
        if match and match.group(1):
            etag_m = _ETAG_RE.search(head)
            lm_m = _LAST_MODIFIED_RE.search(head)
            index[match.group(1)] = OutputEntry(
                path=md,
                etag=etag_m.group(1) if etag_m and etag_m.group(1) else None,
                last_modified=lm_m.group(1) if lm_m and lm_m.group(1) else None,
            )
    return index


def load_done_from_output(out_dir: Path) -> set[str]:
    """يستنتج الروابط المنجَزة من ملفات المخرجات نفسها (حقل source_url).

    هذه هي حالة الاستئناف الدائمة: بما أن مجلد laws/ يُلتزَم في git بينما
    logs/ متجاهَل، فإن مسح المخرجات المُلتزَمة يجعل --resume يعمل حتى في
    جلسة جديدة تستنسخ المستودع من الصفر (كحالة الـ Routine).
    """
    return set(build_source_index(out_dir).keys())


def load_done(log_path: Path) -> set[str]:
    if not log_path.exists():
        return set()
    return {
        line.strip()
        for line in log_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


def _prune_empty_dirs(start: Path, root: Path) -> None:
    """يحذف start وأسلافه طالما فارغين، دون تجاوز root."""
    current = start
    try:
        root = root.resolve()
        current = current.resolve()
    except OSError:
        return
    while current != root and root in current.parents:
        try:
            current.rmdir()
        except OSError:
            break
        current = current.parent


def process_html(
    html: str,
    url: str,
    source: str,
    args: argparse.Namespace,
    existing: dict[str, OutputEntry] | None = None,
    etag: str | None = None,
    last_modified: str | None = None,
) -> tuple[LawDocument, list[str]]:
    doc = get_adapter(source).parse(html, url)
    # حارس M-1: ناتج نثري بلا مواد سيطمس ملفًا قائمًا يحوي مواد لنفس الرابط
    # مؤشّر قوي على فشل التقطيع (تغيّر بنية المصدر) لا وثيقة نثرية جديدة —
    # نرفض الكتابة ونسجّله فشلًا بدل تخريب الملف الجيد بصمت
    if existing is not None and doc.body and not doc.articles:
        prior = existing.get(doc.source_url)
        if prior is not None and prior.path.exists() and _file_has_articles(prior.path):
            raise ParseError(
                "ناتج نثري بلا مواد سيطمس ملفًا قائمًا يحوي مواد (يُحتمل تغيّر بنية المصدر)"
            )
    doc.retrieved_at = date.today().isoformat()
    doc.doc_type = classify_doc_type(doc.title, url, doc.is_decision)
    doc.category = args.category or resolve_category(doc.category, doc.doc_type)
    doc.etag = etag
    doc.last_modified = last_modified
    warnings = validate_document(doc)
    for warning in warnings:
        print(f"تحذير [{doc.title}]: {warning}", file=sys.stderr)
    out_dir = Path(args.out)
    path = output_path(doc, out_dir)
    # حارس M-3: لا تكتب فوق وثيقة مختلفة تتصادم في المسار (اقتطاع الاسم أو
    # نفس العنوان من المصدرين). يُحسم قبل نقل الملف القديم حتى تبقى العملية
    # idempotent: الوجهة المميّزة نفسها تُختار في كل تشغيل.
    path = _resolve_collision(path, doc.source_url)
    if existing is not None:
        old_entry = existing.get(doc.source_url)
        if old_entry is not None and old_entry.path != path and old_entry.path.exists():
            old_entry.path.unlink()
            _prune_empty_dirs(old_entry.path.parent, out_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(format_document(doc), encoding="utf-8")
    if existing is not None:
        existing[doc.source_url] = OutputEntry(path=path, etag=doc.etag, last_modified=doc.last_modified)
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
    parser.add_argument(
        "--check-updates",
        action="store_true",
        help=(
            "لروابط سبق استيرادها: جلب شرطي عبر ETag/Last-Modified، وتخطّي "
            "إعادة التحليل والكتابة إن لم يتغيّر المحتوى منذ آخر جلب"
        ),
    )
    args = parser.parse_args(argv)

    if args.html:
        source = args.source or detect_source(args.url)
        if not source:
            parser.error("مع ‎--html يجب تحديد ‎--source أو ‎--url برابط معروف المصدر")
        existing = build_source_index(Path(args.out))
        try:
            process_html(
                Path(args.html).read_text(encoding="utf-8"), args.url, source, args, existing
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

    # فهرس source_url ← مسار الملف الحالي، يُبنى مرة واحدة لكل التشغيلة:
    # يُستخدم لتثبيت هوية الوثيقة (process_html) ولاشتقاق حالة الاستئناف الدائمة
    existing = build_source_index(Path(args.out))
    done: set[str] = set()
    if args.resume:
        done = load_done(DONE_LOG) | set(existing.keys())

    failures = 0
    processed = 0
    skipped = 0
    unchanged = 0
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
            prior = existing.get(url) if args.check_updates else None
            if prior is not None:
                result = fetcher.get_conditional(url, etag=prior.etag, last_modified=prior.last_modified)
                if result.not_modified:
                    processed += 1
                    unchanged += 1
                    print(f"بلا تغيير: {url}")
                    results.append(RunResult(url=url, status="unchanged"))
                    if args.resume:
                        log_done(url, DONE_LOG)
                    continue
                doc, warnings = process_html(
                    result.text, url, source, args, existing,
                    etag=result.etag, last_modified=result.last_modified,
                )
            else:
                html = fetcher.get(url)
                doc, warnings = process_html(html, url, source, args, existing)
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
    if args.check_updates and unchanged:
        print(f"بلا تغيير منذ آخر جلب: {unchanged}", file=sys.stderr)
    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(build_summary(results, skipped=skipped), encoding="utf-8")
        print(f"التقرير ← {report_path}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(run())
