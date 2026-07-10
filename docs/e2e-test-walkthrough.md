# SF Mission Control — End-to-End Test Walkthrough

Manual steps and expected outcomes for verifying each feature from outside the codebase. Run against local dev environment unless noted.

---

## Setup

```powershell
.\start-local.ps1
# App starts at http://localhost:5000
```

The app supports two startup modes — pick one before running the walkthrough:

1. **Real mode (default).** Set valid Salesforce and Conductor credentials in
   `.env` and leave `SHOW_MOCK=false` (or unset). Every step below runs
   against the connected org and Conductor. Use a non-production org (`dev` or
   `sandbox`) so the destructive write steps are safe.
2. **Demo mode (credential-free).** Set `SHOW_MOCK=true` in `.env`. The whole
   app — every Salesforce call and every Conductor call — is swapped onto the
   in-process `MockSalesforce` / `MockConductorClient` layer, so no real
   credentials are required. The destructive write steps (Bulk Delete /
   Modify / Reassign, Anonymizer live run, merge, trigger-bypass toggle,
   log/trace-flag deletes, etc.) are all safe to run in this mode — they hit
   the mock providers, the `MC.confirm()` modals still appear (the
   confirmation UX is itself demoable), and synthetic counts come back. This
   is the right mode for stakeholder demos and onboarding new contributors.

When `SHOW_MOCK=true`, the navbar shows an amber `MOCK` badge and every
card-header shows a `MOCK DATA` chip — see **Mock/Live Signal** below.

---

## Health Endpoint

**URL:** `GET /health`

**Steps:**
1. `curl http://localhost:5000/health`

**Expected:**
```json
{"status": "ok", "service": "sf-mission-control", "version": "1.0.0", "uptime_seconds": 1.23, "db_status": "unavailable"}
```
- `status` is `"ok"` or `"degraded"` — never 500
- `"sf-mission-control"` service name is always present
- `uptime_seconds` increases on successive calls

---

## Navigation

**Steps:**
1. Open `http://localhost:5000` in browser
2. Verify redirect to `/migration/readiness`
3. Click each top nav tab: Migration, Validation, SOQL, Schema, Data Ops, Settings
4. Verify active tab has orange underline
5. Change org picker from "dev" to "prod"
6. Verify org badge updates to "PROD" without page reload

**Expected:** Each tab loads without 500 errors. Org switch shows toast "Switched to PROD org".

---

## Mock/Live Signal

**Steps:**
1. Start the app with `SHOW_MOCK=true` in `.env`. Open `http://localhost:5000`.
2. Verify the navbar shows an amber **`MOCK`** badge (instead of the green
   `LIVE` badge).
3. Verify every card-header on the dashboard, SOQL, and Migration pages renders
   a small **`MOCK DATA`** chip.
4. Stop the app, set `SHOW_MOCK=false` (or unset it) with real credentials
   configured, and restart.
5. Verify the navbar now shows a green **`LIVE`** badge and no `MOCK DATA`
   chips are present.
6. With `SHOW_MOCK=false` and an org that has no credentials configured,
   switch to that org and trigger any data-loading route — the app boots but
   the route returns a clean error envelope (no silent mock fallback).

**Expected:** The mode is unmissable from the navbar — amber `MOCK` when
`SHOW_MOCK=true`, green `LIVE` otherwise. The K8s / Docker manifests pin
`SHOW_MOCK=false` explicitly so production can never accidentally serve mock
data.

---

## Migration > Readiness Score

**URL:** `/migration/readiness`

**Steps:**
1. Navigate to Migration > Readiness Score (default tab)
2. Observe page loads with "Last run: Never" and empty scorecard
3. Click "Run Now"
4. Verify loading spinner appears during run
5. After completion, scorecard fills with 6+ check rows

**Expected scorecard:**

| Check | Expected |
|---|---|
| PersonAccount SIS_ID__c | Coverage % with a color-coded status badge |
| Ethos GUID coverage | Coverage % with a color-coded status badge |
| ContactPoint parents | Count of broken parent links |
| Duplicate detection | Count of duplicate groups |
| Individual links | Coverage % / count |
| Required fields | Count of records missing required fields |

Each row reflects the connected org's actual data.

- Overall banner shows a composite readiness % and go-live status
- "Last run: [timestamp]" updates
- Click "Export" triggers browser print dialog

**Regression check:** Run a second time — "Last run" timestamp updates.

---

## Migration > Batch Progress

**URL:** `/migration/batch`

**Steps:**
1. Navigate to Migration > Batch Progress
2. Enter workflow name: `EDA_Person_Sync`
3. Click "Load Status"
4. Observe progress bar and stats grid

**Expected:**
- Progress bar reflects the batch's actual completion %
- Completed / Failed / Running / Queued counts populate from Conductor
- ETA is computed from the current processing rate
- Failure breakdown table groups failures by error type with counts

5. Toggle "Auto-refresh" — verify polling starts (console shows periodic fetches)
6. Click "Re-run failures" for an error-type row — confirm the `MC.confirm`
   dialog appears, then confirm
7. Verify success toast

---

## Migration > Error Reconciler

**URL:** `/migration/reconciler`

**Steps:**
1. Navigate to Migration > Error Reconciler
2. Enter workflow: `EDA_Person_Sync`, select "Last 24h"
3. Click Refresh
4. Verify error category cards appear, one per error type

**Expected cards:**
- One card per Salesforce error code returned by the connected org's failed
  workflows, each color-coded by severity with a record count and a retry hint

5. Click "Show all SIS IDs" on a card — list expands
6. Click "Re-run" on a card — confirm the `MC.confirm` dialog appears, confirm,
   and a toast reports the affected workflows queued

---

## Validation > Duplicate PersonAccount Radar

**URL:** `/validation/duplicates`

**Steps:**
1. Navigate to Validation > Duplicate Radar
2. Click "Run Scan"

**Expected:**
- One strategy card per match type — Same SIS_ID, Same Name+DOB, Same Email,
  Same Ethos GUID — each with a count and color-coded status from the connected
  org's data

3. Click "Merge" on a row
4. Verify the merge modal opens with master/victim ID fields and an
   acknowledgement checkbox; the confirm button stays disabled until it is ticked
5. Tick the checkbox and click Confirm — verify success toast
6. Click "Export CSV" — CSV downloads with strategy results

---

## Validation > External ID Coverage

**URL:** `/validation/external-ids`

**Steps:**
1. Navigate to Validation > External ID Coverage
2. Click "Run Report"

**Expected table:**
- One row per relevant object (Account, the three ContactPoint objects,
  IndividualApplication, etc.) showing total records, `SIS_ID__c` coverage, and
  `Ethos_Guid__c` coverage, each with a color-coded badge — all from the
  connected org's actual data

3. Click the Account SIS_ID__c row — drill-down panel opens
4. Verify panel shows sample record IDs with missing SIS_ID__c
5. Click "Export CSV" — downloads missing records list

---

## Validation > ContactPoint Integrity

**URL:** `/validation/contactpoints`

**Steps:**
1. Navigate to Validation > ContactPoint Integrity
2. Click "Scan Now"

**Expected:**
- Three cards: Email, Phone, Address
- Each shows "Missing Parent: X" with red badge if > 0
- Each shows "Missing Individual: X" with red badge if > 0
- Total issues banner shows combined count

---

## SOQL Workbench

**URL:** `/soql`

**Steps:**
1. Navigate to SOQL tab
2. Object Explorer sidebar: type "Account" in search box — list filters
3. Click "Account" — field list populates below
4. Right-click (or click) "SIS_ID__c" field — appended to editor (or adds to current query)
5. Type query in editor:
   ```sql
   SELECT Id, Name, SIS_ID__c FROM Account WHERE IsPersonAccount = true LIMIT 20
   ```
6. Click "Run ▶"

**Expected:**
- Results table appears with columns: Id | Name | SIS_ID__c
- Row count shows the page size and the total matching the connected org
- Download CSV button enabled

7. Click "Run All Pages" — row count shows the full result set
8. Double-click a cell in the results table — inline edit input appears
9. Type new value, press Enter — the `MC.confirm` dialog appears; confirm and a
   "Record updated" toast follows
10. Press Escape — edit cancelled, original value restored

11. Type `SELECT COUNT() FROM Account WHERE IsPersonAccount = true`
12. Click "Explain Plan" — plan panel shows cardinality and index info

13. Click "Save Query", name it "All PersonAccounts"
14. Saved query appears in dropdown
15. Select it from dropdown — textarea populates

---

## Schema > Crosswalk Field Diff

**URL:** `/schema/crosswalk`

**Steps:**
1. Navigate to Schema > Crosswalk Diff
2. Create a test CSV file:
   ```
   eda_object,eda_field,ec_object,ec_field,status
   Contact,hed__Gender__c,Account,Gender__pc,Mapped
   Contact,hed__FERPA_Date__c,Account,FERPADate__pc,Mapped
   hed__Address__c,MailingStreet,ContactPointAddress,Street,Mapped
   ```
3. Upload file via drag-drop or file picker
4. Verify mapping table populates with 3 rows
5. Click "Run Live Check"

**Expected results:**
- Gender: EDA ~75%, EC ~44%, gap highlighted in red
- FERPA Date: coverage matches (green)
- Street: coverage shown

6. Click a gap row — modal opens with sample record IDs

---

## Schema > Org Schema Diff

**URL:** `/schema/org-diff`

**Steps:**
1. Navigate to Schema > Org Diff
2. Left org: dev (active), Right org: prod
3. Select objects: Account, ContactPointEmail
4. Click "Run Diff"

**Expected:**
- Accordion panel per object
- Each panel shows: X fields left-only, Y fields right-only, Z type mismatches —
  reflecting the actual schema gap between the two connected orgs

5. Verify export button available

---

## Schema > Org Metadata Diff

**URL:** `/schema/metadata-diff`

**Steps:**
1. Navigate to Schema > Org Metadata Diff.
2. Left org is the active org (badge); Right org defaults to `prod`.
3. Leave all five metadata-type checkboxes checked (Apex Classes, Apex
   Triggers, Flows, Validation Rules, Custom Objects).
4. Click **Run Diff**.
5. **Expected:** a summary banner reports the total difference count, and one
   accordion panel renders per metadata type with an L/R count and a diff badge.
6. Expand a panel — Left-only / Right-only / Modified sections list component
   names with detail.
7. **Expected:** the diff reflects the real metadata gap between the two
   connected orgs — left-only, right-only, and modified components. Comparing an
   org against itself shows zero differences.

Unlike Org Schema Diff (fields), this compares deployable metadata components.

---

## Schema > Record Inspector

**URL:** `/schema/inspect`

**Steps:**
1. Navigate to Schema > Record Inspector.
2. Enter `Account` in Object API Name.
3. With **Salesforce ID** mode, enter any ID value and click **Inspect**.
4. **Expected:** field table renders with Name / Label / Type / Value columns; null values
   show as italic `null`; field count badge appears.
5. Type into **Filter fields** — table narrows and count updates live.
6. Switch to **External ID** mode — confirm External ID Field input appears and the
   label changes to "External ID Value".
7. Enter `SIS_ID__c` and a SIS ID value, click **Inspect**.
8. **Expected:** results bar shows `ext id: SIS_ID__c` mode badge; the record's
   queryable fields render, including `SIS_ID__c`, `Ethos_Guid__c`, and
   `IsPersonAccount`.

---

## Data Ops > SF ↔ SQL Join Builder

**URL:** `/data-ops/join`

**Steps:**
1. Navigate to Data Ops > Join Builder
2. SQL Table: `dbo.Students`
3. SQL Fields: `StudentId, FirstName, LastName`
4. SF Object: select `Account`
5. SF Fields: `Id, SIS_ID__c, PersonEmail`
6. SQL Join Field: `StudentId`, SF Join Field: `SIS_ID__c`
7. Click "Build Query"

**Expected SQL:**
```sql
SELECT s.StudentId, s.FirstName, s.LastName,
       sf.Id, sf.SIS_ID__c, sf.PersonEmail
FROM dbo.Students s
JOIN OPENQUERY(SALESFORCE, '
    SELECT Id, SIS_ID__c, PersonEmail
    FROM Account
    WHERE IsPersonAccount = true
') sf ON sf.SIS_ID__c = s.StudentId
```

8. Click "Copy to clipboard" — toast confirms copy
9. Click "Run here (Python fallback)" — since SQL Server not configured, shows friendly error with setup instructions

---

## Data Ops > Data Import Wizard

**URL:** `/data-ops/import`

**Steps:**
1. Navigate to Data Ops > Import. The four-step wizard nav (Configure / Map Fields /
   Validate / Import) renders with step 1 active.
2. Step 1: object `Account`, operation `Insert`, upload a CSV with columns
   `Name,SIS_ID__c,PersonEmail` and at least one row with a bad email. CSV preview renders.
3. Click "Next: Map Fields →". Step 2 shows a column→field mapping table.
4. Click "Auto-Map" — columns auto-bind to matching SF fields.
5. Click "Next: Validate →", then "Run Validation".
6. **Expected:** four stat cards (Total / Clean / Warnings / Errors). The bad-email row
   is flagged as an **error** in the issues table.
7. With a clean CSV, the "Next: Import →" button appears; advancing to step 4 and
   clicking "Execute Import" returns Total / Succeeded / Failed counts.
8. When failures exist, "Download Error CSV" downloads a file with a `_sf_error` column.

---

## Data Ops > Export

**URL:** `/data-ops/export`

**Steps:**
1. Navigate to Data Ops > Export.
2. Enter `SELECT Id, Name, SIS_ID__c FROM Account LIMIT 10`, filename `accounts.csv`.
3. Click "Download CSV".
4. **Expected:** browser downloads `accounts.csv` with a header row and data rows,
   no `attributes` column.

---

## Data Ops > Bulk Delete / Modify / Reassign

**URLs:** `/data-ops/delete`, `/data-ops/modify`, `/data-ops/reassign`

**Steps (Delete):**
1. Navigate to Data Ops > Delete. A red destructive-operation banner is shown.
2. Object `Account`, WHERE `SIS_ID__c = null`. Click "Preview".
3. **Expected:** matching records + total count render. The "Delete Records" button
   only appears after a successful preview.
4. Click "Delete Records" → the `MC.confirm` dialog appears with an
   acknowledgement checkbox; the confirm button stays disabled until it is ticked.
   Tick it and confirm → result alert with deleted count. (See the dedicated
   confirmation-dialog walkthrough below.)

**Steps (Modify):**
1. Navigate to Data Ops > Modify. Object `Account`, WHERE `Id != null`.
2. Add one or more field/value rows. Click "Preview", then "Update Records".
3. **Expected:** result alert reports an updated count.

**Steps (Reassign):**
1. Navigate to Data Ops > Reassign. Object `Account`, WHERE `Id != null`.
2. Search for a user, select one (green owner badge appears).
3. Click "Preview", then "Reassign Records".
4. **Expected:** result alert reports a reassigned count.

---

## Data Ops > Tune (Data Standardization)

**URL:** `/data-ops/tune`

**Steps:**
1. Navigate to Data Ops > Tune.
2. Object `Account`, WHERE clause `Id != null`.
3. Click **+ Add Field**; enter `Name` and select the **Proper case** rule.
4. Click **Preview**.
5. **Expected:** a Before / After table for records that would change, plus a
   count line ("N of M sampled records would change").
6. The **Apply Standardization** button appears only when the preview found changes.
7. Click **Apply Standardization** — the `MC.confirm` dialog appears; confirm and
   the result alert reports updated / already-clean / error counts written to the
   connected org.

---

## Data Ops > Match (Fuzzy Duplicate Detection)

**URL:** `/data-ops/match`

**Steps:**
1. Navigate to Data Ops > Match.
2. Object `Account`, WHERE clause `Id != null`.
3. Compare Fields `Name, PersonEmail`; Blocking Field `Name`.
4. Adjust the Similarity Threshold slider — the displayed value updates live.
5. Click **Find Matches**.
6. **Expected:** a summary line (records scanned, Soundex blocks, comparisons,
   candidate count) followed by a table of candidate pairs sorted by score, each
   showing both records side by side with linked IDs.
7. Raise the threshold and re-run — fewer candidates are returned.

Detection only — no records are modified. Merge confirmed pairs via
Validation > Duplicate Radar.

---

## Data Ops > Data Backup (CSV Snapshot)

**URL:** `/data-ops/backup`

**Steps:**
1. Navigate to Data Ops > Backup.
2. Confirm the **Objects to back up** textarea pre-fills with the default object
   list (`Account`, `Contact`, `Individual`, the three ContactPoint objects).
3. Click **Run Backup Now**.
4. **Expected:** a result panel reports a status (`success` or `partial`), an
   object count, and a total record count.
5. The **Backup History** table shows the run with trigger `manual`, status,
   object count, and record count.
6. Click **Download ZIP** — a `.zip` downloads containing one `.csv` per object.
7. Click **Refresh** — the history table reloads.

A backup is the recovery point for the destructive Data Ops tools. With no DB
configured the run still produces an in-memory manifest but is not retained;
with a DB it persists and old runs are pruned to `BACKUP_RETAIN`.

---

## Admin > Permissions Audit

**URL:** `/admin/` → Permissions Audit tab

**Steps:**
1. Open Admin, click the "Permissions Audit" tab.
2. **Permission Sets:** list loads with user-count badges; clicking one shows
   Users / Object Perms / Field Perms.
3. **By User:** search, select a user → profile + permission sets + object access.
4. **Object Matrix:** enter `Account` → R/C/E/D/View-All/Modify-All table.
5. **Field Coverage:** enter `Account` → per-field read/edit table.

**Expected:** all four sub-tabs load without error. IDs render as
"↗ Open in Salesforce" deep links to the connected org.

---

## Admin > Automation & Sharing

**URL:** `/admin/` → Automation & Sharing tab

**Steps:**
1. Open Admin, click the "Automation & Sharing" tab.
2. **Validation Rules** loads by default — table with object, status, error message.
3. **Flows**, **Apex Triggers**, **Sharing Model** sub-tabs lazy-load on first view.
4. Use the filter box on any sub-tab.

**Expected:** each sub-tab loads on first view; filter narrows rows live.

---

## Migration > Velocity & ETA

**URL:** `/migration/velocity`

**Steps:**
1. Navigate to Migration > Velocity & ETA.
2. **Expected:** the loading spinner resolves within ~3s and the burn-down chart
   renders. It must NOT spin forever (regression — `mc-migration-snippet.js` was
   previously not loaded on this page).
3. The four summary cards populate; changing the Days selector reloads the chart.

---

## Settings

**URL:** `/settings`

**Steps:**
1. Navigate to Settings
2. Org Connections: click "Test Connection" for the dev org
3. Verify a green badge appears confirming the connection (org ID, instance URL,
   API version)
4. Click "Test Connection" for an org whose credentials are missing or invalid —
   amber/red badge with the error detail

5. Upload a Postman collection JSON file (v2.1 format)
6. Collection appears in table
7. Click "Run" — collection runner executes all requests, shows pass/fail per request
8. Click "Delete" — collection removed from table

---

## Confirmation Dialogs on Destructive Actions

Every state-changing UI action — Salesforce writes, bulk DML execute, Conductor
batch reruns, the trigger-bypass toggle, Apex-log / trace-flag deletes, and the
Anonymizer live run — is gated by the shared `MC.confirm()` dialog. The
destructive ones additionally require ticking an acknowledgement checkbox.

**Steps (using Logs > Delete All Logs):**
1. Navigate to `/logs`, select a time range.
2. Click **Delete All Logs**.
3. **Expected:** the `MC.confirm` modal appears. It shows an acknowledgement
   checkbox, and the confirm button is **disabled**.
4. Click **Cancel** — the modal closes and no delete request is sent (check the
   Network tab).
5. Click **Delete All Logs** again. Tick the acknowledgement checkbox — the
   confirm button becomes enabled.
6. Click the confirm button — the delete runs and a result toast appears.

The same pattern applies to all gated actions; spot-check a write (SOQL inline
edit) and a bulk DML execute to confirm none of them proceed without confirmation.

---

## CLI > Script & Metadata Generator

The CLI tab composes Salesforce CLI (`sf`) scripts and a `force-app` metadata
package for creating fields, flipping External IDs, and building a permission
set. It is read-only against Salesforce (describe only) — the generated
commands run on your own machine. Everything is driven by the header **Org**
picker.

**Steps:**
1. Navigate to `/cli`. **Expected:** the page loads with the setup snippets
   (install / login / project / retrieve) already filled from the defaults, and
   the **Object** dropdown populates from the selected org's describe.
2. In *Environment setup*, type an **Alias** (e.g. `DoaneUAT`) and a **Project
   name**. **Expected:** the Step 3 login and Step 4 project snippets update
   within ~0.4s to include your alias/project; the instance URL and base path
   are prefilled and editable.
3. Click **Copy** on any command box. **Expected:** a "Copied to clipboard"
   toast; the copied text matches the box.
4. In *Step 6 — Build fields*, pick an object, keep **Operation = Create new
   field**, set **Type = Text**, and type a **Field label** (e.g. `Group
   Information`). **Expected:** the **Field API name** auto-fills to
   `Group_Information__c` (SF-style) and remains editable — hand-editing it
   stops the auto-fill for that field. Tick **External ID** + **Unique**, then
   click **+ Add field**. **Expected:** a row appears in the field table; the
   Step 8/9 deploy snippets now include `-m "CustomField:<Object>.Group_Information__c"`.
   Click **Edit** on the row. **Expected:** the builder repopulates with that
   field and the button reads **Update field**; change something and click it to
   update the row in place (the row count stays the same).
5. Switch **Operation** to *Edit existing field (flip to External ID)* and pick
   a field from **Existing field**. **Expected:** the form prefills from the
   live describe (type, length), External ID is forced on, and after adding it
   the **Step 0 backup** and **Step 1 verify** snippets appear (they only show
   when at least one flip is present).
6. Enter a **Permission set** API name (e.g. `SF_Tools_Importer`). **Expected:**
   the deploy snippets gain `-m "PermissionSet:SF_Tools_Importer"` and the
   Step 10 assign snippet names it.
7. Click **Download package (.zip)**. **Expected:** a `sf-cli-package-*.zip`
   downloads. Unzipped, it contains
   `force-app/main/default/objects/<Object>/fields/<Field>.field-meta.xml` for
   each field, a `permissionsets/<Name>.permissionset-meta.xml`, a
   `manifest/package.xml`, and a `README.txt`.
8. Enter an invalid API name (no `__c`) and add it. **Expected:** a warning
   toast; the field is not added (the server also rejects it with a
   `{code: "INVALID_INPUT"}` error envelope).

**Invariant to eyeball:** a Text External-ID field authored here should be
byte-identical to a hand-written one. `tests/characterization/test_cli_artifacts_characterization.py`
pins this against the real Conductor migration artifacts.

---

## Regression Checks (run after any change)

1. `GET /health` returns 200
2. `POST /migration/readiness/run` returns `success: true` with checks array
3. `GET /validation/external-ids/run` returns list with Account entry
4. `POST /soql/run` with `{"query": "SELECT Id FROM Account LIMIT 1"}` returns records
5. `POST /schema/org-diff/run` with `{"compare_org": "prod"}` returns objects dict
6. Navigation — all 6 tabs load without 500
7. Org switch updates session and badge
8. `GET /data-ops/` redirects (302) to `/data-ops/import`
9. `GET /migration/velocity` — chart renders, spinner resolves (no infinite spin)
10. `GET /admin/permissions/sets` and `/admin/automation/validation-rules` return
    `success: true`
11. `POST /data-ops/export/run` with a SOQL body returns a `text/csv` attachment
12. `GET /data-ops/tune/rules` returns 8 standardization rules
13. `POST /data-ops/match/run` with object/where/compare_fields/block_field returns candidate pairs
14. `POST /data-ops/backup/run` with `{"objects": ["Account"]}` returns `success: true` with an object count
15. `POST /schema/metadata-diff/run` with `{"compare_org": "prod"}` returns `success: true` with `total_differences > 0`
16. `POST /schema/inspect/run` with `{"object": "Account", "record_id": "TEST001"}` returns `success: true` with `total_fields > 0`
17. `POST /schema/inspect/run` with `{"object": "Account", "record_id": "12345", "external_id_field": "SIS_ID__c"}` returns `lookup_mode: "external_id:SIS_ID__c"`
18. `pytest tests/ -q` — full suite green (1,301 tests)
19. `pytest tests/characterization/ -q` — Tooling API, route, Tune-rule, Soundex, and CLI-artifact contracts intact
20. `GET /cli` returns 200 and `GET /cli/objects` returns `success: true` with an object list
21. `POST /cli/generate` with a field plan returns all snippet keys; `POST /cli/package` returns an `application/zip` attachment
