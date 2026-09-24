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


def test_intermediate_folder_gets_subfolder_index(tmp_path):
    """مجلد بلا وثائق مباشرة (مثل laws/قرار/ المقسّم بالسنوات) يُولَّد له فهرس فروع."""
    from scripts.build_index import directory_readmes

    entries = [
        {"path": (tmp_path / "قرار" / "1444" / "أ.md").as_posix(), "title": "أ"},
        {"path": (tmp_path / "قرار" / "1444" / "ب.md").as_posix(), "title": "ب"},
        {"path": (tmp_path / "قرار" / "1445" / "ج.md").as_posix(), "title": "ج"},
    ]
    readmes = directory_readmes(entries, tmp_path)
    parent = readmes[tmp_path / "قرار" / "README.md"]
    assert "3 وثيقة موزّعة على 2 مجلدًا فرعيًا" in parent
    assert "| [1444](<1444/README.md>) | 2 |" in parent
    assert "| [1445](<1445/README.md>) | 1 |" in parent
    # مجلد المخرجات نفسه لا يُولَّد له فهرس فروع (README يدوي بقسم مُولَّد)
    assert tmp_path / "README.md" not in readmes


def test_out_readme_browse_section_splits_domain_and_type(tmp_path, monkeypatch):
    _seed(tmp_path)
    other = tmp_path / "لائحة" / "لائحة ما.md"
    other.parent.mkdir()
    other.write_text(DOC.replace("نظام العمل", "لائحة ما"), encoding="utf-8")
    readme = tmp_path / "README.md"
    readme.write_text("# laws\n\n<!-- browse -->\n<!-- /browse -->\n\nنصّ يدوي.\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert run([str(tmp_path), "--out-file", str(tmp_path / "index.json")]) == 0
    text = readme.read_text(encoding="utf-8")
    domain, _, by_type = text.partition("حسب نوع الوثيقة")
    assert "[أنظمة العمل](<أنظمة العمل/README.md>)" in domain
    assert "[لائحة](<لائحة/README.md>)" in by_type
    assert "نصّ يدوي." in text
    # البناء ثابت: تشغيل ثانٍ لا يغيّر شيئًا و--check أخضر
    assert run([str(tmp_path), "--out-file", str(tmp_path / "index.json"), "--check"]) == 0
