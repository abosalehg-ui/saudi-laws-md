"""حرّاس الشبكة: التحويلات المقيَّدة بالقائمة البيضاء، سقف حجم الاستجابة،
واحترام Retry-After."""

import pytest

import scripts.fetch as fetch_mod
from scripts.adapters import host_allowed
from scripts.fetch import MAX_RESPONSE_BYTES, Fetcher, FetchError


class FakeResponse:
    def __init__(self, status_code, text="", headers=None):
        self.status_code = status_code
        self.text = text
        self.encoding = "utf-8"
        self.headers = headers or {}

    @property
    def content(self):
        return self.text.encode("utf-8")


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(fetch_mod.time, "sleep", lambda seconds: None)


def _fetcher(**kwargs):
    return Fetcher(delay=0, host_allowed=host_allowed, **kwargs)


def test_redirect_to_disallowed_host_is_refused(monkeypatch):
    """ردّ 302 من مصدر مخترَق نحو عنوان داخلي يجب ألا يُتَّبع (SSRF)."""
    fetcher = _fetcher()
    visited = []

    def fake_get(url, timeout, headers=None, **kw):
        visited.append(url)
        if "qanoonsa" in url:
            return FakeResponse(302, headers={"Location": "http://169.254.169.254/latest/"})
        return FakeResponse(200, "سرّ")

    monkeypatch.setattr(fetcher.session, "get", fake_get)
    with pytest.raises(FetchError, match="خارج القائمة المسموح"):
        fetcher.get("https://qanoonsa.com/p/1/")
    assert visited == ["https://qanoonsa.com/p/1/"]  # لم يُطلب العنوان الداخلي


def test_redirect_within_allowed_hosts_is_followed(monkeypatch):
    fetcher = _fetcher()

    def fake_get(url, timeout, headers=None, **kw):
        if url.endswith("/old/"):
            return FakeResponse(301, headers={"Location": "https://qanoonsa.com/new/"})
        return FakeResponse(200, "المحتوى")

    monkeypatch.setattr(fetcher.session, "get", fake_get)
    assert fetcher.get("https://qanoonsa.com/old/") == "المحتوى"


def test_redirect_loop_is_bounded(monkeypatch):
    fetcher = _fetcher(max_attempts=1)
    monkeypatch.setattr(
        fetcher.session,
        "get",
        lambda url, timeout, headers=None, **kw: FakeResponse(
            302, headers={"Location": "https://qanoonsa.com/loop/"}
        ),
    )
    with pytest.raises(FetchError, match="تجاوز عدد التحويلات"):
        fetcher.get("https://qanoonsa.com/loop/")


def test_oversized_declared_response_is_refused(monkeypatch):
    fetcher = _fetcher(max_attempts=1)
    monkeypatch.setattr(
        fetcher.session,
        "get",
        lambda url, timeout, headers=None, **kw: FakeResponse(
            200, "x", headers={"Content-Length": str(MAX_RESPONSE_BYTES + 1)}
        ),
    )
    with pytest.raises(FetchError, match="أكبر من الحد"):
        fetcher.get("https://qanoonsa.com/p/1/")


def test_oversized_undeclared_response_is_refused(monkeypatch):
    """خادم لا يرسل Content-Length: يُفحص الحجم الفعلي أيضًا."""
    fetcher = _fetcher(max_attempts=1)
    monkeypatch.setattr(
        fetcher.session,
        "get",
        lambda url, timeout, headers=None, **kw: FakeResponse(200, "ب" * MAX_RESPONSE_BYTES),
    )
    with pytest.raises(FetchError, match="أكبر من الحد"):
        fetcher.get("https://qanoonsa.com/p/1/")


def test_retry_after_header_is_respected(monkeypatch):
    """429 مع Retry-After: ننتظر ما طلبه الخادم لا التراجع الأسّي وحده."""
    fetcher = _fetcher(max_attempts=2)
    slept = []
    monkeypatch.setattr(fetch_mod.time, "sleep", lambda s: slept.append(s))
    responses = iter([FakeResponse(429, headers={"Retry-After": "30"}), FakeResponse(200, "ok")])
    monkeypatch.setattr(
        fetcher.session, "get", lambda url, timeout, headers=None, **kw: next(responses)
    )
    assert fetcher.get("https://qanoonsa.com/p/1/") == "ok"
    assert slept == [30]


def test_retry_after_is_capped(monkeypatch):
    """قيمة ضخمة في Retry-After لا تعلّق التشغيلة."""
    fetcher = _fetcher(max_attempts=2)
    slept = []
    monkeypatch.setattr(fetch_mod.time, "sleep", lambda s: slept.append(s))
    responses = iter([FakeResponse(503, headers={"Retry-After": "99999"}), FakeResponse(200, "ok")])
    monkeypatch.setattr(
        fetcher.session, "get", lambda url, timeout, headers=None, **kw: next(responses)
    )
    fetcher.get("https://qanoonsa.com/p/1/")
    assert slept == [fetch_mod.MAX_RETRY_AFTER]
