"""Tests for agency.network_monitor — NetworkMonitor.

All tests use monkeypatching to avoid real network calls.
"""

from __future__ import annotations

import socket
from unittest.mock import MagicMock, patch

import pytest

from agency.network_monitor import NetworkMonitor


class TestPing:
    def test_ping_reachable_returns_true(self):
        monitor = NetworkMonitor(targets=["8.8.8.8"])
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        with patch("socket.create_connection", return_value=mock_conn):
            result = monitor.ping("8.8.8.8")
        assert result["reachable"] is True
        assert result["host"] == "8.8.8.8"
        assert isinstance(result["latency_ms"], float)

    def test_ping_unreachable_returns_false(self):
        monitor = NetworkMonitor()
        with patch("socket.create_connection", side_effect=OSError("connection refused")):
            result = monitor.ping("192.0.2.0")  # TEST-NET, should never be reachable
        assert result["reachable"] is False
        assert result["latency_ms"] is None

    def test_ping_result_has_all_keys(self):
        monitor = NetworkMonitor()
        with patch("socket.create_connection", side_effect=OSError):
            result = monitor.ping("1.1.1.1")
        for key in ("host", "reachable", "latency_ms"):
            assert key in result


class TestCheckHTTP:
    def _mock_response(self, status_code: int = 200):
        mock_resp = MagicMock()
        mock_resp.status = status_code
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp

    def test_check_http_ok(self):
        monitor = NetworkMonitor()
        with patch("urllib.request.urlopen", return_value=self._mock_response(200)):
            result = monitor.check_http("https://example.com")
        assert result["ok"] is True
        assert result["status_code"] == 200
        assert isinstance(result["latency_ms"], float)

    def test_check_http_server_error(self):
        import urllib.error
        monitor = NetworkMonitor()
        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.HTTPError(
                "https://example.com", 500, "Internal Server Error", {}, None
            ),
        ):
            result = monitor.check_http("https://example.com")
        assert result["ok"] is False
        assert result["status_code"] == 500

    def test_check_http_network_error(self):
        monitor = NetworkMonitor()
        with patch("urllib.request.urlopen", side_effect=OSError("no route to host")):
            result = monitor.check_http("https://unreachable.example.invalid")
        assert result["ok"] is False
        assert result["status_code"] is None

    def test_check_http_result_has_all_keys(self):
        monitor = NetworkMonitor()
        with patch("urllib.request.urlopen", side_effect=OSError):
            result = monitor.check_http("https://x.example.invalid")
        for key in ("url", "status_code", "latency_ms", "ok"):
            assert key in result


class TestFullReport:
    def test_full_report_keys(self):
        monitor = NetworkMonitor(targets=["8.8.8.8"])
        with patch("socket.create_connection", side_effect=OSError):
            report = monitor.full_report()
        for key in ("online", "targets", "ts"):
            assert key in report

    def test_full_report_online_false_when_all_fail(self):
        monitor = NetworkMonitor(targets=["192.0.2.1", "192.0.2.2"])
        with patch("socket.create_connection", side_effect=OSError):
            report = monitor.full_report()
        assert report["online"] is False

    def test_full_report_online_true_when_one_succeeds(self):
        monitor = NetworkMonitor(targets=["8.8.8.8"])
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        with patch("socket.create_connection", return_value=mock_conn):
            report = monitor.full_report()
        assert report["online"] is True

    def test_full_report_ts_is_string(self):
        monitor = NetworkMonitor(targets=[])
        report = monitor.full_report()
        assert isinstance(report["ts"], str)


class TestIsOnline:
    def test_is_online_true(self):
        monitor = NetworkMonitor()
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        with patch("socket.create_connection", return_value=mock_conn):
            assert monitor.is_online() is True

    def test_is_online_false_on_error(self):
        monitor = NetworkMonitor()
        with patch("socket.create_connection", side_effect=OSError):
            assert monitor.is_online() is False
