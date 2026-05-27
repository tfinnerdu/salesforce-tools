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
  readiness_validator.py   §3 pre-go-live scorecard
  duplicate_radar.py       §5 duplicate PersonAccount scan
  batch_tracker.py         §6 migration batch progress
  error_reconciler.py      §7 Conductor failure categorization
  schema_diff.py           §8 sandbox vs prod field diff
  soql_workbench.py        §9 SOQL runner + object explorer
  external_id_coverage.py  §10 SIS_ID__c / Ethos_Guid__c coverage
  contactpoint_scanner.py  §11 broken ContactPoint parent links
  crosswalk_diff.py        §4 EDA→Ed Cloud field mapping diff
  join_builder.py          §14 SF↔SQL Server join query builder
  collection_manager.py    §13 Postman collection runner
  scenarios.py             Multi-step Data Ops pipelines (delete / modify /
                           reassign / bulk_update / tune chained together)
  tags.py                  App-level tagging for saved artifacts (scenarios
                           first); see tag_sync.py for the future SF-field
                           sync scaffold
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
