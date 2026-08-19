"""بوّابة صحة التشغيلة: تفرّق بين روابط ميتة مفردة وعطل بنيوي."""

from scripts.check_run_health import failure_rate, parse_counts, run
from scripts.report import RunResult, build_summary


def _report(ok=0, failed=0, unchanged=0):
    results = [RunResult(url=f"https://q/{i}/", status="ok", title="س") for i in range(ok)]
    results += [
        RunResult(url=f"https://q/f{i}/", status="failed", reason="خطأ") for i in range(failed)
    ]
    results += [RunResult(url=f"https://q/u{i}/", status="unchanged") for i in range(unchanged)]
    return build_summary(results)


def test_parses_counts_from_a_real_summary():
    counts = parse_counts(_report(ok=8, failed=2, unchanged=5))
    assert counts == {"ok": 8, "failed": 2, "unchanged": 5}


def test_failure_rate_counts_unchanged_as_attempted():
    """الروابط «بلا تغيير» محاوَلات ناجحة، فتخفّض النسبة لا ترفعها."""
    assert failure_rate({"ok": 0, "failed": 1, "unchanged": 9}) == 0.1


def test_no_attempts_is_not_a_division_error():
    assert failure_rate({"ok": 0, "failed": 0, "unchanged": 0}) == 0.0


def test_tolerates_a_few_dead_links(tmp_path):
    path = tmp_path / "summary.md"
    path.write_text(_report(ok=90, failed=5, unchanged=5), encoding="utf-8")
    assert run([str(path)]) == 0


def test_fails_on_structural_collapse(tmp_path):
    """سقوط المصدر أو تغيّر بنيته: نسبة فشل عالية = إنذار لا صمت."""
    path = tmp_path / "summary.md"
    path.write_text(_report(ok=10, failed=90), encoding="utf-8")
    assert run([str(path)]) == 1


def test_fails_when_nothing_was_attempted(tmp_path):
    """صفر محاولة = فشل الاكتشاف من الخرائط، لا تشغيلة ناجحة بلا عمل."""
    path = tmp_path / "summary.md"
    path.write_text(_report(), encoding="utf-8")
    assert run([str(path)]) == 1


def test_fails_when_report_is_missing(tmp_path):
    assert run([str(tmp_path / "غائب.md")]) == 1
