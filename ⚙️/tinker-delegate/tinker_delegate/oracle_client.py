"""Client for the TEE email oracle API."""
import hashlib

import httpx

from tinker_delegate.config import Settings
from tinker_delegate.dstack_utils import derive_storage_key, is_dstack_enabled


class OracleClient:
    """Thin wrapper around the email oracle HTTP API."""

    def __init__(self, settings: Settings):
        self.base_url = settings.oracle_url.rstrip("/")
        self.auth_token = settings.oracle_auth_token or self._derive_auth_token(settings)
        self._client = httpx.Client(timeout=30.0)

    def _derive_auth_token(self, settings: Settings) -> str:
        if not is_dstack_enabled():
            return ""
        key = derive_storage_key(settings.oracle_auth_key_path)
        return hashlib.sha256(b"email-oracle-runtime-auth:" + key).hexdigest()

    def _headers(self) -> dict[str, str]:
        if not self.auth_token:
            return {}
        return {"Authorization": f"Bearer {self.auth_token}"}

    def health(self) -> dict:
        resp = self._client.get(f"{self.base_url}/health")
        resp.raise_for_status()
        return resp.json()

    def get_email(self) -> str:
        """Get the oracle's email address."""
        data = self.health()
        return data["oracle_email"]

    def get_pin(
        self,
        from_filter: str = "",
        subject_contains: str = "",
        max_age_seconds: int = 300,
        extract_pattern: str = r"\b\d{6}\b",
        delete_after: bool = False,
    ) -> dict | None:
        """Poll for a PIN/OTP from the inbox.

        Returns dict with 'pin' key on success, None if no matching email found.
        """
        resp = self._client.post(
            f"{self.base_url}/pin",
            headers=self._headers(),
            json={
                "from_filter": from_filter,
                "subject_contains": subject_contains,
                "max_age_seconds": max_age_seconds,
                "extract_pattern": extract_pattern,
                "delete_after": delete_after,
            },
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    def list_inbox(self, count: int = 5) -> list:
        """List recent emails (debug)."""
        resp = self._client.get(
            f"{self.base_url}/inbox",
            headers=self._headers(),
            params={"limit": count},
        )
        resp.raise_for_status()
        return resp.json()
