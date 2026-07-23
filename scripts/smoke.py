"""فحص دخاني ضد المواقع الحيّة: يتأكد أن استخراج عيّنة ما زال ينتج مواد.

الاختبارات على fixtures ثابتة لا تكشف تغيّر بنية HTML للموقعين الحقيقيين
(أخطر أعطال الاستخراج، وصامتة). هذا الفحص يجلب صفحة معروفة من كل مصدر
ويؤكد أنها تُقطَّع إلى مواد/بنود لا إلى ``body`` مسطّح ولا ترفع ParseError.

يُشغَّل مجدولًا (لا في CI العادي، إذ يحتاج شبكة). رمز الخروج ≠0 عند تدهور
بنيوي فعلي؛ ويتجاهل أعطال الشبكة/404 (إشارة مختلفة، لا تغيّر بنية).

الاستخدام:
    python -m scripts.smoke
"""

from __future__ import annotations

import sys

from .adapters import get_adapter
from .adapters.base import ParseError
from .fetch import Fetcher, FetchError
from .schema import validate_document

# صفحات مرجعية مستقرة (نفس مصادر الـ fixtures): نظام حقيقي متعدد المواد
_SAMPLES = {
    "nezams": "https://nezams.com/نظام-العمل/",
    "qanoonsa": "https://qanoonsa.com/p/516403/",
}


def check(source: str, url: str, fetcher: Fetcher) -> str | None:
    """يعيد رسالة خطأ عند تدهور بنيوي، أو None عند السلامة/تعذّر الشبكة."""
    try:
        html = fetcher.get(url)
    except FetchError as exc:
        print(f"↷ تخطّي {source} ({url}): تعذّر الجلب ({exc})", file=sys.stderr)
        return None
    try:
        doc = get_adapter(source).parse(html, url)
    except ParseError as exc:
        return f"{source}: فشل التقطيع ({exc}) — يُحتمل تغيّر بنية الموقع"
    if not doc.articles:
        return f"{source}: لا مواد/بنود (نتج body مسطّح) — يُحتمل تغيّر بنية الموقع"
    degraded = [w for w in validate_document(doc) if "فشل تقطيع" in w]
    if degraded:
        return f"{source}: {degraded[0]}"
    print(f"✓ {source}: {len(doc.articles)} مادة/بند", file=sys.stderr)
    return None


def run(argv: list[str] | None = None) -> int:
    fetcher = Fetcher(delay=2, respect_robots=True)
    failures = [msg for src, url in _SAMPLES.items() if (msg := check(src, url, fetcher))]
    for msg in failures:
        print(f"✗ {msg}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(run())
