"""
CDP Playground — CLI + API server.

CLI usage (from inside the app container):
    python -m app.main screenshot https://example.com
    python -m app.main scrape https://news.ycombinator.com
    python -m app.main crawl https://example.com https://httpbin.org
    python -m app.main js https://example.com "document.title"
    python -m app.main serve

API usage (from host or other containers):
    curl http://localhost:8000/health
    curl -X POST http://localhost:8000/screenshot -H 'Content-Type: application/json' \
         -d '{"url": "https://example.com"}'
    curl -X POST http://localhost:8000/scrape -H 'Content-Type: application/json' \
         -d '{"url": "https://example.com"}'
"""

from __future__ import annotations

import asyncio
import json
import sys

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .automation import (
    execute_js,
    fill_and_submit,
    multi_page_crawl,
    scrape_page,
    take_screenshot,
)
from .config import settings

# ─── FastAPI app ─────────────────────────────────────────────────────────

api = FastAPI(title="CDP Playground", version="0.1.0")


class UrlRequest(BaseModel):
    url: str


class JsRequest(BaseModel):
    url: str
    script: str


class CrawlRequest(BaseModel):
    urls: list[str]


class FormRequest(BaseModel):
    url: str
    fields: dict[str, str]
    submit_selector: str


@api.get("/health")
async def health():
    return {"status": "ok", "cdp_url": settings.cdp_url}


@api.post("/screenshot")
async def api_screenshot(req: UrlRequest):
    path = await take_screenshot(req.url)
    return FileResponse(path, media_type="image/png", filename="screenshot.png")


@api.post("/scrape")
async def api_scrape(req: UrlRequest):
    return await scrape_page(req.url)


@api.post("/js")
async def api_js(req: JsRequest):
    result = await execute_js(req.url, req.script)
    return json.loads(result)


@api.post("/crawl")
async def api_crawl(req: CrawlRequest):
    return await multi_page_crawl(req.urls)


@api.post("/form")
async def api_form(req: FormRequest):
    title = await fill_and_submit(req.url, req.fields, req.submit_selector)
    return {"result_title": title}


# ─── CLI ─────────────────────────────────────────────────────────────────

def cli():
    if len(sys.argv) < 2:
        print("Usage: python -m app.main <command> [args...]")
        print("Commands: serve, screenshot, scrape, crawl, js")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "serve":
        uvicorn.run(api, host=settings.host, port=settings.port)

    elif cmd == "screenshot":
        url = sys.argv[2] if len(sys.argv) > 2 else "https://example.com"
        path = asyncio.run(take_screenshot(url))
        print(f"Screenshot saved: {path}")

    elif cmd == "scrape":
        url = sys.argv[2] if len(sys.argv) > 2 else "https://example.com"
        data = asyncio.run(scrape_page(url))
        print(json.dumps(data, indent=2))

    elif cmd == "crawl":
        urls = sys.argv[2:]
        if not urls:
            urls = ["https://example.com", "https://httpbin.org"]
        results = asyncio.run(multi_page_crawl(urls))
        print(json.dumps(results, indent=2))

    elif cmd == "js":
        url = sys.argv[2] if len(sys.argv) > 2 else "https://example.com"
        script = sys.argv[3] if len(sys.argv) > 3 else "document.title"
        result = asyncio.run(execute_js(url, script))
        print(result)

    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    cli()
