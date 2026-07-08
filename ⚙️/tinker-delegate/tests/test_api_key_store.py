import tempfile
import unittest
from pathlib import Path

from tinker_delegate.api_key_store import ApiKeyStore


class ApiKeyStoreTest(unittest.TestCase):
    def test_round_trips_encrypted_api_key(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "tinker_api_key.enc"
            key = "22" * 32
            api_key = "tml-secret-key-material"

            store = ApiKeyStore(str(path), key_hex=key)
            store.save(api_key)

            self.assertTrue(path.exists())
            self.assertNotIn(api_key.encode(), path.read_bytes())

            reloaded = ApiKeyStore(str(path), key_hex=key)
            self.assertEqual(reloaded.load(), api_key)


if __name__ == "__main__":
    unittest.main()
