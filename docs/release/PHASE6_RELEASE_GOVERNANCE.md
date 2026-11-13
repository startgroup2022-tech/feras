# Phase 6 — Merge Protection & Release Gates

**Status:** PROPOSAL — nothing in this document has been applied.
**Branch under review:** `feature/phase3-functional` (PR #7), head `85bd0cbe`.
**Repository:** `github.com/startgroup2022-tech/feras` (public, owner is a **User**
account, not an organization).
**Date:** 2026-10-31.

> **Nothing here has been executed.** No branch protection was created or
> modified, no ruleset was enabled, PR #7 was not merged, and no environment was
> deployed to. Every setting below is a proposal awaiting the owner's explicit
> approval. The agent's credentials **cannot** read or write branch protection
> (verified: HTTP 403 on `GET .../branches/{branch}/protection` with both the
> app token and the PAT), so even the read side required GraphQL.

---

## 1. Verified current governance state

| Fact | Evidence | Value |
|---|---|---|
| Classic branch protection on `frontend-app-conversion` | `GET .../branches/frontend-app-conversion/protection` | **403 — not readable by this credential**; no protection is known to exist |
| Classic branch protection on `master` | `GET .../branches/master/protection` | **403 — not readable** |
| Rulesets | `GET .../rulesets` | exactly one, id `24439635`, name `"1"` |
| Ruleset `24439635` state | `GET .../rulesets/24439635` | **`enforcement: "disabled"`** |
| Ruleset `24439635` conditions | same | `include: []`, `exclude: []` → **targets nothing** |
| Ruleset `24439635` rules | same | `deletion`, `non_fast_forward` (both inert while disabled) |
| Effective rules on `frontend-app-conversion` | `GET .../rules/branches/frontend-app-conversion` | **`[]` — no rule applies** |
| Effective rules on `master` | `GET .../rules/branches/master` | **`[]` — no rule applies** |
| All seven CI checks are required? | GraphQL `isRequired(pullRequestNumber: 7)` | **`false` for all seven** |
| `CODEOWNERS` file | filesystem search | **absent** |
| Repo default branch | `GET .../repos/...` | `phase2-functional-v1` (**not** protected, **not** gated) |
| Open pull requests | `GET .../pulls?state=open` | #7 (→`frontend-app-conversion`), **#2 (→`master`)**, #1 (→`phase2-functional-v1`) |

**Conclusion:** there is **no effective merge protection anywhere in the
repository.** The CI pipeline added in Phase 5 *reports* but gates nothing, and
the one existing ruleset is disabled and scoped to no branch.

### 1.1 A live gap this exposes

**PR #2 is an open promotion PR `frontend-app-conversion` → `master`.** Its head
commit `91c3c131` has `statusCheckRollup: null` — **no checks ran on it at all**,
because the workflow in `ci.yml` did not exist when that commit was made and the
Phase 5 trigger did not cover a `master` target until the Phase 5 final commit.
PR #2 is currently `mergeStateStatus: CLEAN`, i.e. **it can be merged into
`master` today with zero automated verification.**

Enabling the protection below does **not** retroactively gate PR #2: it must be
re-synced (or `master` re-based onto the integration branch) so the seven checks
run on its head before it can be trusted. This is the single most important
reason to turn the gate on before touching `master`.

---

## 2. The seven required CI check names

Taken from the **live check runs on PR #7 head `85bd0cbe`** (GraphQL
`statusCheckRollup.contexts`), not from the YAML — these are the exact strings
GitHub will match against:

| # | Required check name (exact) | Source job (`ci.yml`) |
|---|---|---|
| 1 | `pytest (Python 3.11)` | `tests` matrix, `3.11` |
| 2 | `pytest (Python 3.12)` | `tests` matrix, `3.12` |
| 3 | `pytest (Python 3.13)` | `tests` matrix, `3.13` |
| 4 | `migrations (PostgreSQL 16)` | `migrations` |
| 5 | `security acceptance sweep` | `security` |
| 6 | `frontend contract` | `frontend-contract` |
| 7 | `dependency audit (pip-audit)` | `dependencies` |

The three matrix jobs are produced by one job definition with
`name: pytest (Python ${{ matrix.python-version }})`, so **all three names must be
listed individually** in the required set. Adding only `pytest` would match
nothing and silently require no test job.

---

## 3. Proposed branch protection — `frontend-app-conversion` and `master`

Two equivalent mechanisms exist. **Recommendation: use a ruleset** (§3.2), because
it covers both branches with one object, expresses the required checks once, and
supports `bypass_actors: []` (no one can bypass). The classic API shape is given
too (§3.1) for environments where rulesets are unavailable.

### 3.1 Option A — classic branch protection (per branch)

Apply the identical body to **both** branches:

```
PUT /repos/startgroup2022-tech/feras/branches/frontend-app-conversion/protection
PUT /repos/startgroup2022-tech/feras/branches/master/protection
```

```json
{
  "required_status_checks": {
    "strict": true,
    "contexts": [
      "pytest (Python 3.11)",
      "pytest (Python 3.12)",
      "pytest (Python 3.13)",
      "migrations (PostgreSQL 16)",
      "security acceptance sweep",
      "frontend contract",
      "dependency audit (pip-audit)"
    ]
  },
  "enforce_admins": true,
  "required_pull_request_reviews": {
    "dismiss_stale_reviews": true,
    "require_code_owner_reviews": false,
    "required_approving_review_count": 1,
    "require_last_push_approval": true
  },
  "restrictions": null,
  "required_linear_history": false,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "required_conversation_resolution": true
}
```

Field-by-field rationale:

| Field | Value | Why |
|---|---|---|
| `required_status_checks.strict` | `true` | The branch must be **up to date** with the base before merging. Without this, a PR can be green on a stale base and merge a regression the checks never saw. |
| `required_status_checks.contexts` | the seven names | §2. |
| `enforce_admins` | `true` | Applies the rules to admins too. **This is the setting that actually prevents bypass** on a user-owned repo, where the owner is by definition an admin. If the owner wants an emergency override, set `false` and accept that every admin can bypass. |
| `required_pull_request_reviews.required_approving_review_count` | `1` | At least one approval. **Caveat:** the repo has no collaborators other than the owner (verified: single-user repo, no `CODEOWNERS`). On a solo repo GitHub does not let the author approve their own PR, so **this setting will block the owner from merging their own work.** Either add a second reviewer account, or set the count to `0` and rely on `required_conversation_resolution` + the checks. This is the one field that needs an owner decision before applying. |
| `dismiss_stale_reviews` | `true` | A new push invalidates prior approvals. |
| `require_last_push_approval` | `true` | Whoever pushed last cannot self-approve; closes the push-then-approve hole. |
| `require_code_owner_reviews` | `false` | No `CODEOWNERS` exists; `true` would be a no-op today. Add `CODEOWNERS` first if you want it. |
| `allow_force_pushes` | `false` | History on a release branch is append-only. |
| `allow_deletions` | `false` | The branch cannot be deleted. |
| `required_conversation_resolution` | `true` | Unresolved review threads block the merge. |
| `restrictions` | `null` | Push allow-lists need a paid plan for a **private** repo; this repo is public, so it is available, but restricting pushes is unnecessary if all changes arrive via PR. Set to a user/team list only if you also want to forbid direct pushes. |
| `required_linear_history` | `false` | Merge commits are how PR #6 and the integration branch were built; forcing linear history would rewrite that convention. Flip to `true` only if you want squash/rebase-only. |

### 3.2 Option B — one ruleset covering both branches (recommended)

```
POST /repos/startgroup2022-tech/feras/rulesets
```

```json
{
  "name": "protect-integration-and-release",
  "target": "branch",
  "enforcement": "active",
  "conditions": {
    "ref_name": {
      "include": ["refs/heads/frontend-app-conversion", "refs/heads/master"],
      "exclude": []
    }
  },
  "bypass_actors": [],
  "rules": [
    { "type": "deletion" },
    { "type": "non_fast_forward" },
    {
      "type": "pull_request",
      "parameters": {
        "required_approving_review_count": 1,
        "dismiss_stale_reviews_on_push": true,
        "require_code_owner_review": false,
        "require_last_push_approval": true,
        "required_review_thread_resolution": true,
        "allowed_merge_methods": ["merge", "squash", "rebase"]
      }
    },
    {
      "type": "required_status_checks",
      "parameters": {
        "strict_required_status_checks_policy": true,
        "do_not_enforce_on_create": false,
        "required_status_checks": [
          { "context": "pytest (Python 3.11)" },
          { "context": "pytest (Python 3.12)" },
          { "context": "pytest (Python 3.13)" },
          { "context": "migrations (PostgreSQL 16)" },
          { "context": "security acceptance sweep" },
          { "context": "frontend contract" },
          { "context": "dependency audit (pip-audit)" }
        ]
      }
    }
  ]
}
```

Why a ruleset is preferable here:

- One object governs both branches; there is no drift between two protection
  configs.
- `bypass_actors: []` is an explicit, auditable statement that **nobody bypasses**
  — stronger and clearer than `enforce_admins`.
- `do_not_enforce_on_create: false` means a newly created matching branch is
  protected from its first commit.

**Housekeeping (do not skip):** the existing disabled ruleset `24439635` (name
`"1"`, targeting nothing) should be **deleted** once the real ruleset is active,
so the ruleset list shows exactly one intended object and nothing looks
accidentally configured:

```
DELETE /repos/startgroup2022-tech/feras/rulesets/24439635
```

### 3.3 What this proposal deliberately does **not** do

- It does **not** protect the default branch `phase2-functional-v1`. That branch
  is a Phase-1/2 historical line; gating it is optional and can be added later if
  it is still an active target.
- It does **not** add `CODEOWNERS`. If you want mandatory review by a named
  owner, add `.github/CODEOWNERS` **first**, then set
  `require_code_owner_reviews: true`.
- It does **not** change merge-method settings at the repository level
  (`allow_merge_commit`/`squash`/`rebase` are all `true` today; the ruleset's
  `allowed_merge_methods` mirrors that).

---

## 4. Owner decisions D01–D11 — decision register

The authoritative mapping is spec §21. Two facts govern this register and are
recorded exactly as found; **no approval is invented**:

1. The spec's own rule §20: *"any effective open D-decision is recorded as open
   and its part is never marked complete"* (`أي قرار D مؤثر غير محسوم يسجل مفتوحًا
   ولا توضع علامة مكتمل لجزئه`).
2. The original Word specification **is now present** at
   `docs/reference/Platform_Executive_Specifications_v1.docx` and was read
   directly on the integration branch — this supersedes the earlier
   "spec missing" limitation.

### 4.1 Recorded authorisation

`docs/audit/SAFIR_EXECUTION_30_OWNER_DECISIONS.md` §1 records, verbatim:

> "The owner authorised implementation of **D01, D02, D03, D04, D09, D10, D11**.
> Not authorised: inventing unspecified financial values, destructive production
> operations, or deployment."

**D05, D06, D07 and D08 are therefore *not* covered by that authorisation.** Their
mechanisms exist in the codebase, but the authorisation line above does not name
them. **This is an ambiguity the owner must resolve**: either extend the
authorisation to D05–D08 explicitly, or accept that their implemented mechanisms
sit outside the recorded grant. The agent will not resolve it by inference.

### 4.2 Register

| ID | Subject (spec §21) | Mechanism in code | Owner **data/value** outstanding | Screens | Impact if not resolved |
|---|---|---|---|---|---|
| **D01** | Holding accounting setup: currency, fiscal year, chart of accounts, invoice timing, settlements, tax, assets | `PolicyProposal` governance (accountant proposes → owner decides → inert until decided); chart of accounts, journals, fiscal periods exist | **Depreciation method/rate, fiscal year, tax rates, invoice & asset policy, settlements.** Values must enter as approved records | S26–S28 (+S05/S06/S08) | Holding accounts and reports cannot produce final figures. **Authorised to build (EXEC 30).** |
| **D02** | Report forms & indicators: the 5 questions, indicator definitions, goals, campaign lead count | KPI registry + target-vs-actual, inert until authorised approval (EXEC 29) | **The exact 5 questions, indicator definitions (source/numerator/denominator/period), goal numbers, campaign lead-count rule** | S09–S10, S14, S18, S21 | Management brief and weekly report show structure but no approved wording or targets. **Authorised to build.** |
| **D03** | Non-financial work states: close/return/cancel authority, customer/project states, correction of the management report | **COMPLETE (EXEC 31):** task & support lifecycles, project/opportunity states, linked versioned management-report correction (`corrects_report_id`, `is_live`, exactly-one-live partial unique index) | **None outstanding for the mechanism.** Authority assignment (who may close/return) follows existing RBAC | S13, S16–S22 | **Closed.** Proved by `tests/test_execution31_d03_report_correction.py` (21 cases). **Authorised.** |
| **D04** | Employee & advisor visibility, incl. lead redistribution and who sees distribution history | Append-only `LeadAssignment` + `website_lead.assign` + scoped `history.read`; `ConfidentialAccessGrant` with mandatory expiry | **Explicit display list for advisors; who may see redistribution history by role** | S12, S13, S15, S19, S23 | Advisor and confidential-record visibility stays default-restricted rather than owner-defined. **Authorised to build.** |
| **D05** | Assessment grades & AI data: 1–5 scale, evidence-gap handling, external data | `Assessment`/`AssessmentItem`, evidence-gap rule, immutable history | **Confirmation of the 1–5 scale against the original spec, criterion weights, permitted external data** | S12, S23 | Assessments can be recorded but the approved scale/weights are unconfirmed. **NOT in the EXEC 30 authorisation line — needs explicit cover.** |
| **D06** | Employee balances & actions: manual vs computed, payroll link | Manual admin records only; movement log; no automatic payroll link | **Confirm v1 manual-only; confirm no accounting entries until a linking policy is approved** | S11 | Balances remain manual; no payroll automation. **NOT in the EXEC 30 authorisation line.** |
| **D07** | Budget source & update: who records it, reference, over-budget detection | `Budget` preserves source + version; explicit escalation without blocking payment | **Who may record/change a budget, the owner reference format, whether over-budget detection is automatic** | S22, S28 | Budgets can be entered but escalation semantics are default. **NOT in the EXEC 30 authorisation line.** |
| **D08** | Annual carry-forward source | `OpeningBalance` submit/approve; **no** automatic December copy | **Confirm no auto carry-forward; the approved source summary** | S04 | Opening balances are manual by design. **NOT in the EXEC 30 authorisation line.** |
| **D09** | Currency change & calc details: preserve historical currency, no conversion before an approved rule/rate/date | `CurrencyChangeRequest` lifecycle (requested→reviewed→approved/rejected→scheduled→applied); cannot apply before its effective period; no-mixing guard live | **Base currency per company; conversion rule, rate and date when conversion is ever permitted** | S03, S06, S07, S10 | Currency changes cannot be applied without an approved rate/date. **Authorised to build.** |
| **D10** | Bank attachment, protection & restore | `backend/core/storage.py` upload limits + per-company protection; `backend/core/backup.py` integrity + isolated restore drill | **Retention period, backup frequency, restore-time objective; the owner's approval for any production restore** | S05, S08, technical | Backups are taken and drills run; **the production restore drill is not executed** (§6). **Authorised to build.** |
| **D11** | Login & notification channels & timing: login method, multi-assignment, time zone, external channels | Internal notification centre + per-event preferences; **2FA (TOTP) with recovery codes and login-time enforcement** | **Login method (SSO or local), multi-assignment user handling, display time zone; whether email/WhatsApp is ever added** | S01, S25 | External channels stay off (no email/WhatsApp). **Authorised to build.** |

### 4.3 Closed decisions — do not reopen

Spec Appendix A decisions Dec. 1 (correction handling), Dec. 2 (included vs added
item) and Dec. 3 (currency / no aggregation) are **closed** and already reflected
in the financial engine (`financial_calc.py`).

### 4.4 Exact approvals requested from the owner

1. **Confirm the D01–D04, D09–D11 authorisation** recorded in EXEC 30 (already in
   writing in the repository; confirm it stands).
2. **Decide on D05–D08:** extend the authorisation to them, or confirm they remain
   out of scope. *One line is sufficient.*
3. **Supply the D01/D02/D09 data values** (depreciation/tax/fiscal policy, the five
   questions and indicator definitions, base currencies and any conversion rule).
4. **Approve the production restore policy (D10):** retention, frequency, RTO, and
   who may authorise a production restore.
5. **Confirm D11 channels:** local login + internal notifications only, or add
   email.

Until (2) is answered, **D05–D08 remain formally open** and their modules must not
be marked complete (spec §20).

---

## 5. PR #7 — verified status

| Property | Value |
|---|---|
| Number / title | #7 — `feat(phase3+4): full functional implementation and verification acceptance` |
| State | **OPEN**, not draft, **not merged** |
| Head → base | `feature/phase3-functional` → `frontend-app-conversion` |
| Head commit | `85bd0cbe59240e2bf733ddc2c8c7cd787754d4a1` |
| Mergeability | `MERGEABLE` / `mergeStateStatus: CLEAN` |
| Review decision | none recorded |
| Commits ahead / behind | 18 ahead / 0 behind (clean fast-forward) |
| CI | **all seven checks pass** on `85bd0cbe` (run `41223213906`) |

CI results on the head commit:

| Check | Result | Duration |
|---|---|---|
| `pytest (Python 3.11)` | ✅ pass | 13m44s |
| `pytest (Python 3.12)` | ✅ pass | 15m38s |
| `pytest (Python 3.13)` | ✅ pass | 13m37s |
| `migrations (PostgreSQL 16)` | ✅ pass | 52s |
| `security acceptance sweep` | ✅ pass | 27s |
| `frontend contract` | ✅ pass | 1m36s |
| `dependency audit (pip-audit)` | ✅ pass | 21s |

All seven are `isRequired: false` — they gate nothing until §3 is approved.

---

## 6. Staging validation & production rollout plan

Nothing in this section has been run. `docs/DEPLOYMENT.md` and
`docs/BACKUP_RESTORE.md` already hold the detailed procedures; this is the
release-gate checklist built on top of them.

### 6.1 Pre-flight (blocking)

| # | Gate | How | Pass condition |
|---|---|---|---|
| P1 | PR #7 merged into `frontend-app-conversion` | owner action | merge commit on integration |
| P2 | Branch protection active on both branches | apply §3 | `GET .../rules/branches/...` non-empty |
| P3 | **PR #2 re-synced and re-checked** | push a merge/update to its head | seven checks present and green on `master`'s target head |
| P4 | D05–D08 authorisation resolved | owner reply | §4.4 item 2 answered |
| P5 | D01/D02/D09 data supplied | owner records | approved policy records exist, not drafts |
| P6 | Rollback target recorded | `git rev-parse` of current staging + prod HEADs | two immutable SHAs written down |

### 6.2 The deployment guide targets the wrong line — RESOLVED

`docs/DEPLOYMENT.md` originally targeted **`phase2-functional-v1`** (commit
`ec77588`, "the approved Phase 2 application") with expected revision
`55d2d244bc1b`. That was internally correct for that branch, but the guide
deployed the wrong line.

**Resolved:** the guide now targets the release line (`feature/phase3-functional`,
PR #7 → `frontend-app-conversion`), checks out that branch, and expects the
current single Alembic head **`d04621f4f9bd`** across **41 revisions**. Confirm
with `alembic heads` before deploying.

### 6.3 Staging validation sequence

Follow `docs/DEPLOYMENT.md` §§2–11, with these additions:

1. **Never seed demo data.** `scripts/seed_demo.py` is local-only; the first real
   owner is created with `scripts/bootstrap_owner.py` (refuses demo domains, weak
   passwords and a second initial owner).
2. **Confirm the environment file** is mode `600`, `APP_ENV=staging`,
   `DEBUG=false`, unique `SECRET_KEY` (≥32 chars — the production guard rejects
   short/placeholder keys), dedicated staging DB, `UPLOAD_DIR` on a persistent
   volume, `AI_PROVIDER=none`.
3. **Exactly one uvicorn worker.** The login rate limiter is in-process; extra
   workers fractionate it. Do not add gunicorn.
4. **Migrations, previewed:**
   ```bash
   python -m alembic upgrade head --sql          # inspect, no writes
   python -c "from backend.core.config import settings; print(settings.DATABASE_URL)"
   python -m alembic upgrade head
   python -m alembic current                     # expect d04621f4f9bd
   python -m alembic check                       # "No new upgrade operations detected."
   ```
5. **Health probes:** `/health` → `{"status":"ok"}`; `/ready` → database + uploads
   both true.
6. **Acceptance re-run on staging** (the same harnesses CI runs): security sweep,
   frontend contract, and the responsive matrix.
7. **The one migration with real risk.** `3473d285d919` (D03) drops
   `uq_report_company_period`, adds `version_number`/`is_live` with
   `server_default`, creates a **partial unique index** `uq_report_company_period_live`
   (`WHERE is_live`) and a new unique `uq_report_company_period_version`. It is
   written with `batch_alter_table` and both `sqlite_where`/`postgresql_where`, so
   it is portable — but on a **populated** production table the partial-index
   creation will fail if any company/period already has two live rows. Before
   applying to production:
   ```sql
   SELECT company_id, period_year, period_month, count(*) AS live_rows
   FROM monthly_reports
   WHERE is_live
   GROUP BY company_id, period_year, period_month
   HAVING count(*) > 1;
   ```
   **Expected: zero rows.** Any row must be resolved before the migration runs.
8. **Load test** — still outstanding (see §7). Staging is the place to run it:
   single worker behind nginx against Postgres, unlike the SQLite dev figures
   (p95 ≈ 21 ms) which are indicative only.

### 6.4 Production rollout

**Backup first — database and uploads together, consistently.** A dump without a
matching uploads snapshot references files that no longer exist. Order:
snapshot uploads → immediately dump the database.

```bash
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
python scripts/backup.py create --dest /backup/safir_${STAMP}
python scripts/backup.py verify --source /backup/safir_${STAMP}     # expect problems: []
python scripts/backup.py drill  --source /backup/safir_${STAMP} \
    --scratch /tmp/safir_restore_prod_check                          # isolated, never over live
```

A backup is only proven once `verify` reports `problems: []` **and** the drill
restores identical row counts.

Then:

1. Put the app in maintenance/read-only if the schema change is non-additive
   (D03's index swap qualifies — do this during a quiet window).
2. Apply migrations with the pre-flight query (§6.3.7) already clean.
3. Restart the service; confirm `/health` and `/ready`.
4. Smoke-test the critical paths: login (+2FA if enabled), dashboard, one report
   read, one approval action, one attachment upload/download.
5. Watch logs and error rate for one full business cycle.

**Rollback**

- **Application-only (no schema change):** check out the previous recorded SHA,
  restart, re-probe `/ready`.
- **Schema:** `alembic downgrade -1` is reversible for `3473d285d919`, but the
  initial migration is `down_revision = None`, so a full downgrade removes **all
  tables**. **Prefer restoring the backup** over downgrading in production.
- **Trigger for rollback:** any 5xx spike, failed `/ready`, failed login for the
  owner, or a data-integrity error in logs.

**Explicit prohibition:** no production restore, and no production migration,
without the owner's written approval and a verified recent backup (D10).

---

## 7. Remaining blockers & release readiness

### 7.1 Blockers (in priority order)

| # | Blocker | Owner? | Notes |
|---|---|---|---|
| B1 | **D05–D08 authorisation ambiguous** — EXEC 30's written authorisation names D01–D04, D09–D11 but not D05–D08, while their mechanisms exist | ✅ owner | One-line resolution (§4.4.2). |
| B2 | **Owner data outstanding** for D01 (depreciation/tax/fiscal/invoice/asset policy), D02 (five questions, indicator definitions, goals), D09 (base currencies, conversion rule) | ✅ owner | Mechanisms are live and inert until approved records exist. |
| B3 | **No merge protection active** — all seven checks `isRequired: false` | ✅ owner (agent cannot write protection) | §3. |
| B4 | **PR #2 can reach `master` unverified** — zero checks on its head | ✅ owner | §1.1; re-sync after §3. |
| B5 | **Production load test not run** | ✅ needs staging access | §6.3.8. |
| B6 | **Production backup/restore drill not run** on the production target | ✅ needs prod access | Tooling exists and was exercised on isolated scratch DBs; the production target has not been touched, by design. |
| ~~B7~~ | ~~`docs/DEPLOYMENT.md` targets `phase2-functional-v1`~~ **RESOLVED** — guide re-pointed to `feature/phase3-functional`, expected head `d04621f4f9bd` (§6.2) | agent | Done. |
| B8 | **PowerPoint visual parity UNVERIFIED** | ✅ owner must supply the deck | See §7.3. |

### 7.2 What *is* proven

- Full suite **1002 passed / 0 failed / 0 skipped** on 3.11, 3.12 and 3.13 (CI,
  run `41223213906`).
- Migrations: `upgrade head` → `check` (no drift) → `downgrade base` → `upgrade
  head`, clean, against **PostgreSQL 16** in CI and locally.
- Security sweep **23/23**; frontend contract **142**; `pip-audit` clean on both
  requirement files (the Phase 5 `pytest` advisory is fixed at 9.0.3).
- Spec mandate: all 28 screens and 28 acceptance criteria evidenced in
  `SAFIR_SPEC_PARITY_MATRIX.md`; security controls re-proved independently.

### 7.3 PowerPoint parity — explicitly NOT verified

**No visual parity is claimed.** No `.pptx` exists anywhere on this machine, in
the repository, or in any remote ref (`find / -iname '*.pptx'` → empty;
`git log --all -- '*.pptx'` → never committed). No slide has been seen. The deck
must be supplied as a file before any parity statement can be made or refuted.
The tooling to compare (`scripts/extract_pptx.py`, `scripts/compare_screens.py`)
is ready and was exercised against a synthetic deck.

### 7.4 Verdict

> ## RELEASE READINESS: **NOT READY**
>
> The **application** is in good shape — the full suite, migrations, security
> sweep and dependency audit all pass on the current head. What holds the release
> is **governance and owner input**, not code:
>
> 1. **No merge protection is active** (B3) and a promotion PR can reach `master`
>    with zero checks (B4).
> 2. **D05–D08 authorisation is ambiguous** (B1) and **owner data for D01/D02/D09
>    is outstanding** (B2).
> 3. **Production load test and production restore drill are not run** (B5, B6).
> 4. **PowerPoint parity is unverifiable** (B8) — the deck is absent.

---

## 8. Approvals requested

Please reply with a decision on each:

1. **Branch protection (§3):** approve Option B (one ruleset, `bypass_actors: []`)
   or Option A (classic, per branch)? And for the review requirement — add a
   second reviewer account, or set `required_approving_review_count: 0` given the
   repo has a single user?
2. **Ruleset `24439635`:** approve deleting the disabled placeholder?
3. **D05–D08 (§4.4.2):** extend the authorisation to them, or confirm they remain
   open?
4. **Owner data (§4.4.3–4.4.5):** supply the D01/D02/D09 values, the D10 restore
   policy, and the D11 channel decision.
5. **PPTX (§7.3):** supply `Platform Interface Design v3.pptx` so parity can be
   verified.
6. **Staging (§6.3):** confirm access so the load test and restore drill can run.

Until (1) is approved, **no protection setting will be applied** — as instructed.

---

_This document was produced by an AI agent (OpenHands) on behalf of the repository
owner. It records only what was verified by command; no approval has been invented._
