from pathlib import Path

from scripts.reclassify import reclassify


def _write(path: Path, title: str, doc_type: str | None, category: str | None, body: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["---", f'title: "{title}"', "source: nezams", 'source_url: "https://nezams.com/x/"']
    if doc_type:
        lines.append(f'doc_type: "{doc_type}"')
    if category:
        lines.append(f'category: "{category}"')
    lines += ["---", "", f"# {title}", "", body]
    path.write_text("\n".join(lines), encoding="utf-8")


def test_relocates_stale_alias_category(tmp_path):
    out = tmp_path / "laws"
    old = out / "أنظمة المواصلات والإتصالات" / "نظام النقل.md"
    _write(old, "نظام النقل", "نظام", "أنظمة المواصلات والإتصالات", "## المادة الأولى\n\nنص.")

    moved, unchanged, conflicts = reclassify(out)

    assert conflicts == []
    assert moved == 1
    assert not old.exists()
    new = out / "أنظمة المواصلات والاتصالات" / "نظام النقل.md"
    assert new.exists()
    assert 'category: "أنظمة المواصلات والاتصالات"' in new.read_text(encoding="utf-8")
    # المجلد القديم الفارغ يُحذف
    assert not old.parent.exists()


def test_reclassifies_decision_title_after_issuer_prefix(tmp_path):
    out = tmp_path / "laws"
    old = out / "غير-مصنف" / "قرار.md"
    _write(
        old, "وزارة الطاقة: قرار رقم (١) نزع ملكية", "أخرى", None,
        "## أولا\n\nنص البند.",
    )

    moved, unchanged, conflicts = reclassify(out)

    assert conflicts == []
    assert moved == 1
    new = out / "قرار" / "وزارة الطاقة قرار رقم (١) نزع ملكية.md"
    assert new.exists()
    content = new.read_text(encoding="utf-8")
    assert 'doc_type: "قرار"' in content
    assert 'category: "قرار"' in content


def test_no_change_when_already_correct(tmp_path):
    out = tmp_path / "laws"
    path = out / "التنظيمات" / "نظام العمل.md"
    _write(path, "نظام العمل", "نظام", "التنظيمات", "## المادة الأولى\n\nنص.")

    moved, unchanged, conflicts = reclassify(out)

    assert moved == 0
    assert unchanged == 1
    assert conflicts == []
    assert path.exists()


def test_merges_nizam_folder_into_tanzimat(tmp_path):
    # قرار المالك: مجلدا "نظام" و"التنظيمات" تصنيف واحد هو "التنظيمات"
    out = tmp_path / "laws"
    old = out / "نظام" / "تنظيم هيئة التراث.md"
    _write(old, "تنظيم هيئة التراث", "نظام", "نظام", "## المادة الأولى\n\nنص.")

    moved, unchanged, conflicts = reclassify(out)

    assert conflicts == []
    assert moved == 1
    assert not old.parent.exists()
    new = out / "التنظيمات" / "تنظيم هيئة التراث.md"
    assert new.exists()
    assert 'category: "التنظيمات"' in new.read_text(encoding="utf-8")


def test_bare_generic_category_goes_to_uncategorized(tmp_path):
    # "الأنظمة السعودية" وحدها لا تميّز شيئًا — كل المستودع أنظمة سعودية
    out = tmp_path / "laws"
    old = out / "الأنظمة السعودية" / "النظام الأساس لمؤسسة.md"
    _write(old, "النظام الأساس لمؤسسة", "أخرى", "الأنظمة السعودية", "نص.")

    moved, unchanged, conflicts = reclassify(out)

    assert conflicts == []
    assert moved == 1
    assert not old.parent.exists()
    assert (out / "غير-مصنف" / "النظام الأساس لمؤسسة.md").exists()


def test_conflict_when_destination_already_occupied(tmp_path):
    out = tmp_path / "laws"
    stale = out / "أنظمة المواصلات والإتصالات" / "نظام النقل.md"
    _write(stale, "نظام النقل", "نظام", "أنظمة المواصلات والإتصالات", "## المادة الأولى\n\nنص.")
    occupied = out / "أنظمة المواصلات والاتصالات" / "نظام النقل.md"
    _write(occupied, "نظام النقل", "نظام", "أنظمة المواصلات والاتصالات", "## المادة الأولى\n\nنص آخر.")

    moved, unchanged, conflicts = reclassify(out)

    assert len(conflicts) == 1
    assert stale.exists()  # لم يُلمس عند وجود تعارض
    assert occupied.exists()


def test_dry_run_does_not_write(tmp_path):
    out = tmp_path / "laws"
    old = out / "أنظمة المواصلات والإتصالات" / "نظام النقل.md"
    _write(old, "نظام النقل", "نظام", "أنظمة المواصلات والإتصالات", "## المادة الأولى\n\nنص.")

    moved, unchanged, conflicts = reclassify(out, dry_run=True)

    assert moved == 1
    assert old.exists()
    assert not (out / "أنظمة المواصلات والاتصالات").exists()
