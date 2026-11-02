"""Probe the endpoints named by the deck compliance matrix.

Signs in as the holding owner (widest scope) and issues each probe request,
recording the HTTP status. Output feeds ``build_deck_compliance.py`` so a slide
whose screen is API-only in the browser can still be scored.

    python scripts/audit/api_probe.py --base http://127.0.0.1:12000 \
        --out artifacts/api_probe.json
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

import httpx

OWNER = "owner@demo.safir.local"
PASSWORD = "SafirDemo!2027"

# (METHOD, path, query) probes named in the compliance matrix. Paths are the
# real router paths (verified against /api/openapi.json), not the deck's prose.
PROBES = [
    ("GET", "/api/v1/monthly-reports", None),
    ("GET", "/api/v1/companies", None),
    ("GET", "/api/v1/accounting/opening-balances", None),
    ("GET", "/api/v1/ai/insights", None),
    ("GET", "/api/v1/accounting/journals", None),
    ("GET", "/api/v1/accounting/parties", None),
    ("GET", "/api/v1/accounting/receivables", None),
    ("GET", "/api/v1/accounting/accounts", None),
    ("GET", "/api/v1/accounting/budgets", None),
    ("GET", "/api/v1/accounting/trial-balance",
     {"company_id": 1, "fiscal_year": 2027, "fiscal_month": 10}),
    ("GET", "/api/v1/accounting/financial-reports/group",
     {"period_year": 2027, "period_month": 10}),
    ("GET", "/api/v1/accounting/kpis", None),
    ("GET", "/api/v1/accounting/kpis/evaluations", None),
    ("GET", "/api/v1/admin/permissions/catalogue", None),
    ("GET", "/api/v1/analytics/holding", None),
    ("GET", "/api/v1/admin/ownerships", None),
    ("GET", "/api/v1/employees", None),
    ("GET", "/api/v1/monthly-reports/1/versions", None),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:12000")
    ap.add_argument("--out", default="artifacts/api_probe.json")
    args = ap.parse_args()

    with httpx.Client(base_url=args.base, timeout=20) as c:
        r = c.post("/api/v1/auth/login",
                   json={"email": OWNER, "password": PASSWORD})
        r.raise_for_status()
        token = r.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        out: dict[str, int] = {}
        for method, path, query in PROBES:
            try:
                resp = c.request(method, path, headers=headers, params=query)
                code = resp.status_code
            except Exception as exc:  # noqa: BLE001
                code = -1
                print(f"  {method} {path}: {exc}", file=sys.stderr)
            out[f"{method} {path}"] = code
            print(f"  {method} {path} -> {code}", file=sys.stderr)

    dest = pathlib.Path(args.out)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=1))
    print(f"wrote {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
