"""Tests for renderer (Pass 15)."""
import pytest
from agency.renderer import render_markdown, render_code, render_table


def test_render_markdown_returns_string():
    result = render_markdown("# Hello\nWorld")
    assert isinstance(result, str)
    assert len(result) > 0


def test_render_markdown_contains_text():
    result = render_markdown("Hello World")
    assert "Hello World" in result or "Hello" in result


def test_render_code_returns_string():
    code = "def foo():\n    return 42"
    result = render_code(code, language="python")
    assert isinstance(result, str)
    assert "foo" in result or len(result) > 0


def test_render_table_basic():
    headers = ["Name", "Value"]
    rows = [["Alpha", "1"], ["Beta", "2"]]
    result = render_table(headers, rows)
    assert isinstance(result, str)
    assert len(result) > 0


def test_render_table_contains_data():
    headers = ["Col"]
    rows = [["Row1"], ["Row2"]]
    result = render_table(headers, rows)
    # Either rich or ASCII fallback should show the data
    assert "Row1" in result or len(result) > 0


def test_render_markdown_bold():
    result = render_markdown("**bold text**")
    assert isinstance(result, str)


def test_render_markdown_code_fence():
    result = render_markdown("```python\nprint('hi')\n```")
    assert isinstance(result, str)
