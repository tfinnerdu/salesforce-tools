# SF Mission Control — Project Context

**Doane University — Salesforce Education Cloud tooling dashboard**

## What this is

Flask web app at `https://du-int.doane.edu/prod/sf-mission-control`. Houses all Salesforce developer/migration tooling in one authenticated dashboard. Replaces ad-hoc scripts + Salesforce Inspector + Demand Tools gaps.

## Stack

- Python 3.11 / Flask 3.x
- `simple_salesforce` — SF REST + Bulk API
- `requests` — Conductor API calls
- `psycopg2` — PostgreSQL (result persistence, saved queries, collections)
- `APScheduler` — daily readiness check at 06:00 CT
- Bootstrap 5 CDN + vanilla JS (no React/Vue)
- K8s `ns=prod`, Traefik stripPrefix

## Tabs and their routes

| Tab | URL prefix | Blueprints |
|---|---|---|
| Migration | `/migration` | `migration_bp` |
| Validation | `/validation` | `validation_bp` |
| SOQL | `/soql` | `soql_bp` |
| Schema | `/schema` | `schema_bp` |
| Data Ops | `/data-ops` | `data_ops_bp` |
| Scenarios | `/scenarios` | `scenarios_bp` |
| Key Maps | `/key-maps` | `key_map_bp` |
| CLI | `/cli` | `cli_bp` |
| Settings | `/settings` | `settings_bp` |

**API routes live UNDER the blueprint prefix**, not at `/api/v1/`. Example: `POST /migration/readiness/run` (not `/api/v1/migration/readiness/run`). The blueprint prefix IS the namespace.

## Provider pattern

- `sf_provider.get_sf(org)` — returns a live `simple_salesforce` client by default; raises `RuntimeError` if the org has no credentials configured. With `SHOW_MOCK=true`, returns a `MockSalesforce` for any org.
- `conductor_provider.get_conductor_client()` — returns a live `ConductorClient` by default; raises `RuntimeError` if Conductor is not configured. With `SHOW_MOCK=true`, returns a `MockConductorClient`.
- `SHOW_MOCK` is all-or-nothing: a single env flag that swaps the whole app onto the mock layer for manual UI / demo testing. There is **no silent mock fallback** — unconfigured credentials raise when SHOW_MOCK is off.
- Tests are independent of `SHOW_MOCK`: pytest patches `get_sf` / `get_conductor_client` with `unittest.mock` doubles per test.

## Salesforce context

- Ed Cloud (EDA → Ed Cloud migration in progress)
- Person Account model — upsert to `Account` with `__pc` suffix fields
- External IDs: `SIS_ID__c` (Colleague person ID), `Ethos_Guid__c` (LDM GUID)
- ContactPoint records parent to `Account` + `Individual` (NOT Contact)
- Migration pipeline: Colleague → Ethos → Conductor → Salesforce

## Key files

```
app.py               Flask factory, registers all blueprints
config.py            Config class, get_org_config()
db.py                psycopg2 connection, init_db(), db_available()
sf_provider.py       SF client factory + Bulk API / DML helpers + MockSalesforce (SHOW_MOCK)
conductor_provider.py Conductor client + MockConductorClient (SHOW_MOCK)
scheduler.py         APScheduler daily readiness job
routes/              One blueprint file per tab
services/            Business logic, one module per feature
  audit.py                 Shared AuditEvent dataclass + emit() — structured
                           stdout JSON line + best-effort audit_events row
                           (never raises; a DB failure only drops the persisted
                           copy). actor resolves session['user'] when present,
                           else 'system' — there is no login layer yet, so
                           every event is 'system' today; current_actor() is
                           the one place that upgrades once real identity
                           lands. Every read of cross-org security posture
                           (cli_fls, cli_access_mirror) emits one event.
  readiness_validator.py   §3 pre-go-live scorecard
  duplicate_radar.py       §5 duplicate PersonAccount scan
  batch_tracker.py         §6 migration batch progress
  error_reconciler.py      §7 Conductor failure categorization
  schema_diff.py           §8 sandbox vs prod field diff
  soql_workbench.py        §9 SOQL runner + object explorer
  field_locator.py         Schema → Field Finder: inverse of the Data
                           Dictionary (field → which objects have it). Tooling
                           CustomField query keyed on DeveloperName (input's __c
                           / namespace auto-stripped); opt-in describe deep-scan
                           also finds standard fields (capped). Read-only.
  external_id_coverage.py  §10 SIS_ID__c / Ethos_Guid__c coverage
  contactpoint_scanner.py  §11 broken ContactPoint parent links
  crosswalk_diff.py        §4 EDA→Ed Cloud field mapping diff
  join_builder.py          §14 SF↔SQL Server join query builder
  collection_manager.py    §13 Postman collection runner
  scenarios.py             Multi-step Data Ops pipelines (delete / modify /
                           reassign / bulk_update / tune / key_map_expand)
  tags.py                  App-level tagging for saved artifacts (scenarios
                           first); see tag_sync.py for the future SF-field
                           sync scaffold
  key_map.py               Source → SF Key Map engine: FK resolution +
                           family routing + variant fanout (preview-only)
  ingest.py                Source ingestion → list[dict] (inline/json/csv/sql)
  file_migration.py        Org→org (or in-place) file migrator. Read side and
                           write side are INDEPENDENT: read 'files'
                           (ContentVersion, relinked via ContentDocumentLink) or
                           'attachments' (legacy Attachment), and write either —
                           so an Attachment can land as a File and vice-versa.
                           Streams bytes source→target (no local staging). Three
                           parent-remap methods: 'crosswalk' (old→new Id CSV),
                           'ext_id' (external-Id match across orgs), or 'identity'
                           (same parent — in-place conversion within one org).
                           ContentDocumentLink ShareType/Visibility are per-run.
                           Engine for the CLI (scripts/migrate_files.py) + the
                           Data Ops → File Migration tab; build_plan is dry-run,
                           execute writes (idempotent)
  sqlserver.py             Shared SQL Server connection (Colleague backend,
                           MS ODBC driver — no Devart in the app)
  cli_metadata.py          CLI tab: describe-driven object/field lists (read-only)
  cli_script.py            CLI tab: sf-command + field/permset/object XML + zip generator
  cli_clone.py             CLI tab: clone a whole object's schema — describe a
                           source object → field specs for the existing generator
                           (+ best-effort CustomObject shell). Skips & reports
                           relationships/formula/roll-up/auto-number/unsupported
                           types (can't reproduce 1:1). Read-only; deploy is upsert
  cli_fls.py               CLI tab: read a field's FLS from a source org (clone
                           visibility) + synthesize a human permission set
  cli_access_mirror.py     CLI tab: read a source org's per-parent object+field
                           access (ObjectPermissions/FieldPermissions grouped by
                           Profile / PermissionSet) and mirror it onto same-named
                           profiles + permission sets that EXIST in the target
                           (skips names the target lacks; field grants scoped to
                           the target's fields so a deploy never dangles). Read-
                           only; generated Profile/PermissionSet deploys are
                           additive (upsert the named perms, leave the rest)
  cli_layout.py            CLI tab: add fields to a pasted page-layout XML (new
                           or existing section) — pure string surgery, org-to-org
  cli_recordtype.py        CLI tab: make a picklist field's values available on a
                           pasted record-type XML — pure string surgery, org-to-org
utils/responses.py   Shared API helpers: error_response() envelope + request_id
templates/           Jinja2, all extend base.html
static/css/          mission-control.css (Doane brand)
static/js/           mission-control.js (MC.* namespace, vanilla JS)
tests/               pytest; SF/Conductor patched with unittest.mock doubles
docs/                e2e walkthrough + user guide
k8s/manifest.yaml   Deployment + IngressRoute + Middleware + TLS
```

## Running locally

```powershell
.\start-local.ps1           # normal
.\start-local.ps1 -ForceDeps # force pip reinstall
```

Or directly:
```bash
python app.py
```

## Environment variables

Copy `.env.example` to `.env`. Salesforce and Conductor credentials are required for the production path. For credential-free manual testing, set `SHOW_MOCK=true` — that swaps the entire app onto the mock layer (single all-or-nothing flag). The UI shows a loud amber `MOCK` badge in the navbar whenever SHOW_MOCK is on.

## Scenarios + Tags

The Scenarios tab saves multi-step Data Ops pipelines (each step is `delete`,
`modify`, `reassign`, `bulk_update`, or `tune` with its params) and runs them
in order. Each step is dispatched to the same service the Data Ops tab calls
directly, so SHOW_MOCK, `dml_guard`, and confirmation gates behave identically.
Steps can `stop` or `continue` on error. The Run button is gated by
`MC.confirm` with an acknowledgement checkbox; runs are synchronous and write
a row to `scenario_runs` with per-step results.

Tags (v1) are interface-only — an app-level labeling layer for organizing
scenarios (extendable to saved queries / collections / snapshots). Stored in
`tags` + `artifact_tags` tables. `services/tag_sync.py` is a scaffold for the
future ability to push tags up to a real Salesforce field (`Config.TAG_SF_FIELD`);
its entry points raise `NotImplementedError` until wired.

## Key Maps (Source → Salesforce)

The Key Maps tab turns source rows (a Colleague SQL result, pasted CSV, or
JSON) into Salesforce records of one SObject. Three layers: FK lookups
resolve foreign keys by an external-ID field (e.g. `AcademicTerm.SIS_ID__c`);
family routing picks a family per source row by column-equals-value rules;
each variant in the family produces one output row, merging its `overlay_json`
onto the resolved-FK base (one source row → many target rows). First consumer
is PTAT (`ProgramTermApplnTimeline`) but the model is generic.

**Preview-only** — `resolve_and_expand` reads from SF to resolve FKs but never
writes; the run returns the would-be-inserted rows + an unresolved-FK list,
exportable as CSV. Wired as a `key_map_expand` Scenario step so a scheduled
Argo run can trigger it (see Scheduled runs below). Live SQL uses the shared `services.sqlserver`
connection (MS ODBC driver, not Devart). FK resolution batches distinct values
into one `IN()` query per (sobject, field). SHOW_MOCK synthesises stable
`MOCK_<sobject>_<value>` ids so previews are demoable without touching SF.

## CLI (Salesforce CLI script generator)

The CLI tab turns a describe-driven field/permission-set plan into `sf` command
snippets (PowerShell backtick style) and a `force-app` metadata package zipped
for download. It is **read-only** against Salesforce — `cli_metadata` describes
objects/fields to drive the pickers and prefill External-ID *flips* — and
**generates only**: the `sf` commands run on the sys admin's own machine, so the
app never deploys. `cli_script` is pure/deterministic; its generated
`field-meta.xml` / `permissionset-meta.xml` reproduce the real Conductor EDA→EDF
artifacts byte-for-byte (pinned in `tests/characterization/test_cli_artifacts_characterization.py`).
Supports create + flip (with auto backup/verify snippets) for Text, Picklist,
Checkbox, Number, Date/DateTime, Email, Phone, Url, (Long)TextArea, and Lookup
(a plain relationship — pick the related object + delete constraint; it references
by object API name so it clones cross-org as long as the target object exists).
Stateless — nothing is persisted. Describe-driven pickers demo under `SHOW_MOCK`.

**Visibility clone (`cli_fls.py`).** Field-level security is separate metadata,
so a created field isn't visible to anyone. The Visibility section reads a
reference field's FLS from a *source* org (e.g. EDA) via the `FieldPermissions`
object (`GET /cli/fls`, read-only, modeled on `perm_auditor`) and generates a
second, human-facing permission set. Reading a field loads **all of that object's
custom fields** into the set at the source field's access level (read vs edit)
and auto-names it, so the read visibly produces a deployable permset — carried
alongside the integration permset through the deploy, dual assign, and package
zip. The set can also grant **object** permissions (`cli_script.object_perms_for`
→ `<objectPermissions>`), since a metadata-deployed object is hidden until object
access is granted — field FLS alone won't make it visible. FLS only — page-layout and record-type availability are handled separately
by their own paste-and-inject sections (below).

**New object (builder).** The field builder can define fresh `CustomObject`s
(API name, label, plural, sharing) that ride in the package as a shell and get
injected into the Object picker so fields target them; `_members`/`deploy_snippet`
put `CustomObject:` ahead of its `CustomField:` members so one deploy creates the
object then its fields.

**Clone object (`cli_clone.py`).** Instead of hand-adding fields, describe a
whole object in a chosen **source org** (per-run picker) and generate a deployable
package of its custom fields:
`POST /cli/clone-object/plan` (preview — fields, per-field skip reasons, optional
shell) and `POST /cli/clone-object/package` (the force-app zip). It maps each
describe field to the same field spec the builder uses, so `cli_script`'s
byte-for-byte generators produce the artifacts. Plain **Lookup** relationships
are cloned (they reference by object API name). Fields it can't reproduce 1:1 —
master-detail and polymorphic relationships, formula/roll-up, auto-number, and
unsupported types (currency, percent, multipicklist, rich text) — are **listed
as skipped**, never dropped silently. When a target org is known (the mirror
flow passes one), a plain **Lookup whose referenceTo object isn't in the target**
(e.g. a managed `hed__Term__c` absent from Ed Cloud) is also skipped —
`plan_from_object(..., target_objects=…)` — so the package never carries a field
whose `referenceTo` would fail to resolve. An opt-in best-effort
`CustomObject` shell (Text name field, `sharingModel` defaulted since describe
omits it) creates the object if it doesn't exist yet; deploy is upsert. Reuses
`build_package_zip` (now with `object_shells`) + an optional access permission set.

**Custom Tab + tab visibility (Phase 2).** A metadata-deployed custom object has
no tab, so it never shows in the App Launcher / nav (reachable only by direct
URL — `sf org open -o <alias> -p "/lightning/o/<Object>/list"`). Ticking
**Generate a Custom Tab** in the Clone (or New-object) card adds a
`CustomTab` (`cli_script.tab_meta_xml`, fullName = the object API name,
`customObject=true` + a stock motif) to the package and grants its visibility in
the access permission set (`permission_set_xml`'s `tab_settings` →
`<tabSettings><tab>…</tab><visibility>Visible</visibility></tabSettings>`).
Closes the create → object-visible → field-visible → **tab-visible** lifecycle.

**Access mirror (Phase 2, `cli_access_mirror.py`).** Cloning the object copies
schema but not *who can see it*. Ticking **Mirror the source org's access by
name** reads every profile + permission set that grants the object in the source
org (`ObjectPermissions`/`FieldPermissions` grouped by parent; a profile-owned
permission set is attributed to its `Parent.Profile.Name`) and reproduces those
exact object + field grants onto the **same-named** profiles / permission sets
that already exist in the **target** (a per-run target-org picker). Names the
target doesn't have are **reported, never invented**. `B2BMA Integration User`
(its B2B Marketing Analytics license locks a managed field, so it rejects even an
additive deploy — `cli_access_mirror.LOCKED_PROFILES`, kept deliberately narrow
since most integration/standard profiles DO deploy additively) is reported as
`skipped_locked`, never emitted. Field grants are scoped
to the fields the deploy will actually create (cloned now ∪ already present) so a
mirrored file never references a missing field (which would fail the whole
deploy). Both profiles and permission sets are emitted
(`cli_script.profile_xml` / `permission_set_xml`) — a partial Profile /
PermissionSet deploy is **additive** (upserts the named object/field perms,
leaves the rest untouched), so this is safe on live metadata.
`POST /cli/access-mirror/plan` previews matched vs unmatched; the clone
`plan`/`package` fold it in when `mirror_access` is set.

**Governance guardrails on the mirror.** Reading another org's full security
posture is itself sensitive, so `mirror_access` requires a short **justification**
string (≥10 chars, server-enforced in `routes/cli.py._require_justification` —
not just a UI modal) and every plan/package call emits an `ACCESS_MIRROR_PLAN`
audit event (`services/audit.py`) carrying it. High-privilege profiles
(`cli_access_mirror.HIGH_PRIVILEGE_PROFILES`, currently `System Administrator`)
are **excluded from `matched` by default** — reported in a separate
`high_privilege_excluded` list, never silently folded in or silently dropped —
and only ride into the package when the caller passes `include_high_privilege`;
even then each matched entry is flagged `high_privilege: true` so the UI can
call it out. This is distinct from `LOCKED_PROFILES` (a deploy-mechanics skip
for profiles that reject the deploy outright) — high-privilege is a governance
gate on profiles that *would* deploy fine but replicate admin-level access.

**Command composer.** A bottom-of-tab utility (`POST /cli/recipes`,
`cli_script.command_recipes`) that turns an object + field selection into
copyable `sf` recipes (describe / query / count / retrieve). Rather than
re-implement live query/describe (the SOQL Workbench and Data Dictionary tabs
already do that), each recipe links out to the matching tab for live results —
the composer's lane is generating the CLI command, not running it in-browser.

**Page layout (`cli_layout.py`).** A field isn't on the record page until it's
on the layout — a third metadata type. Layouts can't be read synchronously here
(simple_salesforce's Metadata API is async-retrieve-only), so the flow is:
generate a **list-layouts** command (`sf org list metadata -m Layout`, to discover
the exact `<Object>-<Layout Name>` fullName) then the retrieve command — both use a
per-section **"retrieve from" source alias** (e.g. EDA) while deploy targets the top
Alias, so a cross-org retrieve→deploy needs no field-swapping — the admin
pastes the retrieved `.layout-meta.xml`,
and either **copies it as-is** (no edits — the pasted `.layout-meta.xml` rides in
the package + deploy verbatim under `layouts/`, for an org-to-org 1:1 copy; the
target must already have every field it references), or `cli_layout` **adds
fields** to it (a new `<layoutSections>`, or into an existing section's first
column) via **pure string surgery that leaves every other byte untouched** —
never a rebuilt layout designer. Fields already on the layout are skipped. Pinned against the real Case layouts in `tests/fixtures/` +
`tests/test_cli_layout.py`. FLS + layout together complete the create → visible →
on-the-page lifecycle.

**Record type (`cli_recordtype.py`).** A picklist field's values aren't
selectable under a record type until they're listed in its `<picklistValues>` —
a fourth metadata type. Same async-retrieve constraint as layouts, so the flow
mirrors the layout one: generate the retrieve command, the admin pastes the
retrieved `.recordType-meta.xml`, and `cli_recordtype` appends the missing
values to the field's existing `<picklistValues>` block (or adds a new block for
a field the record type doesn't yet govern) via the same **byte-preserving
string surgery** — values already present are skipped, an optional `default` is
honored. Value names are written verbatim; SF percent-encodes some value names
(e.g. `/`) so the generator is provisional until pinned against a real
`.recordType-meta.xml` sample (the fixture in `tests/fixtures/` is
representative, not org-exact — see `tests/test_cli_recordtype.py`). This closes
the create → visible → on-the-page → selectable-per-record-type lifecycle.

**API-shape note (standards follow-up).** The CLI tab keeps this app's
blueprint-prefix routing (`/cli/...`) for consistency with the other tabs, and
introduces the shared standards **error envelope** in `utils/responses.py`
(`{success:false, error, code, request_id}` — a superset of `{success, data}`,
so `MC.api` is unaffected) plus an OpenAPI stub at `static/openapi-cli.yaml`.
Full Doane-standard API conformance — moving data/action routes under `/api/v1/`
and mounting a `/swagger` UI (`flask-swagger-ui`) across all blueprints — is a
deliberate, separate pass, not smuggled in via one feature. Adopt
`utils.responses.error_response` in other blueprints when that pass happens.

## Scheduled runs (Argo)

A scenario can be promoted to scheduled execution by flipping `schedule_approved`
(a manual sign-off in the builder; gated by `MC.confirm` when turning on). The
app does **not** talk to the Argo API — the builder generates an Argo
`CronWorkflow` YAML (`services/argo.py`) you commit to your manifests repo. On
its schedule, Argo POSTs `/scenarios/<id>/scheduled-run` with the
`X-MC-Scheduler-Token` header; the app validates it against
`Config.SCHEDULER_TOKEN` (constant-time), refuses unless `schedule_approved` is
set, runs the scenario with its stored org, and logs one structured summary
line to stdout (the Argo-visible notification). A non-clean run returns HTTP 500
so `curl -f` fails and Argo flags the workflow. Blank `SCHEDULER_TOKEN` disables
scheduled runs entirely.

## Shared object picker

Every tab's "which SObject?" input is fed from **one** describe-driven source
instead of each tab hardcoding, freetext-ing, or re-querying its own list.
`GET /meta/objects` (`routes/meta.py`, backed by `services/cli_metadata.py`)
returns the org's full SObject list plus DescribeGlobal capability flags
(`queryable` / `layoutable` / `createable` / `updateable` / `deletable`).
`MC.objectPicker` (in `mission-control.js`) fetches that once per org (cached),
renders a searchable body-level typeahead, and **filters per context** so an
object only appears where the action can actually succeed:

- `all` — describe/read (Data Dictionary, FLS read, schema diff)
- `queryable` — SOQL Workbench, FK lookups, record inspector
- `customizable` (= `layoutable`) — the CLI **field builder**, so system objects
  that reject custom fields (`ContentDocumentLink`, `ContentNote`, `*__Share`,
  `*__History`) never appear where they'd only fail on deploy
- `createable` / `updateable` / `deletable` — Data Ops DML by operation

Wire declaratively, mirroring `data-mc-confirm`: add
`data-mc-objpick="<capability>"` to any `<input>` and the global
`MC.objectPicker.autowire()` (DOMContentLoaded) attaches it. Special widgets
(Join Builder's SF-object field, Org Diff's tag multi-add) call
`MC.objectPicker.attach(id, {capability, onSelect})` directly. The input stays
free-typeable — the picker is assistive, not restrictive, so an object the
describe doesn't return can still be typed by hand. The org picker reloads the
page on change, so the per-org cache needs no explicit invalidation.

## Confirmation dialogs

Every state-changing UI action (SF writes, bulk DML, Conductor reruns, trigger-bypass changes, log/trace-flag deletes) is gated by a confirmation modal. The shared primitive is `MC.confirm()` in `mission-control.js`; most buttons opt in declaratively via a `data-mc-confirm` attribute, intercepted by a capture-phase guard. Conditional cases (anonymizer live run, bulk-update live run) call `MC.confirm()` directly.

## Testing

```bash
pytest tests/ -v
```

## Common gotchas

- `secretKeyRef` indentation in K8s manifest: `name` and `key` must indent UNDER `secretKeyRef`
- Flask binds `0.0.0.0` so Conductor/Docker can reach via `host.docker.internal`
- `use_reloader=False` in hub-launched mode
- An unconfigured org makes `get_sf()` raise unless `SHOW_MOCK=true` — there is no silent mock fallback
