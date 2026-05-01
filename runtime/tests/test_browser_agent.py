"""Tests for browser_agent.py — BrowserAgent (mock mode)."""

from __future__ import annotations

import pytest

from agency.browser_agent import BrowserAgent


@pytest.fixture
def agent():
    a = BrowserAgent()
    # Force mock mode for tests (no network access)
    a.mode = "mock"
    return a


def test_mode_is_set(agent):
    assert agent.mode in ("playwright", "requests", "mock")


def test_fetch_page_returns_dict(agent):
    result = agent.fetch_page("https://example.com")
    assert isinstance(result, dict)


def test_fetch_page_has_url(agent):
    url = "https://example.com"
    result = agent.fetch_page(url)
    assert result["url"] == url


def test_fetch_page_has_title(agent):
    result = agent.fetch_page("https://example.com")
    assert "title" in result


def test_fetch_page_has_text(agent):
    result = agent.fetch_page("https://example.com")
    assert "text" in result
    assert isinstance(result["text"], str)


def test_fetch_page_has_links(agent):
    result = agent.fetch_page("https://example.com")
    assert "links" in result
    assert isinstance(result["links"], list)


def test_fetch_page_has_mode(agent):
    result = agent.fetch_page("https://example.com")
    assert result["mode"] == "mock"


def test_search_web_returns_list(agent):
    results = agent.search_web("Python programming")
    assert isinstance(results, list)


def test_search_web_default_num_results(agent):
    results = agent.search_web("test query")
    assert len(results) == 5


def test_search_web_custom_num_results(agent):
    results = agent.search_web("test query", num_results=3)
    assert len(results) == 3


def test_search_web_result_fields(agent):
    results = agent.search_web("query")
    for r in results:
        assert "title" in r
        assert "url" in r
        assert "snippet" in r


def test_search_web_result_urls_are_strings(agent):
    results = agent.search_web("query")
    for r in results:
        assert isinstance(r["url"], str)
        assert r["url"].startswith("http")


def test_screenshot_mock_returns_none(agent):
    result = agent.screenshot("https://example.com")
    assert result is None


def test_extract_text_returns_string(agent):
    text = agent.extract_text("https://example.com")
    assert isinstance(text, str)


def test_extract_text_non_empty_for_mock(agent):
    text = agent.extract_text("https://example.com")
    assert len(text) > 0


def test_fetch_page_different_urls(agent):
    urls = [
        "https://example.com",
        "https://google.com",
        "https://github.com",
    ]
    for url in urls:
        result = agent.fetch_page(url)
        assert result["url"] == url


def test_search_web_query_in_results(agent):
    query = "unique_search_term_xyz"
    results = agent.search_web(query)
    assert any(query in r["title"] or query in r["snippet"] for r in results)
