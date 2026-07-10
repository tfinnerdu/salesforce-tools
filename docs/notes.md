Bypass Triggers — Salesforce Side
What it is: A Hierarchy Custom Setting in Salesforce. It's a special type of custom object where one instance can be set "for the org" (default), overridden per profile, or per user. Apex code checks it at the top of triggers to short-circuit execution.

Salesforce Setup (one-time, ~15 min):

Create the Custom Setting
Setup → Custom Settings → New
Label: Trigger Bypass Settings (or whatever you want)
Object Name: whatever API name you configure as SF_BYPASS_SETTING (e.g. Trigger_Bypass_Settings__c)
Setting Type: Hierarchy
Visibility: Public
Add a checkbox field
Field Label: Bypass Triggers
Field Name: Bypass_Triggers__c (matches SF_BYPASS_FIELD default)
Default: unchecked
Wire it into each trigger you want to guard:
trigger AccountTrigger on Account (before insert, before update) {
    if (Trigger_Bypass_Settings__c.getInstance().Bypass_Triggers__c) return;
    // ... normal trigger logic
}
That one-liner at the top exits the trigger immediately when the setting is true.
Grant API access — the connected app / integration user needs Customize Application or at minimum the ability to PATCH that Custom Setting object via REST.



Our Side (this app)
When you click Bypass Triggers toggle on the Settings page:

JS toggleBypass(true) → POST /settings/bypass-triggers → sets session['bypass_triggers'] = True
Any subsequent DML (merge duplicate, SOQL inline edit) reads that session flag and passes bypass=True into the service
The service calls dml_guard(sf, bypass=True) which:
Runs dml_throttle() (honors rate limit if set)
Calls sf.restful('sobjects/Trigger_Bypass_Settings__c/', method='PATCH', json={'Bypass_Triggers__c': True})
Yields (actual DML runs here)
In finally: calls the same REST PATCH with False to re-enable triggers
The important thing is the finally block — even if the DML throws an exception, triggers get re-enabled. The setting is never left in a "stuck bypass" state from this app.




Environment variables to set for real use:

SF_BYPASS_SETTING=Trigger_Bypass_Settings__c   # your Custom Setting API name
SF_BYPASS_FIELD=Bypass_Triggers__c             # the checkbox field API name

Leave SF_BYPASS_SETTING blank (the default) and the bypass feature is completely inactive — no REST calls are made, the toggle just changes a session flag with no effect.
