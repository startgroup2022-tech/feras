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
    # Deck slides 107-109: the investment valuation register (read path; the
    # write path is PATCH and would mutate, so it is not probed).
    ("GET", "/api/v1/admin/investment-valuations", None),
    ("GET", "/api/v1/employees", None),
    ("GET", "/api/v1/monthly-reports/1/versions", None),
]

# Deck slides 7-11: each primary role's dashboard must return its own KPI tile
# set. The probe signs in per role and records the tile keys, so the compliance
# matrix can prove the strips differ instead of assuming one screen fits all.
ROLE_LOGINS = [
    ("holding_owner", "owner@demo.safir.local"),
    ("business_development", "bd@demo.safir.local"),
    ("company_manager", "manager.tech@demo.safir.local"),
    ("designer", "design@demo.safir.local"),
    ("marketing", "marketing@demo.safir.local"),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:12000")
    ap.add_argument("--out", default="artifacts/api_probe.json")
    ap.add_argument("--roles-out", default="artifacts/role_summaries.json")
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

        roles = _probe_role_summaries(c)

    dest = pathlib.Path(args.out)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=1))
    print(f"wrote {dest}")

    role_dest = pathlib.Path(args.roles_out)
    role_dest.parent.mkdir(parents=True, exist_ok=True)
    role_dest.write_text(json.dumps(roles, indent=1, ensure_ascii=False))
    print(f"wrote {role_dest}")
    return 0


def _probe_role_summaries(client) -> dict:
    """Sign in per role and record the dashboard's ``role_summary`` tile keys.

    A role with no dedicated summary records ``None`` -- that is the honest
    answer, and the dashboard then keeps the holding strip.
    """
    out: dict[str, dict] = {}
    for role, email in ROLE_LOGINS:
        try:
            r = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
            r.raise_for_status()
            headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
            dash = client.get(
                "/api/v1/dashboard/holding",
                headers=headers,
                params={"year": 2027, "month": 10},
            )
            if dash.status_code >= 400:
                # A company-scoped role has no holding dashboard; use its own.
                cid = _primary_company(client, headers)
                dash = client.get(
                    f"/api/v1/dashboard/company/{cid}",
                    headers=headers,
                    params={"year": 2027, "month": 10},
                )
            summary = (dash.json() or {}).get("role_summary") if dash.status_code == 200 else None
            out[role] = {
                "status": dash.status_code,
                "title_en": (summary or {}).get("title_en"),
                "tiles": [k["key"] for k in (summary or {}).get("kpis", [])],
            }
            print(f"  role {role} -> {out[role]['tiles']}", file=sys.stderr)
        except Exception as exc:  # noqa: BLE001
            out[role] = {"error": str(exc)}
            print(f"  role {role}: {exc}", file=sys.stderr)
    return out


def _primary_company(client, headers) -> int:
    r = client.get("/api/v1/companies", headers=headers)
    companies = r.json() if r.status_code == 200 else []
    if not companies:
        return 1
    return companies[0]["id"]


if __name__ == "__main__":
    raise SystemExit(main())
