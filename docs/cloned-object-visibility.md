# Making a **cloned object** visible (RoomAssignment worked example)

[Verifying field visibility](verifying-field-visibility.md) covers a new *field*
on an object that already exists. Cloning a **whole custom object** across orgs
(EDA → EC-SB via the CLI tab's **Clone object** card) adds two switches *below*
the field ones: the object itself has to be granted, and it needs a **tab** to
appear in the app at all. A metadata-deployed object is hidden from **everyone**
— even a System Administrator — until these are on.

This is the chain the CLI tab now generates end-to-end. Substitute your own
object (`RoomAssignment__c` is the running example).

---

## The switches, bottom to top

| # | Metadata | Question | Who grants it |
|---|---|---|---|
| 0 | **CustomObject** | Does the object exist? | Clone card → *Include the object definition* |
| 1 | **Object permission** (`<objectPermissions>`) | Can this user open the object / its records at all? | Access permission set (Clone card) **and** the access mirror |
| 2 | **Field FLS** (`<fieldPermissions>`) | Can they see each field's value? | Same permission set(s) |
| 3 | **CustomTab** + **tab visibility** | Does the object show in the App Launcher / nav? | Clone card → *Generate a Custom Tab* |

Switches 1–2 are what "Field-Level Security is unchecked across the board /
fields are Hidden" actually is: object + field access were never granted to the
deployed metadata. Switch 3 is why "I can't open the object from the app" — no
tab exists yet.

> **The profile forms lie (on purpose).** Access granted through a **permission
> set** never appears on a profile's *Set Field-Level Security* or *Field
> Accessibility* forms in Setup — those show the **profile's own** grants only.
> A permission-set grant still takes full effect for assigned users. So don't
> verify on the profile form; verify on a **record**, or with the SOQL below.

---

## Switch 0 / 1 — object exists and is grantable

**CLI check — is the object there and can you open it?**
```powershell
# Object exists?
sf sobject describe --sobject RoomAssignment__c --target-org EC-SB --json | `
  Select-String '"name"'

# Open its list view directly (bypasses a missing tab — proves object access):
sf org open --target-org EC-SB --path "/lightning/o/RoomAssignment__c/list"
```
If the list view opens and shows records/columns, object access is on. If you
get "insufficient access," Switch 1 is off.

**Where object access comes from:** the Clone card's access permission set now
emits `<objectPermissions>` (read + create/edit) alongside the field grants —
field FLS alone can't make a hidden object visible. Assign that permission set to
yourself (or the integration user) and the object opens.

---

## Switch 2 — field FLS

Identical to the [field doc's Switch 2](verifying-field-visibility.md#switch-2--field-level-security-can-they-see-the-value)
— the authoritative check is the `FieldPermissions` SOQL, pointed at every field:
```powershell
sf data query --target-org EC-SB --query `
  "SELECT Field, Parent.Name, PermissionsRead, PermissionsEdit `
   FROM FieldPermissions WHERE SobjectType = 'RoomAssignment__c'"
```
Every cloned field should appear with `PermissionsRead = true` on the permission
set(s) you deployed.

---

## Switch 3 — the tab

A cloned object has **no tab**, so it's absent from the App Launcher and nav —
only reachable by the direct `/lightning/o/<Object>/list` URL above. Ticking
**Generate a Custom Tab** on the Clone card adds a `CustomTab` to the package and
grants its visibility in the access permission set, so assignees see the object
where they'd expect to.

**CLI check:**
```powershell
sf org list metadata --metadata-type CustomTab --target-org EC-SB | `
  Select-String "RoomAssignment__c"
```
Then just open the App Launcher (⋮⋮⋮) in the org and search the object's label.

---

## Reproducing EDA's access by name — the access mirror

Assigning one hand-built permission set makes the object usable for *you*.
Reproducing **who had access in EDA** — every profile and permission set — is the
**Mirror the source org's access by name** option on the Clone card.

It reads which profiles + permission sets grant `RoomAssignment__c` in the source
org and generates matching **additive** grants for the **same-named** profiles /
permission sets **that already exist in the target**. Names the target doesn't
have are listed as *skipped* (never invented). Field grants are scoped to the
fields being deployed, so a mirrored profile never references a field the target
lacks (which would fail the whole deploy).

**Preview before you download:** the Clone card shows *matched* vs *not in
target* (and *locked profiles skipped* — see below). Or hit the endpoint directly:
```
POST /cli/access-mirror/plan
{ "object": "RoomAssignment__c", "source_org": "eda", "target_org": "sandbox" }
```

**Two things the mirror/clone skip automatically** (so you don't hand-edit the
manifest, as you would have before):

- **`B2BMA Integration User`.** Its B2B Marketing Analytics license locks a
  managed field, so it rejects even an additive deploy ("You may not turn off
  permission Read … for this License Type"). It's reported as *skipped*, never
  emitted. The skip list is deliberately narrow — most integration/standard
  profiles (Analytics Cloud, CPQ, Sales Insights, SalesforceIQ, Salesforce API
  Only, …) *do* deploy additively and are mirrored normally.
- **Lookups to an object the target doesn't have.** A cloned lookup whose target
  object isn't in the deploy org — classically an EDA/HEDA `hed__Term__c` that Ed
  Cloud doesn't have — is skipped (the field would fail with "referenceTo … does
  not resolve to a valid sObject type"), and its field grant is dropped from the
  mirror too. Create or remap that object first if you need the lookup.

**Re-deploying existing fields.** If the object's fields already live in the
target (a prior clone), you don't need them in this deploy at all — deploy just
the tab + permission sets + profiles. Re-deploying an existing lookup can also
trip "must be unique across all <parent> fields" (its child relationship already
exists). The fields only need to *exist* in the org for the permset/profile
grants to resolve; they don't need to be in this package.

**Why it's safe:** a partial Profile / PermissionSet deploy is *additive* —
Salesforce upserts the object/field permissions the file names and leaves every
other permission on that profile/permission set untouched. The mirror files only
name this object's access, so deploying them can't wipe anything else.

**Verify a mirrored profile took effect — on a record, not the profile form:**
```powershell
sf data query --target-org EC-SB --query `
  "SELECT Parent.Profile.Name, PermissionsRead, PermissionsEdit `
   FROM FieldPermissions `
   WHERE SobjectType = 'RoomAssignment__c' AND Parent.Profile.Name = 'System Administrator'"
```

---

## Quick reference — the cloned-object chain

| Check | Fastest verification |
|---|---|
| 0. Object exists | `sf sobject describe --sobject RoomAssignment__c -o EC-SB --json \| Select-String '"name"'` |
| 1. Object access (open it) | `sf org open -o EC-SB --path "/lightning/o/RoomAssignment__c/list"` |
| 2. Field FLS | `sf data query -o EC-SB -q "SELECT Field, Parent.Name, PermissionsRead FROM FieldPermissions WHERE SobjectType='RoomAssignment__c'"` |
| 3. Tab exists | `sf org list metadata --metadata-type CustomTab -o EC-SB \| Select-String "RoomAssignment__c"` → then App Launcher |
| Mirror preview | `POST /cli/access-mirror/plan` (matched vs not-in-target) |

**Symptom → which switch is off:**

- *Object is nowhere, even for admins* → Switch 1 (object permission not granted) — assign the access permission set.
- *List view opens by URL but there's no tab / nothing in App Launcher* → Switch 3 (no Custom Tab / tab visibility).
- *Object opens but fields are blank/Hidden* → Switch 2 (field FLS).
- *Works for you, not for a colleague on another profile* → run the access mirror so their profile/permission set is granted too.
