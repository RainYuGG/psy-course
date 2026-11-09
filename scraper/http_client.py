"""Shared HTTP client with browser User-Agent, retry policy, and SSL fallback."""

from __future__ import annotations

import ssl
from typing import Any

import httpx

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)


def _is_ssl_error(exc: BaseException) -> bool:
    """Detect whether an exception chain indicates an SSL/TLS certificate failure."""
    current: BaseException | None = exc
    while current is not None:
        if isinstance(current, ssl.SSLError):
            return True
        msg = str(current).upper()
        if "SSL" in msg or "CERTIFICATE_VERIFY_FAILED" in msg or "CERT" in msg:
            return True
        current = current.__cause__ or current.__context__
    return False


class HttpClient:
    """HTTP client wrapper with retry and automatic verify=False SSL fallback."""

    def __init__(
        self,
        timeout: float = 15.0,
        retries: int = 2,
        user_agent: str = DEFAULT_USER_AGENT,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.timeout = timeout
        self.retries = max(0, retries)
        base_headers = {
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        }
        if headers:
            base_headers.update(headers)
        self.headers = base_headers

    def _fetch_with_verify(self, url: str, verify: bool) -> str:
        last_exc: Exception | None = None
        total_attempts = self.retries + 1
        with httpx.Client(
            timeout=self.timeout,
            headers=self.headers,
            follow_redirects=True,
            verify=verify,
        ) as client:
            for _ in range(total_attempts):
                try:
                    response = client.get(url)
                    response.raise_for_status()
                    # Handle legacy Big5 / UTF-8 encoding detection gracefully
                    if response.encoding is None or response.encoding.lower() == "iso-8859-1":
                        response.encoding = response.apparent_encoding or "utf-8"
                    return response.text
                except httpx.HTTPStatusError as exc:
                    last_exc = exc
                    if exc.response.status_code < 500:
                        raise
                except httpx.RequestError as exc:
                    last_exc = exc
                    if verify and _is_ssl_error(exc):
                        raise
        if last_exc is not None:
            raise last_exc
        raise RuntimeError(f"Failed to fetch {url}")

    def get_text(self, url: str) -> str:
        """Fetch URL text with automatic retry and fallback to verify=False on SSL error."""
        try:
            return self._fetch_with_verify(url, verify=True)
        except Exception as exc:
            if _is_ssl_error(exc):
                return self._fetch_with_verify(url, verify=False)
            raise

    def _fetch_bytes_with_verify(self, url: str, verify: bool) -> bytes:
        last_exc: Exception | None = None
        total_attempts = self.retries + 1
        with httpx.Client(
            timeout=self.timeout,
            headers=self.headers,
            follow_redirects=True,
            verify=verify,
        ) as client:
            for _ in range(total_attempts):
                try:
                    response = client.get(url)
                    response.raise_for_status()
                    return response.content
                except httpx.HTTPStatusError as exc:
                    last_exc = exc
                    if exc.response.status_code < 500:
                        raise
                except httpx.RequestError as exc:
                    last_exc = exc
                    if verify and _is_ssl_error(exc):
                        raise
        if last_exc is not None:
            raise last_exc
        raise RuntimeError(f"Failed to fetch {url}")

    def get_bytes(self, url: str) -> bytes:
        """Fetch URL raw bytes with the same retry/verify-fallback policy as get_text."""
        try:
            return self._fetch_bytes_with_verify(url, verify=True)
        except Exception as exc:
            if _is_ssl_error(exc):
                return self._fetch_bytes_with_verify(url, verify=False)
            raise

    def get(self, url: str, **kwargs: Any) -> str:
        """Alias for get_text for convenience."""
        return self.get_text(url)

    def post_json(
        self,
        url: str,
        payload: dict[str, Any],
        headers: dict[str, str] | None = None,
    ) -> str:
        """POST a JSON body with the same retry and verify=False-on-SSL-error policy as get_text."""

        def fetch(verify: bool) -> str:
            last_exc: Exception | None = None
            with httpx.Client(
                timeout=self.timeout,
                headers={**self.headers, **(headers or {})},
                follow_redirects=True,
                verify=verify,
            ) as client:
                for _ in range(self.retries + 1):
                    try:
                        response = client.post(url, json=payload)
                        response.raise_for_status()
                        return response.text
                    except httpx.HTTPStatusError as exc:
                        last_exc = exc
                        if exc.response.status_code < 500:
                            raise
                    except httpx.RequestError as exc:
                        last_exc = exc
                        if verify and _is_ssl_error(exc):
                            raise
            if last_exc is not None:
                raise last_exc
            raise RuntimeError(f"Failed to POST {url}")

        try:
            return fetch(verify=True)
        except Exception as exc:
            if _is_ssl_error(exc):
                return fetch(verify=False)
            raise
