"""فحص صحة تشغيلة الاستيراد من تقريرها، ليُفشل الـ workflow عند تدهور فعلي.

خلفية: خطوة الجلب في ``update-corpus.yml`` كانت تنتهي بـ ``|| true``.
النية مفهومة (فشل رابط واحد يجب ألا يوقف التشغيلة كلها)، لكنها كانت تبتلع
أيضًا **الفشل الكلي**: لو سقط الموقعان أو تغيّرت بنيتهما، تنتهي التشغيلة
«بنجاح» بلا Pull Request وبلا أي إشارة، ويتقادم المستودع بصمت شهورًا.

هذا الفحص يفرّق بين الحالتين بقراءة تقرير التشغيلة: نسبة فشل منخفضة =
روابط ميتة مفردة (طبيعي)، ونسبة مرتفعة = عطل بنيوي يستحق إنذارًا.

الاستخدام:
    python -m scripts.check_run_health logs/summary.md --max-failure-rate 0.2
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_COUNT_RE = {
    "ok": re.compile(r"^- نجح: \*\*(\d+)\*\*", re.MULTILINE),
    "failed": re.compile(r"^- فشل: \*\*(\d+)\*\*", re.MULTILINE),
    "unchanged": re.compile(r"^- بلا تغيير منذ آخر جلب: \*\*(\d+)\*\*", re.MULTILINE),
}


def parse_counts(report: str) -> dict[str, int]:
    """يقرأ أعداد النجاح/الفشل/بلا تغيير من تقرير build_summary."""
    return {
        key: int(m.group(1)) if (m := pattern.search(report)) else 0
        for key, pattern in _COUNT_RE.items()
    }


def failure_rate(counts: dict[str, int]) -> float:
    """نسبة الفشل من مجموع الروابط المحاوَلة (0.0 إن لم يُحاوَل شيء)."""
    attempted = counts["ok"] + counts["failed"] + counts["unchanged"]
    return counts["failed"] / attempted if attempted else 0.0


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.check_run_health",
        description="يُفشل التشغيلة عند تجاوز نسبة الفشل العتبة (بدل ابتلاعها بـ || true)",
    )
    parser.add_argument("report", help="مسار تقرير التشغيلة (logs/summary.md)")
    parser.add_argument(
        "--max-failure-rate", type=float, default=0.2,
        help="أقصى نسبة فشل مقبولة (افتراضي 0.2)",
    )
    args = parser.parse_args(argv)

    path = Path(args.report)
    if not path.exists():
        # لا تقرير أصلًا = لم تصل التشغيلة إلى نهايتها (انهيار مبكر)
        print(f"لا تقرير في {path}: التشغيلة لم تكتمل.", file=sys.stderr)
        return 1

    counts = parse_counts(path.read_text(encoding="utf-8"))
    rate = failure_rate(counts)
    attempted = counts["ok"] + counts["failed"] + counts["unchanged"]
    print(
        f"حصيلة التشغيلة: {attempted} رابطًا · نجح {counts['ok']} · "
        f"بلا تغيير {counts['unchanged']} · فشل {counts['failed']} "
        f"({rate:.1%})",
        file=sys.stderr,
    )
    if attempted == 0:
        print("لم يُحاوَل أي رابط: يُحتمل فشل الاكتشاف من الخرائط.", file=sys.stderr)
        return 1
    if rate > args.max_failure_rate:
        print(
            f"نسبة الفشل {rate:.1%} تتجاوز العتبة {args.max_failure_rate:.0%} — "
            "يُحتمل تغيّر بنية المصدر أو انقطاعه.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(run())
