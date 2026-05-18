# SF Mission Control — End-to-End Test Walkthrough

Manual steps and expected outcomes for verifying each feature from outside the codebase. Run against local dev environment unless noted.

---

## Setup

```powershell
.\start-local.ps1
# App starts at http://localhost:5000
```

With `SF_MOCK=true` and `CONDUCTOR_MOCK=true` (defaults), all data is simulated — no real Salesforce credentials needed.

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

## Migration > Readiness Score

**URL:** `/migration/readiness`

**Steps:**
1. Navigate to Migration > Readiness Score (default tab)
2. Observe page loads with "Last run: Never" and empty scorecard
3. Click "Run Now"
4. Verify loading spinner appears during run
5. After completion, scorecard fills with 6+ check rows

**Expected scorecard (mock data):**

| Check | Status | Expected |
|---|---|---|
| PersonAccount SIS_ID__c | 🔴 Red | ~71% coverage |
| Ethos GUID coverage | 🟡 Amber | ~91% coverage |
| ContactPoint parents | 🔴 Red | 3,204 broken |
| Duplicate detection | 🟡 Amber | 23+ groups |
| Individual links | 🔴 or 🟡 | varies |
| Required fields | 🔴 Red | missing records |

- Overall banner shows red: "Overall Readiness: ~60% — NOT READY FOR GO-LIVE"
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

**Expected (mock):**
- Progress bar fills to ~66% (2,756+91 of 4,312)
- Completed: 2,756 | Failed: 91 | Running: 212 | Queued: 1,253
- ETA shows ~14 min
- Failure breakdown table shows: DUPLICATE_VALUE: 44, FIELD_INTEGRITY_EXCEPTION: 31, TIMEOUT: 16

5. Toggle "Auto-refresh" — verify polling starts (console shows periodic fetches)
6. Click "Re-run failures" for TIMEOUT row
7. Verify success toast

---

## Migration > Error Reconciler

**URL:** `/migration/reconciler`

**Steps:**
1. Navigate to Migration > Error Reconciler
2. Enter workflow: `EDA_Person_Sync`, select "Last 24h"
3. Click Refresh
4. Verify 3 error category cards appear

**Expected cards:**
- 🔴 DUPLICATE_VALUE (44 records) — red border, "safe to retry after dedup" hint
- 🟡 FIELD_INTEGRITY_EXCEPTION (31 records) — amber border
- 🟢 TIMEOUT (16 records) — green border, "safe to retry immediately"

5. Click "Show all SIS IDs" on DUPLICATE_VALUE card — list expands
6. Click "Re-run" on TIMEOUT card — toast confirms 16 workflows queued

---

## Validation > Duplicate PersonAccount Radar

**URL:** `/validation/duplicates`

**Steps:**
1. Navigate to Validation > Duplicate Radar
2. Click "Run Scan"

**Expected:**
| Strategy | Count | Status |
|---|---|---|
| Same SIS_ID | 12 | Amber |
| Same Name+DOB | 23 | Amber |
| Same Email | 8 | Amber |
| Same Ethos GUID | 0 | Green |

3. Click "Merge" on a Same SIS_ID row
4. Verify merge modal opens with master/victim ID fields
5. Click Confirm — verify success toast
6. Click "Export CSV" — CSV downloads with strategy results

---

## Validation > External ID Coverage

**URL:** `/validation/external-ids`

**Steps:**
1. Navigate to Validation > External ID Coverage
2. Click "Run Report"

**Expected table:**
| Object | Total | SIS_ID__c | Ethos_Guid__c |
|---|---|---|---|
| Account (PersonAccounts) | 4,312 | 🔴 71% | 🟡 91% |
| ContactPointEmail | ~4,100 | 🔴 ~80% | N/A |
| ContactPointPhone | ~3,800 | 🔴 ~80% | N/A |
| ContactPointAddress | ~3,204 | 🔴 ~80% | N/A |
| IndividualApplication | ~1,850 | varies | varies |

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
- Row count shows "20 records (showing 20 of 4,312)"
- Download CSV button enabled

7. Click "Run All Pages" — row count shows all 4,312
8. Double-click a cell in the results table — inline edit input appears
9. Type new value, press Enter — "Record updated" toast
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
- Each panel shows: X fields left-only, Y fields right-only, Z type mismatches
- In mock: schemas are identical → all diff sections show empty

5. Verify export button available

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

## Settings

**URL:** `/settings`

**Steps:**
1. Navigate to Settings
2. Org Connections: click "Test Connection" for dev org
3. Verify green badge appears: "Connected — 4,312 records"
4. Click "Test Connection" for prod org (no real creds) — amber/red badge

5. Upload a Postman collection JSON file (v2.1 format)
6. Collection appears in table
7. Click "Run" — collection runner executes all requests, shows pass/fail per request
8. Click "Delete" — collection removed from table

---

## Regression Checks (run after any change)

1. `GET /health` returns 200
2. `POST /migration/readiness/run` returns `success: true` with checks array
3. `GET /validation/external-ids/run` returns list with Account entry
4. `POST /soql/run` with `{"query": "SELECT Id FROM Account LIMIT 1"}` returns records
5. `POST /schema/org-diff/run` with `{"compare_org": "prod"}` returns objects dict
6. Navigation — all 6 tabs load without 500
7. Org switch updates session and badge
