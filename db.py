import logging
from contextlib import contextmanager
from typing import Generator, Optional

import psycopg2
import psycopg2.extras

from config import Config

logger = logging.getLogger(__name__)


def get_connection() -> psycopg2.extensions.connection:
    """Open and return a raw psycopg2 connection."""
    return psycopg2.connect(Config.DATABASE_URL)


@contextmanager
def get_cursor() -> Generator[psycopg2.extras.RealDictCursor, None, None]:
    """Context manager that yields a RealDictCursor, commits on success, rolls back on error."""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Create required tables if they do not already exist."""
    ddl = """
    CREATE TABLE IF NOT EXISTS readiness_runs (
        id          SERIAL PRIMARY KEY,
        org         VARCHAR(50),
        run_at      TIMESTAMP DEFAULT NOW(),
        results     JSONB,
        overall_pct FLOAT
    );

    CREATE TABLE IF NOT EXISTS saved_queries (
        id          SERIAL PRIMARY KEY,
        name        VARCHAR(200),
        query       TEXT,
        created_by  VARCHAR(100),
        created_at  TIMESTAMP DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS query_history (
        id          SERIAL PRIMARY KEY,
        user_key    VARCHAR(100),
        query       TEXT,
        org         VARCHAR(50),
        ran_at      TIMESTAMP DEFAULT NOW(),
        row_count   INTEGER
    );

    CREATE TABLE IF NOT EXISTS api_collections (
        id              SERIAL PRIMARY KEY,
        name            VARCHAR(200),
        collection_json JSONB,
        created_at      TIMESTAMP DEFAULT NOW(),
        updated_at      TIMESTAMP DEFAULT NOW()
    );

    -- Scenarios: saved multi-step Data Ops pipelines (delete / modify /
    -- reassign / bulk_update / tune chained together).
    CREATE TABLE IF NOT EXISTS scenarios (
        id           SERIAL PRIMARY KEY,
        name         VARCHAR(200) NOT NULL,
        description  TEXT,
        org          VARCHAR(50),
        steps_json   JSONB NOT NULL DEFAULT '[]'::jsonb,
        created_by   VARCHAR(100),
        created_at   TIMESTAMP DEFAULT NOW(),
        updated_at   TIMESTAMP DEFAULT NOW()
    );

    -- One row per scenario run; step_results captures per-step outcomes.
    CREATE TABLE IF NOT EXISTS scenario_runs (
        id           SERIAL PRIMARY KEY,
        scenario_id  INTEGER REFERENCES scenarios(id) ON DELETE CASCADE,
        org          VARCHAR(50),
        started_at   TIMESTAMP DEFAULT NOW(),
        finished_at  TIMESTAMP,
        status       VARCHAR(20),
        step_results JSONB DEFAULT '[]'::jsonb
    );

    -- App-level tags for organizing saved artifacts (scenarios first; saved
    -- queries / collections / snapshots can be folded in later). Many-to-many
    -- via artifact_tags so one tag can apply to many artifacts.
    CREATE TABLE IF NOT EXISTS tags (
        id          SERIAL PRIMARY KEY,
        name        VARCHAR(100) NOT NULL UNIQUE,
        color       VARCHAR(20) DEFAULT 'slate',
        created_at  TIMESTAMP DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS artifact_tags (
        id            SERIAL PRIMARY KEY,
        tag_id        INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
        artifact_type VARCHAR(50) NOT NULL,  -- 'scenario' | 'saved_query' | 'collection' | 'snapshot'
        artifact_id   INTEGER NOT NULL,
        created_at    TIMESTAMP DEFAULT NOW(),
        UNIQUE (tag_id, artifact_type, artifact_id)
    );
    CREATE INDEX IF NOT EXISTS idx_artifact_tags_lookup
        ON artifact_tags (artifact_type, artifact_id);

    -- ── Source → Salesforce Key Maps ──────────────────────────────────────
    -- A key_map is a reusable spec for transforming source rows (from a SQL
    -- result or a JSON document) into Salesforce records of one SObject.
    -- PTATs are the first consumer but the model is deliberately generic.
    --
    -- Shape:
    --   key_maps                — one row per saved map (Source → target SObject).
    --   key_map_fk_lookups      — for each FK on the target, how to resolve it
    --                             from a source column (SObject + field to match
    --                             SIS_ID__c / Ethos_Guid__c / etc.).
    --   key_map_families        — a named bundle of variants. Routing rule
    --                             decides which family applies per source row.
    --   key_map_variants        — one row per variant; `overlay_json` is the
    --                             set of target-field values that variant
    --                             contributes on top of the resolved FK base
    --                             (e.g. {APTV_Id: "0PT...", Pre_Id: "0PR..."}).
    --   key_map_runs            — preview-only run history with the expanded
    --                             output rows + per-row resolution notes.
    CREATE TABLE IF NOT EXISTS key_maps (
        id              SERIAL PRIMARY KEY,
        name            VARCHAR(200) NOT NULL UNIQUE,
        description     TEXT,
        target_sobject  VARCHAR(100) NOT NULL,
        created_by      VARCHAR(100),
        created_at      TIMESTAMP DEFAULT NOW(),
        updated_at      TIMESTAMP DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS key_map_fk_lookups (
        id              SERIAL PRIMARY KEY,
        key_map_id      INTEGER NOT NULL REFERENCES key_maps(id) ON DELETE CASCADE,
        source_column   VARCHAR(100) NOT NULL,
        target_field    VARCHAR(100) NOT NULL,         -- e.g. LearningProgramId
        lookup_sobject  VARCHAR(100) NOT NULL,         -- e.g. LearningProgram
        lookup_field    VARCHAR(100) NOT NULL DEFAULT 'SIS_ID__c',
        position        INTEGER NOT NULL DEFAULT 0
    );
    CREATE INDEX IF NOT EXISTS idx_key_map_fk_lookups_key_map
        ON key_map_fk_lookups (key_map_id);

    CREATE TABLE IF NOT EXISTS key_map_families (
        id              SERIAL PRIMARY KEY,
        key_map_id      INTEGER NOT NULL REFERENCES key_maps(id) ON DELETE CASCADE,
        name            VARCHAR(200) NOT NULL,
        -- routing_json describes when this family applies to a source row.
        -- Shape: {"match": [{"source_column": "ACPG_ACAD_LEVEL", "equals": "UG"}, ...]}
        -- Empty/null = default family (used when no other family matches).
        routing_json    JSONB DEFAULT '{}'::jsonb,
        position        INTEGER NOT NULL DEFAULT 0,
        UNIQUE (key_map_id, name)
    );
    CREATE INDEX IF NOT EXISTS idx_key_map_families_key_map
        ON key_map_families (key_map_id);

    CREATE TABLE IF NOT EXISTS key_map_variants (
        id              SERIAL PRIMARY KEY,
        family_id       INTEGER NOT NULL REFERENCES key_map_families(id) ON DELETE CASCADE,
        name            VARCHAR(200) NOT NULL,
        -- overlay_json is {target_field: literal_value, ...} applied on top of
        -- the resolved FK base row. E.g. for a PTAT Readmit variant:
        --   {"ActionPlanTemplateVersionId": "0PR...",
        --    "Pre_decision_Requirements_Action_Plan__c": "0PR...",
        --    "Post_admit_Requirements_Action_Plan__c":  "0PR..."}
        overlay_json    JSONB NOT NULL DEFAULT '{}'::jsonb,
        -- applies_when is an optional per-variant filter (same shape as
        -- routing_json.match). Empty = blanket — applies to every source row
        -- in the family. Reserved for future selective fanout.
        applies_when    JSONB DEFAULT '{}'::jsonb,
        position        INTEGER NOT NULL DEFAULT 0,
        UNIQUE (family_id, name)
    );
    CREATE INDEX IF NOT EXISTS idx_key_map_variants_family
        ON key_map_variants (family_id);

    CREATE TABLE IF NOT EXISTS key_map_runs (
        id              SERIAL PRIMARY KEY,
        key_map_id      INTEGER REFERENCES key_maps(id) ON DELETE CASCADE,
        org             VARCHAR(50),
        started_at      TIMESTAMP DEFAULT NOW(),
        finished_at     TIMESTAMP,
        status          VARCHAR(20),                   -- pending | success | partial | failed
        source_count    INTEGER DEFAULT 0,
        output_count    INTEGER DEFAULT 0,
        unresolved_fks  JSONB DEFAULT '[]'::jsonb,     -- list of {row_idx, source_column, value}
        output_rows     JSONB DEFAULT '[]'::jsonb,     -- the expanded preview rows
        summary         JSONB DEFAULT '{}'::jsonb      -- counts, family/variant breakdown
    );
    CREATE INDEX IF NOT EXISTS idx_key_map_runs_key_map
        ON key_map_runs (key_map_id);
    """
    try:
        with get_cursor() as cur:
            cur.execute(ddl)
        logger.info("Database tables initialised.")
    except Exception as exc:
        logger.error("init_db failed: %s", exc)
        raise


def db_available() -> bool:
    """Return True if a DB connection can be established, False otherwise."""
    try:
        conn = get_connection()
        conn.close()
        return True
    except Exception:
        return False
