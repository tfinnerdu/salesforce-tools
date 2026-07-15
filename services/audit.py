"""Shared audit-event emission — the canonical AuditEvent shape.

Every state-changing operation, and every read of sensitive security data
(the CLI tab's FLS clone and access-mirror reads), should emit one event via
``emit()``. The sink is dual and independent: a structured JSON log line to
stdout (always — zero external dependency) and a best-effort insert into the
``audit_events`` table when the DB is reachable. A DB failure never breaks the
operation being audited — it only drops the persisted copy, and a warning
notes that on its own.

``actor`` resolution: current_actor() reads Flask session['user'] when
present. Nothing in the app populates that key yet — there is no login layer,
so every event today resolves to 'system'. That is a known, real gap (see
CLAUDE.md); current_actor() is the single place that changes once real
identity capture lands, so every call site upgrades for free.
"""
import json
import logging
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone

from db import get_cursor

logger = logging.getLogger('audit')


@dataclass(frozen=True)
class AuditEvent:
    action: str
    actor: str
    resource_type: str
    resource_id: str
    outcome: str  # "success" | "failure" | "partial"
    detail: dict = field(default_factory=dict)
    correlation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    occurred_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat())


def current_actor() -> str:
    """The acting identity for an audit event.

    No auth layer exists yet, so this always resolves to 'system' today.
    """
    try:
        from flask import session
        return session.get('user') or 'system'
    except RuntimeError:
        return 'system'  # outside an app/request context (scheduler, tests)


def emit(action: str, resource_type: str, resource_id: str, outcome: str,
        detail: dict = None, actor: str = None, correlation_id: str = None) -> AuditEvent:
    """Build and emit one AuditEvent. Never raises — a logging/DB failure must
    never break the operation being audited."""
    kwargs = dict(
        action=action,
        actor=actor or current_actor(),
        resource_type=resource_type,
        resource_id=resource_id or '',
        outcome=outcome,
        detail=detail or {},
    )
    if correlation_id:
        kwargs['correlation_id'] = correlation_id
    event = AuditEvent(**kwargs)

    try:
        logger.info(json.dumps(asdict(event)))
    except Exception:
        logger.warning('audit event failed to serialize for logging', exc_info=True)

    try:
        with get_cursor() as cur:
            cur.execute(
                'INSERT INTO audit_events '
                '(action, actor, resource_type, resource_id, outcome, detail, '
                ' correlation_id, occurred_at) '
                'VALUES (%s, %s, %s, %s, %s, %s, %s, %s)',
                (event.action, event.actor, event.resource_type, event.resource_id,
                 event.outcome, json.dumps(event.detail), event.correlation_id,
                 event.occurred_at),
            )
    except Exception:
        logger.warning('audit_events insert failed (event still logged to stdout above)',
                       exc_info=True)

    return event
