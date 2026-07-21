from pathlib import Path

from scripts.audit_duplicates import annotate_duplicates, find_duplicate_groups


def _write(path: Path, title: str, source_url: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f'---\ntitle: "{title}"\nsource_url: "{source_url}"\n---\n\n# {title}\n',
        encoding="utf-8",
    )


def test_find_duplicate_groups_by_title(tmp_path):
    out = tmp_path / "laws"
    _write(out / "a" / "نظام العمل.md", "نظام العمل", "https://qanoonsa.com/p/1/")
    _write(out / "b" / "نظام العمل.md", "نظام العمل", "https://nezams.com/x/")
    _write(out / "a" / "نظام آخر.md", "نظام آخر", "https://qanoonsa.com/p/2/")

    groups = find_duplicate_groups(out)

    assert list(groups.keys()) == ["نظام العمل"]
    assert len(groups["نظام العمل"]) == 2


def test_annotate_links_siblings_without_deleting_or_moving(tmp_path):
    out = tmp_path / "laws"
    a = out / "a" / "نظام العمل.md"
    b = out / "b" / "نظام العمل.md"
    _write(a, "نظام العمل", "https://qanoonsa.com/p/1/")
    _write(b, "نظام العمل", "https://nezams.com/x/")

    group_count, touched = annotate_duplicates(out)

    assert group_count == 1
    assert touched == 2
    assert a.exists() and b.exists()  # لا حذف ولا نقل
    assert 'also_available_from: ["https://nezams.com/x/"]' in a.read_text(encoding="utf-8")
    assert 'also_available_from: ["https://qanoonsa.com/p/1/"]' in b.read_text(encoding="utf-8")


def test_annotate_is_idempotent(tmp_path):
    out = tmp_path / "laws"
    a = out / "a" / "نظام العمل.md"
    b = out / "b" / "نظام العمل.md"
    _write(a, "نظام العمل", "https://qanoonsa.com/p/1/")
    _write(b, "نظام العمل", "https://nezams.com/x/")

    annotate_duplicates(out)
    group_count, touched = annotate_duplicates(out)

    assert touched == 0


def test_dry_run_does_not_write(tmp_path):
    out = tmp_path / "laws"
    a = out / "a" / "نظام العمل.md"
    b = out / "b" / "نظام العمل.md"
    _write(a, "نظام العمل", "https://qanoonsa.com/p/1/")
    _write(b, "نظام العمل", "https://nezams.com/x/")

    group_count, touched = annotate_duplicates(out, dry_run=True)

    assert touched == 2
    assert "also_available_from" not in a.read_text(encoding="utf-8")


def test_unique_titles_untouched(tmp_path):
    out = tmp_path / "laws"
    _write(out / "a" / "نظام فريد.md", "نظام فريد", "https://qanoonsa.com/p/1/")

    group_count, touched = annotate_duplicates(out)

    assert group_count == 0
    assert touched == 0
