"""
CDP automation examples using Playwright.

Each function demonstrates a common pattern for browser automation
via Chrome DevTools Protocol. All functions connect to the neko-chrome
container over CDP — no local browser install needed.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from playwright.async_api import async_playwright

from .config import settings


async def take_screenshot(url: str, path: str | None = None) -> str:
    """Navigate to a URL and save a full-page screenshot.

    Args:
        url: Page to screenshot.
        path: Output file path. Defaults to /data/screenshot.png.

    Returns:
        Path to the saved screenshot.
    """
    out = path or os.path.join(settings.data_dir, "screenshot.png")
    Path(out).parent.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(settings.cdp_url)
        page = await browser.contexts[0].new_page()
        await page.goto(url, wait_until="networkidle")
        await page.screenshot(path=out, full_page=True)
        await page.close()

    return out


async def scrape_page(url: str) -> dict:
    """Scrape a page's title, meta description, headings, and links.

    Args:
        url: Page to scrape.

    Returns:
        Dict with title, description, h1 list, and links.
    """
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(settings.cdp_url)
        page = await browser.contexts[0].new_page()
        await page.goto(url, wait_until="networkidle")

        data = await page.evaluate("""() => {
            const meta = document.querySelector('meta[name="description"]');
            return {
                title: document.title,
                description: meta ? meta.content : null,
                h1: Array.from(document.querySelectorAll('h1')).map(e => e.textContent.trim()),
                links: Array.from(document.querySelectorAll('a[href]')).slice(0, 50).map(a => ({
                    text: a.textContent.trim().substring(0, 100),
                    href: a.href,
                })),
            };
        }""")

        await page.close()

    return data


async def fill_and_submit(url: str, fields: dict[str, str], submit_selector: str) -> str:
    """Navigate to a page, fill form fields, and click submit.

    Args:
        url: Page with the form.
        fields: Mapping of CSS selector → value to type.
        submit_selector: CSS selector for the submit button.

    Returns:
        The page title after submission.
    """
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(settings.cdp_url)
        page = await browser.contexts[0].new_page()
        await page.goto(url, wait_until="networkidle")

        for selector, value in fields.items():
            await page.fill(selector, value)

        await page.click(submit_selector)
        await page.wait_for_load_state("networkidle")
        title = await page.title()
        await page.close()

    return title


async def execute_js(url: str, script: str) -> str:
    """Navigate to a URL and execute arbitrary JavaScript, returning the result.

    Args:
        url: Page to run the script on.
        script: JavaScript expression to evaluate.

    Returns:
        JSON-serialized result.
    """
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(settings.cdp_url)
        page = await browser.contexts[0].new_page()
        await page.goto(url, wait_until="networkidle")
        result = await page.evaluate(script)
        await page.close()

    return json.dumps(result, indent=2, default=str)


async def multi_page_crawl(urls: list[str]) -> list[dict]:
    """Open multiple URLs in parallel tabs and extract their titles.

    Demonstrates reusing a single CDP connection with multiple pages.

    Args:
        urls: List of URLs to crawl.

    Returns:
        List of dicts with url and title.
    """
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(settings.cdp_url)
        context = browser.contexts[0]
        results = []

        for url in urls:
            page = await context.new_page()
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                title = await page.title()
                results.append({"url": url, "title": title})
            except Exception as e:
                results.append({"url": url, "error": str(e)})
            finally:
                await page.close()

    return results
