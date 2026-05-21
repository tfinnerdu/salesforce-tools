# Console Project — Design Notes

**A central command console for Doane platform tooling**
**Status:** Discussion / pre-design. Nothing here is built. This document exists to be argued with.

---

## 1. Purpose

SF Mission Control proved the model: many small tools, one authenticated dashboard. The next question is whether that dashboard should become a **general console** — an MMC-style host that snaps in tools from across the Doane platform estate (SF Mission Control pages, the Ethos console, Conductor tooling) on an ala carte, per-user basis.

This document covers:

- A **plugin (snap-in) standard** so tools can be composed into one shell.
- A **security broker + audit layer** so one-off, cross-platform privileged tasks can be done safely without elevating humans inside each platform.
- Standards to adopt, things to avoid, gotchas, what the current codebase already does right, and a phased migration path.

The two halves interlock: the plugin manifest's **capability declarations** become the vocabulary the security layer uses for authorization and override. Build them together or retrofit auth painfully later.

---

## 2. The console model

Borrow MMC's mental model directly:

| MMC concept | Console equivalent |
|---|---|
| Console | The host shell — nav, auth, org context, theming. Knows nothing tool-specific. |
| Snap-in | A plugin — one tool, self-contained. |
| Local vs. remote snap-in | Native (in-process) vs. embedded (external app) mount tiers. |
| `.msc` saved console | A saved workspace — which snap-ins, which layout, per user. |
| Snap-in tree node + results pane | Nav entry + content pane. |

The shell is deliberately dumb. All tool knowledge lives in snap-ins and their manifests. The shell only does: discover manifests, render nav, enforce auth, inject context, host the pane.

---

## 3. Architecture overview

### 3.1 Two mount tiers

A single-tier design fails the moment you try to host the Ethos console or Conductor tools — those are separate products you will not rewrite as Flask blueprints. The shell must support both:

**Native snap-in** — in-process, like today's blueprints.
- Registered via Python entry point / blueprint registration.
- Full access to the host SDK (`MC.*`, the providers).
- Cheapest to build; use for everything that is or could be Flask.

**Embedded snap-in** — an external app surfaced through the shell.
- Reverse-proxy or iframe, with SSO passed through.
- Gets a nav node and a content pane; runs as its own service.
- Use for Ethos console, Conductor tools, anything not Flask.

A hybrid shell is not a compromise — it is the correct design. MMC itself distinguishes local and remote snap-ins.

### 3.2 Info pages vs. interactive pages

The instinct that "info pages are easier to plug in" is correct and worth designing around:

- **Info pages** (Record Counts, API Limits, Audit Trail, Data Dictionary) are stateless read views. They become plugins almost for free.
- **Interactive pages** (Bulk Update, Anonymizer, Trace Flags) perform writes. They cannot be cleanly plug-and-play until the capability + broker layer exists, because "can this person do this here" must be answerable by the shell, not buried in the tool.

Sequence the work accordingly: prove the plugin shell with read-only pages, but do not convert interactive pages until §6 and §7 exist.

---

## 4. The plugin manifest standard

One `plugin.yaml` per snap-in. Schema-versioned. This is the single most important standard to get right.

```yaml
# plugin.yaml
manifest_version: 1                 # bump when this schema changes

id: sf-observe                      # stable, unique, kebab-case — never reused
name: "Observe"
version: "1.2.0"                    # SemVer; the snap-in's own version
category: "Monitoring"              # groups the console nav tree
icon: "activity"                    # name from the shared icon set
description: "Governor limits, drift detection, data-quality trends."

mount:
  type: native                      # native | embedded
  # --- native fields ---
  blueprint: "routes.observe:observe_bp"
  url_prefix: "/observe"
  # --- embedded fields (use instead of the above) ---
  # url: "https://ethos.doane.edu/console"
  # sso: oidc                       # oidc | saml | header
  # sandbox: "allow-scripts allow-forms allow-same-origin"

requires:
  env: [DATABASE_URL]               # shell grays out the snap-in if unset
  secrets: []
  host_min_version: "1.0.0"         # minimum host SDK contract version
  services: [postgres]              # declared external dependencies

health:
  endpoint: "/observe/health"       # shell polls; drives red/amber/green node
  interval_seconds: 60

context:
  needs_org: true                   # shell injects the active org
  needs_user: true                  # shell injects the authenticated user

capabilities:                       # THE KEYSTONE — see §6
  - id: observe.limits.read
    label: "View API limits"
    type: read
    risk: low
  - id: observe.thresholds.write
    label: "Edit limit thresholds"
    type: write
    risk: medium

ui:
  default_pane: "limits"
  supports_workspace: true          # may be saved into a console layout
```

**Field notes:**

- `id` is forever. Renaming it orphans saved workspaces and audit history. Choose carefully.
- `manifest_version` is separate from the snap-in's `version`. The schema will change; version it from day one.
- `requires.env` lets the shell do what the SF/Conductor mock badges already do — show a snap-in as *unavailable: needs ANTHROPIC_API_KEY* instead of letting it fail at runtime.
- `health.endpoint` returns a standard shape (see §5). The shell colors the nav node from it.
- `capabilities` is not optional and not cosmetic — it is the authorization vocabulary. A snap-in with no declared capabilities can do nothing privileged.

---

## 5. The host-provided contract (the SDK)

The shell offers a small, **versioned, stable** surface that snap-ins build against. You are ~70% of the way there — `MC.*` and the provider pattern already are this SDK; they just are not formalized.

**What to promote into a documented contract:**

| Surface | Today | Becomes |
|---|---|---|
| Org context | `session['active_org']`, `MC.activeOrg()` | `host.context.org` |
| API envelope | `{success, data, error}` + `MC.api()` | `host.api()` — keep the envelope exactly |
| UI primitives | `MC.showToast`, `MC.showSpinner` | `host.ui.*` |
| Deeplinks | `MC.sfUrl`, `MC.sfLinkHtml` | `host.links.*` |
| Privileged clients | `get_sf(org)`, `get_conductor_client()` | `host.broker.sf(...)`, `host.broker.conductor(...)` — see §7 |
| Auth / identity | `session` user | `host.context.user` |

**Standard health-check shape** every snap-in returns:

```json
{ "status": "ok", "detail": "", "checked_at": "2026-05-21T12:00:00Z" }
```

`status` is `ok | degraded | down`. The shell needs nothing else to render the node.

**Rule:** snap-ins talk to the host, never to each other. No cross-importing another snap-in's service module. If snap-in A needs data from snap-in B, it goes through B's HTTP API or a host-mediated channel. Today's Dashboard widgets calling other tabs' endpoints directly is the *acceptable* version of this; a snap-in `import`ing `services.observe` from another plugin is not.

---

## 6. The capability model

This is the hinge between the two halves of the project.

**Capability ID format:** `<plugin>.<resource>.<verb>` — e.g. `observe.thresholds.write`, `dataops.bulk.execute`, `admin.anonymizer.run`.

Each capability declares:

- `type` — `read` or `write`. Read capabilities are cheap to grant broadly.
- `risk` — `low | medium | high`. Drives approval routing and notification loudness.

**Two design tensions to manage deliberately:**

- *Granularity.* Too fine and the RBAC is unusable (hundreds of toggles). Too coarse and it is not safe. **Start coarse — roughly one capability per interactive feature — and split only when a real need appears.**
- *Read visibility.* Many ala carte requests are just "I want to *see* this tool." Model a read capability that grants visibility without action. Most cross-team needs evaporate once people can simply look.

The central RBAC layer is then a single mapping:

```
role/user  ->  set of capability IDs  (per org)
```

A standing grant is a permanent entry. An override (§8) is a temporary, time-boxed entry in the *same* table. There is only one authorization concept.

---

## 7. The security broker + audit layer

### 7.1 The core idea — do not elevate humans

The wrong path: temporarily bump someone's rights inside Salesforce / Conductor / Ethos. Every platform's model differs, grants leak, revocation is unreliable, and the audit trail fragments across systems.

The right path: **the console is a privileged broker.** It holds a scoped service account per platform. Humans never gain elevated rights anywhere. The console runs the action on the user's behalf, enforces a finer-grained capability check, and attributes every action to the real person.

### 7.2 You already have the chokepoint

`get_sf(org)` and `get_conductor_client()` are the single doorway every privileged call passes through. That is exactly where the broker check and the audit write belong. `dml_guard` and `SF_BYPASS_SETTING` are already primitive controlled-override mechanisms — the broker generalizes a pattern you have, it does not invent one.

**Proposed signature change:**

```
# today
get_sf(org) -> client

# broker
host.broker.sf(org, actor=<user>, capability="dataops.bulk.execute")
    -> authorized client   (service-account-backed)
    -> or raises NotAuthorized   (routes turn this into HTTP 403)
```

Every privileged call site names the capability it is exercising. An untagged call through the broker is a bug — fail it closed.

### 7.3 Audit log

Append-only. Never updated, never deleted.

```
audit_log
  id
  ts                  -- UTC
  actor_email
  actor_ip
  plugin_id
  capability
  org
  action_detail       -- jsonb: SOQL, record ids, field, value, etc.
  grant_type          -- standing | jit | break-glass
  grant_id            -- fk to elevation_grants when not standing
  justification       -- carried from the grant
  outcome             -- success | denied | error
  result_summary
```

**Log denied attempts too.** A wall of denials on one capability tells you the RBAC is too tight — that signal is as valuable as the successes.

### 7.4 JIT elevation grants

```
elevation_grants
  id
  requested_by
  requested_at
  capability
  org
  justification
  ticket_ref
  approved_by         -- null until approved
  approved_at
  expires_at
  revoked_at
  revoked_by
  status              -- pending | active | expired | revoked | denied
```

---

## 8. The override flow

For the real scenario: someone with limited rights in platform A needs a one-off task outside their normal scope.

1. **Attempt.** User hits a UI action they lack. The shell does not just hide it — it offers **Request elevation**.
2. **Request.** A form, pre-filled with the capability and org. The user supplies a **justification** and a **ticket reference**, and picks a duration (minutes to hours — short).
3. **Approve.** Routed to an approver who holds that capability and **is not the requester**. High-risk capabilities may require two approvers.
4. **Activate.** On approval the grant goes `active` with an `expires_at`. The broker now passes the check for that actor + capability + org.
5. **Use + audit.** Every action still flows through the broker, still audited, tagged `grant_type=jit` and linked to `grant_id`.
6. **Notify.** The resource owner and a security channel are told on activation and on each use.
7. **Expire.** The grant auto-expires. A scheduled sweep (you already run APScheduler) also revokes stale grants defensively. Manual revoke is always available.

**Break-glass variant** — true emergencies, no approver reachable. Self-approval is permitted but **loud**: an immediate page to the security channel, the shortest possible TTL, and a mandatory post-hoc review. Break-glass is the rare exception, never the everyday path.

---

## 9. Workspace persistence

The `.msc` analogy. Let a user compose their own console — which snap-ins, what layout — and save it. The Dashboard's 8-widget grid is a baby version of this; generalize it into a saved, named, per-user layout. Snap-ins opt in via `ui.supports_workspace`.

---

## 10. Per-user snap-in registry (the ala carte part)

A table mapping who sees which snap-ins:

```
snap_in_grants
  principal       -- user or role
  plugin_id
  granted_by
  granted_at
```

Visibility (does the snap-in appear at all) is separate from capability (what you can do inside it). A user may see a snap-in read-only, or not see it at all. Keep the two concepts distinct.

---

## 11. Standards to adopt

- **Manifest:** YAML, one `plugin.yaml` per snap-in, `manifest_version` from v1.
- **Capability IDs:** `<plugin>.<resource>.<verb>`, lowercase, dot-separated. Stable forever.
- **Every privileged call declares a capability.** No exceptions, fail closed.
- **API envelope:** keep `{success, data, error}` exactly as-is. It is already a good standard.
- **Health endpoint:** every snap-in exposes one, returning the standard shape.
- **SemVer the host SDK.** Snap-ins declare `host_min_version`.
- **Time:** store UTC everywhere, localize to Central in the UI only.
- **Audit is append-only.** No update/delete path, ever.
- **SSO:** pick one protocol (OIDC recommended) for all embedded snap-ins. Do not let each tool roll its own.
- **DB tables:** plugins that create their own tables (the lazy `_ensure_table` pattern) must prefix table names with the plugin `id` to avoid collisions.
- **Secrets:** K8s Secrets as the floor. Move to Vault once multiple platform service accounts exist.
- **Naming:** plugin `id` is immutable; treat renames as deletes.

---

## 12. Things to avoid

- **Do not elevate humans in the native platform.** Broker it. This is the central thesis.
- **Do not let snap-ins import each other's service modules.** Talk through the host or HTTP.
- **Do not share one super-service-account** with all rights across all platforms. Scope per platform, ideally per risk tier.
- **Do not put capability checks only in the UI.** Hiding a button is not security. The broker is the gate; the UI merely reflects it.
- **Do not make break-glass the primary path.** It is the exception, and it must be loud.
- **Do not embed external tools via iframe without** thinking through SSO, CSP, cookie `SameSite`, and clickjacking.
- **Do not let the requester approve their own elevation.**
- **Do not skip justification capture at request time.** The "why" cannot be reconstructed later — it rots.
- **Do not hard-code org lists in snap-ins.** The `dev/prod/sandbox` `<select>` is currently duplicated across many templates — that duplication becomes N copies to fix. The shell should own the org picker and inject context.
- **Do not let capability count explode.** Start coarse. Split on demonstrated need only.
- **Do not build per-snap-in bespoke auth.** Centralize, always.

---

## 13. Gotchas

- **FERPA.** This is student data in an education context. Least-privilege, audit retention, and access reviews are not nice-to-haves — they are compliance posture. The Anonymizer feature shows the awareness already exists; carry it into the console's audit retention and approval design from the start.
- **Auth lifetime mismatch.** Native and embedded snap-ins have different session/token lifetimes. Refreshing a token across an iframe boundary is fiddly — spike it early.
- **Health-check stampede.** Polling every snap-in's health can hammer downstream APIs and burn the very governor limits the Observe tab watches. Cache, back off, and respect those limits.
- **Hot-reload story.** You already hit `use_reloader=False` in hub-launched mode. A plugin registry that scans manifests needs a defined restart story for dev ergonomics.
- **Per-plugin mock state.** `SF_MOCK` / `CONDUCTOR_MOCK` are global today. With N snap-ins you will want per-plugin mock state. The separate SF/Conductor mock badges already started down this path — good instinct, keep going.
- **Grant expiry must be enforced, not just checked.** Check at read time *and* sweep with the scheduler. Show a live countdown in the UI so an active grant is never a surprise.
- **Clock skew** between services breaks expiry math. Trust one clock.
- **Audit log growth.** Decide partitioning / archiving on day one, not at 10M rows.
- **Approver availability.** If the only approver for a capability is on vacation, work stops. Define backup approvers per capability.
- **Traefik `stripPrefix` + iframes.** You already have a `stripPrefix` gotcha noted in CLAUDE.md. Embedded snap-ins behind it will surface cookie-path and asset-path issues — budget time for it.
- **Org context drift.** If the shell holds the active org but an embedded tool has its own org selector, they desync silently. Decide who owns org context (the shell should) and make embedded tools accept it.
- **Back-button / deep-linking** inside an embedded pane is never free.

---

## 14. What the current codebase already does right

These are real assets — the console project leans on every one of them:

- **The provider pattern.** `get_sf` / `get_conductor_client` as the single privileged chokepoint is the thing that makes the broker feasible at all. This is the biggest win.
- **Blueprint-per-tab.** Already modular, already most of the way to snap-ins.
- **Service-per-feature modules.** Clean separation; each becomes a plugin's internals untouched.
- **The `{success, data, error}` envelope.** A consistent API contract already exists and is good — keep it.
- **The `MC.*` namespace.** A de facto host SDK already exists; it needs formalizing, not inventing.
- **Lazy `_ensure_table`.** Plugins managing their own schema without central `db.py` edits — exactly right for plugin independence (just add the id-prefix rule).
- **Mock providers + the new per-source mock badges.** Testability plus per-dependency state awareness — the console needs both.
- **`dml_guard` + `SF_BYPASS_SETTING`.** Controlled-override primitives already in the codebase.
- **Tests per feature (778 and counting).** Each feature self-tests; plugins must keep this discipline.
- **CLAUDE.md capturing gotchas.** Institutional knowledge is being written down — this document continues that habit.
- **The Dashboard widget grid.** A working proto-workspace to generalize.
- **Centralized config** in `config.py` / `get_org_config()`.

---

## 15. Suggested phasing

Build the security spine before extracting plugins. Retrofitting auth into N snap-ins is the classic failure mode.

| Phase | Work | Outcome |
|---|---|---|
| **0** | Formalize the existing contract — document `MC.*`, the envelope, the provider chokepoint. | A written SDK baseline. No behavior change. |
| **1** | Capability registry + audit log + broker check inside `get_sf` / `get_conductor_client`. Tag every existing call site with a capability. Everyone gets standing grants initially. | Full audit trail; nothing breaks; auth is now centralizable. |
| **2** | JIT grant flow + approval UI + override request. | Standing grants can now be tightened safely. |
| **3** | Manifest standard; convert two pilot pages — one info (Record Counts), one interactive (Bulk Update). Minimal shell that reads manifests. | Both mount-adjacent paths proven. |
| **4** | Embedded tier — bring in Conductor tooling or the Ethos console as the first external snap-in with SSO. | The hard unknowns (SSO, CSP) retired. |
| **5** | Workspace persistence + per-user snap-in registry. | True ala carte console. |

---

## 16. Other tips

- **Build §6 and §7 first.** The capability model and audit log before any plugin extraction. Non-negotiable.
- **Pilot one read-only and one interactive page.** Record Counts and Bulk Update prove both the easy path and the hard path.
- **Spike the embedded tier early.** Conductor or Ethos integration is where the unknowns live — do not let it be a Phase 4 surprise.
- **Notifications belong to the override flow.** This is the perfect first consumer of the parked GChat / email alerts work — wire override events into it.
- **Model read-only "shadow" capabilities.** Letting people *see* a tool resolves most ala carte requests without any write risk.
- **Keep break-glass loud.** A page to a channel, not a quiet log line.
- **The override UI should make "why" easy and consequences visible.** Friction in the right place — on justification, not on the click.
- **Treat the shell as its own product** with its own release cadence, even if it starts inside this repo.
- **Version the manifest schema from v1.** You will change it; plan for it.

---

## 17. Open questions / decisions needed

- **Native-first or embedded-first** for Ethos and Conductor? Drives Phase 3 vs. 4 ordering.
- **OIDC provider** — is there a Doane IdP (Entra / Azure AD)? It dictates the embedded SSO approach.
- **Approval routing** — who approves which capabilities? Org admins? A named security group? Backups?
- **Service-account credential store** — stay on K8s Secrets, or move to Vault now?
- **Audit retention** — how long, and what does FERPA require for student-data access logs?
- **Repo strategy** — one console repo, a plugin monorepo, or separate repos per plugin?

---

*Drafted May 2026. Companion to `user-guide.md`. This is a discussion document — revise freely.*
