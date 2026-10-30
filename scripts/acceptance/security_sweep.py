"""Phase 4 section 3 — security and permission acceptance against a live API.

This is the API-level counterpart to ``scripts/e2e_roles.py`` (which checks the
Roles *screen* in a browser). It signs in as each specification role and asks
the running backend two questions:

1. **Isolation** — can a role read or write a record belonging to a company it
   has no access to? "Not yours" and "does not exist" must both be ``404``; a
   ``403`` would confirm the record exists.
2. **Privilege** — can a role perform an action its permission set forbids
   (e.g. an accountant assigning permissions, a company manager reading the
   holding-wide financial roll-up)?

It also sweeps every parameterless ``GET`` as an unauthenticated client and
asserts none answers ``200`` — the simplest, broadest check that no read
endpoint was left unguarded.

Run: ``python -m scripts.acceptance.security_sweep --base http://127.0.0.1:12099``
"""

from __future__ import annotations

import argparse
import json
import pathlib
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "artifacts" / "phase4"
PASSWORD = "SafirDemo!2027"

ROLES = {
    "holding_owner": "owner@demo.safir.local",
    "company_manager": "manager.tech@demo.safir.local",
    "accountant": "accountant@demo.safir.local",
    "business_development": "bd@demo.safir.local",
    "marketing": "marketing@demo.safir.local",
    "designer": "design@demo.safir.local",
    "external_consultant": "consultant@demo.safir.local",
}

RESULTS: list[tuple[str, str, str]] = []


def record(name, ok, detail=""):
    RESULTS.append((name, "PASS" if ok else "FAIL", detail))


def _req(method, url, token=None, body=None, timeout=15):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def login(base, email):
    status, body = _req("POST", f"{base}/api/v1/auth/login",
                        body={"email": email, "password": PASSWORD})
    if status != 200:
        return None
    return json.loads(body)["access_token"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:12099")
    args = ap.parse_args()
    base = args.base.rstrip("/")
    ARTIFACTS.mkdir(parents=True, exist_ok=True)

    tokens = {}
    for role, email in ROLES.items():
        t = login(base, email)
        record(f"login/{role}", t is not None, "" if t else f"{email} failed")
        if t:
            tokens[role] = t
    print(f"authenticated {len(tokens)}/{len(ROLES)} roles")

    # ---- 1. unauthenticated sweep -------------------------------------------
    with urllib.request.urlopen(f"{base}/api/openapi.json", timeout=15) as r:
        spec = json.loads(r.read())
    targets = sorted(
        p for p, ops in spec["paths"].items()
        if "get" in ops and "{" not in p and p.startswith("/api/v1/")
    )
    # ``/api/v1/public`` is the marketing website's surface: it is *meant* to be
    # reachable without a token. Everything else must refuse.
    PUBLIC_PREFIX = "/api/v1/public/"
    leaks = []
    for path in targets:
        if path.startswith(PUBLIC_PREFIX):
            continue
        status, _ = _req("GET", base + path)
        if status == 200:
            leaks.append(path)
    record(f"unauth-sweep/{len(targets)}-endpoints", not leaks,
           f"200 without a token: {leaks[:5]}" if leaks else "")
    print(f"unauthenticated sweep: {len(targets)} endpoints "
          f"({len([t for t in targets if t.startswith(PUBLIC_PREFIX)])} public "
          f"by design), {len(leaks)} leaked")

    # The public surface must stay narrow: no internal identifiers.
    st, body = _req("GET", f"{base}/api/v1/public/opportunities")
    if st == 200:
        raw = body.decode()
        banned = [f for f in ('"company_id"', '"created_by"', '"internal"',
                              '"owner_id"', '"lead_id"')
                  if f in raw]
        record("public/opportunities-exposes-no-internal-ids", not banned,
               f"leaked fields: {banned}")

    # ---- 2. cross-company isolation ----------------------------------------
    # The owner sees every company; a company manager may only see its own.
    # "Not yours" and "does not exist" must both be 404 so the response never
    # confirms that an out-of-scope record exists.
    owner = tokens.get("holding_owner")
    mgr = tokens.get("company_manager")
    if owner and mgr:
        status, body = _req("GET", f"{base}/api/v1/companies", owner)
        ids = [c["id"] for c in json.loads(body)] if status == 200 else []
        # A manager's own company answers; every other id must 404, never 403.
        reachable, forbidden = [], []
        for cid in ids:
            st, _ = _req("GET", f"{base}/api/v1/companies/{cid}", mgr)
            (reachable if st == 200 else forbidden).append((cid, st))
        record("isolation/manager-sees-only-own-company",
               len(reachable) <= 1 and all(s == 404 for _, s in forbidden),
               f"reachable={reachable} other={forbidden}")
        record("isolation/foreign-company-is-404-not-403",
               all(s == 404 for _, s in forbidden),
               f"statuses={[s for _, s in forbidden]}")

        # A foreign company's monthly reports must also be invisible.
        foreign = [cid for cid, st in forbidden if st == 404]
        if foreign:
            st, _ = _req("GET",
                         f"{base}/api/v1/companies/{foreign[0]}/monthly-reports",
                         mgr)
            record("isolation/foreign-company-reports-404", st == 404,
                   f"manager got {st} for company {foreign[0]}")

    # ---- 3. privilege boundaries -------------------------------------------
    # Each probe names an endpoint the role must not be able to use.
    PROBES = [
        ("accountant", "GET", "/api/v1/admin/users",
         "accountant must not list users"),
        ("accountant", "POST", "/api/v1/rbac/sync",
         "accountant must not sync RBAC"),
        ("business_development", "GET", "/api/v1/admin/users",
         "BD must not list users"),
        ("marketing", "GET", "/api/v1/admin/users",
         "marketing must not list users"),
        ("designer", "GET", "/api/v1/admin/users",
         "designer must not list users"),
        ("external_consultant", "GET", "/api/v1/admin/users",
         "consultant must not list users"),
        ("company_manager", "GET", "/api/v1/admin/users",
         "manager must not list users"),
        ("company_manager", "GET", "/api/v1/analytics/holding",
         "manager must not read holding analytics"),
    ]
    for role, method, path, desc in PROBES:
        token = tokens.get(role)
        if not token:
            continue
        st, _ = _req(method, base + path, token)
        record(f"privilege/{role}{path}", st in (403, 404, 405),
               f"{desc}: got {st}")

    # ---- 4. token hygiene ---------------------------------------------------
    for label, tok in (("garbage", "not-a-real-token"),
                       ("empty", "")):
        st, _ = _req("GET", f"{base}/api/v1/auth/me", tok)
        record(f"token/rejects-{label}", st == 401, f"got {st}")
    st, _ = _req("GET", f"{base}/api/v1/auth/me",
                 "Bearer.invalid.signature")
    record("token/rejects-bad-signature", st == 401, f"got {st}")

    out = ARTIFACTS / "security_sweep.json"
    out.write_text(json.dumps(
        [{"case": n, "status": s, "detail": d} for n, s, d in RESULTS],
        ensure_ascii=False, indent=2))
    passed = sum(1 for _, s, _ in RESULTS if s == "PASS")
    failed = len(RESULTS) - passed
    print(f"\n=== security sweep: {passed} passed, {failed} failed ===")
    for n, s, d in RESULTS:
        if s == "FAIL":
            print(f"  FAIL {n}: {d}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
