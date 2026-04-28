#!/usr/bin/env python3
"""
JARVIS Cloud-Local Sync Daemon
==============================
Keeps a local JARVIS instance and a cloud JARVIS instance in sync as one unit.

Syncs:
  - Character state (persona, mood, mode)
  - Lessons ledger (learned behaviours)
  - Trust scores
  - Session export / history

Run standalone:
  python scripts/cloud_sync.py --once
  python scripts/cloud_sync.py --daemon          # loop every JARVIS_SYNC_INTERVAL seconds
  python scripts/cloud_sync.py --push-to-cloud   # one-shot local → cloud
  python scripts/cloud_sync.py --pull-from-cloud # one-shot cloud → local
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


LOCAL_URL = os.getenv("JARVIS_LOCAL_URL", "http://localhost:8765")
CLOUD_URL = os.getenv("JARVIS_CLOUD_URL", "")
SYNC_INTERVAL = int(os.getenv("JARVIS_SYNC_INTERVAL", "30"))
SYNC_SECRET = os.getenv("JARVIS_SYNC_SECRET", "")

SYNC_ENDPOINTS = [
    "/lessons",
    "/trust",
    "/profile",
]


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
        data = _get(base, "/healthz", timeout=5)
        return data.get("status") == "ok"
    except Exception:
        return False


# ── Sync logic ──────────────────────────────────────────────────────────────

def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] {msg}", flush=True)


def sync_endpoint(src: str, dst: str, path: str) -> bool:
    """Pull data from src, push to dst. Returns True on success."""
    try:
        data = _get(src, path)
        _post(dst, path, data)
        return True
    except urllib.error.HTTPError as e:
        _log(f"  HTTP {e.code} syncing {path}: {e.reason}")
        return False
    except Exception as e:
        _log(f"  Error syncing {path}: {e}")
        return False


def sync_lessons(src: str, dst: str) -> bool:
    """Merge lessons from both sides to avoid data loss."""
    try:
        src_data = _get(src, "/lessons")
        dst_data = _get(dst, "/lessons")

        src_lessons = src_data.get("lessons", [])
        dst_lessons = dst_data.get("lessons", [])

        # Merge: union by content string
        seen = set()
        merged = []
        for lesson in src_lessons + dst_lessons:
            key = lesson if isinstance(lesson, str) else json.dumps(lesson, sort_keys=True)
            if key not in seen:
                seen.add(key)
                merged.append(lesson)

        if len(merged) > len(dst_lessons):
            _post(dst, "/lessons", {"lessons": merged})
            _log(f"  Merged {len(merged) - len(dst_lessons)} new lessons → {dst}")
        return True
    except Exception as e:
        _log(f"  Error syncing lessons: {e}")
        return False


def run_sync(direction: str = "both") -> dict:
    """
    direction: 'push'  = local → cloud
               'pull'  = cloud → local
               'both'  = bidirectional merge
    """
    results = {"ok": 0, "fail": 0, "skipped": 0}

    if not CLOUD_URL:
        _log("JARVIS_CLOUD_URL not set — skipping cloud sync")
        results["skipped"] = len(SYNC_ENDPOINTS)
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

    # Lessons: always merge bidirectionally to preserve both sides
    ok = sync_lessons(LOCAL_URL, CLOUD_URL)
    if direction in ("both", "pull"):
        ok = ok and sync_lessons(CLOUD_URL, LOCAL_URL)
    results["ok" if ok else "fail"] += 1

    # Trust and profile
    for path in ["/trust", "/profile"]:
        if direction in ("push", "both"):
            ok = sync_endpoint(LOCAL_URL, CLOUD_URL, path)
            results["ok" if ok else "fail"] += 1
        if direction in ("pull", "both"):
            ok = sync_endpoint(CLOUD_URL, LOCAL_URL, path)
            results["ok" if ok else "fail"] += 1

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
