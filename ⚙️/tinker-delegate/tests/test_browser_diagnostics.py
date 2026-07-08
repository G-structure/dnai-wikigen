import json
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from tinker_delegate import api
from tinker_delegate.browser_diagnostics import _http_probe_cdp, browser_readiness
from tinker_delegate.config import Settings
from tinker_delegate.main import _render_bounded_json


class FakeResponse:
    def __init__(self, payload: dict):
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self.payload


class BrowserDiagnosticsTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.original_settings = api.settings

    def tearDown(self):
        api.settings = self.original_settings

    async def test_browser_readiness_no_config_is_bounded(self):
        result = await browser_readiness(
            Settings(browser_ws_endpoint="", cdp_url="", local_browser_fallback=False)
        )

        self.assertFalse(result["success"])
        self.assertEqual(result["error_kind"], "browser_not_configured")
        self.assertFalse(result["raw_secret_egress"])
        self.assertTrue(result["bounded_output"])
        self.assertFalse(result["captures_page_text"])
        _render_bounded_json(result)

    def test_cdp_http_probe_hashes_raw_browser_urls(self):
        raw_cdp_url = "http://172.20.0.3:9223"
        raw_ws_url = "ws://172.20.0.3:9223/devtools/browser/raw-session-id"
        response = FakeResponse(
            {
                "Browser": "Chrome/120.0.0.0",
                "webSocketDebuggerUrl": raw_ws_url,
            }
        )

        with patch("tinker_delegate.browser_diagnostics.urlopen", return_value=response):
            result = _http_probe_cdp(Settings(cdp_url=raw_cdp_url))

        self.assertTrue(result["success"])
        self.assertEqual(result["browser_family"], "chromium")
        self.assertEqual(result["websocket_url_class"], "private_network")
        rendered = _render_bounded_json(result)
        self.assertNotIn(raw_cdp_url, rendered)
        self.assertNotIn(raw_ws_url, rendered)
        self.assertIn("websocket_url_hash", result)

    def test_browser_readiness_endpoint_disabled_by_default(self):
        api.settings = Settings(allow_browser_readiness_endpoint=False)
        client = TestClient(api.app)

        response = client.get("/browser/readiness")

        self.assertEqual(response.status_code, 403)
        self.assertIn("browser readiness endpoint is disabled", response.json()["detail"])

    def test_browser_readiness_endpoint_returns_bounded_probe(self):
        api.settings = Settings(allow_browser_readiness_endpoint=True)
        client = TestClient(api.app)
        bounded = {
            "surface": "browser_control_path",
            "raw_secret_egress": False,
            "bounded_output": True,
            "read_only": True,
            "success": False,
            "error_kind": "browser_not_configured",
        }

        async def fake_readiness(settings):
            return bounded

        with patch("tinker_delegate.browser_diagnostics.browser_readiness", new=fake_readiness):
            response = client.get("/browser/readiness")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), bounded)


if __name__ == "__main__":
    unittest.main()
