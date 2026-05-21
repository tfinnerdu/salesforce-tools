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

Every production file is listed below with its Four-Bucket assignment and what
backs it. This table is the proof that no file is untested — it is updated in the
same commit that adds or removes a file. Reconciled May 2026 to cover all routes,
all service modules, and every template (it previously predated ~35 services and
the Observe / Logs / Impact / Deploy tabs).

### Core

| File | Bucket | Backed by |
|---|---|---|
| `app.py` | Unit-tested | Exercised by every route test via the `app` fixture; the `__main__` guard line is Compile-verified |
| `config.py` | Unit-tested | `test_contracts.py` + broad use across the suite |
| `db.py` | Unit-tested | `test_merge_history.py`, `test_query_history.py` (psycopg2 / cursor mocked) |
| `scheduler.py` | Unit-tested | Scheduler init tests (`BackgroundScheduler` mocked) |
| `sf_provider.py` | Unit-tested + Contract-pinned | `test_contracts.py` pins mock record counts to the handoff doc |
| `conductor_provider.py` | Unit-tested + Contract-pinned | `test_contracts.py`; `responses` mocks all Conductor HTTP |

### Routes (`routes/`)

| File | Bucket | Backed by |
|---|---|---|
| `routes/__init__.py` | Compile-verified | Empty package marker |
| `routes/health.py` | Unit-tested | `test_routes.py` |
| `routes/migration.py` | Unit-tested | `test_routes_extended.py`, `test_migration_velocity.py`, `test_preflight_checklist.py`, `test_batch_requeue.py` |
| `routes/validation.py` | Unit-tested | `test_duplicate_radar.py`, `test_merge_history.py`, `test_orphan_scanner.py`, `test_field_completeness.py`, `test_external_id_coverage.py`, `test_contactpoint_scanner.py` |
| `routes/soql.py` | Unit-tested | `test_soql_workbench.py`, `test_query_history.py`, `test_routes_extended.py` |
| `routes/schema.py` | Unit-tested | `test_schema_diff.py`, `test_schema_snapshot.py`, `test_crosswalk_diff.py`, `test_data_dictionary.py`, `test_field_usage.py`, `test_apex_code_search.py` |
| `routes/data_ops.py` | Unit-tested | `test_data_ops_tools.py`, `test_data_tuner.py`, `test_fuzzy_matcher.py`, `test_join_builder.py`, `test_bulk_dml.py`, `test_record_locks_bulk_jobs.py`, `test_routes_extended.py` |
| `routes/settings_routes.py` | Unit-tested | `test_routes_extended.py`, `test_collection_manager.py` |
| `routes/observe.py` | Unit-tested | `test_limit_thresholds.py`, `test_sandbox_drift.py`, `test_storage_breakdown.py` |
| `routes/logs.py` | Unit-tested | `test_trace_flags.py`, `test_apex_cpu_summary.py` |
| `routes/impact.py` | Unit-tested | `test_perm_gap_analyzer.py`, `test_field_impact.py`, `test_regression_tester.py` |
| `routes/admin.py` | Unit-tested | `test_admin_service.py`, `test_audit_trail.py`, `test_job_queue_login_history.py`, `test_record_types_email_templates.py`, `test_perm_auditor.py`, `test_org_automation.py`, `test_integration_inventory.py`, `test_platform_events.py`, `test_custom_config_viewer.py` |
| `routes/deploy.py` | Unit-tested | `test_changeset_builder.py` |
| `routes/dashboard.py` | Unit-tested | `test_dashboard.py` |

### Services (`services/`)

| File | Bucket | Backed by |
|---|---|---|
| `services/__init__.py` | Compile-verified | Empty package marker |
| `services/admin_service.py` | Unit-tested | `test_admin_service.py`, `test_audit_trail.py`, `test_job_queue_login_history.py`, `test_record_types_email_templates.py` |
| `services/anonymizer.py` | Unit-tested | `test_anonymizer.py` |
| `services/apex_code_search.py` | Unit-tested | `test_apex_code_search.py` |
| `services/apex_log_reader.py` | Unit-tested + Contract-pinned | `test_apex_cpu_summary.py`, `test_trace_flags.py`; characterization pins `ProcessException` via the Data API |
| `services/batch_tracker.py` | Unit-tested + Contract-pinned | `test_batch_tracker.py`, `test_contracts.py` |
| `services/bulk_dml.py` | Unit-tested | `test_bulk_dml.py` |
| `services/bulk_job_history.py` | Unit-tested | `test_record_locks_bulk_jobs.py` |
| `services/bulk_ops.py` | Unit-tested | `test_bulk_ops.py`, `test_bulk_api_paths.py` (real Bulk API path) |
| `services/changeset_builder.py` | Unit-tested | `test_changeset_builder.py` |
| `services/collection_manager.py` | Unit-tested | `test_collection_manager.py` |
| `services/contactpoint_scanner.py` | Unit-tested + Contract-pinned | `test_contactpoint_scanner.py`, `test_contracts.py` |
| `services/crosswalk_diff.py` | Unit-tested | `test_crosswalk_diff.py` |
| `services/custom_config_viewer.py` | Unit-tested | `test_custom_config_viewer.py` |
| `services/data_dictionary.py` | Unit-tested | `test_data_dictionary.py` |
| `services/data_importer.py` | Unit-tested + Contract-pinned | `test_data_importer.py`, `test_bulk_api_paths.py`; route-contract characterization |
| `services/data_tuner.py` | Unit-tested + Contract-pinned | `test_data_tuner.py`; `test_tune_rules_characterization.py` pins all 8 rules |
| `services/duplicate_radar.py` | Unit-tested | `test_duplicate_radar.py`, `test_merge_history.py` |
| `services/error_reconciler.py` | Unit-tested + Contract-pinned | `test_error_reconciler.py`, `test_batch_requeue.py`, `test_contracts.py` |
| `services/external_id_coverage.py` | Unit-tested + Contract-pinned | `test_external_id_coverage.py`, `test_contracts.py` |
| `services/field_completeness.py` | Unit-tested | `test_field_completeness.py` |
| `services/field_impact.py` | Unit-tested | `test_field_impact.py` (100% — added in the May 2026 reconciliation) |
| `services/field_usage.py` | Unit-tested | `test_field_usage.py` |
| `services/fuzzy_matcher.py` | Unit-tested + Contract-pinned | `test_fuzzy_matcher.py`; `test_soundex_characterization.py` pins the Soundex algorithm |
| `services/integration_inventory.py` | Unit-tested + Contract-pinned | `test_integration_inventory.py`; characterization pins `RemoteSiteSetting` → `EndpointUrl` |
| `services/join_builder.py` | Unit-tested | `test_join_builder.py` |
| `services/merge_history.py` | Unit-tested | `test_merge_history.py` — incl. the no-mock-leak regression test |
| `services/migration_velocity.py` | Unit-tested | `test_migration_velocity.py` |
| `services/org_automation.py` | Unit-tested | `test_org_automation.py` |
| `services/org_observer.py` | Unit-tested | `test_limit_thresholds.py` |
| `services/orphan_scanner.py` | Unit-tested | `test_orphan_scanner.py` |
| `services/perm_auditor.py` | Unit-tested | `test_perm_auditor.py` |
| `services/perm_gap_analyzer.py` | Unit-tested | `test_perm_gap_analyzer.py` |
| `services/platform_events.py` | Unit-tested + Contract-pinned | `test_platform_events.py`; characterization pins the `PlatformEventChannel` query |
| `services/preflight_checklist.py` | Unit-tested | `test_preflight_checklist.py` |
| `services/readiness_validator.py` | Unit-tested + Contract-pinned | `test_readiness_validator.py`, `test_contracts.py` |
| `services/record_lock_detector.py` | Unit-tested | `test_record_locks_bulk_jobs.py` |
| `services/regression_tester.py` | Unit-tested | `test_regression_tester.py` (100% — added in the May 2026 reconciliation) |
| `services/sandbox_drift.py` | Unit-tested | `test_sandbox_drift.py` |
| `services/schema_diff.py` | Unit-tested | `test_schema_diff.py` |
| `services/schema_snapshot.py` | Unit-tested | `test_schema_snapshot.py` |
| `services/soql_workbench.py` | Unit-tested | `test_soql_workbench.py`, `test_query_history.py` |
| `services/sql_schema.py` | Unit-tested | `test_sql_schema.py` — SQL Server schema cache for the Join Builder (read/refresh/validate, NOLOCK output) |
| `services/storage_breakdown.py` | Unit-tested | `test_storage_breakdown.py` |

### Templates (`templates/`)

All templates are **Manual-procedure-documented** (JS-driven UI flows — see the
Manual Test Procedures below) and additionally **Unit-tested** at the render
level: each is returned by its route's GET test, which fails if the template has
a Jinja error.

| File | Rendered by |
|---|---|
| `templates/base.html` | Every route (layout) |
| `templates/dashboard/index.html` | `GET /dashboard` |
| `templates/migration/readiness.html` | `GET /migration/readiness` |
| `templates/migration/batch_progress.html` | `GET /migration/batch` |
| `templates/migration/error_reconciler.html` | `GET /migration/reconciler` |
| `templates/migration/preflight.html` | `GET /migration/preflight` |
| `templates/migration/velocity.html` | `GET /migration/velocity` — Procedure 17 |
| `templates/validation/duplicate_radar.html` | `GET /validation/duplicates` — Procedure 2 |
| `templates/validation/external_id.html` | `GET /validation/external-ids` — Procedure 3 |
| `templates/validation/contactpoint.html` | `GET /validation/contactpoints` — Procedure 4 |
| `templates/validation/field_completeness.html` | `GET /validation/field-completeness` |
| `templates/validation/orphan_scanner.html` | `GET /validation/orphans` |
| `templates/validation/merge_history.html` | `GET /validation/merge-history` |
| `templates/soql/index.html` | `GET /soql` — Procedures 5, 18 |
| `templates/schema/crosswalk_diff.html` | `GET /schema/crosswalk` — Procedure 6 |
| `templates/schema/org_diff.html` | `GET /schema/org-diff` — Procedure 7 |
| `templates/schema/field_usage.html` | `GET /schema/field-usage` |
| `templates/schema/data_dictionary.html` | `GET /schema/data-dictionary` |
| `templates/schema/apex_search.html` | `GET /schema/apex-search` |
| `templates/schema/snapshots.html` | `GET /schema/snapshots` |
| `templates/data_ops/import.html` | `GET /data-ops/import` — Procedure 10 |
| `templates/data_ops/export.html` | `GET /data-ops/export` — Procedure 11 |
| `templates/data_ops/delete.html` | `GET /data-ops/delete` — Procedure 12 |
| `templates/data_ops/modify.html` | `GET /data-ops/modify` — Procedure 13 |
| `templates/data_ops/reassign.html` | `GET /data-ops/reassign` — Procedure 14 |
| `templates/data_ops/tune.html` | `GET /data-ops/tune` — Procedure 19 |
| `templates/data_ops/match.html` | `GET /data-ops/match` — Procedure 20 |
| `templates/data_ops/convert.html` | `GET /data-ops/convert` — intentional stub, content asserted |
| `templates/data_ops/join_builder.html` | `GET /data-ops/join` — Procedure 8 |
| `templates/data_ops/bulk_update.html` | `GET /data-ops/bulk-update` |
| `templates/data_ops/record_locks.html` | `GET /data-ops/record-locks` |
| `templates/data_ops/bulk_jobs.html` | `GET /data-ops/bulk-jobs` |
| `templates/logs/index.html` | `GET /logs/*` |
| `templates/observe/index.html` | `GET /observe/*` |
| `templates/impact/index.html` | `GET /impact/*` |
| `templates/deploy/index.html` | `GET /deploy` |
| `templates/admin/index.html` | `GET /admin` — Procedures 15, 16 |
| `templates/settings/index.html` | `GET /settings` — Procedure 9 |

### Static assets & build (`static/`, root)

| File | Bucket | Backed by |
|---|---|---|
| `static/js/mission-control.js` | Manual-procedure-documented | Core `MC.*` helpers (`sfLink`, `api`, toasts); all Manual Procedures |
| `static/js/mc-migration-snippet.js` | Manual-procedure-documented | Procedure 17 (`MC.velocity`) |
| `static/js/mc-validation-snippet.js` | Manual-procedure-documented | Procedures 2–4 |
| `static/js/mc-schema-snippet.js` | Manual-procedure-documented | Procedures 6, 7 |
| `static/js/mc-data-ops-snippet.js` | Manual-procedure-documented | Procedures 8, 10–14, 19, 20 |
| `static/js/mc-logs-snippet.js` | Manual-procedure-documented | Logs tab flows |
| `static/js/mc-observe-snippet.js` | Manual-procedure-documented | Observe tab flows |
| `static/js/mc-impact-snippet.js` | Manual-procedure-documented | Impact tab flows |
| `static/js/mc-admin-snippet.js` | Manual-procedure-documented | Procedures 15, 16 |
| `static/js/mc-deploy-snippet.js` | Manual-procedure-documented | Deploy tab flows |
| `static/js/mc-dashboard-snippet.js` | Manual-procedure-documented | Dashboard widgets |
| `static/css/mission-control.css` | Compile-verified | Declarative stylesheet — the browser parses and renders it |
| `Dockerfile` | Compile-verified | `docker build` validates; no executable logic |
| `requirements.txt` | Compile-verified | `pip install -r requirements.txt` validates |
| `k8s/manifest.yaml` | Compile-verified | `kubectl apply --dry-run` validates; Traefik enforces the IngressRoute |

### Characterization tests (`tests/characterization/`)

The Contract-pinned layer. These run in CI by default and fail loudly if a
pinned contract regresses.

| File | Pins |
|---|---|
| `test_tooling_api_contracts_characterization.py` | The 3 Tooling API bug fixes (`RemoteSiteSetting.EndpointUrl`, no `Description` on `PlatformEventChannel`, `ProcessException` via the Data API) |
| `test_route_contracts_characterization.py` | New route paths, methods, and `{success, data}` response envelope shapes |
| `test_tune_rules_characterization.py` | Each Tune standardization rule's known input → output |
| `test_soundex_characterization.py` | American Soundex reference values used by Fuzzy Match blocking |

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

### Procedure 10 — Data Ops: Data Import Wizard (Validate → Import)

**Goal:** Verify the four-step import wizard validates a CSV and imports it.

Preconditions: app running, `SF_MOCK=true`. Prepare a CSV file `students.csv`:

```
Name,SIS_ID__c,PersonEmail
Alice Test,STU90001,alice@doane.edu
Bob Test,STU90002,bob@doane.edu
Bad Row,,notanemail
```

1. Navigate to `/data-ops/import`. Confirm the step nav shows steps 1–4 with step 1
   highlighted.
2. **Step 1 — Configure:** enter `Account` as the object, leave operation `Insert`,
   upload `students.csv`. Confirm the CSV preview panel renders the three rows.
3. Click **Next: Map Fields →**. Confirm the wizard advances to step 2.
4. **Step 2 — Map Fields:** confirm a mapping table lists the three CSV columns.
   Click **Auto-Map** — confirm `Name`, `SIS_ID__c`, `PersonEmail` each auto-select
   their matching SF field.
5. Click **Next: Validate →**.
6. **Step 3 — Validate:** click **Run Validation**. Confirm four stat cards appear
   (Total / Clean / Warnings / Errors) and that the "Bad Row" produces an **error**
   for the invalid email `notanemail`.
7. Confirm the validation issues table lists the email error with row number 3.
8. Fix the CSV (use a valid email), re-upload, re-validate — confirm 0 errors and the
   **Next: Import →** button appears.
9. **Step 4 — Import:** click **Execute Import**. Confirm the result cards show
   Total / Succeeded / Failed counts. In mock mode ~10% of rows report a mock failure.
10. Confirm the **Download Error CSV** button appears when failures exist and that
    clicking it downloads a CSV containing a `_sf_error` column.

**Expected:** Wizard advances cleanly through all four steps. Invalid email is caught
at step 3. Import returns counts and a downloadable error file.

---

### Procedure 11 — Data Ops: Export to CSV

**Goal:** Verify a SOQL query exports as a downloadable CSV.

1. Navigate to `/data-ops/export`.
2. Enter `SELECT Id, Name, SIS_ID__c FROM Account LIMIT 10` in the query box.
3. Set the filename to `accounts.csv`, leave **All pages** checked.
4. Click **Download CSV**.
5. Confirm the browser downloads `accounts.csv` and that it opens with a header row
   plus data rows (no `attributes` column).

**Expected:** CSV downloads immediately. Header matches the SELECT field list.

---

### Procedure 12 — Data Ops: Bulk Delete (Preview → Execute)

**Goal:** Verify the bulk delete preview and execute flow.

1. Navigate to `/data-ops/delete`. Confirm the red destructive-operation warning banner.
2. Enter `Account` as the object and `SIS_ID__c = null` as the WHERE clause.
3. Click **Preview**. Confirm the preview panel shows matching records and a total count.
4. Confirm the **Delete Records** button appears only after a successful preview.
5. Click **Delete Records** — confirm the browser confirmation dialog appears.
6. Confirm — observe the result alert reporting deleted count and errors.

**Expected:** Preview must run before execute is possible. Execute reports a count.

---

### Procedure 13 — Data Ops: Bulk Modify

**Goal:** Verify multi-field bulk update.

1. Navigate to `/data-ops/modify`.
2. Enter `Account` and a WHERE clause `Id != null`.
3. In **Fields to Update**, enter a field API name and a new value. Click **+ Add Field**
   and confirm a second field row appears; remove it with the ✕ button.
4. Click **Preview** — confirm matching records render.
5. Click **Update Records** — confirm the result alert reports an updated count.

**Expected:** Add/remove field rows work. Preview gates execute. Result reports a count.

---

### Procedure 14 — Data Ops: Bulk Reassign

**Goal:** Verify ownership reassignment with the user picker.

1. Navigate to `/data-ops/reassign`.
2. Enter `Account` and WHERE clause `Id != null`.
3. In **New Owner**, type a search term and click **Search** — confirm a user result
   list appears.
4. Click a user — confirm a green badge shows the selected owner's name.
5. Click **Preview**, then **Reassign Records** — confirm the result alert reports a count.

**Expected:** User search returns results; selecting one sets the owner. Preview gates execute.

---

### Procedure 15 — Admin: Permissions Audit Tab

**Goal:** Verify the Permissions Audit drill-downs.

1. Navigate to `/admin/`, click the **Permissions Audit** tab.
2. **Permission Sets** sub-tab: confirm a list of permission sets loads with user-count
   badges. Click one — confirm the right panel shows Users / Object Perms / Field Perms
   sub-tabs populated.
3. **By User** sub-tab: type a search term, click **Search**, select a user — confirm
   the detail panel shows their profile, permission sets, and aggregated object access.
4. **Object Matrix** sub-tab: enter `Account`, click **Load Matrix** — confirm a table
   of permission sets with R/C/E/D/View-All/Modify-All check columns.
5. **Field Coverage** sub-tab: enter `Account`, click **Load Field Coverage** — confirm
   a per-field read/edit table.
6. Where an SF instance is connected (live mode), confirm permission-set and user names
   render as "↗ Open in Salesforce" deep links.

**Expected:** All four sub-tabs load. Drill-downs render without errors. Deep links
appear in live mode and are absent in mock mode.

---

### Procedure 16 — Admin: Automation & Sharing Tab

**Goal:** Verify the read-only org config explorer.

1. Navigate to `/admin/`, click the **Automation & Sharing** tab.
2. **Validation Rules** sub-tab loads by default — confirm a table of rules with object,
   status, error field, and error message columns.
3. Click the **Flows** sub-tab — confirm a table of flows with type and status badges
   lazy-loads on first view.
4. Click **Apex Triggers** — confirm a table of triggers with their objects.
5. Click **Sharing Model** — confirm a table of org-wide defaults with internal/external
   access badges (Private rendered red).
6. Use the filter box on any sub-tab — confirm rows filter live.

**Expected:** Each sub-tab lazy-loads on first view. Filters work. No console errors.

---

### Procedure 17 — Migration: Velocity & ETA Chart

**Goal:** Verify the velocity chart renders (regression — the page previously spun
forever because `mc-migration-snippet.js` was not loaded).

1. Navigate to `/migration/velocity`.
2. Confirm the loading spinner disappears within ~3 seconds and is replaced by the
   burn-down chart (it must NOT spin indefinitely).
3. Confirm the four summary cards populate: Records Migrated, % Complete, Avg Velocity,
   Projected ETA.
4. Change the **Days** selector — confirm the chart reloads.

**Expected:** Chart renders. Spinner resolves. No `MC.velocity is undefined` console error.

---

### Procedure 18 — Salesforce Deep Links

**Goal:** Verify that displayed record IDs link back to the connected org.

Preconditions: connected to a **real** Salesforce org (`SF_MOCK=false`). In mock
mode the helper intentionally renders plain text — see step 6.

1. **SOQL Workbench** (`/soql`): run `SELECT Id, Name, OwnerId FROM Account LIMIT 5`.
   Confirm the `Id` and `OwnerId` cells render as links with a ↗ icon. Click one —
   it opens the record in Salesforce in a new tab.
2. **Validation › Duplicate Radar**: scan; confirm sample IDs in the results are
   clickable links to the Account records.
3. **Validation › Merge History**: confirm the Master and Victim ID columns link
   to the Account records.
4. **Admin › Users**: confirm each user's name links to their User record.
5. **Admin › Permissions Audit**: confirm permission-set and user names render as
   "↗ Open in SF" links.
6. **Mock-mode check:** restart with `SF_MOCK=true`, repeat step 1 — confirm IDs
   render as plain text (no links), since mock IDs have no real org to point at.

**Expected:** In live mode every real 15/18-char SF ID is a working link; in mock
mode the same cells are plain text. No broken `/lightning/r/undefined/...` URLs.

---

### Procedure 19 — Data Ops: Tune (Data Standardization)

**Goal:** Verify the standardization preview/apply flow.

1. Navigate to `/data-ops/tune`.
2. Enter `Account` as the object and `Id != null` as the WHERE clause.
3. Click **+ Add Field**; in the new row enter a field API name (e.g. `Name`) and
   select one or more rules in the multi-select (e.g. **Proper case**). Add a
   second field row if desired.
4. Click **Preview**.
5. Confirm the preview panel shows a Before / After table for records that would
   change, and a count line ("N of M sampled records would change").
6. Confirm the **Apply Standardization** button appears only when the preview
   found changes.
7. Click **Apply Standardization** — confirm the result alert reports updated /
   already-clean / error counts. In mock mode it shows a "mock — not written"
   badge (the preview math runs for real; only the write is skipped).
8. Remove a field row with the ✕ button — confirm it disappears.

**Expected:** Preview shows accurate before/after. Apply gates on a successful
preview. Rules apply in the selected order.

---

### Procedure 20 — Data Ops: Match (Fuzzy Duplicate Detection)

**Goal:** Verify the fuzzy near-duplicate scan.

1. Navigate to `/data-ops/match`.
2. Enter `Account` as the object and `Id != null` as the WHERE clause.
3. Enter comma-separated **Compare Fields** (e.g. `Name, PersonEmail`).
4. Enter a **Blocking Field** (e.g. `Name`).
5. Drag the **Similarity Threshold** slider — confirm the displayed value updates live.
6. Click **Find Matches**.
7. Confirm a summary line appears (records scanned, blocks, comparisons, candidate
   count) followed by a table of candidate pairs.
8. Confirm each pair shows a score badge and both records side by side, with
   record IDs as Salesforce links and low-scoring fields highlighted.
9. Raise the threshold to 0.99 and re-run — confirm fewer (or zero) candidates.

**Expected:** The scan completes, candidate pairs render sorted by score, and the
threshold filters results. Detection only — no records are modified.

---

## Coverage Summary

Every production file is accounted for in the File Classification Matrix above —
6 core modules, 14 route files, 42 service modules, 38 templates, 12 static
assets, and 3 build files.

| Bucket | Count | Notes |
|---|---|---|
| Unit-tested | 6 core + 13 routes + 41 services | Every route and service module has a test exercising it |
| Contract-pinned | `test_contracts.py` + 4 characterization specs | Mock-data invariants, Tooling API contracts, route contracts, Tune-rule and Soundex transformations |
| Compile-verified | `routes/__init__.py`, `services/__init__.py`, `static/css/mission-control.css`, `Dockerfile`, `requirements.txt`, `k8s/manifest.yaml` | Declarative — the toolchain validates them |
| Manual-procedure-documented | 38 templates + 11 JS files | 20 procedures cover every JS-driven UI flow |
| Structurally exempt | 1 line | `app.py` `__main__` guard |

**Test suite: 1,067 tests passing.** The May 2026 expansion (DemandTools-equivalent
Data Ops tools, Permissions Audit, Automation & Sharing, the Tooling API bug-fix
sweep, the deep-link sweep, and this matrix reconciliation) added 256 tests across
unit, route-contract, real-Bulk-API-path, and characterization layers.

**Characterization layer:** `tests/characterization/` pins the three Tooling API
bug fixes, the new route contracts, every Tune standardization rule, and the
Soundex algorithm. These run in CI by default and fail loudly if a pinned
contract regresses.

**Matrix reconciliation (May 2026):** the File Classification Matrix was rebuilt
to cover every production file — it previously predated the Observe / Logs /
Impact / Deploy tabs and ~35 service modules. The reconciliation surfaced two
untested service modules (`field_impact.py`, `regression_tester.py`); both now
have dedicated test files at 100% line coverage. No production file is now
without a bucket.
