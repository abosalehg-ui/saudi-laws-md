"""اكتشاف روابط الوثائق من خرائط الموقعين (sitemaps).

كلا الموقعين يعتمد WordPress بخرائط XML قياسية:
- qanoonsa: ``wp-sitemap.xml`` → فهرس يشير إلى ``wp-sitemap-posts-post-N.xml``
  (المنشورات، وهي الأنظمة والقرارات والمراسيم...) وخرائط تصنيفات تُتجاهَل.
- nezams: ``sitemap_index.xml`` (Yoast) → ``post-sitemap.xml`` (الأنظمة
  واللوائح) و``nezam_update-sitemap.xml`` (تعديلات مواد مفردة).

النطاقات المسموح استخراج الوثائق منها فقط، لتجنّب متابعة روابط خارجية.
"""

from __future__ import annotations

import argparse
import re
import sys
from urllib.parse import urlparse

from .fetch import Fetcher, FetchError

SITE_INDEX = {
    "qanoonsa": "https://qanoonsa.com/wp-sitemap.xml",
    "nezams": "https://nezams.com/sitemap_index.xml",
}
_ALLOWED_HOSTS = {"qanoonsa.com", "nezams.com"}

# خرائط فرعية للتصنيفات/الوسوم/المستخدمين لا تحوي وثائق — تُستبعَد
_SKIP_SUBMAP_RE = re.compile(r"(taxonom|category|post_tag|-tag|author|user)", re.I)
# خريطة تعديلات المواد المفردة في nezams (تُدرَج فقط عند طلبها صراحةً)
_UPDATE_SUBMAP_RE = re.compile(r"nezam_update", re.I)
_LOC_RE = re.compile(r"<loc>\s*(.*?)\s*</loc>", re.S)


def _host_ok(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == h or host.endswith("." + h) for h in _ALLOWED_HOSTS)


def _locs(xml: str) -> list[str]:
    return [loc.strip() for loc in _LOC_RE.findall(xml)]


def _is_sitemap_index(xml: str) -> bool:
    return "<sitemapindex" in xml


def discover(
    source: str,
    fetcher: Fetcher,
    include_updates: bool = False,
) -> list[str]:
    """يعيد روابط الوثائق لمصدر واحد بعد المرور على خريطته وخرائطه الفرعية."""
    if source not in SITE_INDEX:
        raise ValueError(f"مصدر غير معروف: {source}")

    index_xml = fetcher.get(SITE_INDEX[source])
    if _is_sitemap_index(index_xml):
        submaps = _locs(index_xml)
    else:
        # بعض المواقع تضع الروابط مباشرة في الخريطة الرئيسة
        submaps = [SITE_INDEX[source]]

    urls: list[str] = []
    seen: set[str] = set()
    for submap in submaps:
        if not _host_ok(submap):
            continue
        if _SKIP_SUBMAP_RE.search(submap):
            continue
        if _UPDATE_SUBMAP_RE.search(submap) and not include_updates:
            continue
        try:
            xml = fetcher.get(submap)
        except FetchError as exc:
            print(f"تعذّر جلب خريطة فرعية {submap}: {exc}", file=sys.stderr)
            continue
        for loc in _locs(xml):
            if _host_ok(loc) and loc not in seen:
                seen.add(loc)
                urls.append(loc)
    return urls


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.discover",
        description="اكتشاف روابط الوثائق من خرائط qanoonsa.com و nezams.com",
    )
    parser.add_argument(
        "sources",
        nargs="*",
        help="المصادر المطلوبة: qanoonsa و/أو nezams (افتراضيًا كلاهما)",
    )
    parser.add_argument("--out", help="ملف لحفظ الروابط (رابط في كل سطر)؛ الافتراضي stdout")
    parser.add_argument(
        "--include-updates",
        action="store_true",
        help="إدراج صفحات تعديلات المواد المفردة (nezam_update) في nezams",
    )
    parser.add_argument("--delay", type=float, default=1.5, help="التأخير بين الطلبات بالثواني")
    args = parser.parse_args(argv)

    sources = args.sources or ["qanoonsa", "nezams"]
    unknown = [s for s in sources if s not in SITE_INDEX]
    if unknown:
        parser.error(f"مصادر غير معروفة: {', '.join(unknown)} (المتاح: qanoonsa، nezams)")
    fetcher = Fetcher(delay=args.delay)
    all_urls: list[str] = []
    for source in sources:
        try:
            found = discover(source, fetcher, include_updates=args.include_updates)
        except (FetchError, ValueError) as exc:
            print(f"فشل اكتشاف {source}: {exc}", file=sys.stderr)
            continue
        print(f"{source}: {len(found)} رابط", file=sys.stderr)
        all_urls.extend(found)

    text = "\n".join(all_urls) + ("\n" if all_urls else "")
    if args.out:
        from pathlib import Path

        Path(args.out).write_text(text, encoding="utf-8")
        print(f"حُفظ {len(all_urls)} رابط في {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0 if all_urls else 1


if __name__ == "__main__":
    sys.exit(run())
