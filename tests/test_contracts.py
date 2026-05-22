"""
Contract tests — pin "what we know should be true".

The mock-data layer (MockSalesforce / MockConductorClient) is gone. These tests
now drive each service through `unittest.mock` doubles and pin the response
SHAPE and BUSINESS LOGIC: status thresholds, sort order, check keys, response
keys, error-code categorization. They do NOT pin fabricated record counts —
those belonged to the deleted mock layer.
"""
from collections import Counter
from unittest.mock import MagicMock, patch

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Salesforce / Conductor doubles
# ─────────────────────────────────────────────────────────────────────────────

def _count_sf(count_map=None, default=0):
    """SF double whose query/query_all return totalSize from count_map.

    count_map: {substring_in_soql: totalSize}. The first substring found in the
    SOQL wins; otherwise `default` is used. Records are always [].
    """
    count_map = count_map or {}

    def _result_for(soql):
        size = default
        for needle, val in count_map.items():
            if needle in soql:
                size = val
                break
        return {'records': [], 'totalSize': size, 'done': True}

    sf = MagicMock()
    sf.query.side_effect = _result_for
    sf.query_all.side_effect = _result_for
    return sf


def _records_sf(records):
    """SF double whose query/query_all return the given records list."""
    sf = MagicMock()
    payload = {'records': records, 'totalSize': len(records), 'done': True}
    sf.query.return_value = payload
    sf.query_all.return_value = payload
    return sf


def _conductor(workflows=None, batch_status=None):
    """Conductor double for batch-status and workflow-search."""
    c = MagicMock()
    c.search_workflows.return_value = workflows if workflows is not None else []
    c.get_batch_status.return_value = batch_status or {
        'completed': 0, 'failed': 0, 'running': 0, 'timed_out': 0,
        'queued': 0, 'total': 0,
    }
    return c


def _failure(code: str, sis_id: str = '', wf_id: str = 'wf-x'):
    """Build a Conductor FAILED-workflow dict whose reason carries an SF error code."""
    import json
    return {
        'workflowId': wf_id,
        'status': 'FAILED',
        'reasonForIncompletion': f'com.netflix.conductor.common.run.Workflow: {code}: detail',
        'input': json.dumps({'sisId': sis_id}),
    }


# ═════════════════════════════════════════════════════════════════════════════
# SECTION 1 — Readiness check response shapes
#
# The deleted mock layer fabricated exact counts (4312 etc.); those assertions
# are obsolete. What remains a contract is the SHAPE each check returns and the
# arithmetic relating total/covered/pct.
# ═════════════════════════════════════════════════════════════════════════════

class TestReadinessCheckShapes:
    """Each check returns the documented keys and internally-consistent numbers."""

    def test_sis_id_coverage_shape(self):
        from services.readiness_validator import check_sis_id_coverage
        sf = _count_sf({'SIS_ID__c != null': 75}, default=100)
        r = check_sis_id_coverage(sf)
        assert set(r) >= {'name', 'check_key', 'total', 'covered', 'pct',
                          'status', 'detail'}
        assert r['check_key'] == 'sis_id_coverage'
        assert r['total'] == 100
        assert r['covered'] == 75
        assert r['pct'] == 75.0

    def test_ethos_guid_coverage_shape(self):
        from services.readiness_validator import check_ethos_guid_coverage
        sf = _count_sf({'Ethos_Guid__c != null': 91}, default=100)
        r = check_ethos_guid_coverage(sf)
        assert r['check_key'] == 'ethos_guid_coverage'
        assert r['covered'] == 91
        assert r['pct'] == 91.0

    def test_contactpoint_parents_shape(self):
        from services.readiness_validator import check_contactpoint_parents
        # Every COUNT returns 10 → 30 total, 30 broken → 0 covered.
        sf = _count_sf(default=10)
        r = check_contactpoint_parents(sf)
        assert r['check_key'] == 'contactpoint_parents'
        assert r['total'] == 30
        assert r['covered'] == 0

    def test_required_fields_shape(self):
        from services.readiness_validator import check_required_fields
        sf = _count_sf({'FirstName = null': 44}, default=1000)
        r = check_required_fields(sf)
        assert r['check_key'] == 'required_fields'
        assert r['total'] == 1000
        assert r['covered'] == 1000 - 44

    def test_duplicates_shape_no_dupes(self):
        from services.readiness_validator import check_duplicates
        # All unique SIS IDs → zero duplicate groups → green.
        sf = _records_sf([
            {'Id': '001', 'SIS_ID__c': 'A'},
            {'Id': '002', 'SIS_ID__c': 'B'},
        ])
        r = check_duplicates(sf)
        assert r['check_key'] == 'duplicates'
        assert r['status'] == 'green'

    def test_duplicates_detects_duplicate_group(self):
        from services.readiness_validator import check_duplicates
        sf = _records_sf([
            {'Id': '001', 'SIS_ID__c': 'DUP'},
            {'Id': '002', 'SIS_ID__c': 'DUP'},
        ])
        r = check_duplicates(sf)
        assert r['status'] == 'amber'  # 1 duplicate group → _issue_status(1)

    def test_individual_links_shape(self):
        from services.readiness_validator import check_individual_links
        sf = _count_sf(default=10)
        r = check_individual_links(sf)
        assert r['check_key'] == 'individual_links'
        assert r['total'] == 30


class TestRunFullReadinessContract:
    """run_full_readiness_check returns exactly six checks with stable keys."""

    def _run(self, sf):
        from services.readiness_validator import run_full_readiness_check
        with patch('services.readiness_validator.get_sf', return_value=sf):
            return run_full_readiness_check('dev')

    def test_has_exactly_six_checks(self):
        result = self._run(_count_sf(default=100))
        assert len(result['checks']) == 6

    def test_check_keys_are_stable(self):
        result = self._run(_count_sf(default=100))
        keys = {c['check_key'] for c in result['checks']}
        assert keys == {
            'sis_id_coverage',
            'ethos_guid_coverage',
            'contactpoint_parents',
            'required_fields',
            'duplicates',
            'individual_links',
        }

    def test_overall_status_red_when_a_check_is_red(self):
        # default=0 → 0% coverage on the percentage checks → red.
        result = self._run(_count_sf(default=0))
        assert result['overall_status'] == 'red'

    def test_overall_status_green_when_all_perfect(self):
        # 100/100 covered everywhere, zero broken CP, no duplicate records.
        from services.readiness_validator import run_full_readiness_check

        def _result(soql):
            # A "broken" count: 0 missing parents/individuals/required fields.
            if ('= null' in soql
                    and ('ParentId' in soql or 'IndividualId' in soql
                         or 'FirstName' in soql)):
                size = 0
            else:
                size = 100  # totals and "!= null" covered counts
            return {'records': [], 'totalSize': size, 'done': True}

        sf = MagicMock()
        sf.query.side_effect = _result
        sf.query_all.side_effect = lambda soql: {
            'records': [], 'totalSize': 0, 'done': True}
        with patch('services.readiness_validator.get_sf', return_value=sf):
            result = run_full_readiness_check('dev')
        assert result['overall_status'] == 'green'

    def test_run_at_present(self):
        result = self._run(_count_sf(default=100))
        assert 'run_at' in result


# ═════════════════════════════════════════════════════════════════════════════
# SECTION 2 — Status threshold boundaries  (pure functions — unchanged)
# ═════════════════════════════════════════════════════════════════════════════

class TestStatusThresholdBoundaries:
    """Exact boundary conditions for _status, _issue_status, _field_status."""

    def test_status_exactly_100_is_green(self):
        from services.readiness_validator import _status
        assert _status(100.0) == 'green'

    def test_status_above_100_is_green(self):
        from services.readiness_validator import _status
        assert _status(100.1) == 'green'

    def test_status_exactly_90_is_amber(self):
        from services.readiness_validator import _status
        assert _status(90.0) == 'amber'

    def test_status_just_below_100_is_amber(self):
        from services.readiness_validator import _status
        assert _status(99.99) == 'amber'

    def test_status_just_below_90_is_red(self):
        from services.readiness_validator import _status
        assert _status(89.99) == 'red'

    def test_status_zero_is_red(self):
        from services.readiness_validator import _status
        assert _status(0.0) == 'red'

    def test_issue_status_zero_is_green(self):
        from services.readiness_validator import _issue_status
        assert _issue_status(0) == 'green'

    def test_issue_status_1_is_amber(self):
        from services.readiness_validator import _issue_status
        assert _issue_status(1) == 'amber'

    def test_issue_status_exactly_25_is_amber(self):
        from services.readiness_validator import _issue_status
        assert _issue_status(25) == 'amber'

    def test_issue_status_26_is_red(self):
        from services.readiness_validator import _issue_status
        assert _issue_status(26) == 'red'

    def test_field_status_matches_readiness_status_thresholds(self):
        """external_id_coverage._field_status must use the same 90/100 cutoffs."""
        from services.external_id_coverage import _field_status
        assert _field_status(100.0) == 'green'
        assert _field_status(90.0) == 'amber'
        assert _field_status(99.99) == 'amber'
        assert _field_status(89.99) == 'red'


# ═════════════════════════════════════════════════════════════════════════════
# SECTION 3 — Readiness status logic against mocked SF data
#
# Pins that each check maps its coverage percentage to the right status colour.
# ═════════════════════════════════════════════════════════════════════════════

class TestReadinessStatusLogic:

    def test_sis_id_below_90_is_red(self):
        from services.readiness_validator import check_sis_id_coverage
        sf = _count_sf({'SIS_ID__c != null': 71}, default=100)
        assert check_sis_id_coverage(sf)['status'] == 'red'

    def test_ethos_guid_between_90_and_100_is_amber(self):
        from services.readiness_validator import check_ethos_guid_coverage
        sf = _count_sf({'Ethos_Guid__c != null': 91}, default=100)
        assert check_ethos_guid_coverage(sf)['status'] == 'amber'

    def test_ethos_guid_full_coverage_is_green(self):
        from services.readiness_validator import check_ethos_guid_coverage
        sf = _count_sf(default=100)  # covered == total
        assert check_ethos_guid_coverage(sf)['status'] == 'green'

    def test_contactpoint_parents_all_broken_is_red(self):
        from services.readiness_validator import check_contactpoint_parents
        # broken == total → 0% covered → red.
        sf = _count_sf(default=10)
        assert check_contactpoint_parents(sf)['status'] == 'red'

    def test_required_fields_few_missing_is_amber(self):
        from services.readiness_validator import check_required_fields
        # 44 missing of 4312 ≈ 98.98% → amber.
        sf = _count_sf({'FirstName = null': 44}, default=4312)
        assert check_required_fields(sf)['status'] == 'amber'


# ═════════════════════════════════════════════════════════════════════════════
# SECTION 4 — Conductor batch-status contract
# ═════════════════════════════════════════════════════════════════════════════

class TestBatchStatusContract:
    """batch_tracker.get_batch_status enriches the Conductor status dict."""

    def test_batch_status_adds_progress_pct(self):
        from services.batch_tracker import get_batch_status
        c = _conductor(batch_status={
            'completed': 50, 'failed': 10, 'running': 5, 'timed_out': 0,
            'queued': 35, 'total': 100,
        })
        with patch('services.batch_tracker.get_conductor_client', return_value=c):
            status = get_batch_status('SFMigrationWorkflow')
        # progress = (completed + failed) / total
        assert status['progress_pct'] == 60.0

    def test_batch_status_rate_and_eta_are_null(self):
        """Conductor carries no throughput data — rate/eta stay null, not fabricated."""
        from services.batch_tracker import get_batch_status
        c = _conductor(batch_status={
            'completed': 1, 'failed': 0, 'running': 0, 'timed_out': 0,
            'queued': 0, 'total': 1,
        })
        with patch('services.batch_tracker.get_conductor_client', return_value=c):
            status = get_batch_status('SFMigrationWorkflow')
        assert status['rate_per_min'] is None
        assert status['eta_minutes'] is None

    def test_failure_reasons_breakdown_by_error_code(self):
        from services.batch_tracker import get_failure_reasons
        workflows = [
            _failure('DUPLICATE_VALUE', 'STU1'),
            _failure('DUPLICATE_VALUE', 'STU2'),
            _failure('TIMEOUT', 'STU3'),
        ]
        c = _conductor(workflows=workflows)
        with patch('services.batch_tracker.get_conductor_client', return_value=c):
            result = get_failure_reasons('SFMigrationWorkflow')
        assert result['total_failures'] == 3
        assert result['breakdown']['DUPLICATE_VALUE'] == 2
        assert result['breakdown']['TIMEOUT'] == 1


# ═════════════════════════════════════════════════════════════════════════════
# SECTION 5 — Error reconciler contracts
#
# categorize_conductor_failures must group failures into error codes, sort them
# largest-first, and carry the right metadata.
# ═════════════════════════════════════════════════════════════════════════════

class TestErrorReconcilerContracts:
    """Error categories, counts, sort order, and metadata are stable."""

    # 5 DUPLICATE_VALUE, 3 FIELD_INTEGRITY_EXCEPTION, 2 TIMEOUT.
    _WORKFLOWS = (
        [_failure('DUPLICATE_VALUE', f'D{i}', f'wf-d{i}') for i in range(5)]
        + [_failure('FIELD_INTEGRITY_EXCEPTION', f'F{i}', f'wf-f{i}') for i in range(3)]
        + [_failure('TIMEOUT', f'T{i}', f'wf-t{i}') for i in range(2)]
    )

    def _categorize(self):
        from services.error_reconciler import categorize_conductor_failures
        c = _conductor(workflows=list(self._WORKFLOWS))
        with patch('services.error_reconciler.get_conductor_client', return_value=c):
            return categorize_conductor_failures('SFMigrationWorkflow')

    def test_three_error_categories_produced(self):
        assert len(self._categorize()) == 3

    def test_sorted_descending_by_count(self):
        counts = [c['count'] for c in self._categorize()]
        assert counts == sorted(counts, reverse=True)

    def test_first_category_is_largest_group(self):
        cats = self._categorize()
        assert cats[0]['error_code'] == 'DUPLICATE_VALUE'
        assert cats[0]['count'] == 5

    def test_second_category_is_field_integrity(self):
        cats = self._categorize()
        assert cats[1]['error_code'] == 'FIELD_INTEGRITY_EXCEPTION'
        assert cats[1]['count'] == 3

    def test_third_category_is_timeout(self):
        cats = self._categorize()
        assert cats[2]['error_code'] == 'TIMEOUT'
        assert cats[2]['count'] == 2

    def test_total_failures_sums_to_input(self):
        total = sum(c['count'] for c in self._categorize())
        assert total == 10

    def test_duplicate_value_severity_is_high(self):
        dupe = next(c for c in self._categorize()
                    if c['error_code'] == 'DUPLICATE_VALUE')
        assert dupe['severity'] == 'high'

    def test_timeout_severity_is_low(self):
        timeout = next(c for c in self._categorize()
                       if c['error_code'] == 'TIMEOUT')
        assert timeout['severity'] == 'low'

    def test_each_category_has_required_keys(self):
        required = {'error_code', 'count', 'label', 'cause', 'suggested_fix',
                    'severity', 'sis_ids', 'workflow_ids'}
        for cat in self._categorize():
            assert required.issubset(cat.keys()), \
                f"Missing keys in {cat['error_code']}"

    def test_sis_ids_are_populated(self):
        dupe = next(c for c in self._categorize()
                    if c['error_code'] == 'DUPLICATE_VALUE')
        assert len(dupe['sis_ids']) == 5


# ═════════════════════════════════════════════════════════════════════════════
# SECTION 6 — ContactPoint scanner contracts
# ═════════════════════════════════════════════════════════════════════════════

class TestContactPointScannerContracts:
    """scan() returns per-CP-type stats with the documented shape and status."""

    def _scan(self, sf):
        from services.contactpoint_scanner import scan
        with patch('services.contactpoint_scanner.get_sf', return_value=sf):
            return scan('dev')

    def test_all_three_cp_types_present(self):
        result = self._scan(_count_sf(default=0))
        for t in ('ContactPointEmail', 'ContactPointPhone', 'ContactPointAddress'):
            assert t in result

    def test_each_type_has_required_keys(self):
        result = self._scan(_count_sf(default=0))
        for t in ('ContactPointEmail', 'ContactPointPhone', 'ContactPointAddress'):
            entry = result[t]
            assert set(entry) >= {'missing_parent', 'missing_individual',
                                  'total', 'sample_ids', 'status'}

    def test_status_green_when_nothing_missing(self):
        # default=0 → no missing parents/individuals → green.
        result = self._scan(_count_sf(default=0))
        assert result['ContactPointEmail']['status'] == 'green'

    def test_status_red_when_records_missing_parent(self):
        # every COUNT returns 5 (including the WHERE ParentId = null) → red.
        result = self._scan(_count_sf(default=5))
        assert result['ContactPointEmail']['status'] == 'red'

    def test_total_issues_sums_missing_across_types(self):
        result = self._scan(_count_sf(default=5))
        expected = sum(
            result[t]['missing_parent'] + result[t]['missing_individual']
            for t in ('ContactPointEmail', 'ContactPointPhone', 'ContactPointAddress')
        )
        assert result['total_issues'] == expected

    def test_sample_ids_capped_at_five(self):
        sample = [{'Id': f'0CP{i}'} for i in range(20)]
        sf = MagicMock()
        sf.query.return_value = {'records': sample, 'totalSize': 20, 'done': True}
        result = self._scan(sf)
        for t in ('ContactPointEmail', 'ContactPointPhone', 'ContactPointAddress'):
            assert len(result[t]['sample_ids']) <= 5


# ═════════════════════════════════════════════════════════════════════════════
# SECTION 7 — External ID coverage contracts
# ═════════════════════════════════════════════════════════════════════════════

class TestExternalIdCoverageContracts:
    """run() reports per-object, per-field coverage with correct status logic."""

    def _run(self, sf):
        from services.external_id_coverage import run
        with patch('services.external_id_coverage.get_sf', return_value=sf):
            rows = run('dev')
        return {r['object']: r for r in rows}

    def test_tracked_objects_present(self):
        by_obj = self._run(_count_sf(default=100))
        for obj in ('Account', 'ContactPointEmail', 'ContactPointPhone',
                    'ContactPointAddress', 'IndividualApplication'):
            assert obj in by_obj

    def test_account_tracks_both_external_id_fields(self):
        by_obj = self._run(_count_sf(default=100))
        assert set(by_obj['Account']['fields']) == {'SIS_ID__c', 'Ethos_Guid__c'}

    def test_field_entry_shape(self):
        by_obj = self._run(_count_sf(default=100))
        entry = by_obj['Account']['fields']['SIS_ID__c']
        assert set(entry) == {'covered', 'total', 'pct', 'status'}

    def test_full_coverage_is_green(self):
        # covered == total everywhere → green.
        by_obj = self._run(_count_sf(default=100))
        assert by_obj['Account']['fields']['SIS_ID__c']['status'] == 'green'

    def test_partial_coverage_is_red(self):
        # SIS_ID__c covered 71 of 100 → red.
        sf = _count_sf({'SIS_ID__c != null': 71}, default=100)
        by_obj = self._run(sf)
        assert by_obj['Account']['fields']['SIS_ID__c']['status'] == 'red'


# ═════════════════════════════════════════════════════════════════════════════
# SECTION 8 — extract_sf_error_code regex contract  (pure function — unchanged)
# ═════════════════════════════════════════════════════════════════════════════

class TestExtractSfErrorCodeContracts:
    """Known Conductor reasonForIncompletion strings → exact error code extracted."""

    CASES = [
        (
            'com.netflix.conductor.common.run.Workflow: DUPLICATE_VALUE: '
            'duplicate value found: SIS_ID__c duplicates value on record with id: STU00142',
            'DUPLICATE_VALUE',
        ),
        (
            'com.netflix.conductor.common.run.Workflow: FIELD_INTEGRITY_EXCEPTION: '
            'Parent record not found for id: STU13678',
            'FIELD_INTEGRITY_EXCEPTION',
        ),
        (
            'com.netflix.conductor.common.run.Workflow: TIMEOUT: worker timed out',
            'TIMEOUT',
        ),
        (
            'com.netflix.conductor.common.run.Workflow: REQUIRED_FIELD_MISSING: '
            'Required fields are missing: [Name]',
            'REQUIRED_FIELD_MISSING',
        ),
        (
            'com.netflix.conductor.common.run.Workflow: INVALID_FIELD: '
            'No such column \'BadField__c\'',
            'INVALID_FIELD',
        ),
        ('', 'UNKNOWN'),
        ('no error code here', 'UNKNOWN'),
    ]

    @pytest.mark.parametrize('reason,expected_code', CASES)
    def test_extract_code(self, reason, expected_code):
        from services.batch_tracker import extract_sf_error_code
        assert extract_sf_error_code(reason) == expected_code
