import pytest
import requests

import scripts.fetch as fetch_mod
from scripts.fetch import Fetcher, FetchError


class FakeResponse:
    def __init__(self, status_code: int, text: str = "", encoding: str | None = "utf-8"):
        self.status_code = status_code
        self.text = text
        self.encoding = encoding
        self.headers: dict[str, str] = {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error")


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    # يتجنّب انتظار إعادة المحاولة الفعلي (2/4/8 ثوانٍ) أثناء الاختبارات
    monkeypatch.setattr(fetch_mod.time, "sleep", lambda seconds: None)


def _fetcher(**kwargs):
    return Fetcher(delay=0, **kwargs)


def test_success_returns_text(monkeypatch):
    fetcher = _fetcher()
    calls = []
    monkeypatch.setattr(
        fetcher.session, "get", lambda url, timeout, headers=None: calls.append(url) or FakeResponse(200, "ok")
    )
    assert fetcher.get("https://nezams.com/x/") == "ok"
    assert calls == ["https://nezams.com/x/"]


def test_retries_on_retryable_status_then_succeeds(monkeypatch):
    fetcher = _fetcher()
    responses = iter([FakeResponse(503), FakeResponse(200, "ok")])
    calls = []
    monkeypatch.setattr(
        fetcher.session, "get", lambda url, timeout, headers=None: calls.append(1) or next(responses)
    )
    assert fetcher.get("https://nezams.com/x/") == "ok"
    assert len(calls) == 2


def test_gives_up_after_max_attempts(monkeypatch):
    fetcher = _fetcher(max_attempts=3)
    calls = []
    monkeypatch.setattr(
        fetcher.session, "get", lambda url, timeout, headers=None: calls.append(1) or FakeResponse(503)
    )
    with pytest.raises(FetchError):
        fetcher.get("https://nezams.com/x/")
    assert len(calls) == 3


def test_network_exception_is_retried(monkeypatch):
    fetcher = _fetcher(max_attempts=2)
    calls = []

    def fake_get(url, timeout, headers=None):
        calls.append(1)
        raise requests.ConnectionError("boom")

    monkeypatch.setattr(fetcher.session, "get", fake_get)
    with pytest.raises(FetchError, match="boom"):
        fetcher.get("https://nezams.com/x/")
    assert len(calls) == 2


def test_non_retryable_status_raises_immediately_without_retry(monkeypatch):
    fetcher = _fetcher(max_attempts=4)
    calls = []
    monkeypatch.setattr(
        fetcher.session, "get", lambda url, timeout, headers=None: calls.append(1) or FakeResponse(404)
    )
    with pytest.raises(requests.HTTPError):
        fetcher.get("https://nezams.com/x/")
    assert len(calls) == 1  # لا إعادة محاولة لخطأ غير قابل للإعادة


def test_iso_8859_1_encoding_forced_to_utf8(monkeypatch):
    fetcher = _fetcher()
    response = FakeResponse(200, "نص", encoding="ISO-8859-1")
    monkeypatch.setattr(fetcher.session, "get", lambda url, timeout, headers=None: response)
    fetcher.get("https://nezams.com/x/")
    assert response.encoding == "utf-8"


def test_missing_encoding_forced_to_utf8(monkeypatch):
    fetcher = _fetcher()
    response = FakeResponse(200, "نص", encoding=None)
    monkeypatch.setattr(fetcher.session, "get", lambda url, timeout, headers=None: response)
    fetcher.get("https://nezams.com/x/")
    assert response.encoding == "utf-8"


def test_declared_utf8_encoding_left_untouched(monkeypatch):
    fetcher = _fetcher()
    response = FakeResponse(200, "نص", encoding="utf-8")
    monkeypatch.setattr(fetcher.session, "get", lambda url, timeout, headers=None: response)
    fetcher.get("https://nezams.com/x/")
    assert response.encoding == "utf-8"


def test_get_conditional_sends_etag_and_last_modified(monkeypatch):
    fetcher = _fetcher()
    seen_headers = {}

    def fake_get(url, timeout, headers=None):
        seen_headers.update(headers or {})
        return FakeResponse(200, "نص جديد")

    monkeypatch.setattr(fetcher.session, "get", fake_get)
    result = fetcher.get_conditional(
        "https://nezams.com/x/", etag='"abc"', last_modified="Wed, 01 Jan 2026 00:00:00 GMT"
    )
    assert seen_headers == {
        "If-None-Match": '"abc"',
        "If-Modified-Since": "Wed, 01 Jan 2026 00:00:00 GMT",
    }
    assert result.not_modified is False
    assert result.text == "نص جديد"


def test_get_conditional_no_prior_values_sends_no_conditional_headers(monkeypatch):
    fetcher = _fetcher()
    seen_headers = {}

    def fake_get(url, timeout, headers=None):
        seen_headers["value"] = headers
        return FakeResponse(200, "نص")

    monkeypatch.setattr(fetcher.session, "get", fake_get)
    fetcher.get_conditional("https://nezams.com/x/")
    assert seen_headers["value"] is None


def test_get_conditional_304_returns_not_modified_without_text(monkeypatch):
    fetcher = _fetcher()
    response = FakeResponse(304)
    monkeypatch.setattr(fetcher.session, "get", lambda url, timeout, headers=None: response)
    result = fetcher.get_conditional(
        "https://nezams.com/x/", etag='"abc"', last_modified="Wed, 01 Jan 2026 00:00:00 GMT"
    )
    assert result.not_modified is True
    assert result.text is None
    assert result.etag == '"abc"'
    assert result.last_modified == "Wed, 01 Jan 2026 00:00:00 GMT"


def test_get_conditional_captures_new_etag_from_response(monkeypatch):
    fetcher = _fetcher()
    response = FakeResponse(200, "نص")
    response.headers = {"ETag": '"new-etag"', "Last-Modified": "Thu, 02 Jan 2026 00:00:00 GMT"}
    monkeypatch.setattr(fetcher.session, "get", lambda url, timeout, headers=None: response)
    result = fetcher.get_conditional("https://nezams.com/x/")
    assert result.etag == '"new-etag"'
    assert result.last_modified == "Thu, 02 Jan 2026 00:00:00 GMT"
