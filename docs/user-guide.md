# SF Mission Control — User Guide

**Doane University Salesforce Tools Dashboard**  
For developers and migration engineers working on the Doane Ed Cloud migration and ongoing Colleague→Salesforce integration.

---

## Getting Started

Open your browser and go to:
- **Dev (local):** `http://localhost:5000`
- **Production:** `https://du-int.doane.edu/prod/sf-mission-control`

The top navigation shows six work areas: **Migration**, **Validation**, **SOQL**, **Schema**, **Data Ops**, and **Settings**.

The **org picker** in the top-right corner lets you switch between `dev`, `sandbox`, and `prod`. Everything — data queries, migration tracking, schema comparisons — uses whichever org is active.

---

## Migration

### Readiness Score

The Readiness Score answers "are we ready to go live?" before each migration milestone.

Click **Run Now** to run a full check against the active org. The scorecard shows:

| Check | What it validates |
|---|---|
| SIS_ID__c coverage | How many PersonAccounts have a Colleague student ID |
| Ethos GUID coverage | How many records are linked to their Ethos identity |
| ContactPoint parents | Emails/phones/addresses with broken account links |
| Duplicate detection | PersonAccounts that appear to be the same person |
| Individual links | PersonAccounts missing their required Individual record |
| Required fields | PersonAccounts with blank FirstName, LastName, or RecordType |

A record-level **red** means the field needs attention before go-live. The **Overall** percentage at the bottom is the composite score — below 90% means not ready.

Scores are stored daily (if the scheduler is running) so you can track migration progress over time.

---

### Batch Progress Tracker

When a migration batch is running, enter the **workflow name** (e.g., `EDA_Person_Sync`) and click **Load Status** to see a live dashboard:

- Progress bar showing how far along the batch is
- Counts for Completed / Failed / Running / Queued
- Estimated time to completion
- Failure breakdown by error type

Turn on **Auto-refresh** to poll every 15 seconds automatically.

Click **Re-run failures** next to an error type to retry those specific workflows after you've fixed the root cause.

---

### Error Reconciler

After a migration batch, this surface shows you exactly what failed and why.

Select the **workflow name** and **time range** (last 1h, 6h, 24h, or 72h), then click **Refresh**.

Each error type gets its own card:

- **DUPLICATE_VALUE** — two records share the same SIS_ID. Fix: run Duplicate Radar, merge duplicates, then retry.
- **FIELD_INTEGRITY_EXCEPTION** — a ContactPoint was created before its parent Account. Fix: reorder Conductor tasks so Individual/Account upserts run first.
- **TIMEOUT** — the Conductor worker took too long. Fix: just retry — these almost always succeed on second attempt.
- **REQUIRED_FIELD_MISSING** — source data in Colleague is blank for a required field. Fix: patch source data or add a default in the Conductor transform.

Click the **SIS IDs** toggle to see the specific student records affected. Click **Re-run** to retry that error category's workflows.

---

## Validation

### Duplicate PersonAccount Radar

Scans for PersonAccounts that might be the same person, using four strategies:

- **Same SIS_ID on multiple records** — the most serious: upsert logic created duplicates
- **Same name + birthdate** — likely the same student entered twice
- **Same primary email** — same person with different account records
- **Same Ethos GUID** — GUID collision from upstream system

Click **Run Scan** to check. Results show how many duplicate groups each strategy found.

Click **Merge** on a row to combine two records into one. You choose which record is the "master" (the one that survives). **This action cannot be undone without Demand Tools** — use the Demand Tools Undo Merge feature if needed.

Export the scan results as CSV to hand off to Demand Tools for fuzzy-match deduplication of near-duplicates.

---

### External ID Coverage Report

Shows what percentage of each record type has `SIS_ID__c` and `Ethos_Guid__c` populated.

| Color | Meaning |
|---|---|
| 🟢 Green (100%) | Fully covered — ready for migration |
| 🟡 Amber (90–99%) | Near complete — investigate the gaps |
| 🔴 Red (< 90%) | Significant coverage gap — migration will have orphaned records |

Click any row to see the specific record IDs with missing external IDs. Export as CSV to run a bulk-fix in Demand Tools or via direct Salesforce data loader.

---

### ContactPoint Integrity Scanner

ContactPoint records (email, phone, address) must be linked to both an Account AND an Individual record. If either link is broken, lookups and integrations silently fail.

This scanner finds every broken link before go-live:

- **Missing Parent** — ContactPoint has no Account link
- **Missing Individual** — ContactPoint has no Individual link

Click **Scan Now**. Red badges mean action needed before migration.

---

## SOQL

### Workbench

A built-in SOQL query runner. Type any SOQL query and click **Run ▶**.

**Object Explorer (left sidebar):** Search for any Salesforce object, click to see all its fields with types and metadata. Click a field to add it to your query.

**Saved Queries:** Click **Save Query** to store a query with a name. It's saved to the shared database — all team members see the same saved query library.

**Run All Pages:** Fetches every page of results, not just the first 200.

**Explain Plan:** Shows Salesforce's query execution plan — useful for diagnosing slow queries or understanding index usage.

**Inline Edit:** Double-click any cell in the results table to edit that field directly. Press Enter to save, Escape to cancel.

---

## Schema

### Crosswalk Field Diff

The Crosswalk Diff validates your EDA→Ed Cloud field mapping document against live data.

1. Upload your crosswalk CSV (or enter mappings manually)
2. Click **Run Live Check**
3. For each mapped field pair: see EDA coverage % vs Ed Cloud coverage %

A large gap (EDA has data, EC doesn't) means the migration transform failed for that field. Click any row to see the specific record IDs where the gap exists — export as CSV for a targeted correction run.

---

### Org Schema Diff

Compares field schemas between two orgs — typically sandbox vs. production.

Select the right-side org to compare against, choose which objects to diff, and click **Run Diff**.

Results are grouped by object. Look for:
- **Left-only fields** — fields that exist in sandbox but not prod (need to deploy)
- **Right-only fields** — fields in prod but not sandbox (will break sandbox upserts)
- **Type mismatches** — same field name, different data type (will cause silent data truncation)
- **Required mismatches** — required in one org but not the other (migration inserts may fail)

---

## Data Ops

### SF ↔ SQL Join Builder

Builds a JOIN query that connects Salesforce data with your SQL Server data without writing OPENQUERY syntax by hand.

1. Enter your SQL Server table name and select which columns to include
2. Select the Salesforce object and fields
3. Set the join key (e.g., SQL: `StudentId` ↔ SF: `SIS_ID__c`)
4. Click **Build Query**

The generated T-SQL uses `OPENQUERY(SALESFORCE, ...)` — paste it into SSMS to run against your Salesforce ODBC linked server.

If the ODBC linked server isn't set up, click **Run here (Python fallback)** — the app fetches both sides separately and joins them in memory.

---

## Settings

### Org Connections

Lists your configured Salesforce orgs (dev, sandbox, prod). Click **Test Connection** to verify credentials are valid and see the live record count.

### API Collections

Import a Postman collection (v2.1 JSON format) to run it from the app. Variable substitution (`{{SF_BASE_URL}}` etc.) is applied using the active org configuration.

Click **Run** to execute all requests in the collection in sequence. Results show pass/fail per request.

Pre-built collections are available for:
- Salesforce REST API basics
- Ethos API common resources
- Conductor workflow management

---

## Tips and Common Patterns

**Pre-migration checklist:** Run Readiness Score → External ID Coverage → ContactPoint Scanner → Duplicate Radar. All four should be green/amber before go-live.

**After a failed batch:** Go to Error Reconciler → fix root cause → Re-run by category. Don't re-run the whole batch — target only failed workflows.

**Investigating a suspicious record:** Use the SOQL Workbench with the student's SIS_ID: `SELECT Id, Name, SIS_ID__c, Ethos_Guid__c, PersonEmail FROM Account WHERE SIS_ID__c = 'STU12345'`.

**Tracking migration progress:** The Readiness Score stores daily snapshots. Run it each morning — the trend shows whether migration work is closing gaps or opening new ones.

**Demand Tools handoff:** Export any list from Duplicate Radar or External ID Coverage as CSV. The format is compatible with Demand Tools import for bulk operations.
