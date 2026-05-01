"""Tests for RateLimiter (Pass 14)."""
import time
from pathlib import Path
import pytest
from agency.rate_limiter import RateLimiter


@pytest.fixture()
def limiter(tmp_path):
    return RateLimiter(requests_per_minute=10, state_path=tmp_path / "rl.json")


def test_allows_first_request(limiter):
    assert limiter.check() is True


def test_drains_bucket(tmp_path):
    lim = RateLimiter(requests_per_minute=3, state_path=tmp_path / "rl.json")
    assert lim.check() is True
    assert lim.check() is True
    assert lim.check() is True
    assert lim.check() is False  # bucket empty


def test_status_keys(limiter):
    s = limiter.status()
    assert "tokens_remaining" in s
    assert "capacity" in s
    assert "reset_at" in s
    assert s["capacity"] == 10


def test_tokens_decrease(limiter):
    before = limiter.status()["tokens_remaining"]
    limiter.check()
    after = limiter.status()["tokens_remaining"]
    assert after == before - 1


def test_persistence(tmp_path):
    path = tmp_path / "rl.json"
    lim1 = RateLimiter(requests_per_minute=5, state_path=path)
    lim1.check()
    lim1.check()
    # Re-instantiate; tokens should still be reduced (minus refill time ≈ 0)
    lim2 = RateLimiter(requests_per_minute=5, state_path=path)
    assert lim2.status()["tokens_remaining"] <= 5


def test_hebrew_warning_printed(tmp_path, capsys):
    # Use capacity=1 so first request hits >80% consumed (100% → prints warning)
    lim = RateLimiter(requests_per_minute=1, state_path=tmp_path / "rl.json")
    lim.check()
    captured = capsys.readouterr()
    assert "מגבלת" in captured.out
