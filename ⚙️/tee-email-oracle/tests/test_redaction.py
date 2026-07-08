import unittest

from email_oracle.redaction import redact_text


class OracleRedactionTest(unittest.TestCase):
    def test_redacts_bearer_pin_otp_and_password_material(self):
        text = (
            'Authorization: Bearer oracle-secret '
            '"pin":"123456" otp=654321 password=hunter2 '
            "ORACLE_RUNTIME_AUTH_TOKEN=secret-token"
        )

        redacted = redact_text(text)

        self.assertNotIn("oracle-secret", redacted)
        self.assertNotIn("123456", redacted)
        self.assertNotIn("otp=654321", redacted)
        self.assertNotIn("hunter2", redacted)
        self.assertNotIn("secret-token", redacted)


if __name__ == "__main__":
    unittest.main()
