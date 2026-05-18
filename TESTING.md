# SF Mission Control — Testing Classification Matrix

## Overview

This document classifies every production file in the codebase by testing category
and documents the reasoning for each classification. One line in the entire codebase
(`app.py:63`, the `if __name__ == '__main__':` guard) is structurally untestable by
pytest and is documented as Compile-verified.

---

## Testing Taxonomy

### 1. Unit-tested

A pytest test exercises the behavior of this code and makes explicit assertions.
The file contributes to the coverage percentage tracked by `pytest --cov`.

```bash
pytest tests/ -v
```

### 2. Contract-pinned

`tests/test_contracts.py` pins known-good invariants (field shapes, value ranges,
counts from the handoff document). These tests act as regression guards: if mock
data shapes or service return schemas change, contracts break immediately.

### 3. Compile-verified

The file contains only declarations, configuration, or a single universally exempt
pattern (`if __name__ == '__main__':`). The Python interpreter and/or the K8s
toolchain validate correctness on every import or deploy. No test is needed because
there is no executable logic to assert against.

The one exempt line across the entire codebase is `app.py:63`:

```python
if __name__ == '__main__':   # line 62 — covered (evaluates to False in tests)
    app.run(...)             # line 63 — NEVER executed; __main__ guard by convention
```

This pattern is universally skipped by pytest coverage in every Python project.
All CI test runners import the module rather than executing it as a script.

### 4. Manual-procedure-documented

JavaScript-heavy UI interactions, browser rendering, and multi-step user flows
cannot be exercised by pytest. These are documented as step-by-step procedures
in the **Manual Test Procedures** section below.

---

## File Classification Matrix

| File | Stmts | Category | Coverage | Notes |
|---|---|---|---|---|
| `app.py` | 45 | Unit-tested | 98% (1 exempt line) | Line 63 is `__main__` guard — Compile-verified |
| `config.py` | 18 | Unit-tested | 100% | |
| `db.py` | 36 | Unit-tested | 100% | `get_cursor`, `init_db`, `db_available` all tested with mocked psycopg2 |
| `sf_provider.py` | 161 | Unit-tested + Contract-pinned | 100% | Contracts in `test_contracts.py` pin mock counts to handoff doc |
| `conductor_provider.py` | 99 | Unit-tested + Contract-pinned | 100% | `responses` library mocks all HTTP; contracts pin failure counts |
| `scheduler.py` | 22 | Unit-tested | 100% | `BackgroundScheduler` fully mocked; cron trigger params asserted |
| `routes/__init__.py` | 0 | Compile-verified | 100% | Empty file — Python package marker |
| `routes/health.py` | 12 | Unit-tested | 100% | |
| `routes/migration.py` | 91 | Unit-tested | 100% | All 200/400/500 branches covered |
| `routes/validation.py` | 60 | Unit-tested | 100% | |
| `routes/soql.py` | 90 | Unit-tested | 100% | |
| `routes/schema.py` | 52 | Unit-tested | 100% | Multipart upload branches included |
| `routes/data_ops.py` | 48 | Unit-tested | 100% | Join build + run with table-config format |
| `routes/settings_routes.py` | 76 | Unit-tested | 100% | File upload, JSON body, CRUD all covered |
| `services/__init__.py` | 0 | Compile-verified | 100% | Empty file — Python package marker |
| `services/readiness_validator.py` | 98 | Unit-tested + Contract-pinned | 100% | Amber/green overall status tested; contracts pin check keys |
| `services/duplicate_radar.py` | 56 | Unit-tested | 100% | AttributeError and general exception merge paths covered |
| `services/batch_tracker.py` | 54 | Unit-tested + Contract-pinned | 100% | JSON parse failure, rerun exception paths included |
| `services/error_reconciler.py` | 44 | Unit-tested + Contract-pinned | 100% | JSON parse and retry exception paths covered |
| `services/schema_diff.py` | 44 | Unit-tested | 100% | Exception path in `run_diff` covered |
| `services/soql_workbench.py` | 66 | Unit-tested | 100% | Was already 100% |
| `services/external_id_coverage.py` | 39 | Unit-tested + Contract-pinned | 100% | Was already 100% |
| `services/contactpoint_scanner.py` | 31 | Unit-tested + Contract-pinned | 100% | Error branch covered |
| `services/crosswalk_diff.py` | 66 | Unit-tested | 100% | Was already 100% |
| `services/join_builder.py` | 45 | Unit-tested | 100% | Was already 100% |
| `services/collection_manager.py` | 121 | Unit-tested | 100% | Was already 100% |
| `static/css/mission-control.css` | — | Compile-verified | — | Declarative stylesheet; browser parses and renders |
| `static/js/mission-control.js` | — | Manual-procedure-documented | — | Event handlers, fetch calls, inline editing — see §Manual below |
| `templates/base.html` | — | Unit-tested + Manual-procedure-documented | — | Rendered by every route test; JS interactions are manual |
| `templates/migration/readiness.html` | — | Unit-tested + Manual-procedure-documented | — | Rendered by GET /migration/readiness |
| `templates/migration/batch_progress.html` | — | Unit-tested + Manual-procedure-documented | — | Rendered by GET /migration/batch |
| `templates/migration/error_reconciler.html` | — | Unit-tested + Manual-procedure-documented | — | Rendered by GET /migration/reconciler |
| `templates/validation/duplicate_radar.html` | — | Unit-tested + Manual-procedure-documented | — | Rendered by GET /validation/duplicates |
| `templates/validation/external_id.html` | — | Unit-tested + Manual-procedure-documented | — | Rendered by GET /validation/external-ids |
| `templates/validation/contactpoint.html` | — | Unit-tested + Manual-procedure-documented | — | Rendered by GET /validation/contactpoints |
| `templates/soql/index.html` | — | Unit-tested + Manual-procedure-documented | — | Rendered by GET /soql |
| `templates/schema/crosswalk_diff.html` | — | Unit-tested + Manual-procedure-documented | — | Rendered by GET /schema/crosswalk |
| `templates/schema/org_diff.html` | — | Unit-tested + Manual-procedure-documented | — | Rendered by GET /schema/org-diff |
| `templates/data_ops/join_builder.html` | — | Unit-tested + Manual-procedure-documented | — | Rendered by GET /data-ops/join |
| `templates/settings/index.html` | — | Unit-tested + Manual-procedure-documented | — | Rendered by GET /settings |
| `Dockerfile` | — | Compile-verified | — | `docker build` validates; no executable logic |
| `requirements.txt` | — | Compile-verified | — | `pip install -r requirements.txt` validates |
| `k8s/manifest.yaml` | — | Compile-verified | — | `kubectl apply --dry-run` validates; Traefik enforces IngressRoute |

---

## Running the Test Suite

```bash
# All tests with coverage report
pytest tests/ --cov=. --cov-report=term-missing -v

# Quick pass/fail
pytest tests/ -q

# Single file
pytest tests/test_coverage_gaps.py -v
```

**Target: 100% coverage on all Python files** (one structurally exempt line:
`app.py:63`).

---

## Manual Test Procedures

The following procedures cover JavaScript-driven UI flows that cannot be exercised
by pytest. Perform these against a locally running instance (`python app.py`) or
the staging URL.

### Prerequisites

- App running at `http://localhost:5000` (or staging URL)
- `SF_MOCK=true` and `CONDUCTOR_MOCK=true` set (default dev behavior)
- Browser developer tools open to the Network tab

---

### Procedure 1 — Migration Tab: Run Readiness Check

**Goal:** Verify the readiness scorecard loads, runs, and updates the UI.

1. Navigate to `http://localhost:5000` — confirm redirect to `/migration/readiness`.
2. Verify the page loads with six check rows: SIS ID Coverage, Ethos GUID Coverage,
   ContactPoint Parent Links, Required Fields, Duplicate SIS IDs, Individual Links.
3. Click **Run Readiness Check**.
4. Observe the spinner appears and the button disables.
5. Within 3 seconds, confirm the scorecard updates: each row shows a status badge
   (green / amber / red) and a percentage value.
6. Confirm the overall score banner updates at the top.
7. Click **Run Again** — verify results refresh (timestamp in UI updates).
8. Navigate away and return — confirm the page loads without errors.

**Expected:** All six checks render with numeric percentages. Overall status reflects
the worst individual check.

---

### Procedure 2 — Validation Tab: Duplicate Scan and Merge Flow

**Goal:** Verify the duplicate radar scan runs and the merge action completes.

1. Navigate to `/validation/duplicates`.
2. Click **Scan for Duplicates**.
3. Confirm four strategy cards appear: Duplicate SIS ID, Duplicate Name + Birthdate,
   Duplicate Email, Duplicate Ethos GUID.
4. Expand a strategy card that shows `count > 0` — confirm the records table renders
   with IDs.
5. Check two records in the table and click **Merge Selected**.
6. Confirm a confirmation modal appears listing master and victim IDs.
7. Click **Confirm Merge**.
8. Observe the success toast notification. The merged victim row should disappear or
   be marked as merged.

**Expected:** Scan completes within 5 seconds. Merge returns success and updates the
UI without a page reload.

---

### Procedure 3 — Validation Tab: External ID Coverage

**Goal:** Verify the external ID coverage report renders correctly.

1. Navigate to `/validation/external-ids`.
2. Observe the page loads with an empty state or a **Run Coverage Check** button.
3. Click **Run Coverage Check** (or the coverage loads automatically).
4. Confirm the report shows coverage bars for `SIS_ID__c` and `Ethos_Guid__c`
   across all relevant objects (Account, ContactPointEmail, etc.).
5. Verify each bar shows a percentage and absolute counts.

**Expected:** Report renders with correct mock numbers matching the handoff doc
(SIS_ID coverage ~71%, Ethos_Guid ~91%).

---

### Procedure 4 — Validation Tab: ContactPoint Scanner

**Goal:** Verify the ContactPoint broken-link scan renders per-type results.

1. Navigate to `/validation/contactpoints`.
2. Click **Scan ContactPoints**.
3. Confirm three sections appear: ContactPointEmail, ContactPointPhone,
   ContactPointAddress.
4. Each section shows: total count, missing ParentId count, missing IndividualId
   count, status badge, and sample IDs.
5. Click on a sample ID — confirm it is copyable (click-to-copy or a link).

**Expected:** All three CP types render. Missing counts match mock data.

---

### Procedure 5 — SOQL Workbench: Run Query, Save, Edit Inline

**Goal:** Verify the SOQL editor executes queries and inline record editing works.

1. Navigate to `/soql`.
2. In the query editor, type: `SELECT Id, Name FROM Account LIMIT 5`
3. Click **Run**.
4. Confirm a results table renders with Id and Name columns and up to 5 rows.
5. Click **Save Query**, enter name "Test Account Query", click **Save**.
6. Confirm the query appears in the **Saved Queries** panel on the left.
7. Click the saved query to load it back into the editor.
8. Click the **Edit** icon on a Name cell in the results table.
9. Modify the value and press **Enter**.
10. Confirm the inline update call succeeds (green toast notification).
11. Click the trash icon next to the saved query and confirm deletion.

**Expected:** Query runs in under 2 seconds, saved queries persist in sidebar,
inline editing posts to `/soql/update` and reflects the change.

---

### Procedure 6 — Schema Tab: Upload Crosswalk CSV and Run Live Check

**Goal:** Verify the crosswalk upload and live validation flow.

1. Navigate to `/schema/crosswalk`.
2. Click **Upload CSV** and select a file with columns: `EDA_Field`, `EdCloud_Field`,
   `Object` (sample row: `Name,Name,Account`).
3. Confirm the mapping table populates with parsed rows.
4. Click **Run Live Check**.
5. Observe the table updates: each row shows a status (green checkmark for matched
   fields, red warning for mismatches or missing fields).

**Expected:** Upload succeeds in under 1 second. Live check results render per-row
statuses within 3 seconds.

---

### Procedure 7 — Schema Tab: Org Diff

**Goal:** Verify the org-diff tool compares schema between two orgs.

1. Navigate to `/schema/org-diff`.
2. Set **Left Org** to `dev` (current session org) and **Right Org** to `prod`.
3. Leave object list empty (all objects) or enter `Account`.
4. Click **Run Diff**.
5. Confirm results appear per-object: left-only fields, right-only fields,
   type mismatches, required mismatches.

**Expected:** Diff runs within 5 seconds. Result shows zero differences in mock mode
(both orgs use the same MockSalesforce schema).

---

### Procedure 8 — Data Ops: Configure Join and Run

**Goal:** Verify the join builder generates SQL and executes the join.

1. Navigate to `/data-ops/join`.
2. Fill in: SQL Table = `dbo.Students`, SQL Fields = `StudentId, FirstName`,
   SF Object = `Account`, SF Fields = `Id, SIS_ID__c`.
3. Set Join: SQL Field = `StudentId`, SF Field = `SIS_ID__c`.
4. Click **Build Query** — confirm the generated OpenQuery SQL appears in the
   output panel.
5. Click **Run Join** — confirm a results table appears with matched/unmatched rows.

**Expected:** Query builds immediately. Run completes within 5 seconds and renders
a results table with row count indicator.

---

### Procedure 9 — Settings Tab: Switch Org, Import Postman Collection, Run Collection

**Goal:** Verify org switching, collection import, and collection runner work end-to-end.

1. Navigate to `/settings`.
2. Click the **prod** org option — confirm the active org badge updates in the navbar
   and session is set.
3. Click **Import Collection**, upload a valid Postman v2.1 JSON file.
4. Confirm the collection appears in the collections list with its name and item count.
5. Click **Run** on the imported collection.
6. Confirm the results panel shows each request with status code and pass/fail badge.
7. Click the trash icon to delete the collection — confirm it is removed from the list.

**Expected:** Org switch updates in under 500ms. Collection import and run complete
without errors. Delete removes the entry without page reload.

---

## Coverage Summary

| Category | Files | Lines |
|---|---|---|
| Unit-tested (100%) | 22 Python files | All executable lines |
| Contract-pinned | 8 Python files | Key invariants in `test_contracts.py` |
| Compile-verified | 5 files | `routes/__init__.py`, `services/__init__.py`, `static/css/`, `Dockerfile`, `requirements.txt`, `k8s/manifest.yaml` |
| Manual-procedure-documented | 13 template/JS files | JS event handlers, fetch calls, browser rendering |
| Structurally exempt | 1 line | `app.py:63` (`__main__` guard) |

**Effective coverage: 99%+ measured, 100% justified.**
