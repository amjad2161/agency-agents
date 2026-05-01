#!/usr/bin/env python3
"""
JARVIS Cloud-Local Sync Daemon
==============================
Keeps a local JARVIS instance and a cloud JARVIS instance in sync as one unit.

Syncs:
  - Lessons ledger (bidirectional append-only merge — new entries propagated both ways)
  - Trust mode (local is authoritative in push/both; cloud in pull)
  - User profile (local is authoritative in push/both; cloud in pull)

Direction semantics:
  push  — local → cloud (trust/profile/new lessons)
  pull  — cloud → local (trust/profile/new lessons)
  both  — lessons merged bidirectionally; local is authoritative for trust & profile

Run standalone:
  python scripts/cloud_sync.py --once
  python scripts/cloud_sync.py --daemon          # loop every JARVIS_SYNC_INTERVAL seconds
  python scripts/cloud_sync.py --push-to-cloud   # one-shot local → cloud
  python scripts/cloud_sync.py --pull-from-cloud # one-shot cloud → local
  python scripts/cloud_sync.py --status          # health check both sides
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone


LOCAL_URL = os.getenv("JARVIS_LOCAL_URL", "http://localhost:8765")
CLOUD_URL = os.getenv("JARVIS_CLOUD_URL", "")
SYNC_INTERVAL = int(os.getenv("JARVIS_SYNC_INTERVAL", "30"))
SYNC_SECRET = os.getenv("JARVIS_SYNC_SECRET", "")


# ── HTTP helpers ────────────────────────────────────────────────────────────

def _get(base: str, path: str, timeout: int = 10) -> dict:
    url = base.rstrip("/") + path
    req = urllib.request.Request(url)
    if SYNC_SECRET:
        # Forwarded for reverse-proxy enforcement (e.g. nginx/Caddy header checks).
        # The JARVIS API endpoints don't validate this header internally.
        req.add_header("X-Sync-Secret", SYNC_SECRET)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _post(base: str, path: str, body: dict, timeout: int = 10) -> dict:
    url = base.rstrip("/") + path
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    if SYNC_SECRET:
        req.add_header("X-Sync-Secret", SYNC_SECRET)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _health(base: str) -> bool:
    try:
        data = _get(base, "/api/health", timeout=5)
        return data.get("status") == "ok"
    except Exception:
        return False


# ── Lesson entry parsing ────────────────────────────────────────────────────

def _normalize_entry(entry: str) -> str:
    return "\n".join(line.rstrip() for line in entry.strip().splitlines()).strip()


def _entry_body(entry: str) -> str:
    """Return the lesson body with only the leading ## timestamp header stripped.

    Preserves any subsequent ## headings that are part of the lesson content.
    Used as the deduplication key so that re-syncing after a fresh server
    timestamp doesn't cause duplicate lesson posts.
    """
    lines = entry.splitlines()
    if lines and lines[0].strip().startswith("## "):
        lines = lines[1:]
    return _normalize_entry("\n".join(lines))


def _parse_lesson_entries(text: str) -> list[str]:
    """Split a lessons file into discrete entries delimited by '## <timestamp>' headers."""
    entries: list[str] = []
    current: list[str] = []

    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("## "):
            if current:
                entry = _normalize_entry("\n".join(current))
                if entry:
                    entries.append(entry)
            current = [stripped]
        else:
            if current:
                current.append(raw_line.rstrip())
            elif stripped:
                current = [raw_line.rstrip()]

    if current:
        entry = _normalize_entry("\n".join(current))
        if entry:
            entries.append(entry)

    return entries


# ── Per-endpoint sync ───────────────────────────────────────────────────────

def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def sync_lessons(src: str, dst: str) -> bool:
    """Append to dst any lesson entries present in src but not in dst."""
    try:
        src_text = _get(src, "/api/lessons").get("text") or ""
        dst_text = _get(dst, "/api/lessons").get("text") or ""

        src_entries = _parse_lesson_entries(src_text)
        # Dedupe by body only (sans timestamp header) so that a fresh timestamp
        # written by the server on POST doesn't make the same lesson re-post on
        # every sync cycle.
        dst_body_set = {_entry_body(e) for e in _parse_lesson_entries(dst_text)}

        pushed = 0
        for entry in src_entries:
            body = _entry_body(entry)
            if body and body not in dst_body_set:
                _post(dst, "/api/lessons", {"text": body})
                dst_body_set.add(body)
                pushed += 1

        if pushed:
            _log(f"  lessons: pushed {pushed} new entr{'y' if pushed == 1 else 'ies'} → {dst}")
        return True
    except Exception as e:
        _log(f"  lessons sync error: {e}")
        return False


def sync_trust(src: str, dst: str) -> bool:
    """Copy trust mode from src to dst."""
    try:
        mode = _get(src, "/api/trust").get("mode", "")
        if mode:
            _post(dst, "/api/trust", {"mode": mode})
        return True
    except Exception as e:
        _log(f"  trust sync error: {e}")
        return False


def sync_profile(src: str, dst: str) -> bool:
    """Copy full profile text from src to dst (full replacement).

    Always POSTs, even when text is empty — the server treats empty text
    as a delete, which correctly propagates profile deletions.
    """
    try:
        text = _get(src, "/api/profile").get("text", "")
        _post(dst, "/api/profile", {"text": text})
        return True
    except Exception as e:
        _log(f"  profile sync error: {e}")
        return False


# ── Orchestration ───────────────────────────────────────────────────────────

def run_sync(direction: str = "both") -> dict:
    """
    direction: 'push'  = local → cloud
               'pull'  = cloud → local
               'both'  = lessons merged bidirectionally;
                         local is authoritative for trust & profile
    """
    results = {"ok": 0, "fail": 0, "skipped": 0}

    if not CLOUD_URL:
        _log("JARVIS_CLOUD_URL not set — skipping cloud sync")
        results["skipped"] = 3
        return results

    local_up = _health(LOCAL_URL)
    cloud_up = _health(CLOUD_URL)

    if not local_up:
        _log(f"Local JARVIS at {LOCAL_URL} is DOWN — skipping sync")
        return results
    if not cloud_up:
        _log(f"Cloud JARVIS at {CLOUD_URL} is DOWN — skipping sync")
        return results

    _log(f"Sync started ({direction}) local={LOCAL_URL} cloud={CLOUD_URL}")

    def _run(fn, *args):
        ok = fn(*args)
        results["ok" if ok else "fail"] += 1

    # Lessons: merge in the requested direction(s)
    if direction in ("push", "both"):
        _run(sync_lessons, LOCAL_URL, CLOUD_URL)
    if direction in ("pull", "both"):
        _run(sync_lessons, CLOUD_URL, LOCAL_URL)

    # Trust: directional — local authoritative on push/both, cloud on pull
    if direction in ("push", "both"):
        _run(sync_trust, LOCAL_URL, CLOUD_URL)
    elif direction == "pull":
        _run(sync_trust, CLOUD_URL, LOCAL_URL)

    # Profile: directional — local authoritative on push/both, cloud on pull
    if direction in ("push", "both"):
        _run(sync_profile, LOCAL_URL, CLOUD_URL)
    elif direction == "pull":
        _run(sync_profile, CLOUD_URL, LOCAL_URL)

    _log(f"Sync done — ok={results['ok']} fail={results['fail']}")
    return results


# ── CLI ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="JARVIS cloud-local sync")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--daemon", action="store_true", help="Run forever, syncing every JARVIS_SYNC_INTERVAL seconds")
    mode.add_argument("--once", action="store_true", help="Sync once and exit")
    mode.add_argument("--push-to-cloud", action="store_true", help="Push local state to cloud")
    mode.add_argument("--pull-from-cloud", action="store_true", help="Pull cloud state to local")
    mode.add_argument("--status", action="store_true", help="Show health of both instances")
    args = parser.parse_args()

    if args.status:
        local_ok = _health(LOCAL_URL)
        cloud_ok = _health(CLOUD_URL) if CLOUD_URL else None
        print(f"Local  ({LOCAL_URL}): {'✅ UP' if local_ok else '❌ DOWN'}")
        if cloud_ok is None:
            print("Cloud: JARVIS_CLOUD_URL not configured")
        else:
            print(f"Cloud  ({CLOUD_URL}): {'✅ UP' if cloud_ok else '❌ DOWN'}")
        sys.exit(0 if local_ok else 1)

    if args.push_to_cloud:
        run_sync("push")
    elif args.pull_from_cloud:
        run_sync("pull")
    elif args.daemon:
        _log(f"Sync daemon started — interval={SYNC_INTERVAL}s")
        while True:
            try:
                run_sync("both")
            except Exception as e:
                _log(f"Unhandled sync error: {e}")
            time.sleep(SYNC_INTERVAL)
    else:
        # --once or no flag
        run_sync("both")


if __name__ == "__main__":
    main()
