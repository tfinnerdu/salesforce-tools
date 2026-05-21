import logging

from sf_provider import get_sf

logger = logging.getLogger(__name__)


def scan_field(org: str, object_name: str, field_name: str) -> dict:
    sf = get_sf(org)
    field_upper = field_name.upper()
    field_lower = field_name.lower()

    # ── Validation Rules (Tooling API) ────────────────────────────────────────
    try:
        vr_soql = (
            f"SELECT Id, EntityDefinition.QualifiedApiName, ValidationName, "
            f"Description, ErrorMessage "
            f"FROM ValidationRule "
            f"WHERE Metadata LIKE '%{field_upper}%'"
        )
        vr_res = sf.restful('tooling/query/', params={'q': vr_soql})
        validation_rules = vr_res.get('records', [])
    except Exception as exc:
        logger.warning("ValidationRule tooling query failed: %s", exc)
        validation_rules = []

    # ── Active Flows (FlowDefinitionView — Data API) ──────────────────────────
    # Note: simple REST cannot inspect flow XML. We return active flows with a
    # note that manual review is required to confirm field references.
    # FlowDefinition (Tooling) has no ProcessType/Status columns —
    # FlowDefinitionView is the queryable view that does.
    try:
        flow_soql = (
            "SELECT ApiName, Label, ProcessType, Description "
            "FROM FlowDefinitionView WHERE IsActive = true"
        )
        flow_res = sf.query(flow_soql)
        flows_raw = flow_res.get('records', [])
    except Exception as exc:
        logger.warning("FlowDefinitionView query failed: %s", exc)
        flows_raw = []

    flows = [
        {**f, '_note': 'Manual review required — field references cannot be confirmed via REST API'}
        for f in flows_raw
    ]

    # ── Reports (Standard API) ────────────────────────────────────────────────
    try:
        report_soql = "SELECT Id, Name, FolderName, LastRunDate FROM Report LIMIT 200"
        report_res = sf.query_all(report_soql)
        reports_count = report_res.get('totalSize', len(report_res.get('records', [])))
    except Exception as exc:
        logger.warning("Report query failed: %s", exc)
        reports_count = 0

    vr_count = len(validation_rules)
    flow_count = len(flows)
    summary_parts = []
    if vr_count:
        summary_parts.append(f"{vr_count} validation rule(s) reference {field_name}")
    if flow_count:
        summary_parts.append(
            f"{flow_count} active flow(s) found — manual XML review needed to confirm {field_name} usage"
        )
    if reports_count:
        summary_parts.append(
            f"{reports_count} report(s) in org — manual check needed to confirm {field_name} columns"
        )
    summary = "; ".join(summary_parts) if summary_parts else f"No automated references found for {field_name}"

    return {
        'object_name': object_name,
        'field_name': field_name,
        'validation_rules': validation_rules,
        'flows': flows,
        'reports_count': reports_count,
        'summary': summary,
    }
