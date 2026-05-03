"""Smoke test: control_server boots, all endpoints respond."""
import json
import sys
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "runtime"))

from http.server import ThreadingHTTPServer  # noqa: E402

from runtime.agency.control_server import Handler  # noqa: E402
from runtime.agency.registry import default_registry  # noqa: E402

default_registry()  # warm

PORT = 8766
httpd = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
t = threading.Thread(target=httpd.serve_forever, daemon=True)
t.start()
time.sleep(0.2)

BASE = f"http://127.0.0.1:{PORT}"


def _get(path: str):
    with urllib.request.urlopen(BASE + path, timeout=5) as r:
        return r.status, json.loads(r.read())


def _post(path: str, body):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


try:
    code, h = _get("/healthz")
    print("healthz:", code, h)
    assert code == 200 and h["ok"] is True

    code, a = _get("/agents")
    print("agents.count:", a["count"], "domains:", len(a["domains"]))
    assert code == 200 and a["count"] >= 300 and len(a["domains"]) == 18

    code, a = _get("/agents?domain=engineering")
    print("eng.count:", a["count"])
    assert a["count"] >= 30

    code, a = _get("/agents?color=blue")
    print("blue.count:", a["count"])
    assert a["count"] >= 5

    code, hits = _post("/route", {"query": "optimize a postgres index", "k": 3})
    print("route.hits:", len(hits), "top:", hits[0]["name"] if hits else None)
    assert code == 200 and len(hits) >= 1

    code, run = _post("/run", {
        "domain": "engineering",
        "slug": hits[0]["slug"] if hits and hits[0]["domain"] == "engineering"
                 else "database-optimizer",
        "payload": {"task": "smoke"},
    })
    print("run.code:", code, "ok:", run.get("ok"), "agent:", run.get("output", {}).get("agent"), "err:", run.get("error"))
    assert code in (200, 502)

    code, kpi = _get("/kpi")
    assert code == 200 and "counters" in kpi
    print("kpi.counters keys:", list(kpi["counters"].keys())[:5])

    code, tr = _get("/traces?n=5")
    print("traces.count:", tr["count"])
    assert code == 200

    print("\nOK")
finally:
    httpd.shutdown()
    httpd.server_close()
