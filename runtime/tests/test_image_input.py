"""Tests for image-input multimodal support."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from agency.executor import _image_content_block, Executor
from agency.skills import Skill


def test_data_url_becomes_base64_block():
    spec = "data:image/png;base64,iVBORw0KGgo="
    b = _image_content_block(spec)
    assert b == {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/png",
            "data": "iVBORw0KGgo=",
        },
    }


def test_data_url_jpeg():
    b = _image_content_block("data:image/jpeg;base64,/9j/4AAQ=")
    assert b["source"]["media_type"] == "image/jpeg"


def test_https_url_becomes_url_block():
    b = _image_content_block("https://example.com/cat.jpg")
    assert b == {"type": "image",
                 "source": {"type": "url", "url": "https://example.com/cat.jpg"}}


def test_http_url_accepted():
    b = _image_content_block("http://example.com/x.png")
    assert b["source"]["type"] == "url"


def test_invalid_spec_raises():
    with pytest.raises(ValueError, match="unrecognized image spec"):
        _image_content_block("just a string")


def test_malformed_data_url_raises():
    with pytest.raises(ValueError, match="malformed data URL"):
        _image_content_block("data:image/png")  # no comma


def test_empty_spec_raises():
    with pytest.raises(ValueError):
        _image_content_block("")


# ----- end-to-end: Executor with images turns user message into block list ----


def test_initial_messages_with_images_returns_content_block_list(tmp_path):
    fake_skill = Skill(
        slug="t", name="T", description="d", category="testing",
        color="white", emoji="🧪", vibe="v", body="You are a tester.",
        path=tmp_path / "t.md", extra={},
    )
    fake_registry = MagicMock()
    fake_registry.all = lambda: [fake_skill]
    fake_llm = MagicMock()

    ex = Executor(fake_registry, fake_llm, profile=None, lessons=None)

    msgs = ex._initial_messages(
        session=None,
        user_message="what's in this picture?",
        images=["data:image/png;base64,XYZ", "https://example.com/a.jpg"],
    )
    assert len(msgs) == 1
    user = msgs[0]
    assert user["role"] == "user"
    assert isinstance(user["content"], list)
    # text + 2 image blocks
    assert len(user["content"]) == 3
    assert user["content"][0] == {"type": "text", "text": "what's in this picture?"}
    assert user["content"][1]["type"] == "image"
    assert user["content"][1]["source"]["type"] == "base64"
    assert user["content"][2]["source"]["type"] == "url"


def test_initial_messages_without_images_uses_string_content(tmp_path):
    fake_skill = Skill(
        slug="t", name="T", description="d", category="testing",
        color="white", emoji="🧪", vibe="v", body="You are a tester.",
        path=tmp_path / "t.md", extra={},
    )
    fake_registry = MagicMock()
    fake_registry.all = lambda: [fake_skill]
    fake_llm = MagicMock()
    ex = Executor(fake_registry, fake_llm, profile=None, lessons=None)
    msgs = ex._initial_messages(session=None, user_message="hi")
    assert msgs[0]["content"] == "hi"  # string, not a list — back-compat


def test_initial_messages_empty_images_list_uses_string(tmp_path):
    """An empty images list should also fall back to plain string content."""
    fake_skill = Skill(
        slug="t", name="T", description="d", category="testing",
        color="white", emoji="🧪", vibe="v", body="You are a tester.",
        path=tmp_path / "t.md", extra={},
    )
    fake_registry = MagicMock()
    fake_registry.all = lambda: [fake_skill]
    fake_llm = MagicMock()
    ex = Executor(fake_registry, fake_llm, profile=None, lessons=None)
    msgs = ex._initial_messages(session=None, user_message="hi", images=[])
    assert msgs[0]["content"] == "hi"
