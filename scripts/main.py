"""نقطة الدخول: يحدد المصدر من الرابط ويستدعي الـ adapter المناسب ثم يكتب الناتج.

أمثلة:
    python -m scripts.main https://nezams.com/نظام-العمل/
    python -m scripts.main --from-file urls.txt --out laws
    python -m scripts.main --html page.html --source nezams --url https://nezams.com/...
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from urllib.parse import unquote, urlparse

from .adapters import detect_source, get_adapter, host_allowed
from .adapters.base import ParseError
from .classify import classify_doc_type, resolve_category
from .dates import parse_gregorian, parse_hijri
from .discover import discover
from .fetch import Fetcher, FetchError
from .formatter import (
    atomic_write,
    disambiguated_filename,
    ensure_within,
    format_document,
    output_path,
    prune_empty_dirs,
)
from .report import RunResult, build_summary
from .schema import MIN_BODY_CHARS, LawDocument, body_length, validate_document
from .status import normalize_status
from .urls import canonical_url

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
# حدّ أمان لعدد أسطر الـ front matter (يمنع قراءة ملف ضخم بلا فاصل ثانٍ)
_MAX_FRONT_MATTER_LINES = 100
# عنوان مادة في متن Markdown (## أو ### المادة ...)، لكشف أن ملفًا قائمًا يحوي مواد
_ARTICLE_HEADING_MD_RE = re.compile(r"^#{2,3}\s*المادة\s", re.MULTILINE)


def _front_matter_head(path: Path) -> str:
    """يقرأ كتلة الـ front matter فقط (حتى الفاصل ``---`` الثاني)، بلا قراءة
    كامل الملف. حدٌّ بنيوي لا عددي (يزيل الرقم السحري السابق)، ويوفّر قراءة
    آلاف الملفات الكاملة في كل تشغيلة (كان يُقرأ الملف كله ثم يُقتطع)."""
    lines: list[str] = []
    try:
        with path.open(encoding="utf-8") as f:
            first = f.readline()
            if first.rstrip("\n") != "---":
                return ""  # لا front matter
            for line in f:
                if line.rstrip("\n") == "---" or len(lines) >= _MAX_FRONT_MATTER_LINES:
                    break
                lines.append(line)
    except OSError:
        return ""
    return "".join(lines)


def _read_source_url(path: Path) -> str | None:
    """يقرأ source_url من كتلة front matter لملف مخرجات موجود (أو None)."""
    match = _SOURCE_URL_RE.search(_front_matter_head(path))
    return match.group(1) if match and match.group(1) else None


def _file_has_articles(path: Path) -> bool:
    try:
        return bool(_ARTICLE_HEADING_MD_RE.search(path.read_text(encoding="utf-8")))
    except OSError:
        return False


def _disambiguate_path(path: Path, url: str, counter: int | None = None) -> Path:
    """يشتق اسمًا مميزًا عند تصادم المسار مع وثيقة أخرى، من آخر مقطع في الرابط.

    لـ qanoonsa هذا معرّف المنشور (p/516403 ← 516403)، ولـ nezams اسم
    المقالة (slug) — كلاهما فريد لكل وثيقة، فالنتيجة حتمية وقابلة للتكرار.
    ``counter`` يُضاف داخل المميِّز (لا بعده) كي ينجو من الاقتطاع فيختلف
    الاسم فعليًا في كل دورة من دورات فضّ التصادم.
    """
    segments = [s for s in urlparse(url).path.split("/") if s]
    disc = unquote(segments[-1]) if segments else "نسخة"
    if counter is not None:
        disc = f"{disc} {counter}"
    return path.with_name(disambiguated_filename(path.stem, disc) + path.suffix)


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
        candidate = _disambiguate_path(path, source_url, counter)
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
        head = _front_matter_head(md)
        match = _SOURCE_URL_RE.search(head)
        if match and match.group(1):
            etag_m = _ETAG_RE.search(head)
            lm_m = _LAST_MODIFIED_RE.search(head)
            index[canonical_url(match.group(1))] = OutputEntry(
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
        canonical_url(line.strip())
        for line in log_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


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
    # حارس الوثيقة الجوفاء: صفحات كثيرة في qanoonsa تعرض البيانات الوصفية
    # فقط ونصّها في مرفق PDF. كتابتها تُنتج ملفًا يدّعي أنه نصّ النظام
    # وليس فيه سوى سطر تاريخ — 191 حالة تسرّبت هكذا. نرفضها عند المصدر
    # ونسجّلها فشلًا كي تظهر في التقرير بدل أن تدخل المُدوَّنة بصمت.
    if body_length(doc) < MIN_BODY_CHARS:
        raise ParseError(
            f"وثيقة جوفاء: متن بطول {body_length(doc)} محرفًا فقط "
            f"(الحدّ {MIN_BODY_CHARS}) — الصفحة بلا نصّ أو الاستخراج فشل"
        )
    doc.retrieved_at = date.today().isoformat()
    doc.doc_type = classify_doc_type(doc.title, url, doc.is_decision)
    doc.category = args.category or resolve_category(doc.category, doc.doc_type)
    doc.status, doc.status_note = normalize_status(doc.status)
    doc.issued_date_hijri = parse_hijri(doc.issued_date) or parse_hijri(doc.approval_date_hijri)
    doc.publish_date_gregorian = parse_gregorian(doc.publish_date) or parse_gregorian(
        doc.gazette_ref
    )
    doc.etag = etag
    doc.last_modified = last_modified
    warnings = validate_document(doc)
    if not getattr(args, "quiet_warnings", False):
        for warning in warnings:
            print(f"تحذير [{doc.title}]: {warning}", file=sys.stderr)
    out_dir = Path(args.out)
    path = output_path(doc, out_dir)
    # حارس M-3: لا تكتب فوق وثيقة مختلفة تتصادم في المسار (اقتطاع الاسم أو
    # نفس العنوان من المصدرين). يُحسم قبل نقل الملف القديم حتى تبقى العملية
    # idempotent: الوجهة المميّزة نفسها تُختار في كل تشغيل.
    path = _resolve_collision(path, doc.source_url)
    ensure_within(path, out_dir)
    # الترتيب مقصود: تُكتب النسخة الجديدة أولًا (كتابةً ذرّية) ثم تُحذف
    # القديمة. العكس — وهو ما كان — يفقد الوثيقة كليًا إن فشلت الكتابة
    # بعد الحذف (قرص ممتلئ، انقطاع العملية)، وهو مسار يمرّ به كل ملف
    # ينتقل بين المجلدات في تشغيلة إعادة التصنيف الشهرية.
    atomic_write(path, format_document(doc))
    if existing is not None:
        old_entry = existing.get(doc.source_url)
        if old_entry is not None and old_entry.path != path and old_entry.path.exists():
            old_entry.path.unlink()
            prune_empty_dirs(old_entry.path.parent, out_dir)
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


def _build_parser() -> argparse.ArgumentParser:
    """تعريف واجهة الطرفية وحدها — منفصلة عن التنفيذ ليمكن اختبارها."""
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
        "--shard",
        metavar="I/N",
        help=(
            "معالجة الشريحة I من N فقط (مثال: 2/4). التقسيم حتمي بتجزئة "
            "الرابط، فكل شريحة ثابتة عبر التشغيلات وتغطي الشرائح مجتمعةً "
            "كل الروابط — يُبقي التشغيلة المجدولة داخل سقف زمنها"
        ),
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
    parser.add_argument(
        "--ignore-robots",
        action="store_true",
        help="تعطيل فحص robots.txt (يُحترَم افتراضيًا)",
    )
    parser.add_argument(
        "--quiet-warnings",
        action="store_true",
        help="كتم تفصيل تحذيرات التحقق أثناء التشغيل (يبقى العدّاد والتقرير)",
    )
    return parser


def parse_shard(spec: str) -> tuple[int, int]:
    """يحلّل ``I/N`` ويتحقق من معقوليته؛ يرفع ValueError برسالة عربية."""
    try:
        index_text, count_text = spec.split("/", 1)
        index, count = int(index_text), int(count_text)
    except ValueError:
        raise ValueError(f"صيغة الشريحة غير صحيحة: «{spec}» (المتوقع I/N مثل 2/4)") from None
    if count < 1 or not 0 <= index < count:
        raise ValueError(f"شريحة خارج المدى: «{spec}» (يجب 0 ≤ I < N و N ≥ 1)")
    return index, count


def select_shard(urls: list[str], index: int, count: int) -> list[str]:
    """يختار شريحة حتمية من الروابط بتجزئة مستقرة عبر التشغيلات.

    ``hash()`` المدمج في بايثون مُملَّح عشوائيًا لكل عملية، فلا يصلح —
    نستخدم md5 حتى تعطي نفس الشريحة نفس الروابط في كل تشغيلة، وتغطي
    الشرائح مجتمعةً كل الروابط بلا تكرار ولا ثغرة.
    """
    if count <= 1:
        return urls
    return [
        url for url in urls
        if int(hashlib.md5(url.encode("utf-8")).hexdigest(), 16) % count == index
    ]


def _read_url_file(path_text: str, parser: argparse.ArgumentParser) -> list[str]:
    try:
        lines = Path(path_text).read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        parser.error(f"تعذّر قراءة ملف الروابط «{path_text}»: {exc}")
    return [line.strip() for line in lines if line.strip() and not line.startswith("#")]


def _collect_urls(args: argparse.Namespace, fetcher: Fetcher,
                  parser: argparse.ArgumentParser) -> list[str]:
    """يجمع الروابط من كل مصادرها (مباشرة، ملف، اكتشاف) ويطبّق الشريحة."""
    urls = list(args.urls)
    if args.from_file:
        urls += _read_url_file(args.from_file, parser)
    if args.discover:
        for source in [s.strip() for s in args.discover.split(",") if s.strip()]:
            print(f"اكتشاف روابط {source}…", file=sys.stderr)
            try:
                found = discover(source, fetcher, include_updates=args.include_updates)
            except (FetchError, ValueError) as exc:
                print(f"فشل اكتشاف {source}: {exc}", file=sys.stderr)
                continue
            print(f"{source}: {len(found)} رابط", file=sys.stderr)
            urls += found
    if args.shard:
        try:
            index, count = parse_shard(args.shard)
        except ValueError as exc:
            parser.error(str(exc))
        before = len(urls)
        urls = select_shard(urls, index, count)
        print(f"الشريحة {args.shard}: {len(urls)} من {before} رابط", file=sys.stderr)
    return urls


@dataclass
class RunStats:
    """حصيلة تشغيلة معالجة واحدة."""

    processed: int = 0
    failures: int = 0
    skipped: int = 0
    unchanged: int = 0
    warned: int = 0
    results: list[RunResult] = field(default_factory=list)


def _process_urls(urls: list[str], args: argparse.Namespace, fetcher: Fetcher) -> RunStats:
    """حلقة المعالجة: جلب (شرطي عند الطلب) ثم تحويل وكتابة، مع الإحصاء."""
    # فهرس source_url ← مسار الملف الحالي، يُبنى مرة واحدة لكل التشغيلة:
    # يُستخدم لتثبيت هوية الوثيقة (process_html) ولاشتقاق حالة الاستئناف الدائمة
    existing = build_source_index(Path(args.out))
    done: set[str] = set()
    if args.resume:
        done = load_done(DONE_LOG)
        # مع --check-updates تمرّ الروابط المعروفة (لها ملف) على الجلب
        # الشرطي بدل تخطّيها، وإلا لبطل --resume الفحصَ الشرطي بصمت (M-5)
        if not args.check_updates:
            done |= set(existing.keys())

    stats = RunStats()
    total = len(urls)
    for position, raw_url in enumerate(urls, start=1):
        url = canonical_url(raw_url)  # هوية موحّدة عبر resume/check-updates/الفهرس
        if args.resume and url in done:
            stats.skipped += 1
            continue
        if args.limit is not None and stats.processed >= args.limit:
            print(
                f"بلغت الدفعة حدّها ({args.limit})؛ توقّف. المتبقي يُعالَج في تشغيل لاحق.",
                file=sys.stderr,
            )
            break
        # مؤشّر تقدّم: التشغيلة الكاملة تمتدّ ساعات على آلاف الروابط، وبلا
        # موضع حالي لا يعرف المشغّل إن كانت تتقدّم أم علقت
        print(f"[{position}/{total}] {url}", file=sys.stderr)
        source = detect_source(url)
        if not source:
            log_failure(url, "مصدر غير معروف")
            print(f"تخطي: مصدر غير معروف: {url}", file=sys.stderr)
            stats.failures += 1
            stats.results.append(RunResult(url=url, status="failed", reason="مصدر غير معروف"))
            continue
        try:
            prior = existing.get(url) if args.check_updates else None
            if prior is not None:
                result = fetcher.get_conditional(
                    url, etag=prior.etag, last_modified=prior.last_modified
                )
                if result.not_modified:
                    stats.processed += 1
                    stats.unchanged += 1
                    print(f"بلا تغيير: {url}")
                    stats.results.append(RunResult(url=url, status="unchanged"))
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
            stats.failures += 1
            stats.results.append(RunResult(url=url, status="failed", reason=str(exc)))
        else:
            stats.processed += 1
            if warnings:
                stats.warned += 1
            stats.results.append(RunResult(
                url=url, status="ok", title=doc.title,
                doc_type=doc.doc_type, warnings=warnings,
            ))
            if args.resume:
                log_done(url, DONE_LOG)
    return stats


def _run_html_mode(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    """وضع الملف المحلي (بلا شبكة)."""
    source = args.source or detect_source(args.url)
    if not source:
        parser.error("مع ‎--html يجب تحديد ‎--source أو ‎--url برابط معروف المصدر")
    existing = build_source_index(Path(args.out))
    try:
        process_html(
            Path(args.html).read_text(encoding="utf-8"),
            canonical_url(args.url), source, args, existing,
        )
    except (ParseError, OSError, ValueError) as exc:
        log_failure(args.html, str(exc))
        print(f"فشل: {args.html}: {exc}", file=sys.stderr)
        return 1
    return 0


def _write_report(args: argparse.Namespace, stats: RunStats) -> None:
    report_path = Path(args.report)
    try:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            build_summary(stats.results, skipped=stats.skipped), encoding="utf-8"
        )
    except OSError as exc:
        print(f"تعذّرت كتابة التقرير في «{report_path}»: {exc}", file=sys.stderr)
        return
    print(f"التقرير ← {report_path}", file=sys.stderr)


def run(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.html:
        return _run_html_mode(args, parser)

    fetcher = Fetcher(
        delay=args.delay,
        respect_robots=not args.ignore_robots,
        host_allowed=host_allowed,
    )
    urls = _collect_urls(args, fetcher, parser)
    if not urls:
        parser.error("لم يُمرر أي رابط (استخدم روابط مباشرة أو --from-file أو --discover أو --html)")

    stats = _process_urls(urls, args, fetcher)

    if args.resume and stats.skipped:
        print(f"تُخطّي {stats.skipped} رابطًا مكتملًا سابقًا.", file=sys.stderr)
    if args.check_updates and stats.unchanged:
        print(f"بلا تغيير منذ آخر جلب: {stats.unchanged}", file=sys.stderr)
    if stats.warned:
        print(f"وثائق بتحذيرات: {stats.warned}", file=sys.stderr)
    if args.report:
        _write_report(args, stats)
    return 1 if stats.failures else 0


if __name__ == "__main__":
    sys.exit(run())
