"""بناء تقرير ملخّص لتشغيلة استيراد بالجملة.

يجمع نتائج المعالجة (نجاح/فشل/تخطٍّ، الأنواع، التحذيرات، أسباب الفشل)
في ملف Markdown واحد، بدل تفرّقها بين stderr و logs/failed.txt.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class RunResult:
    """سجل معالجة رابط واحد ضمن تشغيلة."""

    url: str
    status: str                       # "ok" | "failed"
    title: str | None = None
    doc_type: str | None = None
    reason: str | None = None         # سبب الفشل عند status == "failed"
    warnings: list[str] = field(default_factory=list)


def build_summary(results: list[RunResult], skipped: int = 0) -> str:
    """يبني تقرير Markdown من نتائج التشغيلة."""
    ok = [r for r in results if r.status == "ok"]
    failed = [r for r in results if r.status == "failed"]
    warned = [r for r in ok if r.warnings]
    types = Counter(r.doc_type or "غير محدد" for r in ok)

    lines = [
        f"# تقرير الاستيراد — {datetime.now().isoformat(timespec='seconds')}",
        "",
        f"- نجح: **{len(ok)}**",
        f"- فشل: **{len(failed)}**",
        f"- تُخطّي (مكتمل سابقًا): **{skipped}**",
        f"- بتحذيرات: **{len(warned)}**",
        "",
    ]

    if types:
        lines.append("## توزيع الأنواع")
        lines.append("")
        for doc_type, count in types.most_common():
            lines.append(f"- {doc_type}: {count}")
        lines.append("")

    if failed:
        lines.append("## الفشل")
        lines.append("")
        for r in failed:
            lines.append(f"- `{r.url}` — {r.reason}")
        lines.append("")

    if warned:
        lines.append("## التحذيرات")
        lines.append("")
        for r in warned:
            label = r.title or r.url
            lines.append(f"- **{label}**")
            for w in r.warnings:
                lines.append(f"  - {w}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
