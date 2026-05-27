"""Tags — app-level labels for organizing saved artifacts.

v1 scope is interface-only: tags live in Postgres and attach to the app's own
saved entities (Scenarios first; saved queries / collections / snapshots can
be folded in later). No Salesforce writes — see ``services/tag_sync.py`` for
the future SF-field-sync scaffold.

Artifact kinds supported here are tracked in ``_ARTIFACT_TYPES``; adding a new
kind is a one-line change plus its UI wiring.
"""
import logging
from typing import Optional

from db import db_available, get_cursor

logger = logging.getLogger(__name__)

# Artifact types that may be tagged. Anything outside this set is rejected so
# typos in the UI can't silently create orphan tag links.
_ARTIFACT_TYPES = {'scenario', 'saved_query', 'collection', 'snapshot'}

# Doane palette swatches available for tag chips. Anything else falls back to
# 'slate' in the UI. Keeping the list closed avoids unbounded one-off colors.
_TAG_COLORS = {'slate', 'orange', 'green', 'amber', 'red', 'blue', 'purple', 'muted'}


# ── Tag CRUD ─────────────────────────────────────────────────────────────────

def list_tags() -> list:
    """All tags, alphabetical."""
    if not db_available():
        return []
    with get_cursor() as cur:
        cur.execute(
            'SELECT id, name, color, created_at FROM tags ORDER BY LOWER(name)'
        )
        return [dict(r) for r in cur.fetchall()]


def create_tag(name: str, color: str = 'slate') -> dict:
    name = (name or '').strip()
    if not name:
        raise ValueError('Tag name is required')
    if color not in _TAG_COLORS:
        color = 'slate'
    if not db_available():
        raise RuntimeError('Tags require a database connection.')
    with get_cursor() as cur:
        cur.execute(
            'INSERT INTO tags (name, color) VALUES (%s, %s) '
            'ON CONFLICT (name) DO UPDATE SET color = EXCLUDED.color '
            'RETURNING id, name, color, created_at',
            (name, color),
        )
        return dict(cur.fetchone())


def delete_tag(tag_id: int) -> bool:
    """Delete a tag. Cascade removes every artifact_tags row that points at it."""
    if not db_available():
        raise RuntimeError('Tags require a database connection.')
    with get_cursor() as cur:
        cur.execute('DELETE FROM tags WHERE id = %s', (tag_id,))
        return cur.rowcount > 0


# ── Attach / detach ──────────────────────────────────────────────────────────

def _check_artifact_type(artifact_type: str) -> None:
    if artifact_type not in _ARTIFACT_TYPES:
        raise ValueError(
            f'Unknown artifact_type {artifact_type!r} — must be one of '
            f'{sorted(_ARTIFACT_TYPES)}'
        )


def attach_tag(tag_id: int, artifact_type: str, artifact_id: int) -> bool:
    """Attach a tag to an artifact. Idempotent — ON CONFLICT DO NOTHING."""
    _check_artifact_type(artifact_type)
    if not db_available():
        raise RuntimeError('Tags require a database connection.')
    with get_cursor() as cur:
        cur.execute(
            'INSERT INTO artifact_tags (tag_id, artifact_type, artifact_id) '
            'VALUES (%s, %s, %s) '
            'ON CONFLICT (tag_id, artifact_type, artifact_id) DO NOTHING',
            (tag_id, artifact_type, artifact_id),
        )
    return True


def detach_tag(tag_id: int, artifact_type: str, artifact_id: int) -> bool:
    _check_artifact_type(artifact_type)
    if not db_available():
        raise RuntimeError('Tags require a database connection.')
    with get_cursor() as cur:
        cur.execute(
            'DELETE FROM artifact_tags '
            'WHERE tag_id = %s AND artifact_type = %s AND artifact_id = %s',
            (tag_id, artifact_type, artifact_id),
        )
        return cur.rowcount > 0


# ── Lookups ──────────────────────────────────────────────────────────────────

def get_tags_for(artifact_type: str, artifact_id: int) -> list:
    """Return all tags attached to one artifact."""
    _check_artifact_type(artifact_type)
    if not db_available():
        return []
    with get_cursor() as cur:
        cur.execute(
            'SELECT t.id, t.name, t.color '
            'FROM tags t JOIN artifact_tags a ON a.tag_id = t.id '
            'WHERE a.artifact_type = %s AND a.artifact_id = %s '
            'ORDER BY LOWER(t.name)',
            (artifact_type, artifact_id),
        )
        return [dict(r) for r in cur.fetchall()]


def get_tag_map(artifact_type: str, artifact_ids: list) -> dict:
    """Return {artifact_id: [tag, ...]} for a batch of artifacts.

    Lets the index views render tag chips without an N+1 query.
    """
    _check_artifact_type(artifact_type)
    if not artifact_ids or not db_available():
        return {}
    with get_cursor() as cur:
        cur.execute(
            'SELECT a.artifact_id, t.id, t.name, t.color '
            'FROM artifact_tags a JOIN tags t ON t.id = a.tag_id '
            'WHERE a.artifact_type = %s AND a.artifact_id = ANY(%s) '
            'ORDER BY LOWER(t.name)',
            (artifact_type, list(artifact_ids)),
        )
        out: dict = {}
        for row in cur.fetchall():
            out.setdefault(row['artifact_id'], []).append({
                'id': row['id'], 'name': row['name'], 'color': row['color'],
            })
    return out


def find_artifacts_by_tag(artifact_type: str, tag_id: int) -> list:
    """Return artifact IDs of the given kind tagged with this tag."""
    _check_artifact_type(artifact_type)
    if not db_available():
        return []
    with get_cursor() as cur:
        cur.execute(
            'SELECT artifact_id FROM artifact_tags '
            'WHERE artifact_type = %s AND tag_id = %s',
            (artifact_type, tag_id),
        )
        return [row['artifact_id'] for row in cur.fetchall()]
