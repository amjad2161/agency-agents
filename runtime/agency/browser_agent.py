"""Browser automation: Playwright → requests+BeautifulSoup → mock fallback."""

from __future__ import annotations

import re
import urllib.parse
from typing import Optional

# ---------------------------------------------------------------------------
# Lazy imports: Playwright and BeautifulSoup are optional
# ---------------------------------------------------------------------------

try:
    from playwright.sync_api import sync_playwright  # type: ignore
    _HAS_PLAYWRIGHT = True
except ImportError:
    _HAS_PLAYWRIGHT = False

try:
    import requests as _requests
    from bs4 import BeautifulSoup as _BS  # type: ignore
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False


def _strip_tags(html: str) -> str:
    """Remove HTML tags and collapse whitespace."""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


class BrowserAgent:
    """Web browsing via Playwright, requests+BS4, or mock."""

    def __init__(self) -> None:
        if _HAS_PLAYWRIGHT:
            self.mode = "playwright"
        elif _HAS_REQUESTS:
            self.mode = "requests"
        else:
            self.mode = "mock"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch_page(self, url: str) -> dict:
        """Fetch a page. Returns {url, title, text, links, mode}."""
        if self.mode == "playwright":
            return self._fetch_playwright(url)
        if self.mode == "requests":
            return self._fetch_requests(url)
        return self._mock_page(url)

    def search_web(self, query: str, num_results: int = 5) -> list[dict]:
        """DuckDuckGo lite search. Returns [{title, url, snippet}]."""
        if self.mode == "mock":
            return self._mock_search(query, num_results)
        return self._ddg_search(query, num_results)

    def screenshot(self, url: str) -> Optional[bytes]:
        """Take a screenshot (Playwright only). Returns None otherwise."""
        if self.mode != "playwright":
            return None
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch()
                page = browser.new_page()
                page.goto(url, timeout=15000)
                data = page.screenshot()
                browser.close()
                return data
        except Exception:
            return None

    def extract_text(self, url: str) -> str:
        """Fetch and return cleaned plain text from URL."""
        result = self.fetch_page(url)
        return result.get("text", "")

    # ------------------------------------------------------------------
    # Playwright implementation
    # ------------------------------------------------------------------

    def _fetch_playwright(self, url: str) -> dict:
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch()
                page = browser.new_page()
                page.goto(url, timeout=15000)
                title = page.title()
                content = page.content()
                links = page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
                browser.close()
            text = _strip_tags(content)
            return {"url": url, "title": title, "text": text[:5000], "links": links[:50], "mode": "playwright"}
        except Exception as exc:
            return {"url": url, "title": "", "text": str(exc), "links": [], "mode": "playwright", "error": str(exc)}

    # ------------------------------------------------------------------
    # requests + BeautifulSoup implementation
    # ------------------------------------------------------------------

    def _fetch_requests(self, url: str) -> dict:
        try:
            headers = {"User-Agent": "Mozilla/5.0 (JARVIS; +https://github.com/jarvis)"}
            resp = _requests.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            soup = _BS(resp.text, "html.parser")
            title = soup.title.string.strip() if soup.title else ""
            # Remove scripts and styles
            for tag in soup(["script", "style", "noscript"]):
                tag.decompose()
            text = soup.get_text(separator=" ", strip=True)[:5000]
            links = [
                urllib.parse.urljoin(url, a.get("href", ""))
                for a in soup.find_all("a", href=True)
            ][:50]
            return {"url": url, "title": title, "text": text, "links": links, "mode": "requests"}
        except Exception as exc:
            return {"url": url, "title": "", "text": str(exc), "links": [], "mode": "requests", "error": str(exc)}

    def _ddg_search(self, query: str, num_results: int) -> list[dict]:
        try:
            encoded = urllib.parse.quote_plus(query)
            url = f"https://html.duckduckgo.com/html/?q={encoded}"
            headers = {"User-Agent": "Mozilla/5.0 (JARVIS)"}
            resp = _requests.get(url, headers=headers, timeout=10)
            soup = _BS(resp.text, "html.parser")
            results: list[dict] = []
            for result in soup.select(".result"):
                a = result.select_one(".result__a")
                snippet_el = result.select_one(".result__snippet")
                if not a:
                    continue
                href = a.get("href", "")
                # DuckDuckGo wraps links — extract actual URL
                parsed = urllib.parse.urlparse(href)
                qs = urllib.parse.parse_qs(parsed.query)
                actual_url = qs.get("uddg", [href])[0]
                results.append({
                    "title": a.get_text(strip=True),
                    "url": actual_url,
                    "snippet": snippet_el.get_text(strip=True) if snippet_el else "",
                })
                if len(results) >= num_results:
                    break
            return results
        except Exception:
            return self._mock_search(query, num_results)

    # ------------------------------------------------------------------
    # Mock fallbacks
    # ------------------------------------------------------------------

    def _mock_page(self, url: str) -> dict:
        return {
            "url": url,
            "title": f"Mock Page: {url}",
            "text": f"[mock content for {url}]",
            "links": [],
            "mode": "mock",
        }

    def _mock_search(self, query: str, num_results: int) -> list[dict]:
        return [
            {
                "title": f"Mock result {i + 1} for '{query}'",
                "url": f"https://example.com/result{i + 1}",
                "snippet": f"This is mock snippet {i + 1} for query: {query}",
            }
            for i in range(num_results)
        ]
