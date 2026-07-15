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
   - [Org Metadata Diff](#org-metadata-diff)
   - [Record Inspector](#record-inspector)
   - [Field Usage](#field-usage)
   - [Data Dictionary](#data-dictionary)
   - [Field Finder](#field-finder)
   - [Apex Code Search](#apex-code-search)
   - [Schema Snapshots](#schema-snapshots)
7. [Data Ops](#data-ops)
   - [Data Import](#data-import)
   - [Export](#export)
   - [Bulk Modify](#bulk-modify)
   - [Tune (Data Standardization)](#tune-data-standardization)
   - [Match (Fuzzy Duplicate Detection)](#match-fuzzy-duplicate-detection)
   - [Bulk Delete](#bulk-delete)
   - [Bulk Reassign](#bulk-reassign)
   - [Join Builder](#join-builder)
   - [Data Backup](#data-backup)
   - [Bulk Update](#bulk-update)
   - [Record Lock Detector](#record-lock-detector)
   - [Bulk API Job History](#bulk-api-job-history)
8. [Scenarios](#scenarios)
   - [Scenario List & Tags](#scenario-list--tags)
   - [Building a Scenario](#building-a-scenario)
   - [Running a Scenario](#running-a-scenario)
   - [Scheduling (Argo)](#scheduling-argo)
9. [Key Maps](#key-maps)
   - [Key Map List](#key-map-list)
   - [Building a Key Map](#building-a-key-map)
   - [Running a Preview](#running-a-preview)
   - [Using a Key Map in a Scenario](#using-a-key-map-in-a-scenario)
10. [Logs](#logs)
    - [Apex Logs](#apex-logs)
    - [Flow Errors](#flow-errors)
    - [CPU Summary](#cpu-summary)
    - [Trace Flags](#trace-flags)
11. [Observe](#observe)
    - [API Limits](#api-limits)
    - [Data Quality Trends](#data-quality-trends)
    - [Cross-Org Record Count](#cross-org-record-count)
    - [Record Counts by Object](#record-counts-by-object)
    - [Sandbox Drift Detector](#sandbox-drift-detector)
12. [Impact](#impact)
    - [Field Impact Scanner](#field-impact-scanner)
    - [Permission Set Viewer](#permission-set-viewer)
    - [Regression Tester](#regression-tester)
    - [Permission Gap Analyzer](#permission-gap-analyzer)
13. [Admin](#admin)
    - [Scheduled Jobs](#scheduled-jobs)
    - [Test Coverage](#test-coverage)
    - [Deployment History](#deployment-history)
    - [User Audit](#user-audit)
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
14. [Deploy](#deploy)
15. [Settings](#settings)
16. [CLI](#cli)

---

## Getting Started

### URLs

| Environment | URL |
|---|---|
| Local development | `http://localhost:5000` |
| Production | `https://du-int.doane.edu/prod/sf-mission-control` |

### Org Picker

The **Org** dropdown in the top-right navbar switches the active Salesforce org. Every data query, migration check, and schema comparison runs against whichever org is selected. Options are `dev`, `sandbox`, and `prod`. The org badge next to the dropdown (e.g., `SANDBOX`) confirms which org is active at a glance.

### Connection Badges

Two badges in the navbar show the connection state of each data source independently:

| Badge | Meaning |
|---|---|
| `LIVE` (green) | Real mode — connected to a configured Salesforce org and Conductor instance |
| `MOCK` (amber) | Demo mode (`SHOW_MOCK=true`) — every Salesforce and Conductor call is served by the in-process mock layer, no live systems are touched |

Click the badge for a tooltip with details. The `LIVE` / `MOCK` indicator is
all-or-nothing — a single flag controls both Salesforce and Conductor.

When the app is in mock mode, the navbar shows the amber **`MOCK`** badge and
every card-header renders a small **`MOCK DATA`** chip so the mode is
unmissable on every screen.

### Demo Mode (Credential-Free)

For stakeholder demos, training, and onboarding new contributors who don't yet
have Salesforce or Conductor credentials, set `SHOW_MOCK=true` in `.env` (or in
your shell environment) before starting the app. The whole app is swapped onto
an in-process `MockSalesforce` / `MockConductorClient` layer — every page
renders with realistic synthetic data, write actions are accepted by the mock
providers (and return synthesized counts), and the `MC.confirm()` confirmation
modals still appear so the safety UX is itself demoable.

`SHOW_MOCK` is a single all-or-nothing flag: when on, both Salesforce and
Conductor are mocked; when off (the default), the app uses live providers and
will surface a clear error envelope if an org has no credentials configured —
it never silently falls back to mock data. The production K8s and Docker
manifests pin `SHOW_MOCK=false` explicitly, so production can never
accidentally serve mock data.

### Confirmation Before Destructive Actions

Any action that changes data — Salesforce writes, bulk delete / modify / reassign, importing records, Conductor batch reruns, the trigger-bypass toggle, deleting Apex logs or trace flags, and running the Anonymizer — asks for confirmation before it runs. A dialog appears summarizing what will happen; click **Cancel** to back out with nothing changed. For the most destructive actions you must also tick an acknowledgement checkbox before the confirm button becomes active. Read-only actions (Refresh, Preview, Run Scan) run immediately with no prompt.

### Navigation

The top nav contains all tabs: **Dashboard · Migration · Validation · SOQL · Schema · Data Ops · Scenarios · Key Maps · Logs · Observe · Impact · Admin · Deploy · CLI · Settings**. The active tab is underlined in amber.

### Salesforce Deep Links

Any Salesforce record ID shown in a table — in SOQL results, scan results, the
Users list, and more — is a clickable link (marked with a ↗) that opens that
record directly in Salesforce in a new tab. This works for `Id` columns and
lookup fields alike.

---

## Dashboard

**URL:** `/dashboard`

The Dashboard is the home page — a single-screen health summary across all tools. All eight widgets load in parallel when the page opens.

**How to use it:** Open it as your daily morning check before starting migration work. Each widget has its own footer link (e.g. **Run Check →**, **View Batches →**, **Open Checklist →**) to navigate to the full feature page.

### Widgets

| Widget | What it shows |
|---|---|
| **Pre-Go-Live Readiness** | Latest composite readiness % with a color-coded badge (green ≥90%, amber 70–89%, red <70%) |
| **API Limits** | Top 3 governor limits closest to their threshold — name, % used, mini progress bar |
| **Data Validation** | Quick-links to the 5 validation sub-tabs (Duplicate Radar, External IDs, Contact Points, Field Completeness, Orphaned Records), each with a status badge |
| **Migration Batches** | Aggregate counts across recent batches — Total, Completed, In Progress, Failed |
| **Apex Test Coverage** | Org-wide Apex test coverage — classes passing / total (≥75% threshold), with a warning if any class is below it |
| **Pre-flight Checklist** | Progress bar showing how many of the 21 pre-flight checklist items are complete, broken down by the 5 categories |
| **Recent Changes** | Last 5 Setup Audit Trail entries — section, action, and how long ago |
| **Org Health** | Letter grade (A/B/C/D) computed from readiness + preflight percentages |

---

## Migration

### Readiness

**URL:** `/migration/readiness`

The Readiness scorecard answers "are we ready to go live?" before each migration milestone. It runs 6 checks against the active org and scores each one.

**How to use it:**
1. Select the org from the card dropdown.
2. Click **Run Now**.
3. Review each check row — green (100%, or 0 duplicate groups for Duplicate SIS IDs), amber (90–99%, or up to 25 duplicate groups), red (below 90%, more than 25 duplicate groups, or a query failure). Each row's detail column shows the raw record counts behind the percentage.

**Checks explained:**

| Check | What it validates | Why it matters |
|---|---|---|
| SIS ID Coverage | % of PersonAccounts with a Colleague student ID (`SIS_ID__c`) | Required for matching during upsert |
| Ethos GUID Coverage | % linked to Ethos identity (`Ethos_Guid__c`) | Required for LDM reconciliation |
| ContactPoint Parent Links | % of Email/Phone/Address ContactPoints with a non-null ParentId | Broken parents cause FIELD_INTEGRITY_EXCEPTION |
| Required Fields | % of PersonAccounts with FirstName, LastName, and RecordType populated | Blank required fields fail validation rules |
| Duplicate SIS IDs | Number of `SIS_ID__c` values shared by more than one PersonAccount | Duplicates cause DUPLICATE_VALUE on upsert |
| Individual Links | % of Email/Phone/Address ContactPoints with a non-null IndividualId | Required by the Person Account model |

The **Overall %** at the bottom is a composite score — a red result on any single check pulls the overall status to red. Scores are stored in PostgreSQL and charted historically on the Observe → Data Quality Trends section.

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
| Severity | HIGH (blocks migration) / MEDIUM (needs a look) / LOW (safe to retry) |
| Cause | Plain-English explanation of what went wrong |
| Suggested fix | Actionable next step |
| SIS IDs | Expandable list of Colleague person IDs affected |

---

### Batch Progress

**URL:** `/migration/batches`

Live dashboard for a running Conductor migration batch.

**How to use it:**
1. Enter the **Workflow Name** (e.g., `EDA_Person_Sync`) and optionally a **Start Time**.
2. Click **Load Status**.
3. Toggle **Auto-refresh (15s)** to poll for new data, instead of a manual refresh.

| Element | Description |
|---|---|
| Progress bar | Overall % complete with animated striping while running |
| ETA / Rate | Estimated time to completion and current records-per-minute rate |
| Status counts | Completed / Failed / Running / Queued breakdown |
| Failure table | Per-workflow failure details with error message and Re-run button |

**Re-run All Failures** requeues every failed workflow in the current result set back to Conductor — you are asked to confirm before the reruns are submitted.

---

### Pre-flight Checklist

**URL:** `/migration/preflight`

A 21-item go-live checklist stored in PostgreSQL so progress persists across sessions and team members.

**How to use it:**
1. Review items grouped into 5 categories.
2. Click the checkbox next to each item to mark it complete — saves immediately.
3. The progress bar at the top updates in real time.
4. Click **Print Checklist** for a printable copy.

**Default categories:**

| Category | Example items |
|---|---|
| Data Quality | SIS ID coverage ≥99%, no duplicate PersonAccounts, zero orphaned ContactPoints |
| Integrations | Conductor connection verified, Named Credentials confirmed, Remote Site Settings active |
| Permissions | Migration Admin permission set assigned, sysadmin count reviewed |
| Testing | Apex test coverage ≥75%, regression suite baselined |
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
2. Review the results table — one row per strategy, with the duplicate count, sample record IDs, and a status badge.
3. Click **Merge** on a strategy row — opens the merge modal prefilled with the strategy's first two sample IDs as the Master (kept) and Victim (merged & deleted) Record IDs.
4. Adjust the Master/Victim Record IDs if needed, tick the acknowledgement checkbox, then click **Confirm Merge**.

**Match types (5 strategy cards):**

| Type | Logic |
|---|---|
| Same SIS ID | Two records share the same `SIS_ID__c` |
| Same Name + Birthdate | Two records share the same Name and `PersonBirthdate` |
| Same Email | Two records share the same `PersonEmail` |
| Same Ethos GUID | Two records share the same `Ethos_Guid__c` |
| Fuzzy Name | Name within edit distance ≤2 (Wagner-Fischer), compared within the same 3-character name prefix group — catches typos (e.g. "Johnson" vs "Jonhson") |

> **Warning:** Merge is irreversible. A confirmation dialog with an acknowledgement checkbox guards the action. Always verify the records in Salesforce before confirming.

---

### External ID Coverage

**URL:** `/validation/external-ids`

Reports what percentage of records have each external ID field populated, across five tracked objects: PersonAccounts (`SIS_ID__c` + `Ethos_Guid__c`), the three ContactPoint objects (`SIS_ID__c`), and `IndividualApplication` (`SIS_ID__c` + `Ethos_Guid__c`).

**How to use it:** Select the org and click **Run Report**.

| Field | Purpose | Threshold |
|---|---|---|
| `SIS_ID__c` | Colleague person ID — required for upsert matching | 100% green, ≥90% amber, below 90% red |
| `Ethos_Guid__c` | Ethos LDM GUID — required for cross-system reconciliation | 100% green, ≥90% amber, below 90% red |

Each row shows total records, records with the field populated, coverage %, and a color-coded badge.

---

### ContactPoint Scanner

**URL:** `/validation/contactpoints`

Checks that `ContactPointEmail`, `ContactPointPhone`, and `ContactPointAddress` records have valid parent links to both an `Account` (via `ParentId`) and an `Individual` (via `IndividualId`) — including records that are parented, but to the *wrong* object (a `ParentId` whose 3-character prefix is `003`, i.e. a Contact, instead of `001` for Account). That wrongly-typed case used to report green under an older null-only check.

**How to use it:** Select the org and click **Run Scan**. Review broken records grouped by ContactPoint type.

**Checks performed (per ContactPoint type — Email, Phone, Address):**

| Check | Description |
|---|---|
| Missing Parent | `ParentId` is null — the record is completely orphaned |
| Parented to the wrong object | `ParentId` is non-null but doesn't start with `001` (Account) — typically a Contact (`003`) |
| Missing Individual | `IndividualId` is null |

Broken ContactPoint parents cause `FIELD_INTEGRITY_EXCEPTION` errors during migration and must be resolved before a batch can succeed.

---

### Field Completeness

**URL:** `/validation/completeness`

Checks 10 fixed, migration-critical (object, field) pairs — spanning PersonAccounts, Business Accounts, the three ContactPoint objects, and Individual — and reports the fill rate for each.

**How to use it:** Select the org and click **Run Check**.

**Fields checked:** PersonAccount `SIS_ID__c`, `Ethos_Guid__c`, `PersonEmail`, `PersonBirthdate`, `Phone`; Business Account `BillingStreet`; `ContactPointEmail.EmailAddress`; `ContactPointPhone.TelephoneNumber`; `ContactPointAddress.Street`; `Individual.FirstName`

Each row shows the object, field, label, total records, populated count, missing count, fill %, and a status badge (green ≥95%, amber ≥75%, red <75%).

---

### Orphan Scanner

**URL:** `/validation/orphans`

Finds records that exist in Salesforce but are disconnected from their required parent records.

**How to use it:** Select the org and click **Run Scan**.

**Orphan checks:**

| Check | Orphan condition |
|---|---|
| ContactPointEmail — missing Account | `ParentId` is null |
| ContactPointPhone — missing Account | `ParentId` is null |
| ContactPointAddress — missing Account | `ParentId` is null |
| ContactPointEmail — missing Individual | `IndividualId` is null |
| ContactPointPhone — missing Individual | `IndividualId` is null |
| Person Account — no linked Individual | `IndividualId` is null on the PersonAccount |

Each card shows the orphan count and sample record IDs (with Salesforce deeplinks).

---

### Merge History

**URL:** `/validation/merge-history`

Audit log of all duplicate merges performed through Duplicate Radar. Stored in PostgreSQL.

**How to use it:** Select the org and click **Refresh**.

| Column | Description |
|---|---|
| Date | Timestamp of the merge operation |
| Master ID | Salesforce ID of the record that was retained |
| Victim ID | Salesforce ID of the record that was absorbed |
| Bypass | Whether Bypass Triggers was active during the merge |
| Status | Whether the merge succeeded or errored |

The stats summary shows Total Merges, Successful, Failed, and Bypass Used counts across all sessions.

---

## SOQL Workbench

**URL:** `/soql`

A full SOQL query editor with result display, history, and saved queries.

**How to use it:**
1. Type a SOQL query in the text area (e.g., `SELECT Id, Name FROM Account LIMIT 10`).
2. Select the target org.
3. Click **Run** (or **Run All Pages** to page past the 2,000-row SOQL limit).
4. Results display in a sortable table.
5. Click **Download CSV** to save the results.

**Saved Queries:**
- Click **Save Query** to store the current query — you're prompted for a name.
- Select a saved query from the dropdown to load it into the editor.
- With a saved query selected, click **Delete** to remove it.

**Query History:**
- Click the **Recent Queries** panel header to expand the last 25 queries you ran in this org (stored in PostgreSQL).
- Click any entry to reload it into the editor.
- Click the ✕ next to an entry to remove it from history.

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

### Org Metadata Diff

**URL:** `/schema/metadata-diff`

Compares *deployable metadata components* between two orgs — the counterpart to Org Schema Diff (which covers fields). Covers five metadata types: Apex Classes, Apex Triggers, Flows, Validation Rules, and Custom Objects.

**How to use it:**
1. The Left Org is the active org (shown as a badge). Select the Right Org from the dropdown (default: `prod`).
2. Choose which metadata types to compare — all five are checked by default.
3. Click **Run Diff**.

Each accordion panel reports:
- **Left-only** — components in the active org not yet deployed to the right org
- **Right-only** — components in the right org that were removed from or never existed in the active org (legacy)
- **Modified** — present in both, but configured differently (e.g., different API version, length, or active status)

The component count badges are green (no differences) or orange (has differences). Expand any panel to see the full list.

---

### Record Inspector

**URL:** `/schema/inspect`

Fetches every queryable field value for a single Salesforce record — a lightweight alternative to Salesforce Inspector for confirming migrated data without writing a SOQL query.

**How to use it:**
1. Enter the **Object API Name** (e.g. `Account`, `ContactPointEmail`).
2. Choose the lookup mode:
   - **Salesforce ID** — enter the 18-character record ID directly.
   - **External ID** — enter the External ID field API name (e.g. `SIS_ID__c`) and the value to match.
3. Click **Inspect**.

The results table shows every non-compound, non-binary field with its API name, label, type, and live value. Use the **Filter fields** box to narrow by name, label, or value.

> Tip: the "Open in Salesforce" button appears for SF ID lookups and links directly to the record in the org.

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

**How to use it:** Start typing in the **SObject Name** box — it autocompletes against the selected org's objects (the same searchable picker used across the app) — pick one and click **Generate**. Click **Export CSV** to download as a spreadsheet. Every object box in Mission Control now works this way; each is scoped to what makes sense for that tab (Data Dictionary lists everything you can describe; SOQL lists queryable objects; the CLI field builder lists only objects that accept custom fields).

**Output columns:** Field Name · Label · Type · Length · Required · Unique · External ID · Formula · Picklist Values · Help Text · Description

Custom fields are sorted to the top of the list.

---

### Field Finder

**URL:** `/schema/field-finder`

The inverse of the Data Dictionary: instead of listing every field on one object, you give it a field and it lists every object that has it. Useful before renaming or removing a field, or to find every custom object that stores a given External ID.

**How to use it:**
1. Enter the **Field API name** — paste it however you have it. A trailing `__c` and any managed-package namespace prefix (e.g. `hed__`) are stripped automatically, so `SIS_ID__c`, `SIS_ID`, and `hed__SIS_ID__c` all resolve to the same search.
2. Click **Find**. This always runs the fast path first: one Tooling API `CustomField` query keyed on the normalized name, which finds **custom** fields only and returns almost instantly.
3. Tick **Deep scan — also find standard fields** before clicking Find to also catch **standard** fields (and any custom field the fast path missed) — this describes every object in the org one at a time and can take up to a minute on a large org. The scan is capped at 500 objects; if the org has more, the summary line notes the scan was capped.
4. Click **Export CSV** once results are showing to download the table.

The results table lists Object, Field API Name, Label, Type, and Custom (a checkmark) for every match, sorted by object; custom-field rows get a light amber row highlight. The summary line above the table reports the normalized field name, how many objects matched, the custom/standard split, and which method ran (Tooling API vs. deep scan). If a Tooling-only search comes back empty, a warning banner suggests ticking Deep scan in case it's a standard field. Read-only — Field Finder never writes to Salesforce.

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
the execute step asks for confirmation before it runs.

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
your original rows back with an `sf__Error` column explaining each failure — fix
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

### Match (Fuzzy Duplicate Detection)

**URL:** `/data-ops/match`

Finds **near**-duplicate records — typos, nicknames, transposed characters —
that exact matching misses. Where the [Duplicate Radar](#duplicate-radar) catches
records with an identical SIS ID or email, Match catches "John Smith" vs
"Jon Smith". It is the in-house equivalent of DemandTools' Match.

**How it works:**
- Records are bucketed by the **Soundex** code of a blocking field, so only
  plausibly-similar records are compared (this keeps the scan fast).
- Within each bucket, every pair is scored 0–100% on how similar the chosen
  compare fields are.
- Pairs scoring at or above your threshold are reported.

**How to use it:**
1. Enter the **Object** and a **WHERE clause**.
2. **Compare Fields** — comma-separated fields whose similarity is averaged
   (e.g. `FirstName, LastName, PersonEmail`).
3. **Blocking Field** — the field whose Soundex buckets records (e.g. `LastName`).
4. Set the **Similarity Threshold** with the slider (default 0.85).
5. Click **Find Matches** — candidate pairs appear sorted by score, with each
   record's ID linked to Salesforce and the fields that differ highlighted.

Match is **detection only** — it never modifies records. Review the candidate
pairs and merge confirmed duplicates via the Duplicate Radar.

> **Scan limits:** up to 2,000 records per run; very large Soundex buckets are
> capped at 300 records (the summary flags when this happens). Narrow the WHERE
> clause for large objects.

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

**URL:** `/data-ops/join`

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

### Data Backup

**URL:** `/data-ops/backup`

Captures point-in-time CSV snapshots of key objects (every queryable field) and stores them compressed in the database. It is the recovery point for the destructive Data Ops tools — the Salesforce Recycle Bin only soft-deletes, and only for 15 days.

**How to use it:**
1. Review the **Objects to back up** list — it pre-fills with `Account`, `Contact`, `Individual`, and the three ContactPoint objects. Edit it (one object per line) as needed.
2. Click **Run Backup Now**. Large objects can take a minute.
3. The **Backup History** table lists each run with its trigger, status, object count, and record count.
4. Click **Download ZIP** on any run to download a ZIP archive containing one CSV per object.

**Scheduled runs:** Set `BACKUP_ENABLED=true` to register a nightly run at 02:00 CT. `BACKUP_RETAIN` (default 14) controls how many runs are kept — older runs are pruned automatically.

> **Note:** Restore is a separate, planned feature. For now, download a backup and re-import via the Import tool to recover data.

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
- Execute asks for confirmation before it runs.

> **Warning:** Bulk updates bypass most validation rules and triggers (unless trigger bypass is off in Settings). Always Preview before executing in production.

---

### Record Lock Detector

**URL:** `/data-ops/record-locks`

Finds records stuck in pending approval processes — a common cause of DML failures when migration triggers try to update locked records.

**How to use it:** Select the org, optionally filter by Object, and click **Refresh**.

| Column | Description |
|---|---|
| ProcessInstance ID | Salesforce ID of the approval process instance |
| Target Record | ID of the locked record (SF deeplink) |
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

## Scenarios

The Scenarios tab chains individual Data Ops actions — delete, modify field, reassign owner, bulk update, tune — into a single saved, repeatable pipeline. Each step calls the exact same service the Data Ops tab calls directly, so the same `SHOW_MOCK` demo data, `dml_guard` safety checks, and audit trail apply — a scenario is just Data Ops steps run in sequence and remembered for next time. Scenarios can be tagged for organization and, once tested, approved for unattended scheduled runs via Argo.

### Scenario List & Tags

**URL:** `/scenarios`

Lists every saved scenario.

**How to use it:**
1. Click **+ New Scenario** to start building one ([see below](#building-a-scenario)).
2. The **Saved scenarios** table shows each scenario's Name (with its description underneath, if set), Steps count, Tags, and Last updated time.
3. Click **Edit** to open the builder, **Run** to execute it immediately from the list (asks for confirmation with a required acknowledgement checkbox, same as the builder's Run button), or **×** to delete it (asks for confirmation).

**Tags** (left rail): click **+ New** to create a tag — a name plus a color from a fixed palette (slate, orange, amber, green, blue, purple, red, muted). Click a tag chip to filter the scenario list to just that tag; click **Show all scenarios** to clear the filter. Click the **×** on a tag row to delete it — this also detaches it from every scenario it was on.

---

### Building a Scenario

**URL:** `/scenarios/new` (or `/scenarios/<id>` to edit an existing one)

**How to use it:**
1. Enter a **Name** (required) and optional **Description**.
2. Pick a step type from the dropdown — **Delete**, **Modify field**, **Reassign owner**, **Bulk update**, or **Tune (standardize)** — and click **+ Add**. Each added step gets its own card with the parameter fields for that type:

   | Step type | Fields |
   |---|---|
   | Delete | SF Object, WHERE clause |
   | Modify field | SF Object, WHERE clause, Field, New value |
   | Reassign owner | SF Object, WHERE clause, New owner ID |
   | Bulk update | SF Object, WHERE clause, Field, Value, Dry run |
   | Tune (standardize) | SF Object, WHERE clause, Field rules (JSON, e.g. `{"FirstName": ["trim","title_case"]}` — see [Tune](#tune-data-standardization) for the rule vocabulary) |

3. On each step card, use **▲** / **▼** to reorder it, **×** to remove it (asks for confirmation — the step is only removed from the editor until you click Save), the **On error** dropdown to choose **Stop pipeline** or **Continue to next step** if that step fails, and the **Bypass triggers** checkbox to pass `bypass_triggers` through to that step's Data Ops call.
4. Click **Save**. Saving a brand-new scenario redirects you to its canonical `/scenarios/<id>` URL — the **Run** button stays disabled until then.

> **Not in the dropdown:** the backend also recognizes a sixth step type, `key_map_expand` (requires `key_map_id` + `source` params), for driving a [Key Map](#key-maps) preview from inside a pipeline. It has no row in the step-type dropdown or parameter form — the only way to add one today is to include it in the `steps` array you `POST` directly to `/api/v1/scenarios/create` or `/update/<id>`. See [Using a Key Map in a Scenario](#using-a-key-map-in-a-scenario).

**Tags:** once the scenario is saved, click **Manage tags** — this opens a browser prompt listing existing tag names; type an existing name to attach it, or a new name to create-and-attach a tag (created in the default *slate* color). Click the **×** on an attached tag chip to detach it.

**Scheduling** — see [Scheduling (Argo)](#scheduling-argo) below.

---

### Running a Scenario

Run from the builder's **▶ Run** button or the list's **Run** button — both execute synchronously (the request doesn't return until every step has finished) and both are gated by the same confirmation dialog with a required acknowledgement checkbox, since this performs live writes.

Each step runs in order. A step's outcome is recorded even when it fails; if that step's **On error** was **Continue to next step**, the run keeps going and finishes `partial`. If it was **Stop pipeline** (the default), the run stops there and finishes `failed`. A run with no failed steps finishes `success`.

The builder's **Last run** card (appears after you click Run) shows a status badge — green **SUCCESS**, amber **PARTIAL**, or red **FAILED** — and a table of every step's index, type, status, and detail. This card only reflects the run you just triggered; it does not reload from history on a page refresh.

> **Which org does it run against?** An interactive Run — from either the builder or the list — always runs against whatever org is currently selected in the top-right **Org** dropdown, regardless of which org the scenario was created under. Only the scheduled (Argo-triggered) run below uses the org the scenario was originally saved with.

Every run is recorded server-side and retrievable via `GET /api/v1/scenarios/<id>/runs` (documented in `/swagger`), but there is no run-history table in the UI today — the builder only ever shows the most recent run.

---

### Scheduling (Argo)

**URL:** `/scenarios/<id>` (Scheduling card)

A scenario can be promoted to unattended, scheduled execution once you've run it interactively and trust it.

**How to use it:**
1. Toggle **Approved for scheduled runs** on. Turning it on asks for confirmation — approving lets the scenario run unattended with no one watching, so only do this after testing it interactively. Turning it off needs no confirmation.
2. Enter a **Cron schedule** (5 fields, e.g. `0 6 * * 0` for 6am every Sunday).
3. Click **Generate Argo CronWorkflow** — a modal shows the generated YAML in a read-only textarea. Click **Copy** to copy it.
4. Commit the YAML to your manifests repo. It references a K8s secret holding the scheduler token that must match the app's `SCHEDULER_TOKEN` config — the modal spells out the exact secret name and key to use.

On its cron schedule, Argo `POST`s the token-authed `/api/v1/scenarios/<id>/scheduled-run` endpoint (header `X-MC-Scheduler-Token`). The app checks the token, refuses the run unless **Approved for scheduled runs** is on, then runs the scenario against the org it was created in and logs one structured summary line to stdout — that log line is what shows up in the Argo UI. A run that doesn't finish clean (any failed step) returns HTTP 500, so `curl -f` fails and Argo flags the CronWorkflow.

> **Blank `SCHEDULER_TOKEN` disables scheduling entirely** — every scheduled-run request is rejected, so there is no accidental unauthenticated trigger of a write pipeline.

---

## Key Maps

A Key Map turns source rows — a Colleague SQL Server query, pasted CSV, or pasted JSON — into Salesforce records of one target SObject. Build one when a single source row needs to fan out into several related Salesforce records that each resolve different foreign keys and set different literal field values. PTAT (`ProgramTermApplnTimeline`) is the first consumer, but the model is generic. A key map isn't tied to a specific org — only its target SObject is fixed; FK resolution runs against whichever org is active in the navbar when you preview or export.

Three layers make up a key map:
- **FK lookups** resolve a target foreign-key field from a source column by matching another SObject's external-ID field (e.g. source `TERMS_ID` → `AcademicTermId` via `AcademicTerm.SIS_ID__c`).
- **Family routing** picks which family of variants applies to a given source row, based on column-equals-value rules (a family with no rule is the default, used when no other family's routing matches).
- **Variants** — each variant in the chosen family produces one output row, merging its overlay (target field → literal value) onto the FK-resolved base. One source row can become several output rows this way.

A key map is **preview-only** — running it reads from Salesforce to resolve FKs but never writes. Every run returns the would-be-inserted rows plus a list of anything that couldn't be resolved, exportable as CSV.

### Key Map List

**URL:** `/key-maps`

Lists every saved key map. The **Saved key maps** table shows Name (with description underneath, if set), Target SObject, and Updated time. Click **Edit** to open the builder, **Run** to go straight to the preview page, or **×** to delete it (asks for confirmation).

---

### Building a Key Map

**URL:** `/key-maps/new` (or `/key-maps/<id>` to edit an existing one)

**How to use it:**
1. Under **Details**, enter a **Name**, the **Target SObject**, and an optional **Description**, then click **Save**. FK lookups and families can't be added until the key map has been saved once.
2. Under **Foreign-key lookups**, fill in **source column**, **target field**, **lookup SObject** (an autocomplete restricted to queryable objects), and **lookup field** (defaults to `SIS_ID__c`), then click **+ Add**. Each lookup appears in the table above with a **×** to delete it.
3. Under **Families & variants**, type a family name and click **+ Family** — a modal lets you add **+ Condition** rows (`source column` = `value`); leave it with no conditions to make this the default family. Click **Create family**.
4. On a family card, click **+ Variant** to open the Add Variant modal: name the variant, add one or more **Overlay** rows (target field → literal value — every row needs both a field and a value), and choose **Applies to**: **Every row in this family** (default), or **Only when…** with its own `source column` = `value` condition rows. Click **Add variant**.

Each family card shows its routing summary (`when X=Y AND ...`, or `(default — no routing)`) and a table of its variants (name, overlay, applies-when) with a **×** to delete each one. Deleting a family (confirmed) removes all of its variants too.

Once saved, a **Run / Preview →** link appears next to Save, taking you to the preview page below.

---

### Running a Preview

**URL:** `/key-maps/<id>/run`

**How to use it:**
1. Choose a source mode — **SQL** (default), **CSV**, or **JSON**:
   - **SQL** — a read-only `SELECT` query against the Colleague SQL Server (the same shared connection the Join Builder uses).
   - **CSV** — paste CSV or TSV text; the first row is the header.
   - **JSON** — paste a JSON array of objects (or an object plus an optional **records_path** to navigate to the array).
2. Click **▶ Preview**. The results card shows a badge (`N rows from M source` — green if every FK resolved, amber if any didn't), summary tiles for **Source rows**, **Output rows**, **Unresolved FKs**, and **Skipped (no family)**, and two tabs:
   - **Output rows** — the expanded rows, columns dynamic per your FK/overlay fields. Capped to the first 200 rows in the preview (a note says so and points you to Export for the full set).
   - **Unresolved FKs** — one row per source value that didn't resolve, showing which row, source column, value, and lookup SObject/field it failed against. Also capped at 200.
3. Click **⭳ Export CSV** (enabled once a preview has run) to download the full, uncapped result as `key_map_preview.csv`.

> A source row that doesn't match any family (including no default family) is silently counted in **Skipped (no family)** rather than erroring — check that count if your output has fewer rows than you expected.

---

### Using a Key Map in a Scenario

A key map can be driven from a [Scenario](#scenarios) as a `key_map_expand` step instead of run manually — useful for a scheduled Argo run that regenerates the preview on a cadence. The step's params are `key_map_id` and `source` (the same `{mode, ...}` source spec used above — `sql`, `csv`, `json`, or an API-only `inline` mode that takes a literal `rows` list). Running the step ingests the source rows, expands them through the key map, and saves a run; the scenario's own step result carries only the summary (counts), not the full row set, to keep the scenario run record small — pull the full output from the key map's Run / Preview page instead.

As noted in [Building a Scenario](#building-a-scenario), `key_map_expand` has no row in the Steps UI dropdown — add it by including it in the `steps` array when you `POST` to `/api/v1/scenarios/create` or `/update/<id>` directly.

---

## Logs

### Apex Logs

**URL:** `/logs`

Lists and inspects Apex debug logs for the active org.

**How to use it:**
1. Select a **time range** (All available / Last 15 min / 1 hour / 6 hours / 24 hours / custom).
2. Toggle **Auto-refresh** to poll for new logs every 10 seconds.
3. Click a log row to open the detail panel.
4. Click **Delete** on a row to remove a single log.
5. Click **Delete All Logs** to clear all debug logs.

The detail panel shows: log header (user, duration, heap size, CPU time), parsed event timeline grouped by category (SOQL, DML, Apex calls, limits), and the raw log body.

> **Note:** Delete and Delete All Logs ask for confirmation before removing logs.

---

### Flow Errors

**URL:** `/logs` → Flow Errors tab

Lists recent Flow interview failures — `FlowInterview` records with `InterviewStatus = 'Error'` (a Data API object; it has no `ErrorMessage` field to show).

**How to use it:** Click **Refresh** to fetch recent failures.

**Columns:** Flow · Element · Status · Created.

Use this to catch flows failing silently during migration data loads — Flow errors don't appear in Apex logs.

---

### CPU Summary

**URL:** `/logs` → CPU Summary tab

Shows `DurationMilliseconds` from the `ApexLog` metadata for the 20 most recent logs, without downloading each log body — a quick way to spot slow transactions.

**How to use it:** Click **Refresh**.

**Columns:** User · Operation · Duration (ms) · Log Size · Status.

Logs over 5 seconds are highlighted amber; a non-Success status is highlighted red. Use this to spot slow transactions before a high-volume migration batch, without downloading full log bodies.

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
4. Select **Duration** (15 minutes, 30 minutes, 1 hour, 2 hours, or until midnight).
5. Click **Create Trace Flag**.

**Quick action:** Click **⚡ Trace Me (30 min)** to immediately create a 30-minute FINEST trace flag for the current user.

**Cleanup:** Click **Delete Expired** to remove all expired flags at once. Click the trash icon on a row to remove a specific flag.

> **Note:** Create, Delete Expired, and trace-flag deletes ask for confirmation before they run.

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

Objects included: Person Accounts · Business Accounts · `ContactPointEmail` · `ContactPointPhone` · `ContactPointAddress` · `Individual` · `Campaign` · `CampaignMember` · `Task` · `Event` · `Case` · `Opportunity`.

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

Searches Validation Rules, active Flows, and Reports for references to a given field — essential before renaming or deleting a field. Not an Apex code search (see Apex Code Search under Schema for that).

**How to use it:** Select the org, enter the Object and Field API Name, then click **Scan**.

Three accordion sections:
- **Validation Rules** — rules (via the Tooling API) whose error condition formula contains the field name: Object, Rule Name, Description, Error Message.
- **Active Flows** — every active flow in the org, flagged "Manual review required": the REST API doesn't expose flow XML, so this lists all active flows rather than confirming which ones actually reference the field.
- **Reports** — a count of reports in the org, with the same manual-review caveat.

Use this before any schema change to understand the blast radius — keeping in mind the Flow and Report sections are leads to check manually, not confirmed matches.

---

### Permission Set Viewer

**URL:** `/impact` → Permissions tab

Field-centric permission audit — for an object (and optionally one field), shows which permission sets grant Read/Edit access to each of its fields.

**How to use it:** Enter an **Object API Name** (and optionally a **Field API Name** to narrow to one field), then click **Audit**.

The results table lists one row per field with the permission sets granting Read access and the permission sets granting Edit access. Entering a specific field additionally shows an access-detail table: Permission Set · Read · Edit · Users.

Use this to verify the integration user's permission set grants access to all migration fields before go-live.

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
1. In the saved suites table, click **Run** on a suite.
2. Results show Pass (matches expected) or Fail (differs from expected/baseline).
3. Click **Set Baseline** on a suite to store current results as the new expected values.

Example assertion: "Account with SIS_ID__c should return exactly 4,312 records." A regression on this suite means a migration step accidentally wiped or duplicated records.

---

### Permission Gap Analyzer

**URL:** `/impact` → Perm Gap tab

Compares two permission sets and shows exactly which object and field permissions differ.

**How to use it:** Opening the tab auto-loads the org's permission sets into the two dropdowns; select Permission Set A and B, then click **Compare**.

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

**Columns:** Name · Type (Scheduled Apex / Data Export / Unknown) · State (Waiting / Acquired / Executing / Complete / Deleted / Paused / Error / Blocked) · Next Fire · Previous Fire · Triggered (times triggered) · Cron.

Use this to verify the daily readiness scheduler is active and to check for jobs that conflict with migration batch windows.

---

### Test Coverage

**URL:** `/admin` → Test Coverage tab

Shows Apex code coverage for every class and trigger in the org.

**Columns:** Class/Trigger name · Lines covered · Lines uncovered · Coverage %.

Rows below 75% are highlighted in red (Salesforce deployment requires ≥75% overall coverage). Sort by Coverage % ascending to find the classes that need new tests before a deployment.

---

### Deployment History

**URL:** `/admin` → Deployment History tab

Lists recent metadata deployments to the org.

**Columns:** Deployment ID · Status (Succeeded/Failed/Pending) · Deployed by · Start time · Duration · Components deployed · Components failed.

Use this to find recent deployments that may have introduced regressions, and to check whether a deployment is still in progress before running migration.

---

### User Audit

**URL:** `/admin` → User Audit tab

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

Two tables: Platform Event Channels, and their Subscriptions (Channel Members).

**Platform Event Channels columns:** Label · API Name · Description.

**Subscriptions (Channel Members) columns:** Name · Channel · Subscriber Type (Flow, Apex Trigger, or Process Builder).

Use this to understand what fires when migration records are inserted or updated, and to identify platform event subscribers that may add unexpected overhead to high-volume batches.

---

### Record Types

**URL:** `/admin` → Record Types tab

Lists all record types for all objects in the org.

**Columns:** SObject · Name · Developer Name · Active · Count (record count, shown for Account/Opportunity/Case/Campaign/Contact).

Use this to verify the `PersonAccount` record type is active and correctly named before migration upserts — the record type ID is required on every Account insert.

---

### Email Templates

**URL:** `/admin` → Email Templates tab

Lists all email templates with their folder, subject, encoding, active status, and last-modified date. A search box filters by name, folder, or subject.

Use this to find templates that reference fields being renamed or removed during migration, and to confirm template availability before go-live if any migration workflows trigger email notifications.

---

### Audit Trail

**URL:** `/admin` → Audit Trail tab

Shows the Salesforce Setup Audit Trail — every Setup change made in the org within the selected window.

**How to use it:** Select the number of days to look back (1 / 7 / 14 / 30) and click **Refresh**. A search box filters by section, user, or detail.

**Columns:** Date · By · Section (what area of Setup changed) · Action · Detail.

Use this to answer "what changed in this org recently?" after an unexpected migration failure or behavior change.

---

### Job Queue

**URL:** `/admin` → Job Queue tab

Live view of the Apex async job queue (`AsyncApexJob`) — shows Batch Apex, Queueable, Scheduled, and Future jobs.

**How to use it:** Select a Status filter pill (All / Queued / Processing / Completed / Failed) and optionally toggle **Auto-refresh** (polls every 10 seconds).

| Column | Description |
|---|---|
| Class | The Apex class being executed |
| Type | BatchApex / Queueable / ScheduledApex / Future |
| Status | Blue = Processing · Amber = Queued · Green = Completed · Red = Failed |
| Progress | Items Processed / Total Items |
| Errors | Error count for the job |
| By | Who submitted the job |
| Started | When the job was created |
| Duration | Elapsed time |

Hover the Status badge on a row with extended status (e.g. a failure) to see the error message.

Use this to monitor long-running batch jobs during migration and to verify no jobs are stuck in a Queued state that would block your batch from starting.

---

### Login History

**URL:** `/admin` → Login History tab

Shows the last 200 login history events for the org, with a filter box (IP, platform, or status) and summary badges (total, failed, unique IPs, unique users).

**Columns:** Time · IP · Platform · Login Type · Browser · Status (Success/Failed).

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

> **Requires `PII_SERVICE_URL`** in your environment. Without it, the service runs in stub mode — logs what it would send but does not modify data. **Run Anonymizer** asks for confirmation before submitting records to the PII service.

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
1. Pick a component-type tab — Classes, Triggers, Fields, Flows, Perm Sets, or Val Rules (`ApexClass`, `ApexTrigger`, `CustomField`, `Flow`, `PermissionSet`, `ValidationRule` — queried from the active org).
2. Click **Load <Type>** to fetch that type's components, then check the ones to include (or use **Select All** / **Clear**). Selections accumulate across tabs in the **Selected Components** sidebar.
3. Click **Generate Package** to produce the `package.xml`.
4. Copy the XML or download it for use with `sf project deploy` or the Metadata API.

A pre-deployment checklist is generated alongside the package — standard items to verify before deploying (backup taken, tests passing, maintenance window scheduled, etc.).

---

## Settings

**URL:** `/settings`

Configures org connections, trigger bypass behavior, and API collection runners.

### Org Connection Test

Select an org and click **Test Connection** to verify that the credentials in your environment variables are valid — it runs a trivial `SELECT Id FROM Account LIMIT 1` query. Returns a record count and the instance URL on success, or a detailed error message on failure.

### Bypass Triggers

This toggle sets a per-session flag (it does not itself write to Salesforce) and asks for confirmation before changing it. When on, and `SF_BYPASS_SETTING`/`SF_BYPASS_FIELD` are configured, subsequent writes that check the flag (SOQL inline edit, Duplicate Radar merge) flip your Hierarchy Custom Setting's bypass field to `true` on Salesforce immediately before the write and restore it to `false` immediately after — so triggers are disabled only for the duration of that write, not left on.

> **Important:** Turn the toggle back off once you're done with writes that need the bypass. Leaving it on for the rest of your session means every subsequent bypass-aware write in that session skips triggers, which can cause data integrity issues and missed automations if left on into unrelated work.

### API Collections

Imports and runs Postman v2.1 collection files against your Salesforce orgs. Collections are built in Postman (or hand-written as Postman JSON) and imported here — there's no in-app request builder.

**How to use it:**
1. Choose a Postman collection `.json` file and click **Import**.
2. The collection appears in the table (Collection Name · Requests · Last Run · Last Status).
3. Click **Run** on a collection to execute all its requests in sequence.
4. Results list each request's name with a color-coded status-code badge (green for 2xx, red otherwise), plus a toast summarizing how many passed.
5. Click **Delete** to remove a collection (asks for confirmation).

Collections are stored in PostgreSQL and shared across all sessions. Use this for smoke-testing integration endpoints after a deployment, or verifying Named Credential callouts are working correctly against a specific org.

---

## CLI

The **CLI** tab makes the Salesforce CLI (`sf`) approachable for creating fields, flipping External IDs, and building permission sets — without memorizing command syntax or hand-writing metadata XML. You fill in a few boxes and pick fields from live dropdowns; the app writes the exact `sf` commands and a ready-to-deploy metadata package. **The app never changes your org** — it only generates scripts, which you run on your own machine (the CLI logs in as you).

The target org is whatever is selected in the header **Org** picker.

The page reads top-to-bottom in four parts:

### 1. Environment setup (run once per project)

- **Step 2 — Install the CLI:** copy the snippet and run it once per machine to install `sf` and confirm it can see your orgs.
- **Step 3 — Authorize the org:** the **Alias** comes prefilled (`EC-SB`) — keep it, change it, or clear it — and, if needed, adjust the **Sandbox instance URL**. Copy the generated `sf org login web …` command — it opens a browser to log you in. Sandboxes require the instance URL, which is why it's prefilled.
- **Step 4 — Generate the project:** the **Project name** (`doane-sf`) and **base path** come prefilled and editable. The snippet creates the local project folder and checks the connection.
- **Step 5 — Retrieve metadata:** copy the retrieve command to pull down the objects, fields, and permission sets you'll be editing.

Every command box has a **Copy** button.

### 2. Build fields

- Pick an **Object** (the dropdown is loaded live from the selected org). It
  only lists objects that **accept custom fields** — system/relationship objects
  like `ContentDocumentLink`, `ContentNote`, `*__Share` and `*__History` are
  hidden here, because Salesforce rejects custom fields on them (they'd fail on
  deploy). They still appear in the Command composer and Data Dictionary, where
  describing/querying them is valid.
- Choose the **Operation:**
  - **Create new field** — you're adding a brand-new field.
  - **Edit existing field (flip to External ID)** — you're turning an existing field into an External ID. Pick the field from the **Existing field** dropdown; its current settings prefill so the redeploy doesn't wipe them.
- Enter the **Field API name** (must end in `__c`), a **Label**, and the **Type**. Type-specific options appear below (length, External ID, Unique, picklist values, etc.).
- Set **Field-level security** (Readable / Editable) — these feed the permission set.
- Click **+ Add field**. Repeat for as many fields as you need; they collect in a table where each row has **Edit** (loads it back into the form to change — the button becomes **Update field**) and remove (**×**).

> **Picklist values:** one value per line. Just type the value — the API value (code) and the label are both set to that text (e.g. `Freshman`). Use `CODE=Label` only when you want them to differ (e.g. `MAJ=Major, Faculty`). Prefix a line with `-` to retire (deactivate) a value instead of deleting it — existing records keep their value.

### New object (optional) — define a fresh custom object

Building fields on an object that doesn't exist yet? Define it here instead of
creating it by hand in Setup first:

- **API name** (must end in `__c`), **Label**, **Plural label**, and
  **Sharing** model.
- Click **+ Add**. The object joins the Object picker above so your fields can
  target it, and rides into the package as a best-effort `CustomObject` shell
  (a Text "Name" field) ahead of its fields, so a single deploy creates the
  object then the fields on it.
- **Generate a Custom Tab for each new object** (checked by default): a fresh
  object has no tab, so it never shows in the App Launcher or nav — only
  reachable by a direct URL. This adds a `CustomTab` to the package and grants
  its visibility in the human permission set (below), closing the
  create → visible → on-the-page → **in-the-nav** lifecycle in one deploy.

### Clone object (optional) — copy a whole object's schema across orgs

Instead of hand-adding fields one at a time, describe a **whole object** in a
source org (EDA, say) and generate a package that reproduces its custom fields
in your target org:

- Pick a **Source org** and **Source object**, then **Preview**. The result
  shows fields it can clone (reusing the exact same field generator as the
  builder above, so the output is identical either way) and fields it
  **skips and reports** — relationships it can't reproduce 1:1 (master-detail,
  polymorphic), formulas, roll-ups, auto-numbers, and unsupported types
  (currency, percent, multi-select picklist, rich text). Plain **Lookup**
  fields *do* clone — they reference by object API name, so they work as long
  as the target has that object. If the target is known (see Mirror below), a
  Lookup whose target object doesn't exist there (e.g. a managed
  `hed__Term__c` absent from Ed Cloud) is skipped too, rather than shipping a
  field that would fail to deploy.
- **Include the object definition** creates the object (a best-effort shell)
  if it doesn't exist in the target yet; leave it off to just sync fields into
  an object that's already there.
- **Also generate a permission set** grants read/edit on the cloned fields —
  otherwise they're invisible, same as any new field.
- **Generate a Custom Tab** — same as New object above: without one, a cloned
  object is only reachable by direct URL.
- **Mirror the source org's access by name** — see below.
- **Download package (.zip)** once you're happy with the preview.

#### Mirror the source org's access by name (optional)

Cloning the object's *schema* doesn't clone *who can see it*. This reads every
profile and permission set that grants the object in the **source** org and
reproduces those same object + field grants onto the **same-named** profiles /
permission sets that already exist in your **target** org — so the object's
real-world security posture comes with it, not just its fields:

- Pick the **Target org** (whose profile/permission-set names to match
  against) and enter a short **justification** (required — this reads another
  org's full security posture, so the read is logged, not silent).
- The preview shows **matched** (name exists in target — these ride into the
  package), **not in target** (skipped, never invented), and any
  **license-locked** profiles that can't take even an additive deploy (e.g.
  `B2BMA Integration User` — reported, not emitted).
- **High-privilege profiles** (`System Administrator` and equivalents) are
  **excluded by default** — shown separately as "excluded," not silently
  mirrored — since replicating admin-level access deserves a deliberate
  choice. Tick **include high-privilege profiles** if you specifically mean to.
- Both **Profiles** and **Permission Sets** are generated. A partial
  Profile/PermissionSet deploy is *additive* — it only adds the object/field
  grants this package names and leaves everything else on that
  profile/permission set untouched, so this is safe to deploy onto live
  metadata.

> **New to this lifecycle?** [Making a cloned object visible](cloned-object-visibility.md)
> walks the whole chain — object exists → object access → field FLS → tab →
> mirrored security — with a worked example and the `sf` CLI commands that
> verify each switch from the terminal, plus the two gotchas real deploys hit
> (re-deploying a field that already exists; a lookup whose target object
> the destination org doesn't have).

### 3. Permission set (optional)

The permission set **API name** and **Label** come prefilled (`SF_Tools_Importer`) and editable — it's built from the Readable/Editable choices on each field you added. **Clear the API name to skip the permission set** entirely. (This is the *integration* user's access — for staff visibility, see Visibility below.)

### Visibility — clone field-level security from another org (optional)

Creating a field doesn't make it visible to anyone — in Salesforce, visibility (field-level security) is separate metadata. Use this section to give your new fields the **same visibility a field has in another org** (e.g. EDA), as a second, human-facing permission set:

- **Source org / Reference object / Reference field:** pick an org and a field to read. Click **Read visibility** — the tool shows which profiles and permission sets can see and edit that field in that org, and (in the muted note) which profiles to assign the new set to.
- **Existing fields:** for fields that **already exist** and only need visibility (nothing to create), paste their API names one per line as `Object.Field__c` — or type an object and click **Load custom fields** to pull them from the org. They're added to the permission set *without* re-creating them — no CustomField, permission set only. (Fields you built above are included automatically, so you only list ones you didn't build here.)
- **Human permission set — API name / Label:** fill these to generate a *second* permission set (alongside the integration one) that grants those fields the same access. **Access granted** (edit vs read-only) is set to match the reference field when you read it; adjust as needed. Tick **read-only companion** to also generate a `<name>_ReadOnly` set — assign the edit set to power users and the read-only set to a view-only audience.
- The generated deploy and assign snippets (and the package zip) then include **both** permission sets. Assignment is per user — for bulk, Setup → *Permission Sets → Manage Assignments* is easier.

> **Just adding visibility to existing fields?** Leave the field builder empty, clear the integration permission-set name, paste the field names under *Existing fields*, name the *Human permission set*, and hit **Download package** — you get a permission-set-only zip. Unzip into your project and deploy `-m "PermissionSet:<name>"` (the field definitions are untouched).

### Page layout — place the fields on a layout (optional)

Creating a field and granting visibility still doesn't put it **on the page** — that's the page layout, a third piece of metadata. This section adds your fields to a real layout by cloning its metadata (it is *not* a layout editor — it edits the actual layout you retrieve, org to org):

1. **Layout full name:** enter the layout's `fullName` (e.g. `Case-Case Layout`). Find it with `sf org list metadata -m Layout` (filter to `Case-*`).
2. **Step A — retrieve:** copy/run the generated retrieve command to pull the layout to your project.
3. **Step B — paste:** open the retrieved `.layout-meta.xml` and paste its contents into the box.
4. **Placement:** either **New section** (name it, e.g. `Case Assistance`) or **Existing section** (click *load* to pick one from the pasted layout). Choose **Edit** or **Read-only**.
5. **Fields to place:** click *fill from my fields* (or type API names, one per line). Fields already on the layout are skipped automatically.
6. **Build modified layout** → **Download** it, save back over the file in `force-app\main\default\layouts\`, and deploy with the generated command (add `--dry-run` first).

> Everything else in the layout — sections, related lists, buttons — is preserved byte-for-byte; only your fields are added. Do one layout at a time (Case has several: Case Layout, Advisee Case, CARE Referral, Close Case).

### Record type — make a picklist's values available (optional)

On an object that uses record types, a picklist's values aren't available on a record type until that record type lists them. Same clone flow as the layout:

1. **Record type full name** (e.g. `Case.Advisee_Case`) — Step A generates the retrieve command.
2. Paste the retrieved `.recordType-meta.xml`.
3. **Picklist field** (e.g. `Type_of_Assistance__c`), the **values** to make available (one per line), and an optional **default**. Values already available are skipped; if the field already has a block, the new values are appended to it.
4. **Build → Download** → save into `force-app\main\default\objects\<Object>\recordTypes\` → deploy (dry-run first).

> Only picklist fields on record-type objects need this. **Heads-up:** Salesforce percent-encodes some value names in record types (e.g. `/`) — plain code values are fine; for special characters, paste the exact form from a retrieved record type and dry-run.

> **New to Salesforce visibility/accessibility?** After you deploy, use
> [Verifying field visibility & accessibility](verifying-field-visibility.md) —
> a step-by-step, Case-based walkthrough of what "correct" looks like in Setup
> for all four switches (field · FLS · layout · record type), plus the `sf` CLI
> commands that check the same thing from the terminal.

### 4. Generate & deploy

- If any field is a **flip**, a **Step 0 back up** and **Step 1 verify** snippet appear first — run these to save the current field state and to confirm the flip is actually needed (skip fields that are already External IDs).
- **Download package (.zip)** produces the metadata package. Unzip it and copy the `force-app` folder into your project (a `README.txt` inside spells out exactly where). A `manifest/package.xml` is included too.
- **Step 8 — Validate with a dry run:** deploy with `--dry-run` first — it checks against the org without changing anything.
- **Step 9 — Deploy for real:** the same command without `--dry-run`. These use `-m`, which deploys from your project — run **Download package** and unzip first, or you'll hit *"No source-backed components present."* The **"deploy the whole folder"** box (`--source-dir force-app`) is a no-`-m` alternative that pushes everything in the project.
- **Step 10 — Assign the permission set** to the integration user.

### Command composer (explore an object from the terminal)

At the bottom of the tab, a small utility for the field-guide "explore from the terminal" recipes: pick an **object** (and, for the query, some **fields**), and copy ready-to-run `sf` commands — **describe**, **query rows**, **count records**, and **retrieve the object's metadata**. Rather than re-implement things the app already does in-browser, each recipe links to the matching tab for live results: **Run this live in SOQL Workbench →** under the query, and **Explore fields live in Data Dictionary →** under describe. Use the CLI recipe when you want to run it on your own machine; use the link when you just want to see the answer now.

**Why use it:** the SF CLI is powerful but easy to get wrong (a backslash instead of a backtick, a sandbox login without its instance URL, a redeploy that clobbers a field's attributes). This tab bakes those lessons in, so a field authored here deploys identically to one written by hand — verified against our real Conductor migration package.

---

*Last updated: July 2026 — covers all features through Wave 6 plus the CLI tab (Salesforce CLI script & metadata generator).*
