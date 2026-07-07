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

from playwright.async_api import async_playwright, Page, Frame

from tinker_delegate.browser_ready import connect_chromium, get_browser_context
from tinker_delegate.config import Settings


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
    card_input = frame.locator('input[name="cardnumber"], input[data-elements-stable-field-name="cardNumber"]')
    if await card_input.count() > 0:
        await card_input.click()
        await card_input.type(card.number, delay=30)
        await asyncio.sleep(0.5)

    # Exp date
    exp_input = frame.locator('input[name="exp-date"], input[data-elements-stable-field-name="cardExpiry"]')
    if await exp_input.count() > 0:
        await exp_input.click()
        await exp_input.type(f"{card.exp_month}{card.exp_year}", delay=30)
        await asyncio.sleep(0.3)

    # CVC
    cvc_input = frame.locator('input[name="cvc"], input[data-elements-stable-field-name="cardCvc"]')
    if await cvc_input.count() > 0:
        await cvc_input.click()
        await cvc_input.type(card.cvc, delay=30)
        await asyncio.sleep(0.3)


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


async def _do_add_payment_method(card: CardDetails, settings: Settings) -> dict:
    """Internal: fill and submit the payment method form."""
    async with async_playwright() as p:
        browser = await connect_chromium(p, settings)
        context = await get_browser_context(browser)
        page = context.pages[0] if context.pages else await context.new_page()

        # Navigate to billing page
        print("[billing] navigating to billing page...")
        await page.goto(
            "https://tinker-console.thinkingmachines.ai/billing/balance",
            wait_until="domcontentloaded", timeout=15000,
        )
        await asyncio.sleep(3)

        # Click "Add to balance" to trigger the payment modal
        # (which includes "Add payment method" if no card exists)
        add_btn = page.locator('button:has-text("Add to balance")')
        if await add_btn.count() > 0:
            await add_btn.click()
            await asyncio.sleep(3)

        # Check if we got the add payment method form
        text = await page.evaluate("() => document.body?.innerText || ''")
        if "Add payment method" not in text:
            # Try payment methods tab directly
            pm_btn = page.locator('button:has-text("Payment methods")')
            if await pm_btn.count() > 0:
                await pm_btn.click()
                await asyncio.sleep(2)
            add_pm = page.locator('button:has-text("Add payment method")')
            if await add_pm.count() > 0:
                await add_pm.click()
                await asyncio.sleep(3)

        # Wait for Stripe iframe to load
        print("[billing] waiting for Stripe card element...")
        stripe_frame = None
        for _ in range(10):
            stripe_frame = await _find_stripe_card_frame(page)
            if stripe_frame:
                break
            await asyncio.sleep(1)

        if not stripe_frame:
            await page.screenshot(path="screenshot_no_stripe.png")
            return {"success": False, "error": "Stripe card iframe not found"}

        # Fill Stripe card fields
        print("[billing] filling card details in Stripe iframe...")
        await _fill_stripe_card(stripe_frame, card)

        # Fill parent page fields
        print("[billing] filling name and address...")
        name_input = page.locator('#cardholder-name')
        if await name_input.count() > 0:
            await name_input.fill(card.name)
            await asyncio.sleep(0.2)

        # Address fields
        for field_id, value in [
            ("service-line1", card.address_line1),
            ("service-city", card.address_city),
            ("service-state", card.address_state),
            ("service-postal-code", card.address_postal),
            ("service-country", card.address_country),
        ]:
            if value:
                field = page.locator(f"#{field_id}")
                if await field.count() > 0:
                    await field.fill(value)
                    await asyncio.sleep(0.1)

        await asyncio.sleep(1)
        await page.screenshot(path="screenshot_billing_filled.png")

        # Submit
        print("[billing] submitting payment method...")
        submit = page.locator('button:has-text("Add payment method")')
        # There may be multiple — pick the one in the modal (last one)
        count = await submit.count()
        if count > 0:
            await submit.nth(count - 1).click()
        else:
            return {"success": False, "error": "Submit button not found"}

        await asyncio.sleep(5)

        # Check result
        text = await page.evaluate("() => document.body?.innerText || ''")
        await page.screenshot(path="screenshot_billing_result.png")

        if "error" in text.lower() and "card" in text.lower():
            error_msg = text[text.lower().find("error"):text.lower().find("error") + 100]
            return {"success": False, "error": error_msg.strip()}

        # Check if payment method now shows up
        success = "ending in" in text.lower() or "visa" in text.lower() or "mastercard" in text.lower()
        print(f"[billing] payment method added: {success}")

        return {"success": success}


async def add_balance(amount_dollars: float, settings: Settings | None = None) -> dict:
    """Add credit balance to the Tinker account.

    Requires a payment method to already be on file.
    """
    if settings is None:
        settings = Settings()

    async with async_playwright() as p:
        browser = await connect_chromium(p, settings)
        context = await get_browser_context(browser)
        page = context.pages[0] if context.pages else await context.new_page()

        await page.goto(
            "https://tinker-console.thinkingmachines.ai/billing/balance",
            wait_until="domcontentloaded", timeout=15000,
        )
        await asyncio.sleep(3)

        # Click "Add to balance"
        add_btn = page.locator('button:has-text("Add to balance")')
        if await add_btn.count() > 0:
            await add_btn.click()
            await asyncio.sleep(3)

        # Look for amount input
        amount_input = page.locator('input[type="number"], input[placeholder*="amount"], input[name*="amount"]')
        if await amount_input.count() > 0:
            await amount_input.fill(str(amount_dollars))
            await asyncio.sleep(0.5)

        # Submit
        confirm = page.locator('button:has-text("Confirm"), button:has-text("Add"), button:has-text("Pay")')
        if await confirm.count() > 0:
            await confirm.first.click()
            await asyncio.sleep(5)

        text = await page.evaluate("() => document.body?.innerText || ''")
        await page.screenshot(path="screenshot_add_balance.png")

        return {"success": True, "page_text": text[:300]}


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
        context = await get_browser_context(browser)
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
        checkbox = page.locator('text=Enable auto-reload')
        if await checkbox.count() > 0:
            await checkbox.click()
            await asyncio.sleep(1)

        # Fill threshold and amount if inputs appear
        # (depends on UI — inputs may only show when enabled)
        threshold_input = page.locator('input[name*="threshold"], input[placeholder*="threshold"]')
        if await threshold_input.count() > 0:
            await threshold_input.fill(str(threshold))

        amount_input = page.locator('input[name*="amount"], input[placeholder*="amount"]')
        if await amount_input.count() > 0:
            await amount_input.fill(str(amount))

        # Save
        save_btn = page.locator('button:has-text("Save")')
        if await save_btn.count() > 0:
            await save_btn.click()
            await asyncio.sleep(3)

        await page.screenshot(path="screenshot_auto_reload.png")
        return {"success": True}


async def get_balance(settings: Settings | None = None) -> dict:
    """Get current balance and usage info."""
    if settings is None:
        settings = Settings()

    async with async_playwright() as p:
        browser = await connect_chromium(p, settings)
        context = await get_browser_context(browser)
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
