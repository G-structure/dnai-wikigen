"""Automate Thinking Machines Tinker signup/sign-in via browser + email oracle.

Full flow:
  1. Navigate to Tinker console → auth.thinkingmachines.ai
  2. Enter email → Continue → magic-code OTP page
  3. Poll email oracle /pin for 6-digit code → enter code
  4. Complete onboarding form (name, TOS)
  5. Create API key → capture it
  6. Return email + API key

Requires:
  - Email oracle running
  - Browser automation path that Tinker does not classify as blocked
"""
import asyncio
import time

from playwright.async_api import async_playwright, Page

from tinker_delegate.browser_ready import connect_chromium, get_browser_context
from tinker_delegate.api_key_store import build_api_key_store
from tinker_delegate.config import Settings
from tinker_delegate.oracle_client import OracleClient


class AuthAccessBlockedError(RuntimeError):
    """Raised when the Tinker auth flow rejects the browser session."""


async def wait_for_otp(oracle: OracleClient, settings: Settings) -> str:
    """Poll email oracle for the Tinker OTP code."""
    start = time.time()
    print("[otp] polling email oracle for verification code...")

    while time.time() - start < settings.otp_poll_timeout:
        result = oracle.get_pin(
            subject_contains="",
            max_age_seconds=settings.otp_max_age,
            extract_pattern=r"\b\d{6}\b",
            caller_identity="tinker-delegate.signup",
            reason="tinker-passwordless-auth",
            delete_after=True,
        )
        if result and result.get("pin"):
            pin = result["pin"]
            print(f"[otp] got code from: {result.get('sender', '?')}")
            return pin

        elapsed = int(time.time() - start)
        print(f"[otp] no code yet ({elapsed}s elapsed)...")
        await asyncio.sleep(settings.otp_poll_interval)

    raise TimeoutError(
        f"No OTP received within {settings.otp_poll_timeout}s. "
        f"Check oracle inbox: {settings.oracle_url}/inbox"
    )


async def enter_otp(page: Page, code: str) -> None:
    """Enter the 6-digit OTP into the verification page."""
    for selector in [
        'input[inputmode="numeric"]',
        'input[data-input-otp="true"]',
        'input[autocomplete="one-time-code"]',
        'input[maxlength="1"]',
    ]:
        inputs = page.locator(selector)
        count = await inputs.count()
        if count >= 6:
            print(f"[otp] entering into {count} input boxes")
            for i, digit in enumerate(code[:6]):
                await inputs.nth(i).fill(digit)
                await asyncio.sleep(0.1)
            return
        elif count == 1:
            await inputs.first.fill(code)
            return

    # Last resort
    await page.keyboard.type(code, delay=80)


async def _navigate(page: Page, url: str) -> None:
    """Navigate with fallback."""
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=20000)
    except Exception:
        await page.goto("https://auth.thinkingmachines.ai/", wait_until="domcontentloaded", timeout=15000)
    await asyncio.sleep(2)


async def _page_state(page: Page) -> dict:
    """Get current page state."""
    return await page.evaluate("""() => ({
        url: window.location.href,
        text: document.body?.innerText?.substring(0, 1500) || '',
        hasEmailInput: !!document.querySelector('input[name="email"]'),
        hasFirstNameInput: !!document.querySelector('input[name="first_name"]'),
        hasFullNameInput: !!document.querySelector('input[name="fullName"]'),
        hasOtpInputs: document.querySelectorAll('input[inputmode="numeric"]').length,
    })""")


# ---------------------------------------------------------------------------
# Main entry points
# ---------------------------------------------------------------------------

async def signup(settings: Settings | None = None) -> dict:
    """Full Tinker signup: auth → onboarding → API key.

    Returns dict with email, api_key, success.
    """
    if settings is None:
        settings = Settings()

    oracle = OracleClient(settings)
    email = settings.email or oracle.get_email()
    print(f"[signup] email: {email}")

    async with async_playwright() as p:
        browser = await connect_chromium(p, settings)
        context = await get_browser_context(browser)
        page = context.pages[0] if context.pages else await context.new_page()

        # Step 1: Authenticate
        await _authenticate(page, email, oracle, settings)

        # Step 2: Handle onboarding if present
        await _handle_onboarding(page, settings)

        # Step 3: Create API key
        api_key = await _create_api_key(page)

        result = {"email": email, "api_key": api_key, "success": bool(api_key)}
        print(f"\n[done] success={result['success']}")
        if api_key:
            try:
                store = build_api_key_store(settings)
                store.save(api_key)
                result["stored"] = True
            except Exception as e:
                result["stored"] = False
                result["store_error"] = str(e)
            print(f"[done] TINKER_API_KEY={api_key[:12]}...<redacted>")
        return result


async def signin(settings: Settings | None = None) -> dict:
    """Sign in to existing Tinker account."""
    if settings is None:
        settings = Settings()

    oracle = OracleClient(settings)
    email = settings.email or oracle.get_email()
    print(f"[signin] email: {email}")

    async with async_playwright() as p:
        browser = await connect_chromium(p, settings)
        context = await get_browser_context(browser)
        page = context.pages[0] if context.pages else await context.new_page()

        await _authenticate(page, email, oracle, settings)

        final_url = page.url
        return {"email": email, "url": final_url, "success": "tinker-console" in final_url}


# ---------------------------------------------------------------------------
# Internal steps
# ---------------------------------------------------------------------------

async def _authenticate(page: Page, email: str, oracle: OracleClient, settings: Settings) -> None:
    """Navigate to auth, enter email, complete OTP. Leaves browser on console."""
    print("[auth] navigating to Tinker console...")
    await _navigate(page, settings.tinker_console_url)

    state = await _page_state(page)

    def ensure_not_access_blocked(state: dict) -> None:
        if "access blocked" in state["text"].lower():
            raise AuthAccessBlockedError(
                "Tinker auth returned 'Access blocked, please contact support.' "
                "The current headed local Chrome control passes, but the deployed "
                "headless automation path is being blocked."
            )

    # If on leftover OTP page, start fresh
    if state["hasOtpInputs"] > 0 or "magic-code" in state["url"]:
        print("[auth] clearing stale OTP page...")
        await _navigate(page, settings.tinker_console_url)
        state = await _page_state(page)

    # Already authenticated?
    if "tinker-console" in state["url"] and not state["hasEmailInput"]:
        print("[auth] already authenticated")
        return

    # Enter email on sign-in page
    if state["hasEmailInput"]:
        print("[auth] entering email...")
        email_input = page.locator('input[name="email"]')
        await email_input.fill("")
        await email_input.click()
        await email_input.type(email, delay=30)
        await asyncio.sleep(0.5)

        await page.click('button[type="submit"]')
        await asyncio.sleep(4)

        state = await _page_state(page)
        ensure_not_access_blocked(state)

        # If landed on sign-up form (new account via sign-in flow)
        if state["hasFirstNameInput"]:
            print("[auth] redirected to sign-up form, filling...")
            await page.fill('input[name="first_name"]', settings.first_name)
            await asyncio.sleep(0.2)
            await page.fill('input[name="last_name"]', settings.last_name)
            await asyncio.sleep(0.2)
            await page.locator('input[name="email"]').click()
            await page.locator('input[name="email"]').type(email, delay=30)
            await asyncio.sleep(0.5)
            await page.click('button[type="submit"]')
            await asyncio.sleep(4)
            state = await _page_state(page)

        # Should be on magic-code page now
        if "magic-code" not in state["url"] and "Check your email" not in state["text"]:
            # Try clicking Sign up link and filling the form
            signup_link = page.locator('a:has-text("Sign up")')
            if await signup_link.count() > 0:
                print("[auth] trying sign-up flow...")
                await signup_link.click()
                await page.locator('input[name="first_name"]').wait_for(state="visible", timeout=10000)
                await asyncio.sleep(1)
                await page.fill('input[name="first_name"]', settings.first_name)
                await asyncio.sleep(0.2)
                await page.fill('input[name="last_name"]', settings.last_name)
                await asyncio.sleep(0.2)
                await page.locator('input[name="email"]').click()
                await page.locator('input[name="email"]').type(email, delay=30)
                await asyncio.sleep(0.5)
                await page.click('button[type="submit"]')
                await asyncio.sleep(4)
                state = await _page_state(page)

        ensure_not_access_blocked(state)

    # Complete OTP
    if "magic-code" in state["url"] or "Check your email" in state["text"]:
        print("[auth] on OTP page, waiting for code...")
        code = await wait_for_otp(oracle, settings)
        print(f"[auth] entering code: {code}")
        await enter_otp(page, code)
        await asyncio.sleep(5)

        try:
            await page.wait_for_url("**/tinker-console.thinkingmachines.ai/**", timeout=15000)
        except Exception:
            pass

        await asyncio.sleep(2)
        print(f"[auth] authenticated → {page.url}")
    else:
        raise RuntimeError(f"Unexpected state after email submit: {state['url']}")


async def _handle_onboarding(page: Page, settings: Settings) -> None:
    """Complete onboarding form if present."""
    state = await _page_state(page)

    if "onboarding" not in state["url"] and not state["hasFullNameInput"]:
        return

    print("[onboarding] completing form...")
    await page.fill('input[name="fullName"]', f"{settings.first_name} {settings.last_name}")
    await asyncio.sleep(0.3)

    # TOS checkbox — click the label (input is hidden/styled)
    tos_label = page.locator('text=I have read and agree')
    if await tos_label.count() > 0:
        await tos_label.click()
        await asyncio.sleep(0.5)

    await page.click('button:has-text("Continue")')
    await asyncio.sleep(5)
    print(f"[onboarding] done → {page.url}")


async def _create_api_key(page: Page) -> str | None:
    """Navigate to API keys page, create a key, return it."""
    print("[apikey] navigating to API keys page...")
    await page.goto("https://tinker-console.thinkingmachines.ai/keys",
                    wait_until="domcontentloaded", timeout=15000)
    # Wait for page to fully render (initial load shows "Loading...")
    await asyncio.sleep(3)
    await page.reload(wait_until="domcontentloaded", timeout=15000)
    await asyncio.sleep(3)

    # Click "New key"
    new_key = page.locator('button:has-text("New key")')
    if await new_key.count() == 0:
        print("[apikey] no 'New key' button found")
        await page.screenshot(path="screenshot_no_new_key.png")
        return None

    print("[apikey] creating new key...")
    await new_key.click()
    await asyncio.sleep(1)

    generate_key = page.locator('button:has-text("Generate key")')
    if await generate_key.count() > 0:
        print("[apikey] confirming key generation...")
        await generate_key.first.click()
        await asyncio.sleep(3)
    else:
        await asyncio.sleep(2)

    # Extract the key from the dialog
    api_key = await page.evaluate("""() => {
        const candidates = document.querySelectorAll('code, pre, [data-key], input[readonly], .font-mono');
        for (const el of candidates) {
            const text = (el.textContent || el.value || '').trim();
            if (text.startsWith('tml-') && text.length > 30) return text;
        }
        // Fallback: search all text nodes
        const body = document.body?.innerText || '';
        const match = body.match(/tml-[A-Za-z0-9_-]{30,}/);
        return match ? match[0] : null;
    }""")

    if api_key:
        print(f"[apikey] captured: {api_key[:20]}...")
    else:
        print("[apikey] failed to extract key")
        await page.screenshot(path="screenshot_key_extraction_fail.png")

    # Close dialog
    close_btn = page.locator('button:has-text("Close")')
    if await close_btn.count() > 0:
        await close_btn.first.click()
        await asyncio.sleep(1)

    return api_key
