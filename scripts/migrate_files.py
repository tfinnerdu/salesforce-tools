#!/usr/bin/env python3
"""Org-to-org Salesforce file (ContentVersion) migrator — CLI wrapper.

Thin command-line front end over ``services.file_migration`` (the shared engine,
also used by the Data Ops "File Migration" tab). Streams Files or legacy
Attachments from a source org to a target org **without staging them locally**
and relinks each item to the migrated parent record — from a direct old→new
crosswalk CSV (``--id-map``), by resolving an external-Id field (``--parent`` +
``--ext-id``), or keeping the same parent for an in-place conversion
(``--remap identity``). The read (``--mode``) and write (``--dest``) sides are
independent, so an Attachment can land as a File and vice-versa.

Dry-run by default; writes only with ``--commit``. See ``scripts/README.md``.

Examples
--------
    # Crosswalk: point straight at your migration spreadsheet
    python scripts/migrate_files.py --source eda --target prod \
        --id-map accommodations.csv \
        --map-old-col Accommodation__c --map-new-col NEW_Accommodation__c

    # External-Id: all files on Person Accounts, matched by SIS_ID__c
    python scripts/migrate_files.py --source eda --target prod \
        --parent Account --ext-id SIS_ID__c --by filter --where "IsPersonAccount = true"

    # In-place: convert legacy Attachments to modern Files within one org
    python scripts/migrate_files.py --source prod --target prod \
        --remap identity --mode attachments --dest files \
        --parent Accommodation__c --by filter --where "Id != null"

    # Add --commit to actually write to the target org
    python scripts/migrate_files.py ... --commit
"""
import argparse
import csv
import logging
import os
import sys

# Allow running from the repo root: make the app package importable.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))

from sf_provider import get_sf  # noqa: E402
from services.file_migration import (  # noqa: E402
    DEFAULT_MAX_MB, build_plan, execute, report_rows, summarize)

# Re-export the engine helpers so existing imports (and tests) keep working.
from services.file_migration import (  # noqa: E402,F401
    chunked, compose_parent_map, load_id_map, soql_in_list)

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger('migrate_files')


def write_report(path, plan):
    """Write the per-file plan to a CSV report."""
    rows = report_rows(plan)
    with open(path, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=['source_cv_id', 'title', 'size_bytes',
                                           'resolved_parents', 'unresolved_parents',
                                           'oversize', 'action'])
        w.writeheader()
        w.writerows(rows)
    logger.info('Report written: %s', path)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--source', required=True, help='source org name (e.g. eda)')
    ap.add_argument('--target', required=True, help='target org name (e.g. prod)')
    ap.add_argument('--parent', default='', help='parent SObject (e.g. Account, Case) — '
                    'required unless --id-map is used')
    ap.add_argument('--ext-id', default='', dest='ext_id',
                    help='external-Id field on the parent to remap old→new (e.g. SIS_ID__c) — '
                    'required unless --id-map is used')
    ap.add_argument('--by', choices=['filter', 'list'], default='filter',
                    help='scope mode (external-Id path): SOQL filter, or a file of Ids/ext-Ids')
    ap.add_argument('--where', default='', help="SOQL WHERE for --by filter")
    ap.add_argument('--ids-file', default='', help='file of parent Ids/ext-Id values for --by list')
    ap.add_argument('--id-map', default='', help='crosswalk CSV of old→new parent Ids; when set, '
                    'it drives both scope and remap (no external-Id lookups). Point it straight '
                    'at your migration spreadsheet.')
    ap.add_argument('--map-old-col', default='old_id', help='crosswalk column with the source Id')
    ap.add_argument('--map-new-col', default='new_id', help='crosswalk column with the target Id')
    ap.add_argument('--mode', choices=['files', 'attachments'], default='files',
                    help="what to READ: 'files' = modern Files (ContentVersion); "
                    "'attachments' = legacy Attachment")
    ap.add_argument('--dest', choices=['files', 'attachments'], default='',
                    help="what to WRITE (default: same as --mode). Set to convert one to the "
                    "other, e.g. --mode attachments --dest files")
    ap.add_argument('--remap', choices=['crosswalk', 'ext_id', 'identity'], default='',
                    help="how parents map old→new: 'crosswalk' (needs --id-map), 'ext_id' "
                    "(needs --parent/--ext-id), or 'identity' (same parent — in-place "
                    "conversion). Default: infer crosswalk if --id-map else ext_id.")
    ap.add_argument('--max-mb', type=int, default=DEFAULT_MAX_MB,
                    help=f'flag files larger than this many MB (default {DEFAULT_MAX_MB})')
    ap.add_argument('--report', default='file_migration_report.csv', help='CSV report path')
    ap.add_argument('--commit', action='store_true',
                    help='actually write to the target org (default is dry-run)')
    cfg = ap.parse_args(argv)

    remap = cfg.remap or ('crosswalk' if cfg.id_map else 'ext_id')
    if remap == 'crosswalk':
        if not cfg.id_map:
            ap.error('crosswalk remap requires --id-map')
        if not os.path.exists(cfg.id_map):
            ap.error(f'--id-map file not found: {cfg.id_map}')
    elif remap == 'ext_id':
        if not cfg.parent or not cfg.ext_id:
            ap.error('ext_id remap requires --parent and --ext-id')
        if cfg.by == 'list' and not cfg.ids_file:
            ap.error('--by list requires --ids-file')
    else:  # identity
        if cfg.by == 'filter' and not cfg.parent:
            ap.error('identity remap with --by filter requires --parent')
        if cfg.by == 'list' and not cfg.ids_file:
            ap.error('--by list requires --ids-file')

    source_sf = get_sf(cfg.source)
    target_sf = get_sf(cfg.target)

    desc = {'crosswalk': f'crosswalk {cfg.id_map}',
            'ext_id': f'parent {cfg.parent} by ext-Id {cfg.ext_id}',
            'identity': f'same parent ({cfg.parent or "by list"})'}[remap]
    logger.info('Planning migration: %s → %s  (%s; read %s, write %s)',
                cfg.source, cfg.target, desc, cfg.mode, cfg.dest or cfg.mode)
    plan, resolved, unresolved, stats = build_plan(source_sf, target_sf, cfg)
    write_report(cfg.report, plan)

    s = summarize(plan, unresolved, cfg.max_mb)
    logger.info('\n=== PLAN SUMMARY ===')
    logger.info('  parents in scope: %d,  files found: %d',
                stats['parents_in_scope'], stats['files_found'])
    logger.info('  migrate      : %d file(s), %.1f MB', s['migrate'], s['migrate_mb'])
    logger.info('  skip (no parent resolved): %d', s['no_parent'])
    logger.info('  skip (too large > %d MB) : %d', cfg.max_mb, s['oversize'])
    logger.info('  unresolved parents       : %d', s['unresolved_parents'])

    if not cfg.commit:
        logger.info('\nDRY RUN — nothing was written. Re-run with --commit to migrate.')
        return 0

    logger.info('\nCOMMIT — writing to %s …', cfg.target)
    counts = execute(source_sf, target_sf, plan, cfg.mode, cfg.dest or cfg.mode)
    logger.info('Done. created=%(created)d reused=%(reused)d linked=%(linked)d skipped=%(skipped)d',
                counts)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
