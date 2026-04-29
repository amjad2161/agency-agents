#!/usr/bin/env python3
"""
JARVIS Cloud-Local Sync Daemon
==============================
Keeps a local JARVIS instance and a cloud JARVIS instance in sync as one unit.

Syncs:
  - Character profile (full text replacement)
  - Lessons ledger (append-only merge — new entries propagated both ways)
  - Trust mode (mode string)

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


# ── Per-endpoint sync ───────────────────────────────────────────────────────

def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def sync_lessons(src: str, dst: str) -> bool:
    """Append to dst any lesson lines present in src but not in dst."""
    try:
        src_text = (_get(src, "/api/lessons").get("text") or "").strip()
        dst_text = (_get(dst, "/api/lessons").get("text") or "").strip()

        src_lines = {l.strip() for l in src_text.splitlines() if l.strip() and not l.startswith("#")}
        dst_lines = {l.strip() for l in dst_text.splitlines() if l.strip() and not l.startswith("#")}
        new_lines = src_lines - dst_lines

        for line in sorted(new_lines):
            _post(dst, "/api/lessons", {"text": line})

        if new_lines:
            _log(f"  lessons: pushed {len(new_lines)} new line(s) → {dst}")
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
    """Copy full profile text from src to dst (full replacement)."""
    try:
        text = _get(src, "/api/profile").get("text", "")
        if text:
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
               'both'  = bidirectional merge
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

    # Lessons: always merge both ways to preserve all knowledge
    _run(sync_lessons, LOCAL_URL, CLOUD_URL)
    if direction in ("pull", "both"):
        _run(sync_lessons, CLOUD_URL, LOCAL_URL)

    # Trust: local is authoritative on push, cloud on pull
    if direction in ("push", "both"):
        _run(sync_trust, LOCAL_URL, CLOUD_URL)
    if direction == "pull":
        _run(sync_trust, CLOUD_URL, LOCAL_URL)

    # Profile: local is authoritative on push, cloud on pull
    if direction in ("push", "both"):
        _run(sync_profile, LOCAL_URL, CLOUD_URL)
    if direction == "pull":
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
