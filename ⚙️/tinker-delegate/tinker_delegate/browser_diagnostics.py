"""Bounded browser-control readiness diagnostics.

This module is safe for deployment evidence: it never navigates, clicks, types,
screenshots, returns page text, or exposes raw browser/CDP URLs. It only reports
coarse readiness stages and endpoint hashes/classes.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import socket
import ssl
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import urlopen

from playwright.async_api import async_playwright

from tinker_delegate.browser_ready import _cdp_probe_url
from tinker_delegate.config import Settings

BROWSER_READINESS_VERSION = "2026-07-08.2"
SURFACE = "browser_control_path"


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _url_class(value: str) -> str:
    if not value:
        return "empty"
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    if host in {"localhost", "127.0.0.1", "::1"}:
        return "loopback"
    if host.startswith("172.") or host.startswith("10.") or host.startswith("192.168."):
        return "private_network"
    if host.endswith(".phala.network"):
        return "phala_gateway"
    if parsed.scheme in {"ws", "wss", "http", "https"}:
        return "network_url"
    return "other"


def _endpoint_summary(value: str) -> dict[str, Any]:
    return {
        "configured": bool(value),
        "url_class": _url_class(value),
        "url_hash": _sha256(value) if value else "",
    }


def _browser_family(browser_value: str) -> str:
    lower = browser_value.lower()
    if "chrome" in lower or "chromium" in lower:
        return "chromium"
    if browser_value:
        return "other"
    return "unknown"


def _http_probe_cdp(settings: Settings) -> dict[str, Any]:
    if not settings.cdp_url:
        return {
            "attempted": False,
            "success": False,
            "error_kind": "not_configured",
        }

    probe_url = _cdp_probe_url(settings.cdp_url)
    result: dict[str, Any] = {
        "attempted": True,
        "success": False,
        "probe_url_hash": _sha256(probe_url),
        "probe_url_class": _url_class(probe_url),
        "metadata_json": False,
        "websocket_advertised": False,
        "browser_family": "unknown",
        "error_kind": "",
    }
    try:
        with urlopen(probe_url, timeout=5) as response:
            payload = response.read().decode("utf-8", errors="replace")
        data = json.loads(payload)
    except HTTPError as exc:
        result["error_kind"] = f"http_{exc.code}"
        return result
    except URLError:
        result["error_kind"] = "connection_unreachable"
        return result
    except TimeoutError:
        result["error_kind"] = "timeout"
        return result
    except json.JSONDecodeError:
        result["error_kind"] = "invalid_json"
        return result
    except Exception:
        result["error_kind"] = "unknown_failure"
        return result

    websocket = str(data.get("webSocketDebuggerUrl") or "")
    result.update(
        {
            "success": bool(websocket),
            "metadata_json": True,
            "websocket_advertised": bool(websocket),
            "websocket_url_class": _url_class(websocket),
            "websocket_url_hash": _sha256(websocket) if websocket else "",
            "browser_family": _browser_family(str(data.get("Browser") or "")),
            "error_kind": "" if websocket else "missing_websocket_debugger_url",
        }
    )
    return result


def _http_status_band(status_code: int) -> str:
    if status_code == 101:
        return "101"
    if 100 <= status_code <= 599:
        return f"{status_code // 100}xx"
    return "unknown"


def _read_http_headers(sock: socket.socket) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while total < 4096:
        chunk = sock.recv(512)
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        joined = b"".join(chunks)
        if b"\r\n\r\n" in joined:
            return joined.split(b"\r\n\r\n", 1)[0]
    return b"".join(chunks)


def _probe_websocket_upgrade(websocket_url: str, timeout: float) -> dict[str, Any]:
    result: dict[str, Any] = {
        "attempted": bool(websocket_url),
        "success": False,
        "url_class": _url_class(websocket_url),
        "url_hash": _sha256(websocket_url) if websocket_url else "",
        "tcp_connect": False,
        "tls": False,
        "upgrade_request_sent": False,
        "http_status_band": "",
        "error_kind": "not_configured" if not websocket_url else "",
    }
    if not websocket_url:
        return result

    parsed = urlparse(websocket_url)
    if parsed.scheme not in {"ws", "wss"} or not parsed.hostname:
        result["error_kind"] = "unsupported_websocket_url"
        return result

    port = parsed.port or (443 if parsed.scheme == "wss" else 80)
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    timeout_seconds = max(0.1, min(float(timeout or 5.0), 10.0))
    host_header = parsed.hostname if parsed.port is None else f"{parsed.hostname}:{port}"

    raw_sock: socket.socket | None = None
    wrapped_sock: socket.socket | None = None
    try:
        raw_sock = socket.create_connection((parsed.hostname, port), timeout=timeout_seconds)
        raw_sock.settimeout(timeout_seconds)
        result["tcp_connect"] = True
        if parsed.scheme == "wss":
            wrapped_sock = ssl.create_default_context().wrap_socket(
                raw_sock,
                server_hostname=parsed.hostname,
            )
            sock: socket.socket = wrapped_sock
            result["tls"] = True
        else:
            sock = raw_sock

        nonce = base64.b64encode(os.urandom(16)).decode("ascii")
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host_header}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {nonce}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "\r\n"
        )
        sock.sendall(request.encode("ascii"))
        result["upgrade_request_sent"] = True
        headers = _read_http_headers(sock).decode("iso-8859-1", errors="replace")
    except socket.timeout:
        result["error_kind"] = "timeout"
        return result
    except ConnectionRefusedError:
        result["error_kind"] = "connection_refused"
        return result
    except ssl.SSLError:
        result["error_kind"] = "tls_failed"
        return result
    except OSError:
        result["error_kind"] = "network_error"
        return result
    finally:
        if wrapped_sock is not None:
            try:
                wrapped_sock.close()
            except OSError:
                pass
        elif raw_sock is not None:
            try:
                raw_sock.close()
            except OSError:
                pass

    status_code = 0
    first_line = headers.splitlines()[0] if headers.splitlines() else ""
    parts = first_line.split()
    if len(parts) >= 2 and parts[1].isdigit():
        status_code = int(parts[1])
    result["http_status_band"] = _http_status_band(status_code)
    result["success"] = status_code == 101
    result["error_kind"] = "" if status_code == 101 else "upgrade_rejected"
    if not status_code:
        result["error_kind"] = "invalid_upgrade_response"
    return result


def _probe_cdp_websocket_handshake(settings: Settings) -> dict[str, Any]:
    result: dict[str, Any] = {
        "attempted": bool(settings.cdp_url),
        "success": False,
        "metadata_success": False,
        "url_class": "empty",
        "url_hash": "",
        "tcp_connect": False,
        "tls": False,
        "upgrade_request_sent": False,
        "http_status_band": "",
        "error_kind": "not_configured" if not settings.cdp_url else "",
    }
    if not settings.cdp_url:
        return result

    probe_url = _cdp_probe_url(settings.cdp_url)
    try:
        with urlopen(probe_url, timeout=5) as response:
            payload = response.read().decode("utf-8", errors="replace")
        data = json.loads(payload)
    except HTTPError as exc:
        result["error_kind"] = f"metadata_http_{exc.code}"
        return result
    except URLError:
        result["error_kind"] = "metadata_connection_unreachable"
        return result
    except TimeoutError:
        result["error_kind"] = "metadata_timeout"
        return result
    except json.JSONDecodeError:
        result["error_kind"] = "metadata_invalid_json"
        return result
    except Exception:
        result["error_kind"] = "metadata_unknown_failure"
        return result

    result["metadata_success"] = True
    websocket = str(data.get("webSocketDebuggerUrl") or "")
    if not websocket:
        result["error_kind"] = "missing_websocket_debugger_url"
        return result

    result.update(_probe_websocket_upgrade(websocket, settings.cdp_connect_timeout))
    result["metadata_success"] = True
    return result


async def _try_playwright_server(settings: Settings) -> dict[str, Any]:
    result: dict[str, Any] = {
        "attempted": bool(settings.browser_ws_endpoint),
        "success": False,
        "error_kind": "not_configured" if not settings.browser_ws_endpoint else "",
    }
    if not settings.browser_ws_endpoint:
        return result

    try:
        async with async_playwright() as playwright:
            browser = await asyncio.wait_for(
                playwright.chromium.connect(settings.browser_ws_endpoint),
                timeout=settings.browser_connect_timeout,
            )
            context_count = len(getattr(browser, "contexts", []) or [])
            await browser.close()
    except asyncio.TimeoutError:
        result["error_kind"] = "timeout"
        return result
    except Exception:
        result["error_kind"] = "connect_failed"
        return result

    result["success"] = True
    result["context_count_band"] = "2+" if context_count >= 2 else str(context_count)
    return result


async def _try_cdp_connect(settings: Settings) -> dict[str, Any]:
    result: dict[str, Any] = {
        "attempted": bool(settings.cdp_url),
        "success": False,
        "error_kind": "not_configured" if not settings.cdp_url else "",
    }
    if not settings.cdp_url:
        return result

    try:
        async with async_playwright() as playwright:
            browser = await asyncio.wait_for(
                playwright.chromium.connect_over_cdp(settings.cdp_url),
                timeout=settings.cdp_connect_timeout,
            )
            context_count = len(getattr(browser, "contexts", []) or [])
            await browser.close()
    except asyncio.TimeoutError:
        result["error_kind"] = "timeout"
        return result
    except Exception:
        result["error_kind"] = "connect_failed"
        return result

    result["success"] = True
    result["context_count_band"] = "2+" if context_count >= 2 else str(context_count)
    return result


async def browser_readiness(settings: Settings | None = None) -> dict[str, Any]:
    """Return bounded readiness evidence for browser-control endpoints."""

    if settings is None:
        settings = Settings()
    cdp_http = await asyncio.to_thread(_http_probe_cdp, settings)
    cdp_websocket = await asyncio.to_thread(_probe_cdp_websocket_handshake, settings)
    playwright_server = await _try_playwright_server(settings)
    cdp_connect = await _try_cdp_connect(settings)
    success = bool(playwright_server.get("success") or cdp_connect.get("success"))
    if success:
        error_kind = ""
    elif cdp_http.get("attempted") and not cdp_http.get("success"):
        error_kind = f"cdp_http_{cdp_http.get('error_kind') or 'failed'}"
    elif cdp_connect.get("attempted"):
        error_kind = f"cdp_{cdp_connect.get('error_kind') or 'failed'}"
    elif playwright_server.get("attempted"):
        error_kind = f"playwright_{playwright_server.get('error_kind') or 'failed'}"
    else:
        error_kind = "browser_not_configured"

    return {
        "version": BROWSER_READINESS_VERSION,
        "surface": SURFACE,
        "raw_secret_egress": False,
        "bounded_output": True,
        "read_only": True,
        "navigates": False,
        "captures_page_text": False,
        "success": success,
        "error_kind": error_kind,
        "browser_ws_endpoint": _endpoint_summary(settings.browser_ws_endpoint),
        "cdp_endpoint": _endpoint_summary(settings.cdp_url),
        "local_browser_fallback_enabled": bool(settings.local_browser_fallback),
        "playwright_server_connect": playwright_server,
        "cdp_http_metadata": cdp_http,
        "cdp_websocket_handshake": cdp_websocket,
        "cdp_connect": cdp_connect,
    }


def run_browser_readiness(settings: Settings | None = None) -> dict[str, Any]:
    return asyncio.run(browser_readiness(settings))
