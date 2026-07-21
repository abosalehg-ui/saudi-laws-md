"""طبقة HTTP مهذبة: user-agent واضح، مهلة، تأخير بين الطلبات، وإعادة محاولة متدرجة."""

from __future__ import annotations

import time

import requests

USER_AGENT = "saudi-laws-md/0.1 (+https://github.com/abosalehg-ui/saudi-laws-md)"
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class FetchError(Exception):
    pass


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

    def get(self, url: str) -> str:
        last_error: str = ""
        for attempt in range(self.max_attempts):
            self._wait()
            try:
                response = self.session.get(url, timeout=self.timeout)
            except requests.RequestException as exc:
                last_error = str(exc)
            else:
                if response.status_code not in _RETRYABLE_STATUS:
                    response.raise_for_status()
                    if not response.encoding or response.encoding.lower() == "iso-8859-1":
                        response.encoding = "utf-8"
                    return response.text
                last_error = f"HTTP {response.status_code}"
            if attempt < self.max_attempts - 1:
                time.sleep(2 ** (attempt + 1))
        raise FetchError(f"فشل جلب {url}: {last_error}")
