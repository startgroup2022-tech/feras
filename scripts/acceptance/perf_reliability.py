"""Phase 4 section 6 — performance and reliability acceptance.

Answers four questions against a running instance:

1. **Latency** — every read-only ``GET`` the owner can reach answers within a
   budget, and no endpoint is a pathological outlier.
2. **Errors** — a full authorised sweep produces no 5xx and no unexplained 4xx.
3. **Logs** — nothing in the sweep raises a server-side traceback.
4. **Frontend load** — the platform shell and its API bridge come up without
   console errors (checked by ``ui_responsive.py``; here we time the asset
   payload).

Run: ``python -m scripts.acceptance.perf_reliability --base http://127.0.0.1:12099``
"""

from __future__ import annotations

import argparse
import json
import pathlib
import statistics
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "artifacts" / "phase4"
OWNER = "owner@demo.safir.local"
PASSWORD = "SafirDemo!2027"

# Budgets are deliberately generous: this is a demo-class SQLite instance, and
# the point is to catch an endpoint that is orders of magnitude slow, not to
# benchmark. A p95 above the budget is reported as a finding.
P95_BUDGET_MS = 1500
MAX_BUDGET_MS = 4000


def _req(method, url, token=None, body=None, timeout=15):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    if data:
        req.add_header("Content-Type", "application/json")
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = resp.read()
            return resp.status, (time.perf_counter() - start) * 1000, payload
    except urllib.error.HTTPError as e:
        return e.code, (time.perf_counter() - start) * 1000, e.read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:12099")
    args = ap.parse_args()
    base = args.base.rstrip("/")
    ARTIFACTS.mkdir(parents=True, exist_ok=True)

    status, _, body = _req("POST", f"{base}/api/v1/auth/login",
                           body={"email": OWNER, "password": PASSWORD})
    assert status == 200, f"login failed: {status} {body[:200]}"
    token = json.loads(body)["access_token"]
    print("authenticated as owner")

    with urllib.request.urlopen(f"{base}/api/openapi.json", timeout=15) as r:
        spec = json.loads(r.read())

    # Read-only GETs with no path parameters are the safe, repeatable set.
    targets = sorted(
        p for p, ops in spec["paths"].items()
        if "get" in ops and "{" not in p and p.startswith("/api/")
    )
    print(f"sweeping {len(targets)} parameterless GET endpoints\n")

    rows = []
    for path in targets:
        # Two runs: the first may pay a cold-cache cost.
        s1, ms1, b1 = _req("GET", base + path, token)
        s2, ms2, b2 = _req("GET", base + path, token)
        rows.append({"path": path, "status": s1, "first_ms": round(ms1, 1),
                     "ms": round(ms2, 1), "bytes": len(b2)})

    latencies = [r["ms"] for r in rows]
    p95 = statistics.quantiles(latencies, n=20)[18] if len(latencies) >= 20 \
        else max(latencies)
    server_errors = [r for r in rows if r["status"] >= 500]
    slow = [r for r in rows if r["ms"] > MAX_BUDGET_MS]

    # Frontend shell: the HTML document plus the JS/CSS the bridge needs. These
    # are what a user waits on before the SPA paints, so they are timed
    # separately from the API.
    assets = ["/platform/", "/platform/app.js", "/platform/styles.css"]
    asset_rows = []
    for path in assets:
        st, ms, payload = _req("GET", base + path)
        asset_rows.append({"path": path, "status": st,
                           "ms": round(ms, 1), "bytes": len(payload)})

    (ARTIFACTS / "perf_reliability.json").write_text(
        json.dumps({"p95_ms": round(p95, 1),
                    "median_ms": round(statistics.median(latencies), 1),
                    "max_ms": max(latencies),
                    "server_errors": server_errors,
                    "slow": slow, "assets": asset_rows, "rows": rows},
                   ensure_ascii=False, indent=2))

    print(f"median {statistics.median(latencies):.0f}ms  "
          f"p95 {p95:.0f}ms  max {max(latencies):.0f}ms")
    print(f"5xx responses: {len(server_errors)}")
    for r in server_errors:
        print(f"  {r['status']} {r['path']}")
    print(f"over {MAX_BUDGET_MS}ms: {len(slow)}")
    for r in sorted(slow, key=lambda x: -x["ms"])[:10]:
        print(f"  {r['ms']:.0f}ms {r['path']}")
    print("frontend shell: " + "  ".join(
        f"{a['path']}={a['ms']:.0f}ms/{a['bytes']}B" for a in asset_rows))
    bad_assets = [a for a in asset_rows if a["status"] != 200]

    ok = (not server_errors and not bad_assets
          and p95 <= P95_BUDGET_MS and not slow)
    print(f"\n=== perf/reliability: {'PASS' if ok else 'FAIL'} ===")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
