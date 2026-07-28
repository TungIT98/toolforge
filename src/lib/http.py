"""HTTP client shim for CF Python Workers.

CF Python Workers (pyodide) does NOT bundle `httpx` by default, and
`wrangler 4.80.0` doesn't auto-install Python deps from `requirements.txt`.
This module provides a minimal async HTTP client implemented with
`urllib.request` (stdlib) so the rest of the codebase can keep using
an `httpx`-shaped API.

Trade-offs vs real httpx:
- Only POST/GET with json body and Bearer header
- No streaming, no HTTP/2, no proxies, no retries
- Synchronous I/O (urllib) wrapped in `asyncio.to_thread` so it
  doesn't block the Workers event loop
- Tested patterns: POST with JSON body + auth header, check status,
  parse JSON response

If you need full httpx semantics, deploy with `wrangler versions deploy`
and bundle httpx via a custom build step (not yet supported on the
free tier as of 2026-07).
"""
from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request
from typing import Any


class HTTPError(Exception):
    """Raised when the HTTP layer fails (timeout, connection, etc.)."""


class TimeoutException(HTTPError):
    """Raised on request timeout."""


class _Response:
    """Minimal response object with the httpx-style attrs we use.

    Accepts:
        _Response(200, "body string")
        _Response(200, json.dumps({...}))  # position 2 = body string
        _Response(200, body_json={...})  # kwarg, accepts dict (gets JSON-serialized)
        _Response(200, text="...")  # explicit text kwarg
    """

    def __init__(
        self,
        status_code: int,
        body: str | None = None,
        *,
        body_json: Any | None = None,
        text: str | None = None,
    ):
        if body_json is not None and not isinstance(body_json, str):
            self._body = json.dumps(body_json, ensure_ascii=False)
        else:
            self._body = text if text is not None else (body or "")
        self.status_code = status_code
        self.text = self._body

    def json(self) -> Any:
        return json.loads(self._body) if self._body else {}


class AsyncClient:
    """Async context-manager wrapper that mimics httpx.AsyncClient for
    `await client.post(url, headers=..., json=...)`.

    Usage:
        async with AsyncClient(timeout=30) as client:
            resp = await client.post(url, headers={...}, json={...})
            assert resp.status_code == 200
            data = resp.json()
    """

    def __init__(self, timeout: int = 30) -> None:
        self.timeout = timeout

    async def __aenter__(self) -> "AsyncClient":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        return None

    async def post(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
    ) -> _Response:
        return await self._request("POST", url, headers=headers, json_body=json)

    async def get(
        self,
        url: str,
        headers: dict[str, str] | None = None,
    ) -> _Response:
        return await self._request("GET", url, headers=headers, json_body=None)

    async def _request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None,
        json_body: dict[str, Any] | None,
    ) -> _Response:
        req_headers = dict(headers or {})
        body_bytes: bytes | None = None
        if json_body is not None:
            body_bytes = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
            req_headers.setdefault("Content-Type", "application/json")

        def _do_request() -> _Response:
            req = urllib.request.Request(
                url,
                data=body_bytes,
                headers=req_headers,
                method=method,
            )
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    raw = resp.read().decode("utf-8", errors="replace")
                    return _Response(resp.status, raw)
            except urllib.error.HTTPError as e:
                # Non-2xx: return as a Response (caller checks status)
                raw = e.read().decode("utf-8", errors="replace") if e.fp else ""
                return _Response(e.code, raw)
            except urllib.error.URLError as e:
                if "timed out" in str(e).lower() or "timeout" in str(e).lower():
                    raise TimeoutException(f"timeout after {self.timeout}s") from e
                raise HTTPError(f"url error: {e}") from e
            except (TimeoutError, ConnectionError) as e:
                raise TimeoutException(f"connection timeout: {e}") from e
            except Exception as e:
                # Classify timeouts that bubble up from socket layer
                msg = str(e).lower()
                if "timed out" in msg or "timeout" in msg:
                    raise TimeoutException(f"timeout: {e}") from e
                raise HTTPError(f"request failed: {e}") from e

        # Run sync urllib in a thread so we don't block the event loop
        return await asyncio.to_thread(_do_request)


# Module-level shims so `import http; http.TimeoutException` works too
# (in case any code does this).
HTTPError = HTTPError
TimeoutException = TimeoutException
