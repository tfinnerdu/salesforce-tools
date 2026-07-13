# Verifying field visibility & accessibility (Case worked example)

A new custom field in Salesforce is **invisible and unusable by default**.
Creating the field is only step 1 of 4 — three more independent pieces of
metadata each have to be switched "on" before a human actually sees the field,
on the record page, with the right values. The CLI tab generates all four; this
doc is how you **confirm each one landed** in the Salesforce UI, and the `sf`
CLI commands that check the same thing without clicking.

This walkthrough uses the Case fields we set up (e.g. `Group_Information__c`, the
picklist `Type_of_Assistance__c` with values Academic / Financial / Medical, and
the human permission set `Case_Assistance_Fields`) as the running example.
Substitute your own object, fields, and permission-set name.

---

## The mental model — four separate switches

| # | Metadata type | The question it answers | CLI-tab section that builds it |
|---|---|---|---|
| 1 | **Custom Field** | Does the field exist at all? | Build fields |
| 2 | **Field-Level Security (FLS)** — granted via a **permission set** | Can this user *see / edit the value*? | Visibility |
| 3 | **Page Layout** | Does the field *show up on the record page*? | Page layout |
| 4 | **Record Type** | Which *picklist values are selectable* here? | Record type |

They are genuinely independent. A field can exist (1) but be invisible because
FLS was never granted (2). It can be visible in reports and the API (2) but
missing from the page a user looks at (3). A picklist can be on the page (3) but
only offer two of its five values because a record type restricts it (4). When
"the user still can't see it," the fix is almost always one of these four being
off — so verify them in order.

> **Why permission sets, not profiles.** Doane grants FLS through permission
> sets (never by editing profiles directly). That's what the Visibility section
> clones out of EDA and what you assign to people. So everywhere below, "who can
> see the field" is answered by looking at the **permission set**, not the
> profile.

---

## Switch 1 — Does the field exist?

**In the UI:**
Setup (⚙ gear, top right) → **Object Manager** → **Case** → **Fields &
Relationships** → find the field by label or API name.

**What "correct" looks like:** the field is in the list. Click it to confirm the
type, length, and — for external-ID/unique fields — that those flags match what
you intended.

**CLI check:**
```powershell
# Fast: is the field present? (describe is large; this filters to the name)
sf sobject describe --sobject Case --target-org EC-SB --json | `
  Select-String "Group_Information__c"
```
Or just open the field page directly:
```powershell
sf org open --target-org EC-SB `
  --path "/lightning/setup/ObjectManager/Case/FieldsAndRelationships/view"
```

---

## Switch 2 — Field-Level Security (can they see the value?)

This is the one people miss. A brand-new field has **no FLS for anyone** — even
a System Administrator often can't see it until FLS is granted. The Visibility
section builds a permission set that grants it (cloned from how EDA had it).

**In the UI — look at the permission set (the Doane way):**
Setup → **Permission Sets** → **`Case_Assistance_Fields`** → **Object Settings**
→ **Case** → scroll to **Field Permissions**.

**What "correct" looks like:** each field you built has **Read Access** checked
(and **Edit Access** checked wherever EDA granted edit). Because the Visibility
section *cloned* EDA's pattern, "correct" literally means "the same Read/Edit
pattern the reference field had in EDA."

**Also check it's actually assigned to people:**
Setup → Permission Sets → `Case_Assistance_Fields` → **Manage Assignments** →
confirm the users (or the group you assign by) are listed. FLS granted by an
*unassigned* permission set does nothing.

**CLI check — this is the authoritative one for FLS.** It's the exact same
`FieldPermissions` query the Visibility section uses to read EDA, pointed at your
target org:
```powershell
sf data query --target-org EC-SB --query `
  "SELECT Parent.Name, Parent.Profile.Name, PermissionsRead, PermissionsEdit `
   FROM FieldPermissions `
   WHERE SobjectType = 'Case' AND Field = 'Case.Group_Information__c'"
```
Every row is a permission set (or profile) that grants access. You want to see
`Case_Assistance_Fields` in the list with `PermissionsRead = true` (and
`PermissionsEdit` matching intent). If the field returns **zero rows**, FLS was
never granted — nobody can see it yet.

**Confirm the assignment via CLI too:**
```powershell
sf data query --target-org EC-SB --query `
  "SELECT Assignee.Name, PermissionSet.Name FROM PermissionSetAssignment `
   WHERE PermissionSet.Name = 'Case_Assistance_Fields'"
```

---

## Switch 3 — Page Layout (is it on the record page?)

FLS lets a user see the value *if they can find it* — in reports, list views, the
API. To make it appear on the Case record page, it has to be on the **page
layout**. The Page layout section adds it (paste the retrieved layout, it injects
the field, you deploy the result).

**In the UI:**
Setup → Object Manager → **Case** → **Page Layouts** → open the layout you
edited (e.g. **Case Layout**). The field should sit in a section. Double-click
the field in the editor (or hover → wrench) → **Layout Properties** to confirm
its **Read-Only / Required** flags.

**The gotcha — layout *assignment*.** Editing a layout only matters if it's the
layout your users actually get. Setup → Object Manager → Case → Page Layouts →
**Page Layout Assignment** (button, top of the list) → a grid of **Profile ×
Record Type**. Confirm the layout you edited is the one assigned to the
profile + record type your users fall under. Editing "Case Layout" does nothing
for a user whose profile+record-type is assigned "Advisee Case Layout."

**CLI check:** layouts aren't cleanly SOQL-queryable, so retrieve and eyeball —
this is the same retrieve command the CLI tab hands you:
```powershell
# List the Case layouts so you retrieve the exact name:
sf org list metadata --metadata-type Layout --target-org EC-SB | `
  Select-String "Case"

# Retrieve one and inspect it for your field:
sf project retrieve start --target-org EC-SB `
  --metadata "Layout:Case-Case Layout"
# then open force-app/main/default/layouts/Case-Case Layout.layout-meta.xml
# and search for the field API name inside a <layoutItems> block.
```

---

## Switch 4 — Record Type (which picklist values are selectable?)

Only relevant for **picklist** fields. Even with FLS (2) and the field on the
page (3), a record type can limit *which values* are offered. The Record type
section adds the missing values to a record type's `<picklistValues>`.

**In the UI:**
Setup → Object Manager → **Case** → **Record Types** → open the record type
(e.g. **Advisee Case**) → scroll to the **Picklists** section → click the
picklist field (e.g. **Type of Assistance**). You'll see **Available Values** vs
**Selected Values** and the **Default**.

**What "correct" looks like:** the values you added (Academic, Financial,
Medical) are in **Selected Values**, and the intended one is the **Default**.
Values in "Available" but not "Selected" won't appear in the dropdown for a
record of that record type.

**CLI check:** like layouts, easiest to retrieve and read the metadata:
```powershell
sf project retrieve start --target-org EC-SB `
  --metadata "RecordType:Case.Advisee_Case"
# open force-app/main/default/objects/Case/recordTypes/Advisee_Case.recordType-meta.xml
# confirm each value appears under the field's <picklistValues> block.
```

---

## The real test — "look at it as the person who reported it"

All four switches can read "correct" in Setup and a user still hits a wall,
usually because of **assignment** (the permission set isn't on them, or their
profile+record-type gets a different layout). So finish with an end-to-end look:

1. **Confirm assignment** — permission set is on the user (Switch 2's Manage
   Assignments / the `PermissionSetAssignment` query).
2. **See it through their eyes** — Setup → **Users** → the user → **Login As**
   (requires "Administrators Can Log in as Any User" to be enabled), open a Case
   **of the right record type**, and confirm: the field is on the page, in the
   right section, editable-or-read-only as intended, and the picklist offers the
   right values. If Login As isn't available, have the user open one Case and
   screenshare.

If it looks right there, it's right for real — that view is the sum of all four
switches plus assignment.

---

## Quick reference — verify order & one command each

Run these top to bottom; the first one that's wrong is your problem.

| Check | Fastest verification |
|---|---|
| 1. Field exists | `sf sobject describe --sobject Case --target-org EC-SB --json \| Select-String "<field>"` |
| 2. FLS granted (**most common miss**) | `sf data query -o EC-SB -q "SELECT Parent.Name, PermissionsRead, PermissionsEdit FROM FieldPermissions WHERE SobjectType='Case' AND Field='Case.<field>'"` → want your permset listed |
| 2b. Permset assigned | `sf data query -o EC-SB -q "SELECT Assignee.Name FROM PermissionSetAssignment WHERE PermissionSet.Name='Case_Assistance_Fields'"` |
| 3. On the page | `sf project retrieve start -o EC-SB -m "Layout:Case-Case Layout"` → grep the field |
| 3b. Right layout assigned | UI: Object Manager → Case → Page Layouts → **Page Layout Assignment** |
| 4. Picklist values (if applicable) | `sf project retrieve start -o EC-SB -m "RecordType:Case.Advisee_Case"` → grep the values |
| 5. End to end | Setup → Users → **Login As** → open a Case of that record type |

**Symptom → which switch is off:**

- *Field is nowhere, even for admins* → Switch 2 (FLS not granted) or the permset isn't assigned.
- *Visible in reports/API but not on the record page* → Switch 3 (not on the layout, or a different layout is assigned).
- *Picklist shows fewer values than expected* → Switch 4 (record type restricts them).
- *Works for you, not for a colleague* → assignment: the permission set isn't on them, or their profile + record type maps to a layout you didn't edit.
