"""Bounded CDP automation for full Tinker API-key lifecycle management.

The Tinker console at ``/keys`` is the only surface that lists, names, and
deletes the *upstream* (`tml-...`) account keys. `signup.py` already covers the
create-one-key bootstrap; this module adds the rest of the lifecycle the
delegate needs to custody the account:

  * ``list_api_keys``        — read the key table (name, id/prefix, timestamps)
  * ``create_named_api_key`` — create a key with an explicit name
  * ``delete_api_key``       — revoke a key found by name or id prefix

Everything here is bounded: the full ``tml-...`` secret only exists transiently
at creation (returned once by the console) and is never logged; listings expose
names, id prefixes, and coarse timestamps only. The parsing of the key table is
factored into a pure function (``parse_keys_table``) so it is unit-testable
without a live browser.
"""
from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass, field
from typing import Any, Sequence

from playwright.async_api import Page, async_playwright

from tinker_delegate.automation_receipts import (
    AutomationOutcome,
    AutomationStage,
    AutomationSurface,
    classify_automation_error,
    make_receipt,
)
from tinker_delegate.browser_ready import connect_chromium, get_browser_context
from tinker_delegate.config import Settings
from tinker_delegate.redaction import redact_text

KEYS_URL = "https://tinker-console.thinkingmachines.ai/keys"

# Row containers on the /keys page. Kept as an explicit, bounded family because
# Tinker has changed this markup before (see API_KEY_CREATE_SELECTORS history).
API_KEY_ROW_SELECTORS = (
    '[data-testid="api-key-row"]',
    'tr[data-key-id]',
    'table tbody tr',
    '[role="row"]',
    'li[data-key-id]',
)

# Name field shown in the create-key dialog (when the console offers naming).
API_KEY_NAME_INPUT_SELECTORS = (
    'input[name="name"]',
    'input[name="keyName"]',
    'input[placeholder*="name" i]',
    'input[aria-label*="name" i]',
    '[data-testid="key-name-input"]',
)

# Per-row delete/revoke control.
API_KEY_DELETE_SELECTORS = (
    'button[aria-label="Delete"]',
    'button[aria-label="Revoke"]',
    'button:has-text("Delete")',
    'button:has-text("Revoke")',
    '[data-testid="delete-key"]',
    '[data-testid="revoke-key"]',
)

# Confirmation control in the delete dialog.
API_KEY_DELETE_CONFIRM_SELECTORS = (
    'button:has-text("Delete key")',
    'button:has-text("Revoke key")',
    'button:has-text("Confirm")',
    'button:has-text("Delete")',
    'button[aria-label="Confirm delete"]',
    '[data-testid="confirm-delete-key"]',
)

_TML_PREFIX = "tml-"


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


@dataclass(frozen=True)
class ApiKeyRecord:
    """Bounded metadata for one listed API key. Never carries the full secret."""

    name: str
    key_id: str = ""
    key_prefix: str = ""
    created: str = ""
    last_used: str = ""

    def to_public_dict(self) -> dict[str, Any]:
        # Names can be operator-chosen and low-sensitivity, but we still expose a
        # hash alongside so audit records never depend on raw name egress.
        return {
            "name": self.name,
            "name_hash": _hash_text(self.name) if self.name else "",
            "key_id": self.key_id,
            "key_prefix": self.key_prefix,
            "created": self.created,
            "last_used": self.last_used,
        }


@dataclass(frozen=True)
class KeyListResult:
    keys: tuple[ApiKeyRecord, ...] = ()
    outcome: AutomationOutcome = AutomationOutcome.SUCCESS
    furthest_stage: AutomationStage = AutomationStage.API_KEY_LIST_READ
    error_kind: str = ""

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "surface": AutomationSurface.API_KEY_MANAGEMENT.value,
            "operation": "list",
            "success": self.outcome == AutomationOutcome.SUCCESS,
            "outcome": self.outcome.value,
            "furthest_stage": self.furthest_stage.value,
            "error_kind": self.error_kind,
            "count": len(self.keys),
            "keys": [k.to_public_dict() for k in self.keys],
            "raw_secret_egress": False,
        }


def _clean(value: str | None) -> str:
    return " ".join((value or "").split()).strip()


def _looks_like_prefix(token: str) -> bool:
    return token.startswith(_TML_PREFIX) and (
        "…" in token or "..." in token or "*" in token or len(token) <= 24
    )


def parse_keys_table(rows: Sequence[Sequence[str]]) -> tuple[ApiKeyRecord, ...]:
    """Turn raw per-row cell text into bounded ``ApiKeyRecord``s.

    ``rows`` is a sequence of rows, each a sequence of cell strings as scraped
    from the console table. This is deliberately tolerant of column reordering:
    a cell that looks like a masked ``tml-...`` prefix is treated as the key
    prefix; date-like cells fill created/last-used in order; the first remaining
    non-empty, non-prefix, non-date cell is the name.

    Pure and side-effect-free so it can be unit-tested without a browser.
    """
    records: list[ApiKeyRecord] = []
    for row in rows:
        cells = [_clean(c) for c in row]
        cells = [c for c in cells if c and c.lower() not in {"delete", "revoke", "copy"}]
        if not cells:
            continue

        key_prefix = ""
        name = ""
        dates: list[str] = []
        leftovers: list[str] = []
        for cell in cells:
            if not key_prefix and _looks_like_prefix(cell):
                key_prefix = cell
            elif _looks_like_date(cell):
                dates.append(cell)
            else:
                leftovers.append(cell)

        if leftovers:
            name = leftovers[0]
        created = dates[0] if dates else ""
        last_used = dates[1] if len(dates) > 1 else ""
        key_id = ""
        # A bare non-tml token that isn't the name can serve as an id handle.
        if len(leftovers) > 1:
            key_id = leftovers[1]

        if not (name or key_prefix or key_id):
            continue
        records.append(
            ApiKeyRecord(
                name=name,
                key_id=key_id,
                key_prefix=key_prefix,
                created=created,
                last_used=last_used,
            )
        )
    return tuple(records)


_MONTHS = (
    "jan", "feb", "mar", "apr", "may", "jun",
    "jul", "aug", "sep", "oct", "nov", "dec",
)


def _looks_like_date(token: str) -> bool:
    low = token.lower()
    if any(m in low for m in _MONTHS):
        return True
    if any(w in low for w in ("ago", "never", "today", "yesterday")):
        return True
    # ISO-ish or slashed dates.
    digits = sum(ch.isdigit() for ch in token)
    return digits >= 4 and ("-" in token or "/" in token or ":" in token)


def find_key_by_ref(keys: Sequence[ApiKeyRecord], ref: str) -> ApiKeyRecord | None:
    """Match a key by exact name, then id, then key-prefix (case-insensitive)."""
    ref_c = _clean(ref)
    if not ref_c:
        return None
    low = ref_c.lower()
    for k in keys:
        if k.name and k.name.lower() == low:
            return k
    for k in keys:
        if k.key_id and k.key_id.lower() == low:
            return k
    for k in keys:
        if k.key_prefix and (k.key_prefix.lower().startswith(low) or low.startswith(k.key_prefix.lower().rstrip(".…*"))):
            return k
    return None


async def _click_first_available(page: Page, selectors: tuple[str, ...]) -> str | None:
    for selector in selectors:
        locator = page.locator(selector)
        try:
            if await locator.count() > 0:
                await locator.first.click()
                return selector
        except Exception:
            continue
    return None


async def _load_keys_page(page: Page, settings: Settings) -> None:
    await page.goto(KEYS_URL, wait_until="domcontentloaded", timeout=15000)
    await asyncio.sleep(3)
    # Initial render often shows "Loading..."; a reload settles the table.
    await page.reload(wait_until="domcontentloaded", timeout=15000)
    await asyncio.sleep(3)


async def _scrape_key_rows(page: Page) -> list[list[str]]:
    """Return raw per-row cell text from the first matching row family."""
    for selector in API_KEY_ROW_SELECTORS:
        rows = page.locator(selector)
        try:
            count = await rows.count()
        except Exception:
            continue
        if count == 0:
            continue
        scraped: list[list[str]] = []
        for i in range(count):
            row = rows.nth(i)
            # Prefer structured cells; fall back to the row's inner text.
            cells = row.locator("td, th, [role='cell'], [data-cell]")
            try:
                cell_count = await cells.count()
            except Exception:
                cell_count = 0
            if cell_count > 0:
                texts = []
                for j in range(cell_count):
                    texts.append(await cells.nth(j).inner_text())
                scraped.append(texts)
            else:
                text = await row.inner_text()
                scraped.append([line for line in text.split("\n") if line.strip()])
        if scraped:
            return scraped
    return []


async def list_api_keys(page: Page, settings: Settings) -> KeyListResult:
    """Navigate the console keys page and return bounded key metadata."""
    try:
        await _load_keys_page(page, settings)
    except Exception as exc:
        return KeyListResult(
            outcome=classify_automation_error(redact_text(exc)),
            furthest_stage=AutomationStage.API_KEYS_PAGE_LOADED,
            error_kind=classify_automation_error(redact_text(exc)).value,
        )
    rows = await _scrape_key_rows(page)
    keys = parse_keys_table(rows)
    print(f"[apikey] listed {len(keys)} keys")
    return KeyListResult(keys=keys)


async def create_named_api_key(
    page: Page, settings: Settings, name: str
) -> tuple[str | None, AutomationStage]:
    """Create a key, entering ``name`` when the console exposes a name field.

    Returns the raw ``tml-...`` value (once) and the furthest stage reached. The
    caller is responsible for sealing the returned key and never logging it.
    """
    # Import here to reuse the maintained create/confirm/close selector families.
    from tinker_delegate.signup import (
        API_KEY_CLOSE_SELECTORS,
        API_KEY_CONFIRM_SELECTORS,
        API_KEY_CREATE_SELECTORS,
    )

    await _load_keys_page(page, settings)
    stage = AutomationStage.API_KEYS_PAGE_LOADED

    if not await _click_first_available(page, API_KEY_CREATE_SELECTORS):
        print("[apikey] no create-key selector found")
        return None, stage
    stage = AutomationStage.API_KEY_CREATE_CLICKED
    await asyncio.sleep(1)

    name_clean = _clean(name)
    if name_clean:
        name_selector = None
        for selector in API_KEY_NAME_INPUT_SELECTORS:
            field_loc = page.locator(selector)
            try:
                if await field_loc.count() > 0:
                    await field_loc.first.fill(name_clean)
                    name_selector = selector
                    break
            except Exception:
                continue
        if name_selector:
            stage = AutomationStage.API_KEY_NAME_ENTERED
            print("[apikey] entered key name")
            await asyncio.sleep(0.3)
        else:
            print("[apikey] no name field in dialog; creating unnamed")

    if await _click_first_available(page, API_KEY_CONFIRM_SELECTORS):
        stage = AutomationStage.API_KEY_GENERATE_CLICKED
        await asyncio.sleep(3)
    else:
        await asyncio.sleep(2)

    api_key = await page.evaluate(
        """() => {
        const candidates = document.querySelectorAll('code, pre, [data-key], input[readonly], .font-mono');
        for (const el of candidates) {
            const text = (el.textContent || el.value || '').trim();
            if (text.startsWith('tml-') && text.length > 30) return text;
        }
        const body = document.body?.innerText || '';
        const match = body.match(/tml-[A-Za-z0-9_-]{30,}/);
        return match ? match[0] : null;
    }"""
    )
    if api_key:
        stage = AutomationStage.API_KEY_CAPTURED
        print("[apikey] captured key")
    else:
        print("[apikey] failed to extract key")

    await _click_first_available(page, API_KEY_CLOSE_SELECTORS)
    await asyncio.sleep(1)
    return api_key, stage


async def delete_api_key(page: Page, settings: Settings, ref: str) -> dict[str, Any]:
    """Delete/revoke the key matching ``ref`` (name, id, or prefix)."""
    listing = await list_api_keys(page, settings)
    if listing.outcome != AutomationOutcome.SUCCESS:
        return _delete_receipt(
            ref, listing.outcome, AutomationStage.API_KEYS_PAGE_LOADED, error=listing.error_kind
        )
    target = find_key_by_ref(listing.keys, ref)
    if target is None:
        print("[apikey] delete target not found")
        return _delete_receipt(ref, AutomationOutcome.KEY_NOT_FOUND, AutomationStage.API_KEY_LIST_READ)

    # Re-scope to the matching row and click its delete control.
    row_selector = None
    row_locator = None
    for selector in API_KEY_ROW_SELECTORS:
        rows = page.locator(selector)
        try:
            count = await rows.count()
        except Exception:
            continue
        for i in range(count):
            row = rows.nth(i)
            try:
                text = _clean(await row.inner_text())
            except Exception:
                continue
            needle = target.name or target.key_prefix or target.key_id
            if needle and needle.lower() in text.lower():
                row_selector = selector
                row_locator = row
                break
        if row_locator is not None:
            break

    if row_locator is None:
        return _delete_receipt(ref, AutomationOutcome.SELECTOR_MISSING, AutomationStage.API_KEY_LIST_READ)

    clicked = None
    for selector in API_KEY_DELETE_SELECTORS:
        control = row_locator.locator(selector)
        try:
            if await control.count() > 0:
                await control.first.click()
                clicked = selector
                break
        except Exception:
            continue
    if not clicked:
        # Some layouts put the delete control outside the row (e.g. a menu).
        clicked = await _click_first_available(page, API_KEY_DELETE_SELECTORS)
    if not clicked:
        return _delete_receipt(ref, AutomationOutcome.SELECTOR_MISSING, AutomationStage.API_KEY_LIST_READ)
    await asyncio.sleep(1)
    stage = AutomationStage.API_KEY_DELETE_CLICKED

    if await _click_first_available(page, API_KEY_DELETE_CONFIRM_SELECTORS):
        stage = AutomationStage.API_KEY_DELETE_CONFIRMED
        await asyncio.sleep(2)

    # Verify by re-listing: the target should be gone.
    after = await list_api_keys(page, settings)
    still_present = find_key_by_ref(after.keys, ref) is not None
    if still_present:
        return _delete_receipt(ref, AutomationOutcome.UNKNOWN_FAILURE, stage)
    print("[apikey] deleted key")
    return _delete_receipt(ref, AutomationOutcome.SUCCESS, AutomationStage.API_KEY_DELETED)


# ---------------------------------------------------------------------------
# Orchestrators: open browser, authenticate (reusing signup), run one operation.
# ---------------------------------------------------------------------------

async def _with_authenticated_page(settings: Settings, operation):
    """Connect the browser and run ``operation`` on an authenticated console page.

    ``operation`` is an async callable ``(page) -> dict``. The browser session is
    long-lived and usually already signed in, so we go straight to ``/keys`` and
    only fall back to the OTP login (``signup._authenticate``) if we actually
    land on a sign-in page. Errors are surfaced as bounded, redacted receipts.
    """
    from tinker_delegate.oracle_client import OracleClient
    from tinker_delegate.signup import AuthAccessBlockedError, _authenticate, _page_state

    async with async_playwright() as p:
        browser = await connect_chromium(p, settings)
        context = await get_browser_context(browser, settings)
        page = context.pages[0] if context.pages else await context.new_page()

        # Try the existing session first: navigate to /keys and see where we land.
        needs_login = False
        try:
            await page.goto(KEYS_URL, wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(2)
            state = await _page_state(page)
            url = str(state.get("url", ""))
            if "access blocked" in str(state.get("text", "")).lower():
                return {
                    "success": False,
                    "outcome": AutomationOutcome.AUTH_ACCESS_BLOCKED.value,
                    "error_kind": AutomationOutcome.AUTH_ACCESS_BLOCKED.value,
                    "raw_secret_egress": False,
                }
            needs_login = bool(state.get("hasEmailInput")) or "auth." in url or "sign-in" in url or "magic-code" in url
        except Exception as exc:
            # Navigation/state read failed — treat as "needs login" so the full
            # flow (which has its own retries/fallbacks) gets a chance.
            print(f"[apikey] direct keys nav failed ({exc.__class__.__name__}); trying full auth")
            needs_login = True

        if needs_login:
            try:
                email = getattr(settings, "email", "") or OracleClient(settings).get_email()
                await _authenticate(page, email, OracleClient(settings), settings)
            except AuthAccessBlockedError as exc:
                return {
                    "success": False,
                    "outcome": AutomationOutcome.AUTH_ACCESS_BLOCKED.value,
                    "error_kind": AutomationOutcome.AUTH_ACCESS_BLOCKED.value,
                    "furthest_stage": exc.furthest_stage.value,
                    "raw_secret_egress": False,
                }
            except Exception as exc:
                return {
                    "success": False,
                    "operation": "authenticate",
                    "outcome": classify_automation_error(redact_text(str(exc))).value,
                    "error_kind": classify_automation_error(redact_text(str(exc))).value,
                    "error_type": exc.__class__.__name__,
                    "error_detail": redact_text(str(exc))[:300],
                    "raw_secret_egress": False,
                }

        return await operation(page)


async def run_list_keys(settings: Settings) -> dict[str, Any]:
    """List the account's API keys (bounded metadata only)."""

    async def _op(page):
        return (await list_api_keys(page, settings)).to_public_dict()

    return await _with_authenticated_page(settings, _op)


async def run_create_key(settings: Settings, name: str = "") -> dict[str, Any]:
    """Create a (optionally named) key, seal it, return a bounded receipt."""

    async def _op(page):
        api_key, stage = await create_named_api_key(page, settings, name)
        stored = False
        store_error = ""
        api_key_hash = _hash_text(api_key) if api_key else ""
        if api_key:
            try:
                from tinker_delegate.api_key_store import build_api_key_store

                build_api_key_store(settings).save(api_key)
                stored = True
                stage = AutomationStage.API_KEY_STORED
            except Exception as exc:
                store_error = redact_text(exc)
        outcome = (
            AutomationOutcome.SUCCESS
            if stored
            else AutomationOutcome.STORE_FAILED
            if api_key
            else AutomationOutcome.SELECTOR_MISSING
        )
        receipt = make_receipt(
            surface=AutomationSurface.API_KEY_MANAGEMENT,
            outcome=outcome,
            furthest_stage=stage,
            evidence={"api_key_hash": api_key_hash, "stored": stored, "store_error": store_error},
            bounded_message=f"api_key_create:{outcome.value}",
        )
        return {
            "surface": AutomationSurface.API_KEY_MANAGEMENT.value,
            "operation": "create",
            "success": stored,
            "outcome": outcome.value,
            "furthest_stage": stage.value,
            "name_hash": _hash_text(_clean(name)) if _clean(name) else "",
            "api_key_hash": api_key_hash,
            "api_key_returned": False,
            "stored": stored,
            "attempt_record": receipt.to_public_dict(),
            "raw_secret_egress": False,
        }

    return await _with_authenticated_page(settings, _op)


async def run_delete_key(settings: Settings, ref: str) -> dict[str, Any]:
    """Delete/revoke a key by name, id, or prefix."""

    async def _op(page):
        return await delete_api_key(page, settings, ref)

    return await _with_authenticated_page(settings, _op)


def _delete_receipt(
    ref: str, outcome: AutomationOutcome, stage: AutomationStage, *, error: str = ""
) -> dict[str, Any]:
    receipt = make_receipt(
        surface=AutomationSurface.API_KEY_MANAGEMENT,
        outcome=outcome,
        furthest_stage=stage,
        evidence={"ref_hash": _hash_text(ref) if ref else "", "error": error},
        bounded_message=f"api_key_delete:{outcome.value}",
    )
    return {
        "surface": AutomationSurface.API_KEY_MANAGEMENT.value,
        "operation": "delete",
        "success": outcome == AutomationOutcome.SUCCESS,
        "outcome": outcome.value,
        "furthest_stage": stage.value,
        "ref_hash": _hash_text(ref) if ref else "",
        "attempt_record": receipt.to_public_dict(),
        "raw_secret_egress": False,
    }
