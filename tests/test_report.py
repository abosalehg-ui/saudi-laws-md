from scripts.report import RunResult, build_summary


def test_summary_counts_and_sections():
    results = [
        RunResult(url="u1", status="ok", title="نظام العمل", doc_type="نظام"),
        RunResult(url="u2", status="ok", title="لائحة", doc_type="لائحة",
                  warnings=["خلل في التسلسل: بعد المادة 5 جاءت المادة 79"]),
        RunResult(url="u3", status="failed", reason="لم يُستخرج أي مادة"),
    ]
    md = build_summary(results, skipped=4)

    assert "نجح: **2**" in md
    assert "فشل: **1**" in md
    assert "تُخطّي (مكتمل سابقًا): **4**" in md
    assert "بتحذيرات: **1**" in md
    # توزيع الأنواع
    assert "- نظام: 1" in md
    assert "- لائحة: 1" in md
    # قسم الفشل مع السبب
    assert "`u3` — لم يُستخرج أي مادة" in md
    # قسم التحذيرات مع العنوان
    assert "**لائحة**" in md
    assert "بعد المادة 5 جاءت المادة 79" in md


def test_summary_empty_run():
    md = build_summary([], skipped=0)
    assert "نجح: **0**" in md
    assert "فشل: **0**" in md
    # لا أقسام فرعية عندما لا يوجد فشل/تحذيرات
    assert "## الفشل" not in md
    assert "## التحذيرات" not in md
