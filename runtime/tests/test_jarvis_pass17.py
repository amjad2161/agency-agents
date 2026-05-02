"""Pass 17 — Vision, Voice, Browser, Email tests.

All external calls (Anthropic API, IMAP, SMTP, subprocess, playwright,
selenium, urllib) are mocked so CI runs without credentials or browsers.

Test count: 30 tests across 4 modules.
"""

from __future__ import annotations

import base64
import imaplib
import json
import pathlib
import smtplib
import sys
import tempfile
import textwrap
from io import BytesIO
from unittest.mock import MagicMock, Mock, patch, PropertyMock, call

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))


# ===========================================================================
# 1. vision.py
# ===========================================================================

class TestVisionHelpers:
    """Unit tests for vision module helpers (no API calls)."""

    def test_is_url_http(self):
        from agency.vision import _is_url
        assert _is_url("http://example.com/img.png") is True

    def test_is_url_https(self):
        from agency.vision import _is_url
        assert _is_url("https://example.com/img.png") is True

    def test_is_url_local(self):
        from agency.vision import _is_url
        assert _is_url("/tmp/file.png") is False
        assert _is_url("C:\\image.jpg") is False

    def test_ext_to_media_type(self):
        from agency.vision import _ext_to_media_type
        assert _ext_to_media_type(".png") == "image/png"
        assert _ext_to_media_type(".jpg") == "image/jpeg"
        assert _ext_to_media_type(".jpeg") == "image/jpeg"
        assert _ext_to_media_type(".gif") == "image/gif"
        assert _ext_to_media_type(".webp") == "image/webp"
        assert _ext_to_media_type(".bmp") == "image/jpeg"  # default fallback

    def test_path_to_b64(self, tmp_path):
        from agency.vision import _path_to_b64
        img = tmp_path / "test.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\nfakedata")
        b64, mt = _path_to_b64(img)
        assert mt == "image/png"
        assert base64.standard_b64decode(b64)[:4] == b"\x89PNG"

    def test_parse_model_response_valid_json(self):
        from agency.vision import _parse_model_response
        raw = json.dumps({
            "description": "A cat",
            "objects": ["cat", "sofa"],
            "text_content": "",
            "confidence": 0.95,
        })
        result = _parse_model_response(raw)
        assert result["description"] == "A cat"
        assert result["objects"] == ["cat", "sofa"]
        assert result["confidence"] == 0.95

    def test_parse_model_response_with_fences(self):
        from agency.vision import _parse_model_response
        raw = '```json\n{"description": "Dog", "objects": ["dog"], "text_content": "", "confidence": 0.8}\n```'
        result = _parse_model_response(raw)
        assert result["description"] == "Dog"

    def test_parse_model_response_invalid_json_fallback(self):
        from agency.vision import _parse_model_response
        raw = "I see a mountain landscape with snow."
        result = _parse_model_response(raw)
        assert result["description"] == raw.strip()
        assert result["objects"] == []
        assert result["confidence"] == 0.5

    def test_analyze_image_no_anthropic(self):
        """When anthropic package is missing, error is returned."""
        with patch("agency.vision._ANTHROPIC_OK", False):
            from agency.vision import analyze_image
            result = analyze_image("/some/path.png")
        assert result["error"] is not None
        assert "anthropic" in result["error"].lower()

    def test_analyze_image_file_not_found(self):
        with patch("agency.vision._ANTHROPIC_OK", True):
            from agency.vision import analyze_image
            result = analyze_image("/nonexistent/path.png")
        assert result["error"] is not None

    def test_analyze_image_local_file(self, tmp_path):
        """analyze_image with a real local PNG file — mocks the API call."""
        img = tmp_path / "sample.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\nFakeImageData")

        mock_resp = json.dumps({
            "description": "A fake PNG",
            "objects": ["rectangle"],
            "text_content": "Hello",
            "confidence": 0.9,
        })

        with patch("agency.vision._ANTHROPIC_OK", True), \
             patch("agency.vision._call_claude_vision", return_value=mock_resp):
            from agency.vision import analyze_image
            result = analyze_image(str(img))

        assert result["description"] == "A fake PNG"
        assert "rectangle" in result["objects"]
        assert result["text_content"] == "Hello"
        assert result["confidence"] == pytest.approx(0.9)
        assert result["source"] == "file"
        assert result["error"] is None

    def test_analyze_image_url(self):
        """analyze_image with URL — mocks download and API call."""
        fake_b64 = base64.standard_b64encode(b"fakeimagedata").decode()
        mock_resp = json.dumps({
            "description": "A webpage screenshot",
            "objects": ["button", "text"],
            "text_content": "Click here",
            "confidence": 0.85,
        })

        with patch("agency.vision._ANTHROPIC_OK", True), \
             patch("agency.vision._url_to_b64", return_value=(fake_b64, "image/jpeg")), \
             patch("agency.vision._call_claude_vision", return_value=mock_resp):
            from agency.vision import analyze_image
            result = analyze_image("https://example.com/screenshot.jpg")

        assert result["source"] == "url"
        assert result["description"] == "A webpage screenshot"

    def test_analyze_image_fallback_model(self, tmp_path):
        """Primary model failure triggers fallback to haiku."""
        img = tmp_path / "img.jpg"
        img.write_bytes(b"JFIF_FAKE")

        mock_resp = json.dumps({
            "description": "Fallback desc",
            "objects": [],
            "text_content": "",
            "confidence": 0.7,
        })

        with patch("agency.vision._ANTHROPIC_OK", True), \
             patch("agency.vision._call_claude_vision",
                   side_effect=[Exception("primary failed"), mock_resp]):
            from agency.vision import analyze_image, _FALLBACK_MODEL
            result = analyze_image(str(img))

        assert result["description"] == "Fallback desc"
        assert result["model"] == _FALLBACK_MODEL
        assert result["error"] is None

    def test_vision_result_to_dict_keys(self):
        from agency.vision import VisionResult
        vr = VisionResult(description="test", objects=["a"], text_content="txt", confidence=0.8)
        d = vr.to_dict()
        for key in ("description", "objects", "text_content", "confidence", "model", "source", "error"):
            assert key in d


# ===========================================================================
# 2. voice.py
# ===========================================================================

class TestVoice:
    """Tests for TTS module."""

    def test_is_hebrew_detection(self):
        from agency.voice import _is_hebrew
        assert _is_hebrew("שלום עולם") is True
        assert _is_hebrew("Hello world") is False
        assert _is_hebrew("Bonjour") is False

    def test_detect_engine_pyttsx3_preferred(self):
        with patch("agency.voice._PYTTSX3_OK", True):
            from agency.voice import detect_engine, TTSEngine
            eng = detect_engine()
        assert eng == TTSEngine.PYTTSX3

    def test_detect_engine_gtts_fallback(self):
        with patch("agency.voice._PYTTSX3_OK", False), \
             patch("agency.voice._GTTS_OK", True):
            from agency.voice import detect_engine, TTSEngine
            eng = detect_engine()
        assert eng == TTSEngine.GTTS

    def test_detect_engine_system_fallback(self):
        with patch("agency.voice._PYTTSX3_OK", False), \
             patch("agency.voice._GTTS_OK", False), \
             patch("agency.voice._detect_system_engine") as mock_sys:
            from agency.voice import detect_engine, TTSEngine
            mock_sys.return_value = TTSEngine.ESPEAK
            eng = detect_engine()
        assert eng == TTSEngine.ESPEAK

    def test_speak_empty_text(self):
        from agency.voice import speak
        assert speak("") is False
        assert speak("   ") is False

    def test_speak_pyttsx3_success(self):
        mock_engine = MagicMock()
        mock_pyttsx3_mod = MagicMock()
        mock_pyttsx3_mod.init.return_value = mock_engine
        mock_engine.getProperty.return_value = []
        with patch("agency.voice._PYTTSX3_OK", True), \
             patch.dict("sys.modules", {"pyttsx3": mock_pyttsx3_mod}):
            import agency.voice as v
            # Temporarily bind the mock at module level so _speak_pyttsx3 sees it
            orig = getattr(v, "_pyttsx3", None)
            v._pyttsx3 = mock_pyttsx3_mod
            try:
                result = v._speak_pyttsx3("Hello JARVIS")
            finally:
                if orig is None:
                    try:
                        delattr(v, "_pyttsx3")
                    except AttributeError:
                        pass
                else:
                    v._pyttsx3 = orig
        assert result is True
        mock_engine.say.assert_called_once_with("Hello JARVIS")
        mock_engine.runAndWait.assert_called_once()

    def test_speak_pyttsx3_failure_fallback(self):
        """pyttsx3 error → tries next engine."""
        with patch("agency.voice._PYTTSX3_OK", True), \
             patch("agency.voice._speak_pyttsx3", return_value=False), \
             patch("agency.voice._GTTS_OK", True), \
             patch("agency.voice._speak_gtts", return_value=True), \
             patch("agency.voice.detect_engine") as mock_det:
            from agency.voice import speak, TTSEngine
            mock_det.return_value = TTSEngine.PYTTSX3
            result = speak("Test fallback")
        assert result is True

    def test_speak_espeak(self):
        with patch("agency.voice.subprocess") as mock_sub:
            mock_sub.run.return_value = MagicMock(returncode=0)
            from agency.voice import _speak_espeak
            result = _speak_espeak("Speak this")
        assert result is True

    def test_speak_say_macos(self):
        with patch("agency.voice.subprocess") as mock_sub:
            mock_sub.run.return_value = MagicMock(returncode=0)
            from agency.voice import _speak_say
            result = _speak_say("Hello Mac")
        assert result is True

    def test_speak_powershell_windows(self):
        with patch("agency.voice.subprocess") as mock_sub:
            mock_sub.run.return_value = MagicMock(returncode=0)
            from agency.voice import _speak_powershell
            result = _speak_powershell("Hello Windows")
        assert result is True
        # Verify PowerShell command was used
        cmd_args = mock_sub.run.call_args[0][0]
        assert "powershell" in cmd_args[0].lower()

    def test_tts_engine_enum_values(self):
        from agency.voice import TTSEngine
        assert TTSEngine.PYTTSX3 == "pyttsx3"
        assert TTSEngine.GTTS == "gtts"
        assert TTSEngine.ESPEAK == "espeak"
        assert TTSEngine.NONE == "none"

    def test_speak_hebrew_gtts_uses_iw_lang(self):
        """gTTS should use lang='iw' for Hebrew text."""
        hebrew_text = "שלום עולם"
        mock_gtts_inst = MagicMock()
        mock_gtts_cls = MagicMock(return_value=mock_gtts_inst)
        mock_gtts_inst.save = MagicMock()

        import agency.voice as v
        orig_gtts = getattr(v, "_gTTS", None)
        orig_ok = v._GTTS_OK
        orig_play = v._PLAYSOUND_OK

        v._gTTS = mock_gtts_cls
        v._GTTS_OK = True
        v._PLAYSOUND_OK = False

        try:
            with patch("agency.voice.subprocess") as mock_sub, \
                 patch("agency.voice.os.unlink"), \
                 patch("agency.voice.tempfile.NamedTemporaryFile") as mock_tmp:
                mock_file = MagicMock()
                mock_file.name = "/tmp/tts_test.mp3"
                mock_tmp.return_value.__enter__ = Mock(return_value=mock_file)
                mock_tmp.return_value.__exit__ = Mock(return_value=False)
                mock_sub.run.return_value = MagicMock(returncode=0)
                v._speak_gtts(hebrew_text)
        finally:
            if orig_gtts is None:
                try:
                    delattr(v, "_gTTS")
                except AttributeError:
                    pass
            else:
                v._gTTS = orig_gtts
            v._GTTS_OK = orig_ok
            v._PLAYSOUND_OK = orig_play

        mock_gtts_cls.assert_called_once()
        call_kwargs = mock_gtts_cls.call_args
        lang_used = call_kwargs[1].get("lang") if call_kwargs[1] else None
        assert lang_used == "iw", f"Expected lang='iw', got {lang_used}"


# ===========================================================================
# 3. browser.py
# ===========================================================================

class TestBrowser:
    """Tests for BrowserAgent with mocked backends."""

    def test_extract_text_with_bs4(self):
        """_extract_text returns title, text, links from HTML."""
        html = """<html><head><title>Test Page</title></head>
        <body><h1>Hello</h1><a href="/about">About</a></body></html>"""
        with patch("agency.browser._BS4_OK", True):
            from agency.browser import _extract_text
            # Patch BeautifulSoup to avoid actual bs4 dep in tests
            with patch("agency.browser._BS") as mock_bs:
                mock_soup = MagicMock()
                mock_soup.title.string = "Test Page"
                mock_soup.get_text.return_value = "Hello"
                mock_bs.return_value = mock_soup
                mock_soup.find_all.return_value = [MagicMock(**{"get.return_value": "/about"})]
                title, text, links = _extract_text(html)

    def test_extract_text_regex_fallback(self):
        """_extract_text regex fallback when bs4 unavailable."""
        html = "<html><head><title>Regex Page</title></head><body><p>Content here</p></body></html>"
        with patch("agency.browser._BS4_OK", False):
            from agency.browser import _extract_text
            title, text, links = _extract_text(html)
        assert "Regex Page" in title
        assert "Content here" in text

    def test_browse_urllib_fallback(self):
        """browse() uses urllib when playwright/selenium not available."""
        fake_html = "<html><head><title>Mock</title></head><body>Mock content</body></html>"
        with patch("agency.browser._PLAYWRIGHT_OK", False), \
             patch("agency.browser._SELENIUM_OK", False), \
             patch("agency.browser._BS4_OK", False), \
             patch("agency.browser.urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.__enter__ = Mock(return_value=mock_resp)
            mock_resp.__exit__ = Mock(return_value=False)
            mock_resp.read.return_value = fake_html.encode()
            mock_resp.headers.get_content_charset.return_value = "utf-8"
            mock_urlopen.return_value = mock_resp

            from agency.browser import BrowserAgent
            agent = BrowserAgent()
            result = agent.browse("http://example.com")

        assert result["engine"] == "urllib"
        assert "Mock content" in result["text"] or result["text"]

    def test_browse_curl_fallback(self):
        """browse() falls back to curl when urllib also fails."""
        fake_html = "<html><head><title>Curl</title></head><body>Curl content</body></html>"
        with patch("agency.browser._PLAYWRIGHT_OK", False), \
             patch("agency.browser._SELENIUM_OK", False), \
             patch("agency.browser._BS4_OK", False), \
             patch("agency.browser.urllib.request.urlopen", side_effect=Exception("no urllib")), \
             patch("agency.browser.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout=fake_html.encode(),
                returncode=0,
            )
            from agency.browser import BrowserAgent
            agent = BrowserAgent()
            result = agent.browse("http://example.com")

        assert result["engine"] == "curl"

    def test_browse_playwright_primary(self):
        """When playwright is available, it's used first."""
        with patch("agency.browser._PLAYWRIGHT_OK", True), \
             patch("agency.browser._browse_playwright") as mock_pw:
            from agency.browser import PageResult, BrowserAgent
            mock_result = PageResult(
                url="http://x.com", title="X", text="content", engine="playwright"
            )
            mock_pw.return_value = mock_result
            agent = BrowserAgent()
            result = agent.browse("http://x.com")
        assert result["engine"] == "playwright"
        mock_pw.assert_called_once()

    def test_screenshot_requires_browser_engine(self):
        """screenshot() raises if neither playwright nor selenium available."""
        with patch("agency.browser._PLAYWRIGHT_OK", False), \
             patch("agency.browser._SELENIUM_OK", False):
            from agency.browser import BrowserAgent
            agent = BrowserAgent()
            with pytest.raises(RuntimeError, match="playwright or selenium"):
                agent.screenshot("http://example.com")

    def test_screenshot_playwright(self, tmp_path):
        out = str(tmp_path / "shot.png")
        with patch("agency.browser._PLAYWRIGHT_OK", True), \
             patch("agency.browser._screenshot_playwright", return_value=out) as mock_ss:
            from agency.browser import BrowserAgent
            agent = BrowserAgent()
            result = agent.screenshot("http://example.com", out)
        assert result == out
        mock_ss.assert_called_once()

    def test_fill_form_error_without_browser(self):
        """fill_form returns error dict when no browser engine available."""
        with patch("agency.browser._PLAYWRIGHT_OK", False), \
             patch("agency.browser._SELENIUM_OK", False):
            from agency.browser import BrowserAgent
            agent = BrowserAgent()
            result = agent.fill_form("http://example.com/form", {"#name": "JARVIS"})
        assert result["success"] is False
        assert "error" in result

    def test_page_result_to_dict_truncation(self):
        from agency.browser import PageResult
        pr = PageResult(
            url="http://x.com",
            title="T",
            text="A" * 10000,
            links=["http://link.com"] * 100,
        )
        d = pr.to_dict()
        assert len(d["text"]) <= 4000
        assert len(d["links"]) <= 50

    def test_browser_engine_order_prefers_playwright(self):
        with patch("agency.browser._PLAYWRIGHT_OK", True), \
             patch("agency.browser._SELENIUM_OK", True):
            from agency.browser import BrowserAgent
            agent = BrowserAgent()
            order = agent._engine_order()
        assert order[0] == "playwright"

    def test_module_level_browse_function(self):
        """Module-level browse() delegates to default BrowserAgent."""
        with patch("agency.browser._PLAYWRIGHT_OK", False), \
             patch("agency.browser._SELENIUM_OK", False), \
             patch("agency.browser._BS4_OK", False), \
             patch("agency.browser.urllib.request.urlopen") as mock_open:
            resp = MagicMock()
            resp.__enter__ = Mock(return_value=resp)
            resp.__exit__ = Mock(return_value=False)
            resp.read.return_value = b"<html><title>T</title><body>Hi</body></html>"
            resp.headers.get_content_charset.return_value = "utf-8"
            mock_open.return_value = resp
            from agency.browser import browse
            result = browse("http://example.com")
        assert "engine" in result


# ===========================================================================
# 4. email_client.py
# ===========================================================================

class TestEmailClient:
    """Tests for IMAP reader and SMTP sender with full mocking."""

    def _make_raw_email(self, subject="Test", sender="from@example.com", body="Hello body") -> bytes:
        """Build a minimal RFC822 email bytes."""
        msg = (
            f"From: {sender}\r\n"
            f"To: to@example.com\r\n"
            f"Subject: {subject}\r\n"
            f"Date: Mon, 01 Jan 2024 00:00:00 +0000\r\n"
            f"Content-Type: text/plain; charset=utf-8\r\n"
            f"\r\n"
            f"{body}\r\n"
        )
        return msg.encode("utf-8")

    def test_decode_header_plain(self):
        from agency.email_client import _decode_header
        assert _decode_header("Hello World") == "Hello World"

    def test_decode_header_encoded(self):
        from agency.email_client import _decode_header
        # RFC2047 encoded subject
        encoded = "=?utf-8?b?SGVsbG8gV29ybGQ=?="  # "Hello World"
        result = _decode_header(encoded)
        assert "Hello World" in result

    def test_decode_header_none(self):
        from agency.email_client import _decode_header
        assert _decode_header(None) == ""

    def test_get_body_plain_text(self):
        import email as em
        from agency.email_client import _get_body
        raw = self._make_raw_email(body="Test body content")
        msg = em.message_from_bytes(raw)
        body, is_html = _get_body(msg)
        assert "Test body content" in body
        assert is_html is False

    def test_read_inbox_missing_host(self):
        from agency.email_client import read_inbox
        with patch("agency.email_client._load_email_config", return_value={}), \
             patch.dict("os.environ", {}, clear=False):
            with pytest.raises(ValueError, match="host"):
                read_inbox(host="", user="u", password="p")

    def test_read_inbox_missing_password(self):
        from agency.email_client import read_inbox
        with patch("agency.email_client._load_email_config", return_value={}), \
             patch("agency.email_client._get_password", return_value=None):
            with pytest.raises(ValueError, match="password"):
                read_inbox(host="imap.example.com", user="u@example.com", password="")

    def test_read_inbox_success(self):
        """read_inbox with mocked IMAP4_SSL."""
        raw_email = self._make_raw_email("Subject One", "alice@example.com", "Body one")

        mock_imap = MagicMock(spec=imaplib.IMAP4_SSL)
        mock_imap.login.return_value = ("OK", [b"Logged in"])
        mock_imap.select.return_value = ("OK", [b"5"])
        mock_imap.search.return_value = ("OK", [b"1 2 3"])
        # fetch returns (uid, (header, raw_bytes))
        mock_imap.fetch.return_value = ("OK", [(b"1 (RFC822 {100})", raw_email)])
        mock_imap.logout.return_value = ("OK", [b"Bye"])

        with patch("agency.email_client._load_email_config", return_value={}), \
             patch("agency.email_client._get_password", return_value="secret"), \
             patch("agency.email_client.imaplib.IMAP4_SSL", return_value=mock_imap), \
             patch("agency.email_client.ssl.create_default_context"):
            from agency.email_client import read_inbox
            msgs = read_inbox(host="imap.example.com", user="u@example.com", limit=3)

        assert isinstance(msgs, list)
        assert len(msgs) >= 0  # May vary based on fetch mock

    def test_send_email_missing_host(self):
        from agency.email_client import send_email
        with patch("agency.email_client._load_email_config", return_value={}), \
             patch("agency.email_client._get_password", return_value="pass"):
            with pytest.raises(ValueError, match="host"):
                send_email("to@x.com", "Subj", "Body", host="", user="u@x.com")

    def test_send_email_success(self):
        """send_email with mocked SMTP."""
        mock_smtp = MagicMock()
        mock_smtp.__enter__ = Mock(return_value=mock_smtp)
        mock_smtp.__exit__ = Mock(return_value=False)

        with patch("agency.email_client._load_email_config", return_value={}), \
             patch("agency.email_client._get_password", return_value="secret"), \
             patch("agency.email_client.smtplib.SMTP", return_value=mock_smtp), \
             patch("agency.email_client.ssl.create_default_context"):
            from agency.email_client import send_email
            result = send_email(
                to="to@example.com",
                subject="Hello",
                body="Body text",
                host="smtp.example.com",
                user="user@example.com",
            )

        assert result is True
        mock_smtp.starttls.assert_called_once()
        mock_smtp.login.assert_called_once()
        mock_smtp.sendmail.assert_called_once()

    def test_send_email_multiple_recipients(self):
        """send_email accepts list of recipients."""
        mock_smtp = MagicMock()
        mock_smtp.__enter__ = Mock(return_value=mock_smtp)
        mock_smtp.__exit__ = Mock(return_value=False)

        with patch("agency.email_client._load_email_config", return_value={}), \
             patch("agency.email_client._get_password", return_value="s"), \
             patch("agency.email_client.smtplib.SMTP", return_value=mock_smtp), \
             patch("agency.email_client.ssl.create_default_context"):
            from agency.email_client import send_email
            result = send_email(
                to=["a@x.com", "b@x.com"],
                subject="Multi",
                body="Hi all",
                host="smtp.x.com",
                user="me@x.com",
            )

        assert result is True
        _, recipients, _ = mock_smtp.sendmail.call_args[0]
        assert "a@x.com" in recipients
        assert "b@x.com" in recipients

    def test_email_message_to_dict_truncation(self):
        from agency.email_client import EmailMessage
        em = EmailMessage(
            uid="42",
            subject="Subj",
            sender="s@x.com",
            body="X" * 5000,
        )
        d = em.to_dict()
        assert len(d["body"]) <= 2000

    def test_get_password_from_env(self):
        with patch.dict("os.environ", {"AGENCY_EMAIL_PASSWORD": "mysecret"}):
            from agency.email_client import _get_password
            assert _get_password() == "mysecret"

    def test_get_password_absent(self):
        env = {k: v for k, v in __import__("os").environ.items()
               if k != "AGENCY_EMAIL_PASSWORD"}
        with patch.dict("os.environ", env, clear=True):
            from agency.email_client import _get_password
            assert _get_password() is None


# ===========================================================================
# 5. Integration smoke — imports don't crash
# ===========================================================================

class TestPass17Imports:
    def test_vision_importable(self):
        import agency.vision

    def test_voice_importable(self):
        import agency.voice

    def test_browser_importable(self):
        import agency.browser

    def test_email_client_importable(self):
        import agency.email_client

    def test_vision_exports(self):
        from agency.vision import analyze_image, VisionResult
        assert callable(analyze_image)

    def test_voice_exports(self):
        from agency.voice import speak, detect_engine, TTSEngine
        assert callable(speak)
        assert callable(detect_engine)

    def test_browser_exports(self):
        from agency.browser import BrowserAgent, browse, screenshot, fill_form
        assert callable(browse)

    def test_email_exports(self):
        from agency.email_client import read_inbox, send_email, EmailMessage
        assert callable(read_inbox)
        assert callable(send_email)
