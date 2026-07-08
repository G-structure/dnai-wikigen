"""Automate Tinker billing: add payment method, add balance, configure auto-reload.

The payment form uses Stripe Elements (cross-origin iframe for PCI compliance).
Card number/exp/CVC live inside `__privateStripeFrame*` iframe.
Name, address fields are in the parent page.

Trust model:
  - Developer encrypts card details to TEE's TDX public key
  - TEE decrypts inside enclave, fills Stripe form, submits
  - Card details zeroed from memory after submission
  - Stripe tokenizes and stores the card (PCI-compliant)
  - TEE never persists card details — they're ephemeral
"""
import asyncio
import math
import re

from playwright.async_api import async_playwright, Page, Frame

from tinker_delegate.automation_receipts import (
    AutomationOutcome,
    AutomationStage,
    AutomationSurface,
    classify_automation_error,
    make_receipt,
)
from tinker_delegate.browser_ready import connect_chromium, get_browser_context
from tinker_delegate.config import Settings
from tinker_delegate.debug_artifacts import purge_secret_debug_artifacts

BILLING_BALANCE_URL = "https://tinker-console.thinkingmachines.ai/billing/balance"

ADD_TO_BALANCE_SELECTORS = (
    'button:has-text("Add to balance")',
    'button:has-text("Add balance")',
    'button:has-text("Add funds")',
    'button[aria-label="Add to balance"]',
    'button[aria-label="Add balance"]',
    '[data-testid="add-to-balance"]',
    '[data-testid="add-balance"]',
)

PAYMENT_METHODS_SELECTORS = (
    'button:has-text("Payment methods")',
    'a:has-text("Payment methods")',
    'button[aria-label="Payment methods"]',
    '[data-testid="payment-methods"]',
)

ADD_PAYMENT_METHOD_SELECTORS = (
    'button:has-text("Add payment method")',
    'button:has-text("Add card")',
    'button:has-text("Save payment method")',
    'button:has-text("Save card")',
    'button[aria-label="Add payment method"]',
    'button[aria-label="Add card"]',
    '[data-testid="add-payment-method"]',
    '[data-testid="save-payment-method"]',
)

CARDHOLDER_NAME_SELECTORS = (
    "#cardholder-name",
    'input[name="cardholderName"]',
    'input[autocomplete="cc-name"]',
    'input[placeholder*="Name"]',
)

ADDRESS_FIELD_SELECTORS = (
    ("address_line1", ("#service-line1", 'input[name="line1"]', 'input[autocomplete="billing address-line1"]')),
    ("address_city", ("#service-city", 'input[name="city"]', 'input[autocomplete="billing address-level2"]')),
    ("address_state", ("#service-state", 'input[name="state"]', 'input[autocomplete="billing address-level1"]')),
    (
        "address_postal",
        ("#service-postal-code", 'input[name="postalCode"]', 'input[autocomplete="billing postal-code"]'),
    ),
    ("address_country", ("#service-country", 'select[name="country"]', 'input[name="country"]')),
)

ADD_BALANCE_DIALOG_SELECTORS = (
    '[role="dialog"], dialog',
    '[role="dialog"]',
    "dialog",
    '[data-testid="add-balance-dialog"]',
)

ADD_BALANCE_AMOUNT_SELECTORS = (
    'input[type="number"], input[placeholder*="amount"], input[name*="amount"]',
    'input[name="amount"]',
    'input[placeholder*="Amount"]',
    '[data-testid="add-balance-amount"]',
)

ADD_BALANCE_CONFIRM_SELECTORS = (
    'button:has-text("Confirm"), button:has-text("Add balance"), button:has-text("Pay")',
    'button:has-text("Confirm")',
    'button:has-text("Add balance")',
    'button:has-text("Pay")',
    'button[aria-label="Confirm"]',
    '[data-testid="confirm-add-balance"]',
)

AUTO_RELOAD_TOGGLE_SELECTORS = (
    'text=Enable auto-reload',
)

AUTO_RELOAD_THRESHOLD_SELECTORS = (
    'input[name*="threshold"], input[placeholder*="threshold"]',
)

AUTO_RELOAD_AMOUNT_SELECTORS = (
    'input[name*="amount"], input[placeholder*="amount"]',
)

AUTO_RELOAD_SAVE_SELECTORS = (
    'button:has-text("Save")',
)

STRIPE_CARD_NUMBER_SELECTORS = (
    'input[name="cardnumber"]',
    'input[data-elements-stable-field-name="cardNumber"]',
)

STRIPE_CARD_EXPIRY_SELECTORS = (
    'input[name="exp-date"]',
    'input[data-elements-stable-field-name="cardExpiry"]',
)

STRIPE_CARD_CVC_SELECTORS = (
    'input[name="cvc"]',
    'input[data-elements-stable-field-name="cardCvc"]',
)

STRIPE_FRAME_MATCHERS = (
    'frame.url contains "elements-inner-card"',
    'frame.name contains "StripeFrame"',
)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

class CardDetails:
    """Payment card details — ephemeral, zeroed after use."""

    def __init__(
        self,
        number: str,
        exp_month: str,
        exp_year: str,
        cvc: str,
        name: str,
        address_line1: str = "",
        address_city: str = "",
        address_state: str = "",
        address_postal: str = "",
        address_country: str = "US",
    ):
        self.number = number
        self.exp_month = exp_month
        self.exp_year = exp_year
        self.cvc = cvc
        self.name = name
        self.address_line1 = address_line1
        self.address_city = address_city
        self.address_state = address_state
        self.address_postal = address_postal
        self.address_country = address_country

    def zero(self):
        """Overwrite all fields with empty strings."""
        for attr in vars(self):
            setattr(self, attr, "")


# ---------------------------------------------------------------------------
# Stripe iframe interaction
# ---------------------------------------------------------------------------

async def _find_stripe_card_frame(page: Page) -> Frame | None:
    """Find the Stripe card element iframe."""
    for frame in page.frames:
        if "elements-inner-card" in (frame.url or ""):
            return frame
    # Fallback: look for __privateStripeFrame
    for frame in page.frames:
        if frame.name and "StripeFrame" in frame.name:
            return frame
    return None


async def _fill_stripe_card(frame: Frame, card: CardDetails) -> None:
    """Type card details into the Stripe Element iframe.

    Stripe Elements uses a single combined input or separate fields.
    The combined card input accepts: number, then exp MM/YY, then CVC.
    """
    # The Stripe card element is a single input that handles all fields
    # Type card number, then tab to exp, then tab to CVC
    card_input = frame.locator(", ".join(STRIPE_CARD_NUMBER_SELECTORS))
    if await card_input.count() > 0:
        await card_input.click()
        await card_input.type(card.number, delay=30)
        await asyncio.sleep(0.5)

    # Exp date
    exp_input = frame.locator(", ".join(STRIPE_CARD_EXPIRY_SELECTORS))
    if await exp_input.count() > 0:
        await exp_input.click()
        await exp_input.type(_format_expiry(card), delay=30)
        await asyncio.sleep(0.3)

    # CVC
    cvc_input = frame.locator(", ".join(STRIPE_CARD_CVC_SELECTORS))
    if await cvc_input.count() > 0:
        await cvc_input.click()
        await cvc_input.type(card.cvc, delay=30)
        await asyncio.sleep(0.3)


def _format_expiry(card: CardDetails) -> str:
    """Return the MMYY string expected by Stripe Elements."""
    month = card.exp_month.strip().zfill(2)
    year = card.exp_year.strip()
    if len(year) == 4:
        year = year[-2:]
    return f"{month}{year}"


def _billing_error_message(text: str) -> str | None:
    """Extract the most useful visible billing failure without returning the page."""
    normalized = re.sub(r"\s+", " ", text).strip()
    patterns = [
        r"(Your card[^.]*\.)",
        r"(The card[^.]*\.)",
        r"(This card[^.]*\.)",
        r"(Payment method[^.]*\.)",
        r"(Unable to[^.]*\.)",
        r"(Failed to[^.]*\.)",
        r"(declined[^.]*\.)",
        r"(invalid[^.]*\.)",
        r"(expired[^.]*\.)",
        r"(test card[^.]*\.)",
        r"(live mode[^.]*\.)",
    ]
    for pattern in patterns:
        match = re.search(pattern, normalized, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


async def _debug_screenshot(page: Page, settings: Settings, path: str, *, contains_secrets: bool = False) -> bool:
    """Write a debug screenshot only when it cannot contain card material."""
    if not settings.debug_screenshots or contains_secrets:
        return False
    await page.screenshot(path=path)
    return True


async def _click_first_available(scope, selectors: tuple[str, ...], *, prefer_last: bool = False) -> str | None:
    """Click the first matching selector in a bounded fallback family."""
    for selector in selectors:
        locator = scope.locator(selector)
        count = await locator.count()
        if count <= 0:
            continue
        target = locator.nth(count - 1) if prefer_last else locator.first
        await target.click()
        return selector
    return None


async def _fill_first_available(scope, selectors: tuple[str, ...], value: str) -> str | None:
    """Fill the first matching selector in a bounded fallback family."""
    for selector in selectors:
        locator = scope.locator(selector)
        if await locator.count() <= 0:
            continue
        await locator.first.fill(value)
        return selector
    return None


async def _first_available_scope(scope, selectors: tuple[str, ...]):
    """Return the first matching locator scope, or the original scope."""
    for selector in selectors:
        locator = scope.locator(selector)
        if await locator.count() > 0:
            return locator.last
    return scope


async def _billing_auth_blocker(page: Page) -> str | None:
    """Return a bounded auth-state reason when billing controls are unavailable."""
    text = await page.evaluate("() => document.body?.innerText || ''")
    lowered = text.lower()
    url = (getattr(page, "url", "") or "").lower()

    if "access blocked" in lowered:
        return "Tinker auth access blocked before billing"
    if "magic-code" in url or "check your email" in lowered:
        return "Tinker auth required before billing"
    if "sign in" in lowered or "log in" in lowered or "login" in lowered:
        return "Tinker auth required before billing"
    if await page.locator('input[type="email"], input[name="email"], input[autocomplete="email"]').count() > 0:
        return "Tinker auth required before billing"
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def add_payment_method(card: CardDetails, settings: Settings | None = None) -> dict:
    """Add a payment method to the Tinker account.

    Fills the Stripe card form + address fields, submits.
    Card details are zeroed from memory after submission.

    Returns dict with success status.
    """
    if settings is None:
        settings = Settings()

    try:
        return await _do_add_payment_method(card, settings)
    finally:
        card.zero()
        if settings.purge_secret_debug_artifacts:
            purge_secret_debug_artifacts(settings.debug_artifact_dir)


async def _do_add_payment_method(card: CardDetails, settings: Settings) -> dict:
    """Internal: fill and submit the payment method form."""
    furthest_stage = AutomationStage.NOT_STARTED
    async with async_playwright() as p:
        browser = await connect_chromium(p, settings)
        context = await get_browser_context(browser, settings)
        page = context.pages[0] if context.pages else await context.new_page()

        # Navigate to billing page
        print("[billing] navigating to billing page...")
        await page.goto(BILLING_BALANCE_URL, wait_until="domcontentloaded", timeout=15000)
        await asyncio.sleep(3)
        furthest_stage = AutomationStage.BILLING_PAGE_LOADED
        auth_blocker = await _billing_auth_blocker(page)
        if auth_blocker:
            return _payment_method_result(False, auth_blocker, furthest_stage, auth_blocker)

        # Click "Add to balance" to trigger the payment modal
        # (which includes "Add payment method" if no card exists)
        if await _click_first_available(page, ADD_TO_BALANCE_SELECTORS):
            await asyncio.sleep(3)
            furthest_stage = AutomationStage.PAYMENT_MODAL_OPENED
            auth_blocker = await _billing_auth_blocker(page)
            if auth_blocker:
                return _payment_method_result(False, auth_blocker, furthest_stage, auth_blocker)

        # Check if we got the add payment method form
        text = await page.evaluate("() => document.body?.innerText || ''")
        if "Add payment method" not in text:
            # Try payment methods tab directly
            if await _click_first_available(page, PAYMENT_METHODS_SELECTORS):
                await asyncio.sleep(2)
            if await _click_first_available(page, ADD_PAYMENT_METHOD_SELECTORS, prefer_last=True):
                await asyncio.sleep(3)
                furthest_stage = AutomationStage.PAYMENT_MODAL_OPENED

        # Wait for Stripe iframe to load
        print("[billing] waiting for Stripe card element...")
        stripe_frame = None
        for _ in range(10):
            stripe_frame = await _find_stripe_card_frame(page)
            if stripe_frame:
                break
            await asyncio.sleep(1)

        if not stripe_frame:
            await _debug_screenshot(page, settings, "screenshot_no_stripe.png")
            error = "Stripe card iframe not found"
            return _payment_method_result(False, error, furthest_stage, text)
        furthest_stage = AutomationStage.STRIPE_IFRAME_FOUND

        # Fill Stripe card fields
        print("[billing] filling card details in Stripe iframe...")
        await _fill_stripe_card(stripe_frame, card)

        # Fill parent page fields
        print("[billing] filling name and address...")
        if await _fill_first_available(page, CARDHOLDER_NAME_SELECTORS, card.name):
            await asyncio.sleep(0.2)

        # Address fields
        for attr, selectors in ADDRESS_FIELD_SELECTORS:
            value = getattr(card, attr)
            if value:
                if await _fill_first_available(page, selectors, value):
                    await asyncio.sleep(0.1)
        furthest_stage = AutomationStage.PAYMENT_FORM_FILLED

        await asyncio.sleep(1)
        await _debug_screenshot(
            page,
            settings,
            "screenshot_billing_filled.png",
            contains_secrets=True,
        )

        # Submit
        print("[billing] submitting payment method...")
        if await _click_first_available(page, ADD_PAYMENT_METHOD_SELECTORS, prefer_last=True):
            furthest_stage = AutomationStage.PAYMENT_SUBMITTED
        else:
            error = "Add payment method submit selector not found"
            return _payment_method_result(False, error, furthest_stage, text)

        await asyncio.sleep(5)

        # Check result
        text = await page.evaluate("() => document.body?.innerText || ''")
        await _debug_screenshot(
            page,
            settings,
            "screenshot_billing_result.png",
            contains_secrets=True,
        )

        error_msg = _billing_error_message(text)
        if error_msg:
            return _payment_method_result(False, error_msg, furthest_stage, text)

        # Check if payment method now shows up
        success = "ending in" in text.lower() or "visa" in text.lower() or "mastercard" in text.lower()
        print(f"[billing] payment method added: {success}")

        if not success:
            return _payment_method_result(False, "Payment method was not added", furthest_stage, text)
        return _payment_method_result(True, None, furthest_stage, text)


async def add_balance(amount_dollars: float, settings: Settings | None = None) -> dict:
    """Add credit balance to the Tinker account.

    Requires a payment method to already be on file.
    """
    if settings is None:
        settings = Settings()

    furthest_stage = AutomationStage.NOT_STARTED
    if not math.isfinite(amount_dollars) or amount_dollars <= 0:
        error = "Funding amount must be finite and positive"
        return _add_balance_result(False, error, amount_dollars, furthest_stage, error)
    if amount_dollars > settings.max_add_balance_usd:
        error = "Funding amount exceeds approved cap"
        return _add_balance_result(False, error, amount_dollars, furthest_stage, error)

    async with async_playwright() as p:
        browser = await connect_chromium(p, settings)
        context = await get_browser_context(browser, settings)
        page = context.pages[0] if context.pages else await context.new_page()

        await page.goto(BILLING_BALANCE_URL, wait_until="domcontentloaded", timeout=15000)
        await asyncio.sleep(3)
        furthest_stage = AutomationStage.BILLING_PAGE_LOADED
        auth_blocker = await _billing_auth_blocker(page)
        if auth_blocker:
            return _add_balance_result(False, auth_blocker, amount_dollars, furthest_stage, auth_blocker)

        # Click "Add to balance"
        if not await _click_first_available(page, ADD_TO_BALANCE_SELECTORS):
            error = "Add-balance open selector not found"
            return _add_balance_result(False, error, amount_dollars, furthest_stage, error)
        await asyncio.sleep(3)
        furthest_stage = AutomationStage.ADD_BALANCE_MODAL_OPENED
        auth_blocker = await _billing_auth_blocker(page)
        if auth_blocker:
            return _add_balance_result(False, auth_blocker, amount_dollars, furthest_stage, auth_blocker)

        text = await page.evaluate("() => document.body?.innerText || ''")
        if "Add payment method" in text and "Name on card" in text:
            error = "Payment method required before adding balance"
            return _add_balance_result(False, error, amount_dollars, furthest_stage, text)

        # Look for amount input
        scope = await _first_available_scope(page, ADD_BALANCE_DIALOG_SELECTORS)
        if await _fill_first_available(scope, ADD_BALANCE_AMOUNT_SELECTORS, str(amount_dollars)):
            await asyncio.sleep(0.5)
            furthest_stage = AutomationStage.ADD_BALANCE_AMOUNT_FILLED
        else:
            error = "Add-balance amount input not found"
            return _add_balance_result(False, error, amount_dollars, furthest_stage, text)

        # Submit
        if await _click_first_available(scope, ADD_BALANCE_CONFIRM_SELECTORS):
            await asyncio.sleep(5)
            furthest_stage = AutomationStage.ADD_BALANCE_SUBMITTED
        else:
            error = "Add-balance submit button not found"
            return _add_balance_result(False, error, amount_dollars, furthest_stage, text)

        text = await page.evaluate("() => document.body?.innerText || ''")
        await _debug_screenshot(page, settings, "screenshot_add_balance.png")

        error_msg = _billing_error_message(text)
        if error_msg:
            return _add_balance_result(False, error_msg, amount_dollars, furthest_stage, text)
        return _add_balance_result(True, None, amount_dollars, furthest_stage, text)


async def configure_auto_reload(
    enabled: bool = True,
    threshold: float = 10.0,
    amount: float = 50.0,
    settings: Settings | None = None,
) -> dict:
    """Configure auto-reload: automatically add credit when balance drops."""
    if settings is None:
        settings = Settings()

    async with async_playwright() as p:
        browser = await connect_chromium(p, settings)
        context = await get_browser_context(browser, settings)
        page = context.pages[0] if context.pages else await context.new_page()

        await page.goto(
            "https://tinker-console.thinkingmachines.ai/billing/balance",
            wait_until="domcontentloaded", timeout=15000,
        )
        await asyncio.sleep(3)
        await page.reload(wait_until="domcontentloaded", timeout=15000)
        await asyncio.sleep(3)

        # Find auto-reload checkbox
        text = await page.evaluate("() => document.body?.innerText || ''")
        if "auto-reload" not in text.lower():
            return {"success": False, "error": "Auto-reload section not found"}

        # Toggle checkbox
        checkbox = page.locator(AUTO_RELOAD_TOGGLE_SELECTORS[0])
        if await checkbox.count() > 0:
            await checkbox.click()
            await asyncio.sleep(1)

        # Fill threshold and amount if inputs appear
        # (depends on UI — inputs may only show when enabled)
        threshold_input = page.locator(", ".join(AUTO_RELOAD_THRESHOLD_SELECTORS))
        if await threshold_input.count() > 0:
            await threshold_input.fill(str(threshold))

        amount_input = page.locator(", ".join(AUTO_RELOAD_AMOUNT_SELECTORS))
        if await amount_input.count() > 0:
            await amount_input.fill(str(amount))

        # Save
        save_btn = page.locator(AUTO_RELOAD_SAVE_SELECTORS[0])
        if await save_btn.count() > 0:
            await save_btn.click()
            await asyncio.sleep(3)

        await _debug_screenshot(page, settings, "screenshot_auto_reload.png")
        return {"success": True}


async def get_balance(settings: Settings | None = None) -> dict:
    """Get current balance and usage info."""
    if settings is None:
        settings = Settings()

    async with async_playwright() as p:
        browser = await connect_chromium(p, settings)
        context = await get_browser_context(browser, settings)
        page = context.pages[0] if context.pages else await context.new_page()

        await page.goto(
            "https://tinker-console.thinkingmachines.ai/billing/balance",
            wait_until="domcontentloaded", timeout=15000,
        )
        await asyncio.sleep(3)
        await page.reload(wait_until="domcontentloaded", timeout=15000)
        await asyncio.sleep(3)

        balance = await page.evaluate("""() => {
            const text = document.body?.innerText || '';
            const match = text.match(/\\$([\\d,.]+)/);
            return match ? match[1] : null;
        }""")

        return {"balance": f"${balance}" if balance else "unknown"}


def _payment_method_result(
    success: bool,
    error: str | None,
    furthest_stage: AutomationStage,
    evidence: object,
) -> dict:
    outcome = AutomationOutcome.SUCCESS if success else classify_automation_error(error)
    receipt = make_receipt(
        surface=AutomationSurface.PAYMENT_METHOD,
        outcome=outcome,
        furthest_stage=furthest_stage,
        evidence=evidence if success else error,
        bounded_message="payment_method_added" if success else (error or "payment_method_failed"),
        card_payload_destroyed=True,
    )
    return {"success": success, "error": error, "attempt_record": receipt.to_public_dict()}


def _add_balance_result(
    success: bool,
    error: str | None,
    amount_dollars: float,
    furthest_stage: AutomationStage,
    evidence: object,
) -> dict:
    outcome = AutomationOutcome.SUCCESS if success else classify_automation_error(error)
    receipt = make_receipt(
        surface=AutomationSurface.ADD_BALANCE,
        outcome=outcome,
        furthest_stage=furthest_stage,
        evidence=evidence if success else error,
        bounded_message="balance_added" if success else (error or "add_balance_failed"),
        amount_dollars=amount_dollars,
    )
    return {"success": success, "error": error, "attempt_record": receipt.to_public_dict()}
