"""Small redaction helpers for logs and bounded API errors."""

from __future__ import annotations

import re


_REDACTIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(Authorization\s*:\s*Bearer\s+)[A-Za-z0-9._~+/=-]+", re.IGNORECASE), r"\1<redacted>"),
    (re.compile(r"(Bearer\s+)[A-Za-z0-9._~+/=-]+", re.IGNORECASE), r"\1<redacted>"),
    (re.compile(r"tml-[A-Za-z0-9_-]{20,}"), "tml-<redacted>"),
    (re.compile(r"(TINKER_API_KEY\s*=\s*)\S+", re.IGNORECASE), r"\1<redacted>"),
    (re.compile(r'("(?:card_number|number)"\s*:\s*")[^"]+(")', re.IGNORECASE), r"\1<redacted>\2"),
    (re.compile(r"((?:card_number|number)\s*=\s*)\S+", re.IGNORECASE), r"\1<redacted>"),
    (re.compile(r'("(?:cvc|cvv)"\s*:\s*")[^"]+(")', re.IGNORECASE), r"\1<redacted>\2"),
    (re.compile(r"((?:cvc|cvv)\s*=\s*)\S+", re.IGNORECASE), r"\1<redacted>"),
    (re.compile(r'("artifact_hex"\s*:\s*")[0-9a-fA-F]{32,}(")', re.IGNORECASE), r"\1<redacted>\2"),
    (re.compile(r"\b(?:\d[ -]?){13,19}\b"), "<redacted-card-number>"),
)


def redact_text(value: object) -> str:
    """Return text with credential, card, and artifact-like material removed."""
    text = str(value)
    for pattern, replacement in _REDACTIONS:
        text = pattern.sub(replacement, text)
    return text
