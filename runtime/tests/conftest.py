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
    these defaults -- pytest applies the inner setenv after autouse
    fixture finalization order, so this is safe.
    """
    if "AGENCY_PROFILE" not in os.environ:
        d = tmp_path_factory.mktemp("agency_profile_iso")
        monkeypatch.setenv("AGENCY_PROFILE", str(d / "absent.md"))
    if "AGENCY_LESSONS" not in os.environ:
        d = tmp_path_factory.mktemp("agency_lessons_iso")
        monkeypatch.setenv("AGENCY_LESSONS", str(d / "absent.md"))
    # Force trust mode to OFF by pointing trust.conf at an absent file
    # and clearing AGENCY_TRUST_MODE / AGENCY_ALLOW_SHELL.
    # Use direct os.environ.pop (not monkeypatch) so that tests which
    # call os.environ directly -- bypassing monkeypatch -- cannot leak
    # state into subsequent tests.  We pop BEFORE yield (clean slate
    # entering the test) and AFTER yield (clean slate leaving the test).
    if "AGENCY_TRUST_CONF" not in os.environ:
        d = tmp_path_factory.mktemp("agency_trust_iso")
        monkeypatch.setenv("AGENCY_TRUST_CONF", str(d / "absent.conf"))
    _trust_vars = ("AGENCY_TRUST_MODE", "AGENCY_ALLOW_SHELL")
    _saved = {k: os.environ.pop(k, None) for k in _trust_vars}
    yield
    # Post-test: discard anything the test wrote directly to os.environ,
    # then restore whatever was present before this fixture ran.
    for k in _trust_vars:
        os.environ.pop(k, None)
        if _saved[k] is not None:
            os.environ[k] = _saved[k]
