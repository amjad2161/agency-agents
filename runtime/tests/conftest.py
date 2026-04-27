"""Test isolation fixtures.

Default-isolate the test suite from the developer's real `~/.agency/`
profile and lessons files. Without this, executor/profile tests pick
up whatever the developer wrote in their profile and assert against
unstable content.
"""

from __future__ import annotations

import os
import pytest


@pytest.fixture(autouse=True)
def _isolate_user_state(tmp_path_factory, monkeypatch):
    """Point AGENCY_PROFILE / AGENCY_LESSONS at empty tmp paths unless
    a test explicitly sets them.

    Tests that set these themselves via monkeypatch.setenv override
    these defaults — pytest applies the inner setenv after autouse
    fixture finalization order, so this is safe.
    """
    if "AGENCY_PROFILE" not in os.environ:
        d = tmp_path_factory.mktemp("agency_profile_iso")
        monkeypatch.setenv("AGENCY_PROFILE", str(d / "absent.md"))
    if "AGENCY_LESSONS" not in os.environ:
        d = tmp_path_factory.mktemp("agency_lessons_iso")
        monkeypatch.setenv("AGENCY_LESSONS", str(d / "absent.md"))
    # Force trust mode to OFF default by pointing trust.conf at an
    # absent file and clearing AGENCY_TRUST_MODE. Tests that need a
    # different mode set them explicitly via their own monkeypatch.
    if "AGENCY_TRUST_CONF" not in os.environ:
        d = tmp_path_factory.mktemp("agency_trust_iso")
        monkeypatch.setenv("AGENCY_TRUST_CONF", str(d / "absent.conf"))
    if "AGENCY_TRUST_MODE" not in os.environ:
        monkeypatch.delenv("AGENCY_TRUST_MODE", raising=False)
    yield
