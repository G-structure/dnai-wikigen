import hashlib
import unittest
from unittest.mock import AsyncMock, Mock, patch

from tinker_delegate.config import Settings
from tinker_delegate.signup import signup


class AsyncPlaywrightStub:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeOracle:
    def __init__(self, settings):
        self.settings = settings

    def get_email(self):
        return "oracle@example.com"


class FakeContext:
    pages = [object()]


class FakeStore:
    def __init__(self, fail_save: bool = False):
        self.fail_save = fail_save
        self.saved_key = None

    def save(self, api_key: str) -> None:
        if self.fail_save:
            raise RuntimeError("seal failed")
        self.saved_key = api_key


class SignupKeyEgressTest(unittest.IsolatedAsyncioTestCase):
    async def test_signup_returns_bounded_metadata_not_raw_api_key(self):
        api_key = "tml-secret-key-material"
        store = FakeStore()

        with (
            patch("tinker_delegate.signup.OracleClient", FakeOracle),
            patch("tinker_delegate.signup.async_playwright", return_value=AsyncPlaywrightStub()),
            patch("tinker_delegate.signup.connect_chromium", new=AsyncMock(return_value=object())),
            patch("tinker_delegate.signup.get_browser_context", new=AsyncMock(return_value=FakeContext())),
            patch("tinker_delegate.signup._authenticate", new=AsyncMock()),
            patch("tinker_delegate.signup._handle_onboarding", new=AsyncMock()),
            patch("tinker_delegate.signup._create_api_key", new=AsyncMock(return_value=api_key)),
            patch("tinker_delegate.signup.build_api_key_store", return_value=store),
        ):
            result = await signup(Settings())

        self.assertTrue(result["success"])
        self.assertTrue(result["stored"])
        self.assertTrue(result["api_key_created"])
        self.assertNotIn("api_key", result)
        self.assertEqual(result["api_key_hash"], hashlib.sha256(api_key.encode()).hexdigest())
        self.assertEqual(store.saved_key, api_key)

    async def test_signup_fails_closed_when_api_key_store_fails(self):
        api_key = "tml-secret-key-material"

        with (
            patch("tinker_delegate.signup.OracleClient", FakeOracle),
            patch("tinker_delegate.signup.async_playwright", return_value=AsyncPlaywrightStub()),
            patch("tinker_delegate.signup.connect_chromium", new=AsyncMock(return_value=object())),
            patch("tinker_delegate.signup.get_browser_context", new=AsyncMock(return_value=FakeContext())),
            patch("tinker_delegate.signup._authenticate", new=AsyncMock()),
            patch("tinker_delegate.signup._handle_onboarding", new=AsyncMock()),
            patch("tinker_delegate.signup._create_api_key", new=AsyncMock(return_value=api_key)),
            patch("tinker_delegate.signup.build_api_key_store", return_value=FakeStore(fail_save=True)),
        ):
            result = await signup(Settings())

        self.assertFalse(result["success"])
        self.assertFalse(result["stored"])
        self.assertTrue(result["api_key_created"])
        self.assertNotIn("api_key", result)
        self.assertIn("store_error", result)


if __name__ == "__main__":
    unittest.main()
