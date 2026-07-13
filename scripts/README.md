# scripts/

Standalone operational scripts. Run from the repo root with the app's
virtualenv so they pick up your `.env` org credentials.

## `migrate_files.py` — org-to-org file (ContentVersion) migrator

Copies Salesforce **Files** from a source org to a target org **without staging
them locally**, and relinks each file to the migrated parent record. Built for
the EDA → Ed Cloud migration, where parent records get **new Ids** in the target
org, so a plain CSV re-upload can't relink them.

It streams each file's bytes source → target, inserts a new `ContentVersion`
(Salesforce auto-creates the `ContentDocument`), then creates a
`ContentDocumentLink` to the **new** parent record — resolved by matching an
external-Id field (e.g. `SIS_ID__c`) across the two orgs.

### Prerequisites

- **Both orgs configured** in `.env` (`SF_<ORG>_USERNAME/PASSWORD/TOKEN`), so
  `get_sf("<org>")` works for the source and the target.
- **The parent records are already migrated** to the target org, and the
  external-Id field you pass (`--ext-id`) is populated on the parent in **both**
  orgs. That field is how old parent Id → new parent Id is resolved.
- The running user can create Files in the target org (Content permissions).

### Files vs Attachments (`--mode` / `--dest`)

Salesforce has two file systems, and this migrates either — and the **read** side
(`--mode`) and **write** side (`--dest`) are independent:

- **`--mode files`** (default) — modern **Files** (`ContentVersion` / `ContentDocument`),
  linked to records via `ContentDocumentLink`. Streams `VersionData`, re-inserts,
  relinks.
- **`--mode attachments`** — legacy **`Attachment`** records (the ones in a record's
  *Notes & Attachments* related list). Streams each `Attachment.Body` and re-creates
  it on the remapped parent. One attachment has exactly one parent, so the crosswalk
  must map the **object the attachment hangs off** (old→new).
- **`--dest {files,attachments}`** — what to *write* (defaults to the same as `--mode`).
  Set it to **convert** one system to the other, e.g. `--mode attachments --dest files`
  reads legacy Attachments and writes modern Files. `ShareType`/`Visibility` apply only
  when writing Files.

Not sure which you have? In the source org, an attachment shows up under a record's
*Notes & Attachments* list and as an `Attachment` row (`00P…` Id); a File shows under
*Files* and as `ContentDocumentLink`. (Reading either requires the integration user to
have **Query All Files** / **View All Data** in the source org.)

### Three ways to remap parents (`--remap`)

All answer the same question — "which target record is this source record's file
supposed to hang off?" — they just establish the old→new link differently. `--remap`
is inferred (`crosswalk` if `--id-map`, else `ext_id`) but can be set explicitly:

- **Crosswalk (`--remap crosswalk`, `--id-map`)** — you already have the old→new
  parent Ids (e.g. the DemandTools multi-org export). Point the script straight at
  that CSV; it drives both scope and remap with **no external-Id lookups**. Simplest
  and fastest when you have the Id pairs.
- **External-Id (`--remap ext_id`, `--parent` + `--ext-id`)** — you *don't* have an
  Id list, but the parent carries a durable business key that's the same in both orgs
  (e.g. `SIS_ID__c`). The script matches on it and live-verifies the target record
  exists. Use when you have no crosswalk.
- **Same parent (`--remap identity`)** — keep the **same** parent record Id (new =
  old). For an **in-place conversion** (e.g. legacy Attachments → modern Files) within
  one org — set `--source` and `--target` to the same org — or a same-Id copy. Scope
  by `--by filter --parent <Object> --where ...` or `--by list --ids-file`.

### Usage

Dry-run is the default — it reads, resolves parents, and writes a CSV report,
but changes **nothing** until you add `--commit`.

```bash
# ── Crosswalk mode: point straight at your existing migration spreadsheet ──
# (columns can be anything — name them; here the file's parent is Accommodation__c)
python scripts/migrate_files.py --source eda --target prod \
    --id-map accommodations.csv \
    --map-old-col Accommodation__c --map-new-col NEW_Accommodation__c

# Or a plain old_id,new_id crosswalk:
python scripts/migrate_files.py --source eda --target prod --id-map account_map.csv

# ── External-Id mode: every file on Person Accounts, matched by SIS_ID__c ──
python scripts/migrate_files.py --source eda --target prod \
    --parent Account --ext-id SIS_ID__c --by filter --where "IsPersonAccount = true"

# External-Id, explicit list of parents (record Ids or ext-Id values, one per line)
python scripts/migrate_files.py --source eda --target prod \
    --parent Case --ext-id Legacy_Case_Id__c --by list --ids-file cases.txt

# ── In-place conversion: legacy Attachments → modern Files within one org ──
python scripts/migrate_files.py --source prod --target prod \
    --remap identity --mode attachments --dest files \
    --parent Accommodation__c --by filter --where "Id != null"

# Add --commit to any of the above to actually write to the target org
python scripts/migrate_files.py --source eda --target prod --id-map account_map.csv --commit
```

`--id-map` reads the columns named by `--map-old-col` / `--map-new-col` (default
`old_id` / `new_id`), falling back to the first two columns — so an existing
spreadsheet with extra columns works as-is. Rows with a blank old or new value
are skipped.

Read the `file_migration_report.csv` it produces before committing — it lists,
per file, the resolved/unresolved parent counts, size, and the action it would
take. **Run a small batch first** (a tight `--where`).

### How it stays safe & repeatable

- **Dry-run by default**; writes only with `--commit`.
- **Idempotent** — a created `ContentVersion` is stamped with the source
  ContentVersion Id in `ExternalDocumentInfo1`; a re-run finds the stamp and
  **reuses** the existing target file (relinking only) instead of duplicating it.
  When writing Attachments, a re-run skips any the target parent already has by
  name.
- Files links default to `ShareType = V` (Viewer) and `Visibility = AllUsers`
  (matching the Data Loader guide) — the app exposes both as per-run options.

### Known limits

- **Large files:** single-call base64 inserts are bounded by request size, so
  files over `--max-mb` (default 35 MB) are **flagged and skipped** in the
  report rather than failing the run. They need a multipart upload — not yet
  implemented here.
- A file linked to **multiple** parents is migrated **once** and linked to each
  resolved parent.
- Files whose parent doesn't resolve (no external Id, or no matching target
  record) are reported and skipped — migrate the parents first, then re-run.

### Relationship to the app

The engine lives in `services/file_migration.py`; this script is a thin CLI over
it. The same engine also powers the **Data Ops → File Migration** tab, which
exposes all three remap methods (crosswalk / external-Id / same-parent), the
read/write mode toggles, and `ShareType`/`Visibility` in the browser: configure,
run a **dry-run** (preview summary + per-file report), and a clean dry-run
unlocks a `MC.confirm`-gated **Migrate** button (any input change re-locks it).
Use the tab for interactive runs; use this CLI for large batches or
scripted/repeatable runs.
