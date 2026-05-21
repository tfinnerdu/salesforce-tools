# SF Mission Control — User Guide

**Doane University Salesforce Tools Dashboard**  
For developers, migration engineers, and admins working on the Doane Ed Cloud migration and Colleague→Salesforce integration.

---

## Table of Contents

1. [Getting Started](#getting-started)
2. [Dashboard](#dashboard)
3. [Migration](#migration)
   - [Readiness](#readiness)
   - [Error Reconciler](#error-reconciler)
   - [Batch Progress](#batch-progress)
   - [Pre-flight Checklist](#pre-flight-checklist)
   - [Velocity & ETA](#velocity--eta)
4. [Validation](#validation)
   - [Duplicate Radar](#duplicate-radar)
   - [External ID Coverage](#external-id-coverage)
   - [ContactPoint Scanner](#contactpoint-scanner)
   - [Field Completeness](#field-completeness)
   - [Orphan Scanner](#orphan-scanner)
   - [Merge History](#merge-history)
5. [SOQL Workbench](#soql-workbench)
6. [Schema](#schema)
   - [Crosswalk Diff](#crosswalk-diff)
   - [Org Diff](#org-diff)
   - [Field Usage](#field-usage)
   - [Data Dictionary](#data-dictionary)
   - [Apex Code Search](#apex-code-search)
   - [Schema Snapshots](#schema-snapshots)
7. [Data Ops](#data-ops)
   - [Data Import](#data-import)
   - [Export](#export)
   - [Bulk Modify](#bulk-modify)
   - [Tune (Data Standardization)](#tune-data-standardization)
   - [Bulk Delete](#bulk-delete)
   - [Bulk Reassign](#bulk-reassign)
   - [Join Builder](#join-builder)
   - [Bulk Update](#bulk-update)
   - [Record Lock Detector](#record-lock-detector)
   - [Bulk API Job History](#bulk-api-job-history)
8. [Logs](#logs)
   - [Apex Logs](#apex-logs)
   - [Flow Errors](#flow-errors)
   - [CPU Summary](#cpu-summary)
   - [Trace Flags](#trace-flags)
9. [Observe](#observe)
   - [API Limits](#api-limits)
   - [Data Quality Trends](#data-quality-trends)
   - [Cross-Org Record Count](#cross-org-record-count)
   - [Record Counts by Object](#record-counts-by-object)
   - [Sandbox Drift Detector](#sandbox-drift-detector)
10. [Impact](#impact)
    - [Field Impact Scanner](#field-impact-scanner)
    - [Permission Set Viewer](#permission-set-viewer)
    - [Regression Tester](#regression-tester)
    - [Permission Gap Analyzer](#permission-gap-analyzer)
11. [Admin](#admin)
    - [Scheduled Jobs](#scheduled-jobs)
    - [Test Coverage](#test-coverage)
    - [Deploy History](#deploy-history)
    - [Users](#users)
    - [Integrations](#integrations)
    - [Platform Events](#platform-events)
    - [Record Types](#record-types)
    - [Email Templates](#email-templates)
    - [Audit Trail](#audit-trail)
    - [Job Queue](#job-queue)
    - [Login History](#login-history)
    - [Anonymizer](#anonymizer)
    - [Custom Metadata](#custom-metadata)
    - [Custom Settings](#custom-settings)
    - [Permissions Audit](#permissions-audit)
    - [Automation & Sharing](#automation--sharing)
12. [Deploy](#deploy)
13. [Settings](#settings)

---

## Getting Started

### URLs

| Environment | URL |
|---|---|
| Local development | `http://localhost:5000` |
| Production | `https://du-int.doane.edu/prod/sf-mission-control` |

### Org Picker

The **Org** dropdown in the top-right navbar switches the active Salesforce org. Every data query, migration check, and schema comparison runs against whichever org is selected. Options are `dev`, `sandbox`, and `prod`. The org badge next to the dropdown (e.g., `SANDBOX`) confirms which org is active at a glance.

### Mock / Live Badges

Two badges in the navbar show the connection state of each data source independently:

| Badge | Meaning |
|---|---|
| `SF LIVE` (green) | Connected to real Salesforce — data is live |
| `SF MOCK` (amber) | `SF_MOCK=true` — all Salesforce data is synthetic |
| `COND LIVE` (green) | Connected to real Conductor orchestration server |
| `COND MOCK` (amber) | `CONDUCTOR_MOCK=true` — batch/workflow data is synthetic |

Click any badge for a detailed tooltip. In mock mode, an **⚠ MOCK DATA** chip appears on every card header and an **⚠ COND MOCK** chip appears on Conductor-driven page titles. Write-action buttons (Delete, Execute, Create) are disabled in mock mode with a tooltip explaining why — read-only Refresh buttons remain active.

### Navigation

The top nav contains all tabs: **Dashboard · Migration · Validation · SOQL · Schema · Data Ops · Logs · Observe · Impact · Admin · Deploy · Settings**. The active tab is underlined in amber.

### Salesforce Deep Links

When you're connected to a real org, any Salesforce record ID shown in a table —
in SOQL results, scan results, the Users list, and more — is a clickable link
(marked with a ↗) that opens that record directly in Salesforce in a new tab.
This works for `Id` columns and lookup fields alike. In mock mode the IDs are
plain text, since there is no real org to open.

---

## Dashboard

**URL:** `/dashboard`

The Dashboard is the home page — a single-screen health summary across all tools. All eight widgets load in parallel when the page opens.

**How to use it:** Open it as your daily morning check before starting migration work. Each widget has a **View Details →** footer link to navigate to the full feature page.

### Widgets

| Widget | What it shows |
|---|---|
| **Readiness Score** | Latest composite readiness % with a color-coded badge (green ≥90%, amber 80–89%, red <80%) |
| **API Limits** | Top 3 governor limits closest to their threshold — name, % used, mini progress bar |
| **Validation Checks** | Quick-links to the 5 validation sub-tabs with a brief description of each |
| **Migration Batches** | Last 3 batch runs — workflow name, status badge, records processed |
| **Test Coverage** | Org-wide Apex test coverage % with pass/fail counts |
| **Pre-flight Progress** | Progress bar showing how many of the 21 pre-flight checklist items are complete |
| **Recent Audit Trail** | Last 5 Setup Audit Trail entries — who changed what and when |
| **Org Health Score** | Letter grade (A–F) computed from readiness + preflight percentages |

---

## Migration

### Readiness

**URL:** `/migration/readiness`

The Readiness scorecard answers "are we ready to go live?" before each migration milestone. It runs 8 checks against the active org and scores each one.

**How to use it:**
1. Select the org from the card dropdown.
2. Click **Run Now**.
3. Review each check row — green (≥95%), amber (80–94%), red (<80%).
4. Click any row to see raw record count details.

**Checks explained:**

| Check | What it validates | Why it matters |
|---|---|---|
| SIS_ID__c coverage | % of PersonAccounts with a Colleague student ID | Required for matching during upsert |
| Ethos GUID coverage | % linked to Ethos identity | Required for LDM reconciliation |
| ContactPoint parents | Emails/phones/addresses with valid Account + Individual | Broken parents cause FIELD_INTEGRITY_EXCEPTION |
| Duplicate PersonAccounts | Records sharing the same name or SIS_ID | Duplicates cause DUPLICATE_VALUE on upsert |
| Individual links | PersonAccounts with a related Individual record | Required by the Person Account model |
| Required fields | Records missing FirstName, LastName, or RecordType | Blank required fields fail validation rules |
| Email format | PersonEmail values with invalid format | Bad emails block ContactPointEmail creation |
| Phone format | Phone numbers with non-standard formatting | Prevents clean ContactPointPhone creation |

The **Overall %** at the bottom is a composite score — below 90% indicates the org is not ready for a production migration push. Scores are stored in PostgreSQL and charted historically on the Observe → Data Quality Trends section.

---

### Error Reconciler

**URL:** `/migration/errors`

Pulls failed Conductor workflow executions and groups them by error type so you can action them in bulk.

**How to use it:**
1. Enter the **Workflow Name** (e.g., `EDA_Person_Sync`).
2. Select a **Time Range** (1 hour to 72 hours back).
3. Click **Refresh**.
4. Review error cards — each shows type, count, cause, and suggested fix.
5. Expand **Show SIS IDs** to see which specific student records are affected.
6. Click **Re-run** on an error group to requeue those workflows in Conductor.

**Error card fields:**

| Field | Description |
|---|---|
| Error type | Salesforce API error code (e.g., `DUPLICATE_VALUE`, `FIELD_INTEGRITY_EXCEPTION`) |
| Count | Number of workflows that failed with this error |
| Severity | HIGH (blocks migration) / LOW (safe to retry) |
| Cause | Plain-English explanation of what went wrong |
| Suggested fix | Actionable next step |
| SIS IDs | Expandable list of Colleague person IDs affected |

> **Note:** Shows **⚠ COND MOCK** in the page title when Conductor is in mock mode.

---

### Batch Progress

**URL:** `/migration/batches`

Live dashboard for a running Conductor migration batch.

**How to use it:**
1. Enter the **Workflow Name** (e.g., `EDA_Person_Sync`).
2. Select the time window.
3. Click **Load Status**.
4. Click **Refresh** to poll for new data.

| Element | Description |
|---|---|
| Progress bar | Overall % complete with animated striping while running |
| ETA / Rate | Estimated time to completion and current records-per-minute rate |
| Status counts | Completed / Failed / Running / Queued breakdown |
| Failure table | Per-workflow failure details with error message and Re-run button |

**Re-run All Failures** requeues every failed workflow in the current result set back to Conductor.

> **Note:** Shows **⚠ COND MOCK** when Conductor is in mock mode.

---

### Pre-flight Checklist

**URL:** `/migration/preflight`

A 21-item go-live checklist stored in PostgreSQL so progress persists across sessions and team members.

**How to use it:**
1. Review items grouped into 5 categories.
2. Click the checkbox next to each item to mark it complete — saves immediately.
3. The progress bar at the top updates in real time.
4. Click **+ Add Item** to add a custom item.
5. Click the trash icon to remove a custom item.

**Default categories:**

| Category | Example items |
|---|---|
| Data Quality | SIS_ID coverage ≥95%, no duplicate PersonAccounts, all ContactPoints valid |
| Integrations | Named Credentials verified, Connected Apps reviewed, Remote Sites active |
| Permissions | Permission sets assigned to integration user, FLS reviewed |
| Testing | All Apex tests passing ≥75%, regression suite baselined |
| Go-Live | Maintenance window scheduled, rollback plan documented, stakeholders notified |

The progress bar on the Dashboard widget reflects this checklist.

---

### Velocity & ETA

**URL:** `/migration/velocity`

A burn-down chart showing daily migration throughput and a projected completion date.

**How to use it:**
1. Select the time window (7 / 14 / 30 / 60 days) from the dropdown.
2. Click **Refresh**.

**Summary stats:**

| Stat | Description |
|---|---|
| Records Migrated | `migrated / target` (target = total PersonAccount universe) |
| % Complete | Color-coded progress bar (green ≥90%, amber ≥60%, red <60%) |
| Avg Velocity | Average records/day over the last 7 days with activity |
| ETA | Projected completion date at current velocity, or "✓ Complete!" |

**Chart:** Dual-axis — amber bars show daily record count (left axis); navy line shows cumulative total (right axis); dashed red line shows the target. When the cumulative line crosses the target, migration is complete.

---

## Validation

### Duplicate Radar

**URL:** `/validation/duplicates`

Scans for PersonAccount records that appear to be the same person — exact external ID matches or fuzzy name matches.

**How to use it:**
1. Select the org and click **Run Scan**.
2. Review duplicate groups — each group shows the matching records.
3. Select the record to **keep** using the radio button.
4. Click **Merge** → confirm in the modal.

**Match types:**

| Type | Logic |
|---|---|
| Exact SIS_ID | Two records share the same `SIS_ID__c` |
| Exact Ethos GUID | Two records share the same `Ethos_Guid__c` |
| Fuzzy name | Last + first name within edit distance 1 (catches typos) |

> **Warning:** Merge is irreversible. The button is disabled in mock mode. In production, always verify the records in Salesforce before confirming.

---

### External ID Coverage

**URL:** `/validation/external-ids`

Reports what percentage of PersonAccounts have each external ID field populated.

**How to use it:** Select the org and click **Run Report**.

| Field | Purpose | Threshold |
|---|---|---|
| `SIS_ID__c` | Colleague person ID — required for upsert matching | ≥95% green |
| `Ethos_Guid__c` | Ethos LDM GUID — required for cross-system reconciliation | ≥95% green |

Each row shows total records, records with the field populated, coverage %, and a color-coded badge.

---

### ContactPoint Scanner

**URL:** `/validation/contactpoints`

Checks that all ContactPoint records have valid parent links to both an `Account` and an `Individual`.

**How to use it:** Select the org and click **Run Scan**. Review broken records grouped by ContactPoint type.

**Checks performed:**

| Check | Description |
|---|---|
| ContactPointEmail → Account | Email's ParentId points to a valid PersonAccount |
| ContactPointEmail → Individual | Email's IndividualId points to a valid Individual |
| ContactPointPhone → Account | Phone parent validation |
| ContactPointPhone → Individual | Phone Individual validation |
| ContactPointAddress → Account | Address parent validation |
| PersonAccount → Individual | PersonAccount has a linked Individual |

Broken ContactPoint parents cause `FIELD_INTEGRITY_EXCEPTION` errors during migration and must be resolved before a batch can succeed.

---

### Field Completeness

**URL:** `/validation/completeness`

Checks 10 migration-critical fields across all PersonAccounts and reports the fill rate for each.

**How to use it:** Select the org and click **Run Check**.

**Fields checked:** `FirstName`, `LastName`, `PersonEmail`, `Phone`, `RecordTypeId`, `SIS_ID__c`, `Ethos_Guid__c`, `PersonBirthdate`, `MailingStreet`, `MailingCity`

Each field shows: total records, non-null count, % complete, status badge (green ≥95%, amber ≥75%, red <75%). Formula and system fields are automatically skipped.

---

### Orphan Scanner

**URL:** `/validation/orphans`

Finds records that exist in Salesforce but are disconnected from their required parent records.

**How to use it:** Select the org and click **Run Scan**.

**Orphan checks:**

| Check | Orphan condition |
|---|---|
| ContactPointEmail | `ParentId` → non-existent Account |
| ContactPointEmail | `IndividualId` → non-existent Individual |
| ContactPointPhone | Same Account + Individual checks |
| ContactPointAddress | Same Account + Individual checks |
| PersonAccount | Missing linked Individual record |

Each card shows the orphan count and sample record IDs (with Salesforce deeplinks in live mode).

---

### Merge History

**URL:** `/validation/merge-history`

Audit log of all duplicate merges performed through Duplicate Radar. Stored in PostgreSQL.

**How to use it:** Select the org and click **Refresh**.

| Column | Description |
|---|---|
| Merged At | Timestamp of the merge operation |
| Kept Record | Salesforce ID of the record that was retained |
| Merged IDs | IDs of records that were absorbed |
| Merge Count | Number of records eliminated |

The stats summary shows total merges performed and total records eliminated across all sessions.

---

## SOQL Workbench

**URL:** `/soql`

A full SOQL query editor with result display, history, and saved queries.

**How to use it:**
1. Type a SOQL query in the text area (e.g., `SELECT Id, Name FROM Account LIMIT 10`).
2. Select the target org.
3. Click **Run** (or press `Ctrl+Enter`).
4. Results display in a sortable table.
5. Click **Export CSV** to download results.
6. Click **Copy** to copy results as JSON.

**Saved Queries:**
- Click **Save** to store the current query with a name.
- Click a saved query to load it into the editor.
- Click the trash icon to delete a saved query.

**Query History:**
- Click **History** to open the last 25 queries (per org, stored in PostgreSQL).
- Click any entry to reload it into the editor.
- Click the trash icon to remove a history entry.

**Object Explorer:**
- Type an object name to see its available fields.
- Click a field name to insert it into the editor at the cursor position.

---

## Schema

### Crosswalk Diff

**URL:** `/schema/crosswalk`

Compares EDA field names to their Ed Cloud equivalents, highlighting fields that have been renamed, restructured, or removed during the EDA→Ed Cloud migration.

**How to use it:** Click **Load Crosswalk**.

| Status | Meaning |
|---|---|
| Mapped | EDA field has a direct Ed Cloud equivalent |
| Renamed | Same data, different API name |
| Restructured | Data moved to a different object or model |
| Removed | EDA field has no Ed Cloud equivalent |
| New | Ed Cloud field with no EDA predecessor |

Use this to identify fields that need custom mapping logic in your Conductor workflows.

---

### Org Diff

**URL:** `/schema/org-diff`

Compares the schema of two orgs side-by-side for a given object.

**How to use it:**
1. Select **Baseline Org** and **Target Org**.
2. Enter the **Object API Name** (e.g., `Account`).
3. Click **Run Diff**.

| Status | Meaning |
|---|---|
| Matching | Field exists in both orgs with the same type |
| Type mismatch | Field exists in both but with different data type or length |
| Missing in target | Field exists in baseline but not target |
| Missing in baseline | Field exists in target but not baseline |

Use after a sandbox refresh to verify the schema matches production, or before deploying a change set.

---

### Field Usage

**URL:** `/schema/field-usage`

Samples up to 40 fields on any object and reports how many records have data in each — identifying empty or rarely-used fields.

**How to use it:** Enter the Object API Name and click **Run Analysis**. Custom fields are sorted to the top.

| Status | Threshold |
|---|---|
| Green (active) | ≥50% of records have a value |
| Amber (sparse) | 10–49% |
| Red (empty) | <10% |
| Skip | System / formula field — not sampled |

---

### Data Dictionary

**URL:** `/schema/data-dictionary`

Generates a full field catalog for any Salesforce object with complete metadata for every field.

**How to use it:** Enter the Object API Name and click **Generate**. Click **Export CSV** to download as a spreadsheet.

**Output columns:** Field Name · Label · Type · Length · Required · Unique · External ID · Formula · Picklist Values · Help Text · Description

Custom fields are sorted to the top of the list.

---

### Apex Code Search

**URL:** `/schema/apex-search`

Searches all Apex classes and triggers in the org for a text pattern, returning matching lines with context.

**How to use it:**
1. Enter a **search pattern** (plain text or regex).
2. Toggle **Case Sensitive** if needed.
3. Check/uncheck **Classes** and **Triggers** to narrow scope.
4. Click **Search**.

Results are grouped by file with the matching line number and 1 line of context above/below. Matching text is highlighted. Results are capped at 50 files to stay within governor limits.

**Common uses:** Find all references to a field before renaming it · locate hardcoded record type IDs · find all triggers on a given object · search for deprecated API calls before a version upgrade.

---

### Schema Snapshots

**URL:** `/schema/snapshots`

Takes point-in-time snapshots of an object's field metadata and diffs two snapshots to detect schema drift.

**How to use it — taking a snapshot:**
1. Select the org and enter the Object API Name.
2. Optionally enter a label (defaults to current date/time UTC).
3. Click **Take Snapshot** — stored in PostgreSQL.

**How to use it — comparing snapshots:**
1. In the history table, click **Diff** on two rows (selected rows highlight).
2. Click **Compare Selected** once two are chosen.
3. The diff panel shows:
   - **Added fields** — present in the newer snapshot, not the older
   - **Removed fields** — present in the older snapshot, not the newer
   - **Changed fields** — present in both but with different metadata (type, length, required, etc.)

**Use cases:** Baseline before a change set deployment · track drift between sandbox refreshes · document field state at each migration milestone.

---

## Data Ops

The Data Ops tab houses the bulk data tools — the in-house equivalent of Validity
DemandTools, tuned for the Colleague → Ethos → Salesforce migration. Every
write tool follows the same safety pattern: **preview first, execute second**, and
write operations are disabled in mock mode.

### Data Import

**URL:** `/data-ops/import`

A four-step wizard for loading CSV files into Salesforce via the Bulk API — with a
validation pass *before* anything is written.

**Step 1 — Configure:** Choose the target Salesforce object, the operation
(Insert, Upsert, Update, or Delete), and upload your CSV file. For Upsert, also
enter the external ID field (e.g., `SIS_ID__c`). A preview of the first few rows
appears so you can confirm the file parsed correctly.

**Step 2 — Map Fields:** Match each CSV column to a Salesforce field. Click
**Auto-Map** to bind columns whose names match a field automatically. Unmapped
columns are ignored.

**Step 3 — Validate:** Click **Run Validation**. The tool checks every row against
the object's schema *without writing anything*:
- Required fields that are empty (Insert only)
- Numbers, dates, and booleans that don't parse
- Email fields that aren't valid email addresses
- Picklist values that aren't in the allowed set
- CSV columns mapped to fields that don't exist

You get four counts — Total, Clean, Warnings, Errors — and a row-by-row issue
list. If there are errors, fix the CSV and re-validate. The **Import** step
unlocks only when there are zero errors.

**Step 4 — Import:** Review the summary and click **Execute Import**. Results show
Succeeded / Failed counts. For any failures, click **Download Error CSV** to get
your original rows back with a `_sf_error` column explaining each failure — fix
those rows and re-import just them.

> **Why two steps?** DemandTools shows you Salesforce's error only *after* a failed
> load. The validate pass catches type errors, bad picklist values, and missing
> required fields up front, so the actual import is clean.

---

### Export

**URL:** `/data-ops/export`

Runs a SOQL query and downloads the results as a CSV.

**How to use it:**
1. Enter a SOQL `SELECT` query.
2. Set the filename.
3. Leave **All pages** checked to fetch beyond the 2,000-row SOQL limit.
4. Click **Download CSV**.

Exported CSVs can be fed straight back into the Import tool — handy for pulling
existing records, editing them, and upserting the changes.

---

### Bulk Modify

**URL:** `/data-ops/modify`

Updates one or more fields across every record matching a WHERE clause.

**How to use it:**
1. Enter the **Object** and a **WHERE clause**.
2. Add one or more **field / new-value** rows (use **+ Add Field** for more).
3. Click **Preview** to see the affected records.
4. Click **Update Records** to execute via the Bulk API.

Capped at 10,000 records per operation. Optionally bypass triggers.

---

### Tune (Data Standardization)

**URL:** `/data-ops/tune`

Cleans up inconsistent data by applying standardization rules in bulk — the
in-house equivalent of DemandTools' Tune. Consistent data fails fewer validation
rules on import.

**Available rules:**

| Rule | What it does |
|---|---|
| Trim whitespace | Collapses repeated spaces and strips the ends |
| Proper case (name-aware) | `JOHN SMITH` → `John Smith`; handles hyphens, apostrophes, the `Mc` prefix |
| Title case | Capitalizes the first letter of every word |
| UPPERCASE / lowercase | Forces case |
| Lowercase email | Trims and lowercases an email address |
| US phone format | `402.555.1234` → `(402) 555-1234` (left unchanged if not 10 digits) |
| State name → abbreviation | `Nebraska` → `NE` |

**How to use it:**
1. Enter the **Object** and a **WHERE clause**.
2. Click **+ Add Field**; enter a field API name and pick one or more rules
   (they apply in the order shown). Add as many field rows as you need.
3. Click **Preview** — a Before / After table shows exactly what would change,
   sampled from the matching records.
4. Click **Apply Standardization** to write the changes via the Bulk API.

Records already in the correct format are left untouched and reported as
"already clean".

---

### Bulk Delete

**URL:** `/data-ops/delete`

Deletes every record matching a WHERE clause. Records go to the Recycle Bin
(soft delete), so a same-day mistake is recoverable from Salesforce.

**How to use it:**
1. Enter the **Object** and a **WHERE clause**.
2. Click **Preview** — the matching records and total count appear.
3. Click **Delete Records** and confirm.

> **Warning:** Destructive. Always preview. Capped at 10,000 records per operation.

---

### Bulk Reassign

**URL:** `/data-ops/reassign`

Changes the Owner of every record matching a WHERE clause.

**How to use it:**
1. Enter the **Object** and a **WHERE clause**.
2. Search for and select the **new owner** from the user picker.
3. Click **Preview**, then **Reassign Records**.

---

### Join Builder

**URL:** `/data-ops/join-builder`

Builds and executes join queries combining Salesforce data with your SQL Server (Colleague) database for cross-system reconciliation.

**How to use it:**
1. Select a **Salesforce Object** and the **SF Join Field** (e.g., `SIS_ID__c`).
2. Enter the **SQL Server table** name and **SQL join column**.
3. Select which SF fields and SQL columns to include.
4. Click **Build Query** to preview the generated SQL.
5. Click **Run** to execute and display results.
6. Click **Export CSV** to download.

The join is performed in Python — no direct database link between Salesforce and SQL Server is required. Results show matched rows, SF-only records (in SF but not SQL), and SQL-only records (in SQL but not SF).

---

### Bulk Update

**URL:** `/data-ops/bulk-update`

Updates a field value across many records using the Salesforce Bulk API v2.

**How to use it:**
1. Enter the **Object API Name**, a **WHERE clause**, the **Field** to update, and the **New Value**.
2. Click **Preview** to see how many records will be affected — no data is modified.
3. Review the count, then click **Execute**.

**Safety features:**
- Preview is required before Execute becomes active.
- Capped at 10,000 records per operation.
- Execute is **disabled in mock mode**.

> **Warning:** Bulk updates bypass most validation rules and triggers (unless trigger bypass is off in Settings). Always Preview before executing in production.

---

### Record Lock Detector

**URL:** `/data-ops/record-locks`

Finds records stuck in pending approval processes — a common cause of DML failures when migration triggers try to update locked records.

**How to use it:** Select the org, optionally filter by Object, and click **Refresh**.

| Column | Description |
|---|---|
| ProcessInstance ID | Salesforce ID of the approval process instance |
| Target Record | ID of the locked record (SF deeplink in live mode) |
| Created Date | When the approval was initiated |
| Days Pending | How long the record has been locked |

Records locked for more than a few days are usually abandoned processes. Work with the record owner or a Salesforce admin to advance or recall the approval before running migration DML against those records.

---

### Bulk API Job History

**URL:** `/data-ops/bulk-jobs`

Shows recent Bulk API v2 ingest jobs and their status.

**How to use it:** Select the org and click **Refresh**. Toggle **Auto-refresh** to poll every 15 seconds while a job is running.

| Status | Color | Meaning |
|---|---|---|
| JobComplete | Green | Finished successfully |
| InProgress | Amber | Currently running |
| Failed | Red | Job failed — check Records Failed count |
| Aborted | Gray | Manually stopped |

**Columns:** Operation · Object · Records Processed · Records Failed (red if >0) · Processing Time · Created date.

Use this after a migration batch to verify all bulk operations completed cleanly before proceeding to the next step.

---

## Logs

### Apex Logs

**URL:** `/logs`

Lists and inspects Apex debug logs for the active org.

**How to use it:**
1. Select a **time range** (Last 15 min / 1 hour / 6 hours / custom).
2. Toggle **Auto-refresh** to poll for new logs every 30 seconds.
3. Click a log row to open the detail panel.
4. Click **Delete** on a row to remove a single log.
5. Click **Delete All Logs** to clear all debug logs.

The detail panel shows: log header (user, duration, heap size, CPU time), parsed event timeline grouped by category (SOQL, DML, Apex calls, limits), and the raw log body.

> **Note:** Delete All Logs is disabled in mock mode.

---

### Flow Errors

**URL:** `/logs` → Flow Errors tab

Lists recent Flow interview failures from `FlowExecutionErrorEvent` records.

**How to use it:** Click **Refresh** to fetch recent failures.

**Columns:** Flow API Name · Error Message · Fault Message · Occurred At.

Use this to catch flows failing silently during migration data loads — Flow errors don't appear in Apex logs.

---

### CPU Summary

**URL:** `/logs` → CPU Summary tab

Aggregates CPU time across recent debug logs to identify the most expensive Apex executions.

**How to use it:** Click **Refresh**.

**Columns:** Class/Trigger name · Total CPU ms · Call count · Average ms per call.

Sorted by total CPU descending — use this to find hotspots before a high-volume migration batch to avoid CPU governor limit errors.

---

### Trace Flags

**URL:** `/logs` → Trace Flags tab

Manages Salesforce debug trace flags — controls which users or Apex classes generate detailed logs and at what verbosity.

**How to use it — viewing flags:**
Click **Refresh** to load active flags. Expired flags are grayed out.

**How to use it — creating a flag:**
1. Select **Entity Type** (User or Apex Class).
2. Start typing a name — matching options appear in the dropdown.
3. Select a **Debug Level** (determines which log categories are captured).
4. Select **Duration** (15 min to 24 hours).
5. Click **Create Trace Flag**.

**Quick action:** Click **⚡ Trace Me (30 min)** to immediately create a 30-minute FINEST trace flag for the current user.

**Cleanup:** Click **Delete Expired** to remove all expired flags at once. Click the trash icon on a row to remove a specific flag.

> **Note:** Create, Delete Expired, and Trace Me are disabled in mock mode.

---

## Observe

### API Limits

**URL:** `/observe`

Shows all Salesforce governor limits and remaining capacity for the active org.

**How to use it:** Select the org and click **Refresh**.

**Color coding:** Green = <50% used · Amber = 50–80% · Red = >80% (or your custom thresholds).

**Custom thresholds:** Click **⚙ Thresholds** to override the default 50%/80% thresholds for specific limits. Changes are saved to PostgreSQL.

**Key limits to watch during migration:**

| Limit | Description |
|---|---|
| `DailyApiRequests` | Total REST/SOAP API calls allowed per 24 hours; resets at midnight GMT |
| `DailyBulkApiRequests` | Bulk API v2 job submissions per day |
| `DataStorageMB` | Org storage cap — bulk inserts can fill this quickly |
| `DailyAsyncApexExecutions` | Async Apex (batch/queueable/scheduled) calls per day |

---

### Data Quality Trends

**URL:** `/observe` → Data Quality Trends section

Charts daily readiness check results over time to show whether migration is improving or degrading data quality.

**How to use it:** Select the org and number of days (7 / 14 / 30), then click **Refresh**.

Each line represents one readiness check's pass rate over time. Lines trending upward mean improving data quality. A sudden drop indicates a regression — cross-reference with the Audit Trail or Error Reconciler to find the cause.

Data comes from the `readiness_runs` PostgreSQL table, populated by the daily 06:00 CT scheduler or manual Readiness runs.

---

### Cross-Org Record Count

**URL:** `/observe` → Cross-Org Record Count section

Runs identical COUNT() queries against multiple orgs simultaneously and highlights divergence.

**How to use it:** Check the orgs to compare, then click **Run Comparison**.

**Color coding:**
- No color — within 10% of the first selected org
- Amber — >10% divergence
- Red — >25% divergence

Use this after a sandbox refresh to verify record counts match production before starting a new migration wave.

---

### Record Counts by Object

**URL:** `/observe` → Record Counts by Object section

Live COUNT() snapshot for the 12 most important migration objects.

**How to use it:** Select the org and click **Refresh**.

Objects included: `Account` · `ContactPointEmail` · `ContactPointPhone` · `ContactPointAddress` · `Individual` · `Lead` · `Contact` · `Opportunity` · `Case` · `Task` · `Event` · `User`.

The ↗ icon in the Actions column opens a pre-built SOQL query for that object in the SOQL Workbench.

---

### Sandbox Drift Detector

**URL:** `/observe` → Sandbox Drift Detector section

Compares two orgs' record counts and flags objects with significant divergence — designed for post-sandbox-refresh verification.

**How to use it:** Select **Baseline** org (usually `prod`) and **Target** org (usually `sandbox`), then click **Run**.

| Status | Drift % | Meaning |
|---|---|---|
| Green (ok) | <5% | Target matches baseline closely |
| Amber (warning) | 5–20% | Noticeable drift — investigate before using sandbox |
| Red (critical) | >20% | Major divergence — sandbox refresh may be incomplete |

An object with 100% drift (0 records in target) is always red regardless of threshold.

---

## Impact

### Field Impact Scanner

**URL:** `/impact`

Searches all Apex classes and triggers to find every reference to a given field — essential before renaming or deleting a field.

**How to use it:** Select the org, enter the Object and Field API Name, then click **Scan**.

Each result shows: file name, file type (Class / Trigger), matching line, and a link to open the file in Salesforce Setup. Use this before any schema change to understand the full blast radius.

---

### Permission Set Viewer

**URL:** `/impact` → Permissions tab

Shows all permission sets in the org and the object/field permissions each one grants.

**How to use it:** Select the org and click **Load Permission Sets**. Click a permission set name to expand it.

Shows: object permissions (Read / Create / Edit / Delete / View All / Modify All) and field permissions (Read / Edit).

Use this to verify the integration user's permission set grants access to all migration objects and fields before go-live.

---

### Regression Tester

**URL:** `/impact` → Regression tab

Saves and re-runs SOQL-based test suites to catch data regressions between migration runs.

**How to use it — creating a suite:**
1. Enter a Suite Name.
2. Add test queries — each should return a COUNT or specific value to assert.
3. Optionally set an expected value for each query.
4. Click **Save Suite**.

**How to use it — running:**
1. Select a saved suite and click **Run Suite**.
2. Results show Pass (matches expected) or Fail (differs from expected/baseline).
3. Click **Save as Baseline** to store current results as the new expected values.

Example assertion: "Account with SIS_ID__c should return exactly 4,312 records." A regression on this suite means a migration step accidentally wiped or duplicated records.

---

### Permission Gap Analyzer

**URL:** `/impact` → Perm Gap tab

Compares two permission sets and shows exactly which object and field permissions differ.

**How to use it:** Select the org, load permission sets, select Permission Set A and B, then click **Compare**.

**Output sections:**
- **Only in A** — permissions granted by A but not B
- **Only in B** — permissions granted by B but not A
- **Conflicting** — same object/field but different access level

Use this to audit whether the integration user's permission set has all the same access as a reference set, or to compare admin vs. standard user access before go-live.

---

## Admin

### Scheduled Jobs

**URL:** `/admin` → Scheduled Jobs tab

Lists all Apex scheduled jobs (`CronTrigger`) in the org.

**Columns:** Job Name · Apex class · State (Active/Deleted/Paused) · Next fire time · Previous fire time · Time zone · Cron expression.

Use this to verify the daily readiness scheduler is active and to check for jobs that conflict with migration batch windows.

---

### Test Coverage

**URL:** `/admin` → Test Coverage tab

Shows Apex code coverage for every class and trigger in the org.

**Columns:** Class/Trigger name · Lines covered · Lines uncovered · Coverage %.

Rows below 75% are highlighted in red (Salesforce deployment requires ≥75% overall coverage). Sort by Coverage % ascending to find the classes that need new tests before a deployment.

---

### Deploy History

**URL:** `/admin` → Deploy History tab

Lists recent metadata deployments to the org.

**Columns:** Deployment ID · Status (Succeeded/Failed/Pending) · Deployed by · Start time · Duration · Components deployed · Components failed.

Use this to find recent deployments that may have introduced regressions, and to check whether a deployment is still in progress before running migration.

---

### Users

**URL:** `/admin` → Users tab

Audit of active users in the org.

**Columns:** Name · Username · Profile · Last login date · Active status. Inactive users are grayed out.

Use this to verify the integration user is set up correctly, confirm the right profile is assigned, and check that the user has logged in recently.

---

### Integrations

**URL:** `/admin` → Integrations tab

Inventories all integration touchpoints in the org across three sub-sections:

- **Named Credentials** — saved endpoint + auth configurations used by Apex callouts
- **Remote Site Settings** — external domains approved for outbound HTTP callouts
- **Connected Apps** — OAuth-connected third-party applications

Use this before go-live to confirm all integration credentials point to production endpoints, not sandbox.

---

### Platform Events

**URL:** `/admin` → Platform Events tab

Lists all Platform Event channels and their current subscribers.

**Columns:** Event API name · Label · Subscribers (Apex triggers, flows, or external CometD subscriptions).

Use this to understand what fires when migration records are inserted or updated, and to identify platform event subscribers that may add unexpected overhead to high-volume batches.

---

### Record Types

**URL:** `/admin` → Record Types tab

Lists all record types for all objects in the org.

**Columns:** Object · Record Type name · API name · Active status · Default.

Use this to verify the `PersonAccount` record type is active and correctly named before migration upserts — the record type ID is required on every Account insert.

---

### Email Templates

**URL:** `/admin` → Email Templates tab

Lists all email templates with their folder, type, and last-modified date.

Use this to find templates that reference fields being renamed or removed during migration, and to confirm template availability before go-live if any migration workflows trigger email notifications.

---

### Audit Trail

**URL:** `/admin` → Audit Trail tab

Shows the Salesforce Setup Audit Trail — every Setup change made in the org within the selected window.

**How to use it:** Select the number of days to look back (1 / 7 / 30) and click **Refresh**.

**Columns:** Action · Section (what area of Setup changed) · Modified by · Date/time.

Use this to answer "what changed in this org recently?" after an unexpected migration failure or behavior change.

---

### Job Queue

**URL:** `/admin` → Job Queue tab

Live view of the Apex async job queue (`AsyncApexJob`) — shows Batch Apex, Queueable, Scheduled, and Future jobs.

**How to use it:** Select a Status filter pill (All / Queued / Processing / Completed / Failed) and optionally toggle **Auto-refresh** (polls every 10 seconds).

| Column | Description |
|---|---|
| Job Type | BatchApex / Queueable / Scheduled / Future |
| Apex Class | The class being executed |
| Status | Green = Completed · Amber = Processing · Red = Failed |
| Progress | Items Processed / Total Items |
| Duration | Elapsed time |
| Extended Status | Hover on failed rows for the error message |

Use this to monitor long-running batch jobs during migration and to verify no jobs are stuck in a Queued state that would block your batch from starting.

---

### Login History

**URL:** `/admin` → Login History tab

Shows recent login activity for the org.

**Columns:** User · Login time · Login type · Source IP · Status (Success/Failed) · Failure reason.

Failed logins are highlighted in red. Use this to verify the integration user is successfully authenticating and to identify credential issues before a migration run.

---

### Anonymizer

**URL:** `/admin` → Anonymizer tab

Sends PII fields to an external anonymization service for scrubbing — designed for use after a sandbox refresh to remove real student data from the sandbox.

**How to use it:**
1. Select an **Object** from the dropdown.
2. Check the **fields** you want to anonymize.
3. Click **Preview** — shows how many records would be affected, no data is modified.
4. Click **Run Anonymizer** to submit to the PII service.

> **Requires `PII_SERVICE_URL`** in your environment. Without it, the service runs in stub mode — logs what it would send but does not modify data. The Run button is disabled in mock mode.

**Available objects and fields:**

| Object | Fields |
|---|---|
| Account | Name, PersonEmail, PersonBirthdate, Phone, SIS_ID__c |
| ContactPointEmail | EmailAddress |
| ContactPointPhone | TelephoneNumber |
| ContactPointAddress | Street, City, PostalCode |

---

### Custom Metadata

**URL:** `/admin` → Custom Metadata tab

Browses Custom Metadata Type records without opening Salesforce Setup.

**How to use it:** Click **Refresh** to load the list of types. Click a type name in the left panel to load its records on the right.

Custom Metadata Types hold org configuration (integration settings, field mappings, feature flags) deployed as metadata rather than data. Use this to inspect records like `Migration_Config__mdt` or `Integration_Setting__mdt` without needing Setup access.

---

### Custom Settings

**URL:** `/admin` → Custom Settings tab

Browses Custom Setting records (Hierarchy and List types) without opening Salesforce Setup.

**How to use it:** Click **Refresh** to load settings. Click a setting name in the left panel to load its records on the right.

**Record columns:** Name · SetupOwner ID · Owner Type (Org / Profile / User).

Hierarchy Custom Settings have one record per level — the most specific level wins at runtime. Use this to check bypass-trigger settings or integration feature flags before a migration run.

---

### Permissions Audit

**URL:** `/admin` → Permissions Audit tab

A one-stop drill-down for "who can see and do what" — the answer to permission
questions without clicking through Setup. Four sub-tabs:

**Permission Sets** — Lists every custom permission set with a badge showing how
many users are assigned. Click a permission set to see, in three sub-tabs: the
**users** assigned to it, the **object permissions** it grants (Read / Create /
Edit / Delete / View All / Modify All), and the **field permissions** it grants.

**By User** — Search for a user by name or username, then select them to see their
full access picture: profile, license, every assigned permission set, and their
aggregated object-level access across all those permission sets.

**Object Matrix** — Enter any Salesforce object (e.g., `Account`). Shows every
permission set that grants access to it and exactly which CRUD operations each one
allows — a fast way to answer "who can delete Accounts?"

**Field Coverage** — Enter an object to see a field-by-field matrix of read/edit
access across all permission sets. Useful for confirming a sensitive field
(e.g., `SIS_ID__c`) is locked down correctly.

Wherever a record ID is shown and you're connected to a real org, names render as
**↗ Open in Salesforce** links that jump straight to the record.

---

### Automation & Sharing

**URL:** `/admin` → Automation & Sharing tab

A read-only explorer for org configuration that normally takes a dozen Setup
clicks to find — and the first place to look when an import row fails. Four
sub-tabs:

**Validation Rules** — Every validation rule in the org, with its object, active
status, error field, and error message. When an import fails with a custom
validation error, look the rule up here to see exactly what it checks.

**Flows** — Every flow definition, with its type (record-triggered, screen,
autolaunched) and status. Record-triggered flows are a common cause of silent
import failures.

**Apex Triggers** — Every Apex trigger and the object it runs on. The other usual
suspect when a bulk load behaves unexpectedly.

**Sharing Model** — The org-wide default (OWD) sharing setting for each object —
internal and external access — with Private settings flagged in red.

Each sub-tab loads on first view and has a filter box. Everything here is
read-only.

---

## Deploy

**URL:** `/deploy`

Builds a Salesforce `package.xml` change set manifest from a selected list of metadata components.

**How to use it:**
1. Select the **Component Type** (ApexClass, CustomObject, CustomField, etc.).
2. Select the org to query available components from.
3. Click **Load Components** to fetch the list.
4. Check the components to include.
5. Click **Generate Package** to produce the `package.xml`.
6. Copy the XML or download it for use with `sf project deploy` or the Metadata API.

A pre-deployment checklist is generated alongside the package — standard items to verify before deploying (backup taken, tests passing, maintenance window scheduled, etc.).

---

## Settings

**URL:** `/settings`

Configures org connections, trigger bypass behavior, and API collection runners.

### Org Connection Test

Select an org and click **Test Connection** to verify that the credentials in your environment variables are valid. Returns the org ID, instance URL, and API version on success, or a detailed error message on failure.

### Bypass Triggers

When `SF_BYPASS_SETTING` is configured in your environment, this toggle flips the checkbox field on your Hierarchy Custom Setting that disables triggers for the integration user. Use this before a bulk migration DML run to prevent triggers from firing on every record.

> **Important:** Always re-enable triggers after the migration run completes. Leaving bypass active in production can cause data integrity issues and missed automations.

### API Collections

Stores and runs Postman-style API request collections against your Salesforce orgs.

**How to use it:**
1. Click **New Collection** and give it a name.
2. Add requests — each has a method (GET / POST / PATCH / DELETE), URL, optional headers, and optional body.
3. Click **Run Collection** to execute all requests in sequence.
4. Results show status code, response time, and response body for each request.

Collections are stored in PostgreSQL and shared across all sessions. Use this for smoke-testing integration endpoints after a deployment, or verifying Named Credential callouts are working correctly against a specific org.

---

*Last updated: May 2026 — covers all features through Wave 6 of SF Mission Control development.*
