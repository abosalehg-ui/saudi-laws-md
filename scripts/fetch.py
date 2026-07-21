"""طبقة HTTP مهذبة: user-agent واضح، مهلة، تأخير بين الطلبات، وإعادة محاولة متدرجة."""

from __future__ import annotations

import time
from dataclasses import dataclass

import requests

USER_AGENT = "saudi-laws-md/0.1 (+https://github.com/abosalehg-ui/saudi-laws-md)"
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class FetchError(Exception):
    pass


@dataclass
class FetchResult:
    """نتيجة جلب شرطي: text=None وnot_modified=True إن لم يتغيّر المحتوى (304)."""

    text: str | None
    etag: str | None
    last_modified: str | None
    not_modified: bool


class Fetcher:
    def __init__(self, delay: float = 1.5, timeout: float = 30, max_attempts: int = 4):
        self.delay = delay
        self.timeout = timeout
        self.max_attempts = max_attempts
        self._last_request: float | None = None
        self.session = requests.Session()
        self.session.headers.update(
            {"User-Agent": USER_AGENT, "Accept-Language": "ar,en;q=0.8"}
        )

    def _wait(self) -> None:
        if self._last_request is not None:
            remaining = self.delay - (time.monotonic() - self._last_request)
            if remaining > 0:
                time.sleep(remaining)
        self._last_request = time.monotonic()

    def _request(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        extra_ok_status: frozenset[int] = frozenset(),
    ) -> requests.Response:
        last_error: str = ""
        for attempt in range(self.max_attempts):
            self._wait()
            try:
                response = self.session.get(url, timeout=self.timeout, headers=headers)
            except requests.RequestException as exc:
                last_error = str(exc)
            else:
                if response.status_code in extra_ok_status:
                    return response
                if response.status_code not in _RETRYABLE_STATUS:
                    response.raise_for_status()
                    if not response.encoding or response.encoding.lower() == "iso-8859-1":
                        response.encoding = "utf-8"
                    return response
                last_error = f"HTTP {response.status_code}"
            if attempt < self.max_attempts - 1:
                time.sleep(2 ** (attempt + 1))
        raise FetchError(f"فشل جلب {url}: {last_error}")

    def get(self, url: str) -> str:
        return self._request(url).text

    def get_conditional(
        self, url: str, etag: str | None = None, last_modified: str | None = None
    ) -> FetchResult:
        """يجلب الصفحة، مرسِلًا If-None-Match/If-Modified-Since إن توفّرا.

        عند رد 304 (لم يتغيّر المحتوى منذ آخر جلب) يعيد نتيجة بلا نص بدل
        تنزيل/تحليل/إعادة كتابة الصفحة من جديد — يفيد إعادة زيارة روابط
        سبق استيرادها للتحقق من وجود تعديل، دون هدر نطاق ترددي أو تغييرات
        زائفة في git (retrieved_at يتغيّر مع كل إعادة كتابة حتى لو تطابق
        المحتوى).
        """
        headers: dict[str, str] = {}
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified
        response = self._request(url, headers=headers or None, extra_ok_status=frozenset({304}))
        if response.status_code == 304:
            return FetchResult(text=None, etag=etag, last_modified=last_modified, not_modified=True)
        return FetchResult(
            text=response.text,
            etag=response.headers.get("ETag"),
            last_modified=response.headers.get("Last-Modified"),
            not_modified=False,
        )
