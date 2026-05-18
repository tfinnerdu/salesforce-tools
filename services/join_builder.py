import logging
from typing import Optional

from config import Config
from sf_provider import get_sf

logger = logging.getLogger(__name__)


def build_query(
    sql_table: str,
    sql_fields: list,
    sf_object: str,
    sf_fields: list,
    join_mapping: dict,
) -> dict:
    """Build OPENQUERY T-SQL, SOQL, and plain SQL strings for a SF-to-SQL join."""
    join_field_sql = join_mapping.get('sql_field', '')
    join_field_sf = join_mapping.get('sf_field', '')

    sql_fields_csv = ', '.join(f's.{f}' for f in sql_fields)
    sf_fields_csv = ', '.join(sf_fields)
    sf_fields_csv_bare = ', '.join(sf_fields)

    soql = (
        f"SELECT {sf_fields_csv_bare} FROM {sf_object} WHERE IsPersonAccount = true"
    )

    openquery_sql = (
        f"SELECT {sql_fields_csv},\n"
        f"       {', '.join(f'sf.{f}' for f in sf_fields)}\n"
        f"FROM dbo.{sql_table} s\n"
        f"JOIN OPENQUERY(SALESFORCE, '\n"
        f"    SELECT {sf_fields_csv_bare}\n"
        f"    FROM {sf_object}\n"
        f"    WHERE IsPersonAccount = true\n"
        f"') sf ON sf.{join_field_sf} = s.{join_field_sql}"
    )

    sql_only = (
        f"SELECT {', '.join(sql_fields)}\n"
        f"FROM dbo.{sql_table}\n"
        f"WHERE {join_field_sql} IS NOT NULL"
    )

    return {
        'openquery_sql': openquery_sql,
        'soql': soql,
        'sql_only': sql_only,
        'join_field_sql': join_field_sql,
        'join_field_sf': join_field_sf,
    }


def run_join(org: str, sql_query: str, soql_query: str, join_mapping: dict) -> dict:
    """Python fallback join: fetch SF records, attempt SQL Server fetch, merge in Python."""
    sf = get_sf(org)
    sf_result = sf.query_all(soql_query)
    sf_records = [
        {k: v for k, v in r.items() if k != 'attributes'}
        for r in sf_result.get('records', [])
    ]
    sf_count = len(sf_records)

    conn_str = Config.SQLSERVER_CONN
    if not conn_str:
        return {
            'success': False,
            'error': 'SQL Server not configured',
            'sf_records_fetched': sf_count,
            'hint': 'Configure SQLSERVER_CONN in .env',
        }

    try:
        import pyodbc  # type: ignore
        conn = pyodbc.connect(conn_str, timeout=10)
        cursor = conn.cursor()
        cursor.execute(sql_query)
        columns = [col[0] for col in cursor.description]
        sql_rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        conn.close()
        sql_count = len(sql_rows)
    except Exception as exc:
        logger.error("run_join: SQL Server query failed: %s", exc)
        return {
            'success': False,
            'error': f'SQL Server query failed: {exc}',
            'sf_records_fetched': sf_count,
            'hint': 'Check SQLSERVER_CONN and SQL query syntax',
        }

    # Merge on join key
    join_sf = join_mapping.get('sf_field', '')
    join_sql = join_mapping.get('sql_field', '')

    sf_index = {str(r.get(join_sf, '')): r for r in sf_records if r.get(join_sf)}
    joined = []
    for sql_row in sql_rows:
        key = str(sql_row.get(join_sql, ''))
        sf_row = sf_index.get(key, {})
        merged = {**sql_row, **{f'sf_{k}': v for k, v in sf_row.items()}}
        joined.append(merged)

    return {
        'success': True,
        'rows': joined,
        'sf_count': sf_count,
        'sql_count': sql_count,
        'joined_count': len(joined),
    }
