from scripts.build_index import build_index, run

DOC = (
    '---\ntitle: "نظام العمل"\nsource: nezams\n'
    'source_url: "https://nezams.com/نظام-العمل/"\n'
    'doc_type: "نظام"\ncategory: "أنظمة العمل"\nstatus: "ساري"\n'
    'also_available_from: ["https://qanoonsa.com/p/1/"]\n---\n\n# نظام العمل\n\nمتن.\n'
)


def _seed(tmp_path):
    p = tmp_path / "أنظمة العمل" / "نظام العمل.md"
    p.parent.mkdir(parents=True)
    p.write_text(DOC, encoding="utf-8")
    return p


def test_build_index_extracts_metadata(tmp_path):
    _seed(tmp_path)
    entries = build_index(tmp_path)
    assert len(entries) == 1
    e = entries[0]
    assert e["title"] == "نظام العمل"
    assert e["doc_type"] == "نظام"
    assert e["category"] == "أنظمة العمل"
    assert e["source_url"] == "https://nezams.com/نظام-العمل/"
    assert e["also_available_from"] == ["https://qanoonsa.com/p/1/"]
    assert e["path"].endswith("نظام العمل.md")


def test_check_mode_detects_staleness(tmp_path, monkeypatch):
    _seed(tmp_path)
    monkeypatch.chdir(tmp_path)
    # لا فهرس بعد ⇒ --check يفشل
    assert run([str(tmp_path), "--check"]) == 1
    # بعد البناء ⇒ --check ينجح
    assert run([str(tmp_path)]) == 0
    assert run([str(tmp_path), "--check"]) == 0
