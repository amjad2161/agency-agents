"""Browser Automation module for JARVIS Pass 17.

BrowserAgent provides:
  browse(url)                  → PageResult (text + title + links)
  screenshot(url, output_path) → path to saved PNG
  fill_form(url, fields)       → FormResult (success flag + response text)

Fallback chain
--------------
1. playwright (async)  — full browser automation
2. selenium            — WebDriver-based
3. urllib + curl       — basic HTTP fetch (no JS)
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import logging
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional imports
# ---------------------------------------------------------------------------
try:
    from playwright.sync_api import sync_playwright  # type: ignore
    _PLAYWRIGHT_OK = True
except ImportError:
    _PLAYWRIGHT_OK = False

try:
    from selenium import webdriver  # type: ignore
    from selenium.webdriver.chrome.options import Options as _ChromeOptions  # type: ignore
    from selenium.webdriver.common.by import By as _By  # type: ignore
    from selenium.webdriver.support.ui import WebDriverWait as _WebDriverWait  # type: ignore
    from selenium.webdriver.support import expected_conditions as _EC  # type: ignore
    _SELENIUM_OK = True
except ImportError:
    _SELENIUM_OK = False

try:
    from bs4 import BeautifulSoup as _BS  # type: ignore
    _BS4_OK = True
except ImportError:
    _BS = None  # type: ignore[assignment]
    _BS4_OK = False


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------
@dataclass
class PageResult:
    url: str = ""
    title: str = ""
    text: str = ""
    links: list[str] = field(default_factory=list)
    html: str = ""
    engine: str = "unknown"
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "title": self.title,
            "text": self.text[:4000],   # truncate for safety
            "links": self.links[:50],
            "engine": self.engine,
            "error": self.error,
        }


@dataclass
class FormResult:
    success: bool = False
    response_text: str = ""
    engine: str = "unknown"
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "response_text": self.response_text[:2000],
            "engine": self.engine,
            "error": self.error,
        }


# ---------------------------------------------------------------------------
# HTML text extraction helper
# ---------------------------------------------------------------------------
def _extract_text(html: str) -> tuple[str, str, list[str]]:
    """Return (title, plain_text, links) from raw HTML."""
    if _BS4_OK:
        soup = _BS(html, "html.parser")
        title = soup.title.string.strip() if soup.title and soup.title.string else ""
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        links = [a.get("href", "") for a in soup.find_all("a", href=True)]
        return title, text, links
    else:
        # Minimal regex fallback
        import re
        title_m = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        title = title_m.group(1).strip() if title_m else ""
        clean = re.sub(r"<[^>]+>", " ", html)
        clean = re.sub(r"\s+", " ", clean).strip()
        links_raw = re.findall(r'href=["\']([^"\']+)["\']', html)
        return title, clean, links_raw


# ---------------------------------------------------------------------------
# Engine implementations — browse
# ---------------------------------------------------------------------------

def _browse_playwright(url: str, timeout_ms: int = 15000) -> PageResult:
    result = PageResult(url=url, engine="playwright")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="networkidle", timeout=timeout_ms)
        html = page.content()
        result.html = html
        result.title, result.text, result.links = _extract_text(html)
        browser.close()
    return result


def _browse_selenium(url: str, timeout: int = 15) -> PageResult:
    result = PageResult(url=url, engine="selenium")
    opts = _ChromeOptions()
    opts.add_argument("--headless")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    driver = webdriver.Chrome(options=opts)
    try:
        driver.set_page_load_timeout(timeout)
        driver.get(url)
        html = driver.page_source
        result.html = html
        result.title, result.text, result.links = _extract_text(html)
    finally:
        driver.quit()
    return result


def _browse_urllib(url: str, timeout: int = 15) -> PageResult:
    result = PageResult(url=url, engine="urllib")
    req = urllib.request.Request(url, headers={"User-Agent": "JARVIS-Browser/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read(2 * 1024 * 1024)  # 2 MB cap
        encoding = resp.headers.get_content_charset("utf-8")
        html = raw.decode(encoding, errors="replace")
    result.html = html
    result.title, result.text, result.links = _extract_text(html)
    return result


def _browse_curl(url: str, timeout: int = 15) -> PageResult:
    result = PageResult(url=url, engine="curl")
    proc = subprocess.run(
        ["curl", "-sL", "--max-time", str(timeout), "-A", "JARVIS-Browser/1.0", url],
        capture_output=True,
        timeout=timeout + 5,
    )
    html = proc.stdout.decode("utf-8", errors="replace")
    result.html = html
    result.title, result.text, result.links = _extract_text(html)
    return result


# ---------------------------------------------------------------------------
# Engine implementations — screenshot
# ---------------------------------------------------------------------------

def _screenshot_playwright(url: str, output_path: str, timeout_ms: int = 15000) -> str:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.goto(url, wait_until="networkidle", timeout=timeout_ms)
        page.screenshot(path=output_path, full_page=True)
        browser.close()
    return output_path


def _screenshot_selenium(url: str, output_path: str, timeout: int = 15) -> str:
    opts = _ChromeOptions()
    opts.add_argument("--headless")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--window-size=1280,800")
    driver = webdriver.Chrome(options=opts)
    try:
        driver.set_page_load_timeout(timeout)
        driver.get(url)
        driver.save_screenshot(output_path)
    finally:
        driver.quit()
    return output_path


# ---------------------------------------------------------------------------
# Engine implementations — fill_form
# ---------------------------------------------------------------------------

def _fill_form_playwright(url: str, fields: dict[str, str], timeout_ms: int = 15000) -> FormResult:
    result = FormResult(engine="playwright")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="networkidle", timeout=timeout_ms)
        for selector, value in fields.items():
            page.fill(selector, value)
        # Click first submit button found
        try:
            page.click("input[type=submit], button[type=submit], button:text('Submit')",
                       timeout=3000)
        except Exception:
            page.keyboard.press("Enter")
        page.wait_for_load_state("networkidle", timeout=timeout_ms)
        html = page.content()
        _, text, _ = _extract_text(html)
        result.response_text = text
        result.success = True
        browser.close()
    return result


def _fill_form_selenium(url: str, fields: dict[str, str], timeout: int = 15) -> FormResult:
    result = FormResult(engine="selenium")
    opts = _ChromeOptions()
    opts.add_argument("--headless")
    opts.add_argument("--no-sandbox")
    driver = webdriver.Chrome(options=opts)
    try:
        driver.set_page_load_timeout(timeout)
        driver.get(url)
        for selector, value in fields.items():
            elem = driver.find_element(_By.CSS_SELECTOR, selector)
            elem.clear()
            elem.send_keys(value)
        try:
            driver.find_element(_By.CSS_SELECTOR, "input[type=submit], button[type=submit]").click()
        except Exception:
            pass
        _, text, _ = _extract_text(driver.page_source)
        result.response_text = text
        result.success = True
    finally:
        driver.quit()
    return result


# ---------------------------------------------------------------------------
# Public BrowserAgent class
# ---------------------------------------------------------------------------

class BrowserAgent:
    """High-level browser automation with auto engine fallback."""

    def __init__(self, preferred_engine: str | None = None):
        self.preferred_engine = preferred_engine

    def _engine_order(self) -> list[str]:
        if self.preferred_engine:
            order = [self.preferred_engine]
        else:
            order = []
        # Auto-detect
        if _PLAYWRIGHT_OK and "playwright" not in order:
            order.append("playwright")
        if _SELENIUM_OK and "selenium" not in order:
            order.append("selenium")
        order.extend(["urllib", "curl"])
        return order

    def browse(self, url: str, timeout: int = 15) -> dict[str, Any]:
        """Fetch a URL and return page text + title."""
        engines = self._engine_order()
        last_error: str | None = None
        for eng in engines:
            try:
                if eng == "playwright" and _PLAYWRIGHT_OK:
                    return _browse_playwright(url, timeout * 1000).to_dict()
                elif eng == "selenium" and _SELENIUM_OK:
                    return _browse_selenium(url, timeout).to_dict()
                elif eng == "urllib":
                    return _browse_urllib(url, timeout).to_dict()
                elif eng == "curl":
                    return _browse_curl(url, timeout).to_dict()
            except Exception as exc:
                last_error = str(exc)
                log.warning("browser.browse: engine %s failed: %s", eng, exc)
        result = PageResult(url=url, error=last_error or "all engines failed")
        return result.to_dict()

    def screenshot(self, url: str, output_path: str | None = None, timeout: int = 15) -> str:
        """Take a screenshot of a URL. Returns path to saved image."""
        if output_path is None:
            fd, output_path = tempfile.mkstemp(suffix=".png")
            os.close(fd)
        if _PLAYWRIGHT_OK:
            try:
                return _screenshot_playwright(url, output_path, timeout * 1000)
            except Exception as exc:
                log.warning("playwright screenshot failed: %s", exc)
        if _SELENIUM_OK:
            try:
                return _screenshot_selenium(url, output_path, timeout)
            except Exception as exc:
                log.warning("selenium screenshot failed: %s", exc)
        raise RuntimeError(
            "screenshot requires playwright or selenium: "
            "pip install playwright && playwright install chromium"
        )

    def fill_form(self, url: str, fields: dict[str, str], timeout: int = 15) -> dict[str, Any]:
        """Fill and submit a web form. fields = {css_selector: value}."""
        if _PLAYWRIGHT_OK:
            try:
                return _fill_form_playwright(url, fields, timeout * 1000).to_dict()
            except Exception as exc:
                log.warning("playwright fill_form failed: %s", exc)
        if _SELENIUM_OK:
            try:
                return _fill_form_selenium(url, fields, timeout).to_dict()
            except Exception as exc:
                log.warning("selenium fill_form failed: %s", exc)
        result = FormResult(error="fill_form requires playwright or selenium")
        return result.to_dict()


# ---------------------------------------------------------------------------
# Module-level convenience functions
# ---------------------------------------------------------------------------

_default_agent = BrowserAgent()


def browse(url: str, timeout: int = 15) -> dict[str, Any]:
    return _default_agent.browse(url, timeout)


def screenshot(url: str, output_path: str | None = None, timeout: int = 15) -> str:
    return _default_agent.screenshot(url, output_path, timeout)


def fill_form(url: str, fields: dict[str, str], timeout: int = 15) -> dict[str, Any]:
    return _default_agent.fill_form(url, fields, timeout)


# ---------------------------------------------------------------------------
# CLI helpers
# ---------------------------------------------------------------------------

def cli_browse(args: Any) -> None:
    import json as _json
    result = browse(args.url)
    if result.get("error"):
        print(f"Error: {result['error']}", file=sys.stderr)
        sys.exit(1)
    print(f"Title: {result['title']}\n")
    print(result["text"][:3000])


def cli_screenshot(args: Any) -> None:
    out = getattr(args, "output", None)
    path = screenshot(args.url, out)
    print(f"Screenshot saved: {path}")
