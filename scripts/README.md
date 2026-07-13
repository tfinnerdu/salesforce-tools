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

### Usage

Dry-run is the default — it reads, resolves parents, and writes a CSV report,
but changes **nothing** until you add `--commit`.

```bash
# Dry run: every file on Person Accounts, matched by SIS_ID__c
python scripts/migrate_files.py --source eda --target prod \
    --parent Account --ext-id SIS_ID__c --by filter --where "IsPersonAccount = true"

# Explicit list of parents (a file of record Ids or external-Id values, one per line)
python scripts/migrate_files.py --source eda --target prod \
    --parent Case --ext-id Legacy_Case_Id__c --by list --ids-file cases.txt

# Same command, actually write to the target org
python scripts/migrate_files.py --source eda --target prod \
    --parent Account --ext-id SIS_ID__c --by filter --where "IsPersonAccount = true" \
    --commit
```

Read the `file_migration_report.csv` it produces before committing — it lists,
per file, the resolved/unresolved parent counts, size, and the action it would
take. **Run a small batch first** (a tight `--where`).

### How it stays safe & repeatable

- **Dry-run by default**; writes only with `--commit`.
- **Idempotent** — each created `ContentVersion` is stamped with the source
  ContentVersion Id in `ExternalDocumentInfo1`; a re-run finds the stamp and
  **reuses** the existing target file (relinking only) instead of duplicating it.
- Links are created with `ShareType = V` (Viewer) and `Visibility = AllUsers`,
  matching the Data Loader guide's defaults.

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

This is the standalone **engine** behind the planned **File Migration tab**
(Phase 2): both selection modes (filter / list) and the per-run external-Id
remap are the same model. The tab will wrap this logic with a preview-first UI
and `MC.confirm` gating.
