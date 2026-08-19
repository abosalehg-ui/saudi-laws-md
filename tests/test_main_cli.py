"""واجهة الطرفية في main: التقسيم إلى شرائح، جمع الروابط، ومعالجة الأخطاء."""

import pytest

from scripts.main import _build_parser, _collect_urls, parse_shard, select_shard

URLS = [f"https://qanoonsa.com/p/{i}/" for i in range(200)]


def test_shards_cover_every_url_exactly_once():
    """الشرائح مجتمعةً تغطي كل الروابط بلا ثغرة ولا تكرار."""
    parts = [select_shard(URLS, i, 4) for i in range(4)]
    assert sorted(u for part in parts for u in part) == sorted(URLS)


def test_shard_membership_is_stable_across_calls():
    """لولا الثبات لتغيّرت الشريحة كل تشغيلة فما اكتملت التغطية أبدًا.

    (hash المدمج مُملَّح عشوائيًا لكل عملية، لذا يُستخدم md5.)
    """
    assert select_shard(URLS, 2, 4) == select_shard(URLS, 2, 4)


def test_single_shard_returns_everything():
    assert select_shard(URLS, 0, 1) == URLS


@pytest.mark.parametrize("spec,expected", [("0/4", (0, 4)), ("3/4", (3, 4)), ("0/1", (0, 1))])
def test_valid_shard_specs(spec, expected):
    assert parse_shard(spec) == expected


@pytest.mark.parametrize("spec", ["4/4", "-1/4", "2/0", "abc", "2", "2/x"])
def test_invalid_shard_specs_are_rejected(spec):
    with pytest.raises(ValueError):
        parse_shard(spec)


def test_missing_url_file_exits_with_arabic_message(capsys):
    parser = _build_parser()
    args = parser.parse_args(["--from-file", "/لا-يوجد.txt"])
    with pytest.raises(SystemExit):
        _collect_urls(args, fetcher=None, parser=parser)
    assert "تعذّر قراءة ملف الروابط" in capsys.readouterr().err


def test_url_file_comments_and_blanks_are_ignored(tmp_path):
    path = tmp_path / "urls.txt"
    path.write_text(
        "# تعليق\n\nhttps://qanoonsa.com/p/1/\n  \nhttps://nezams.com/x/\n", encoding="utf-8"
    )
    parser = _build_parser()
    args = parser.parse_args(["--from-file", str(path)])
    assert _collect_urls(args, fetcher=None, parser=parser) == [
        "https://qanoonsa.com/p/1/",
        "https://nezams.com/x/",
    ]


def test_shard_is_applied_to_collected_urls(tmp_path):
    path = tmp_path / "urls.txt"
    path.write_text("\n".join(URLS), encoding="utf-8")
    parser = _build_parser()
    args = parser.parse_args(["--from-file", str(path), "--shard", "1/4"])
    selected = _collect_urls(args, fetcher=None, parser=parser)
    assert 0 < len(selected) < len(URLS)
    assert selected == select_shard(URLS, 1, 4)


def test_invalid_shard_spec_exits_from_the_cli(tmp_path, capsys):
    path = tmp_path / "urls.txt"
    path.write_text("https://qanoonsa.com/p/1/\n", encoding="utf-8")
    parser = _build_parser()
    args = parser.parse_args(["--from-file", str(path), "--shard", "9/4"])
    with pytest.raises(SystemExit):
        _collect_urls(args, fetcher=None, parser=parser)
    assert "شريحة خارج المدى" in capsys.readouterr().err
