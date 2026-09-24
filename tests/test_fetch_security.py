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

    def iter_content(self, chunk_size=1):
        data = self.content
        for i in range(0, len(data), chunk_size):
            yield data[i : i + chunk_size]

    def close(self):
        pass


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
        lambda url, timeout, headers=None, **kw: FakeResponse(302, headers={"Location": "https://qanoonsa.com/loop/"}),
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
    monkeypatch.setattr(fetcher.session, "get", lambda url, timeout, headers=None, **kw: next(responses))
    assert fetcher.get("https://qanoonsa.com/p/1/") == "ok"
    assert slept == [30]


def test_retry_after_is_capped(monkeypatch):
    """قيمة ضخمة في Retry-After لا تعلّق التشغيلة."""
    fetcher = _fetcher(max_attempts=2)
    slept = []
    monkeypatch.setattr(fetch_mod.time, "sleep", lambda s: slept.append(s))
    responses = iter([FakeResponse(503, headers={"Retry-After": "99999"}), FakeResponse(200, "ok")])
    monkeypatch.setattr(fetcher.session, "get", lambda url, timeout, headers=None, **kw: next(responses))
    fetcher.get("https://qanoonsa.com/p/1/")
    assert slept == [fetch_mod.MAX_RETRY_AFTER]


class EndlessStream(FakeResponse):
    """ردّ مجزّأ (chunked) بلا Content-Length ولا نهاية — يعدّ ما قُرئ منه."""

    def __init__(self):
        super().__init__(200)
        self.read = 0
        self.closed = False

    def iter_content(self, chunk_size=1):
        while True:
            self.read += chunk_size
            yield b"x" * chunk_size

    def close(self):
        self.closed = True


def test_streamed_body_is_cut_at_the_cap(monkeypatch):
    """السقف يُطبَّق أثناء التنزيل: لا يُقرأ الجسم كاملًا قبل قياسه."""
    fetcher = _fetcher(max_attempts=1)
    response = EndlessStream()
    monkeypatch.setattr(fetcher.session, "get", lambda url, timeout, headers=None, **kw: response)
    with pytest.raises(FetchError, match="أكبر من الحد"):
        fetcher.get("https://qanoonsa.com/p/1/")
    assert response.closed
    assert response.read <= MAX_RESPONSE_BYTES + fetch_mod._CHUNK_BYTES


def test_requests_are_streamed(monkeypatch):
    fetcher = _fetcher()
    seen = {}

    def fake_get(url, timeout, headers=None, **kw):
        seen.update(kw)
        return FakeResponse(200, "ok")

    monkeypatch.setattr(fetcher.session, "get", fake_get)
    fetcher.get("https://qanoonsa.com/p/1/")
    assert seen.get("stream") is True


def test_robots_redirect_to_foreign_host_is_not_followed(monkeypatch):
    """طلب robots.txt يمرّ بنفس فحص المضيف: تحويله إلى عنوان داخلي لا يُتَّبع."""
    fetcher = _fetcher(respect_robots=True)
    visited = []

    def fake_get(url, timeout, headers=None, **kw):
        visited.append(url)
        if url.endswith("/robots.txt") and "qanoonsa" in url:
            internal = "http://169.254.169.254/robots.txt"
            # كسلوك requests: يتبع التحويل تلقائيًا ما لم يُطلب allow_redirects=False
            if kw.get("allow_redirects", True):
                return fake_get(internal, timeout, headers)
            return FakeResponse(302, headers={"Location": internal})
        return FakeResponse(200, "المحتوى")

    monkeypatch.setattr(fetcher.session, "get", fake_get)
    assert fetcher.get("https://qanoonsa.com/p/1/") == "المحتوى"
    assert not any("169.254" in url for url in visited)
