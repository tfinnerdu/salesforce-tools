"""
Contract tests — pin "what we know should be true."

These tests do NOT mock the mock. They exercise the full service → mock-SF/Conductor
pipeline and assert exact, pre-calculated values derived from the handoff doc numbers.
If anyone changes mock counts, threshold boundaries, or business-logic rules, a
contract test breaks immediately instead of silently changing downstream behavior.

When a contract test breaks intentionally (e.g. we deliberately raise SIS_ID__c
coverage in the mock), update the constant AND the comment explaining the new value.
"""
import pytest

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1 — Mock SF data counts (_parse_mock_count)
#
# Source: sf_provider._parse_mock_count
# These are the exact integers the mock returns for each SOQL pattern.
# ─────────────────────────────────────────────────────────────────────────────

# PersonAccount / Account totals
MOCK_ACCOUNT_TOTAL                  = 4_312
MOCK_SIS_ID_COVERED                 = 3_065   # idx % 4 != 0 → 75% of 4312, rounded
MOCK_SIS_ID_MISSING                 = MOCK_ACCOUNT_TOTAL - MOCK_SIS_ID_COVERED   # 1 247
MOCK_ETHOS_GUID_COVERED             = 3_923   # idx % 11 != 0
MOCK_ETHOS_GUID_MISSING             = MOCK_ACCOUNT_TOTAL - MOCK_ETHOS_GUID_COVERED  # 389
MOCK_ACCOUNT_INDIVIDUAL_MISSING     = 0       # all PersonAccounts have Individual links
MOCK_ACCOUNT_FIRSTNAME_MISSING      = 44
MOCK_ACCOUNT_LASTNAME_MISSING       = 12
MOCK_ACCOUNT_RECORDTYPEID_MISSING   = 3

# ContactPointEmail
MOCK_CPE_TOTAL                      = 4_100
MOCK_CPE_PARENT_MISSING             = 683
MOCK_CPE_INDIVIDUAL_MISSING         = 512
MOCK_CPE_SIS_ID_MISSING             = 820
MOCK_CPE_SIS_ID_COVERED             = MOCK_CPE_TOTAL - MOCK_CPE_SIS_ID_MISSING    # 3 280

# ContactPointPhone
MOCK_CPP_TOTAL                      = 3_800
MOCK_CPP_PARENT_MISSING             = 633
MOCK_CPP_INDIVIDUAL_MISSING         = 422
MOCK_CPP_SIS_ID_MISSING             = 760
MOCK_CPP_SIS_ID_COVERED             = MOCK_CPP_TOTAL - MOCK_CPP_SIS_ID_MISSING    # 3 040

# ContactPointAddress
MOCK_CPA_TOTAL                      = 3_204
MOCK_CPA_PARENT_MISSING             = 3_204   # all CPA records lack ParentId in mock
MOCK_CPA_INDIVIDUAL_MISSING         = 2_800
MOCK_CPA_SIS_ID_MISSING             = 640
MOCK_CPA_SIS_ID_COVERED             = MOCK_CPA_TOTAL - MOCK_CPA_SIS_ID_MISSING    # 2 564

# IndividualApplication
MOCK_IA_TOTAL                       = 1_850
MOCK_IA_SIS_ID_MISSING              = 185
MOCK_IA_SIS_ID_COVERED              = MOCK_IA_TOTAL - MOCK_IA_SIS_ID_MISSING      # 1 665
MOCK_IA_ETHOS_GUID_MISSING          = 200
MOCK_IA_ETHOS_GUID_COVERED          = MOCK_IA_TOTAL - MOCK_IA_ETHOS_GUID_MISSING  # 1 650

# Conductor (MockConductorClient)
MOCK_CONDUCTOR_TOTAL                = 4_312
MOCK_CONDUCTOR_COMPLETED            = 2_756
MOCK_CONDUCTOR_FAILED               = 91
MOCK_CONDUCTOR_RUNNING              = 212
MOCK_CONDUCTOR_QUEUED               = 1_253
MOCK_CONDUCTOR_TIMED_OUT            = 16
MOCK_CONDUCTOR_DUPLICATE_VALUE      = 44
MOCK_CONDUCTOR_FIELD_INTEGRITY      = 31
MOCK_CONDUCTOR_TIMEOUT              = 16   # same set as timed_out above
assert MOCK_CONDUCTOR_DUPLICATE_VALUE + MOCK_CONDUCTOR_FIELD_INTEGRITY + MOCK_CONDUCTOR_TIMEOUT == MOCK_CONDUCTOR_FAILED


class TestMockSFCounts:
    """_parse_mock_count returns exact expected integers for every SOQL pattern."""

    def setup_method(self):
        from sf_provider import MockSalesforce
        self.sf = MockSalesforce('dev')

    def _count(self, soql: str) -> int:
        return self.sf.query(soql)['totalSize']

    # ── Account ───────────────────────────────────────────────────────────────

    def test_account_total(self):
        assert self._count("SELECT COUNT() FROM Account WHERE IsPersonAccount = true") == MOCK_ACCOUNT_TOTAL

    def test_sis_id_covered(self):
        assert self._count(
            "SELECT COUNT() FROM Account WHERE IsPersonAccount = true AND SIS_ID__c != null"
        ) == MOCK_SIS_ID_COVERED

    def test_sis_id_missing(self):
        assert self._count(
            "SELECT COUNT() FROM Account WHERE IsPersonAccount = true AND SIS_ID__c = null"
        ) == MOCK_SIS_ID_MISSING

    def test_ethos_guid_covered(self):
        assert self._count(
            "SELECT COUNT() FROM Account WHERE IsPersonAccount = true AND Ethos_Guid__c != null"
        ) == MOCK_ETHOS_GUID_COVERED

    def test_ethos_guid_missing(self):
        assert self._count(
            "SELECT COUNT() FROM Account WHERE IsPersonAccount = true AND Ethos_Guid__c = null"
        ) == MOCK_ETHOS_GUID_MISSING

    def test_account_individual_missing(self):
        assert self._count(
            "SELECT COUNT() FROM Account WHERE IsPersonAccount = true AND IndividualId = null"
        ) == MOCK_ACCOUNT_INDIVIDUAL_MISSING

    def test_account_firstname_missing(self):
        assert self._count(
            "SELECT COUNT() FROM Account WHERE IsPersonAccount = true AND FirstName = null"
        ) == MOCK_ACCOUNT_FIRSTNAME_MISSING

    def test_account_lastname_missing(self):
        assert self._count(
            "SELECT COUNT() FROM Account WHERE IsPersonAccount = true AND LastName = null"
        ) == MOCK_ACCOUNT_LASTNAME_MISSING

    def test_account_recordtypeid_missing(self):
        assert self._count(
            "SELECT COUNT() FROM Account WHERE IsPersonAccount = true AND RecordTypeId = null"
        ) == MOCK_ACCOUNT_RECORDTYPEID_MISSING

    # ── ContactPointEmail ─────────────────────────────────────────────────────

    def test_cpe_total(self):
        assert self._count("SELECT COUNT() FROM ContactPointEmail") == MOCK_CPE_TOTAL

    def test_cpe_parent_missing(self):
        assert self._count("SELECT COUNT() FROM ContactPointEmail WHERE ParentId = null") == MOCK_CPE_PARENT_MISSING

    def test_cpe_individual_missing(self):
        assert self._count("SELECT COUNT() FROM ContactPointEmail WHERE IndividualId = null") == MOCK_CPE_INDIVIDUAL_MISSING

    def test_cpe_sis_id_missing(self):
        assert self._count("SELECT COUNT() FROM ContactPointEmail WHERE SIS_ID__c = null") == MOCK_CPE_SIS_ID_MISSING

    def test_cpe_sis_id_covered(self):
        assert self._count("SELECT COUNT() FROM ContactPointEmail WHERE SIS_ID__c != null") == MOCK_CPE_SIS_ID_COVERED

    # ── ContactPointPhone ─────────────────────────────────────────────────────

    def test_cpp_total(self):
        assert self._count("SELECT COUNT() FROM ContactPointPhone") == MOCK_CPP_TOTAL

    def test_cpp_parent_missing(self):
        assert self._count("SELECT COUNT() FROM ContactPointPhone WHERE ParentId = null") == MOCK_CPP_PARENT_MISSING

    def test_cpp_individual_missing(self):
        assert self._count("SELECT COUNT() FROM ContactPointPhone WHERE IndividualId = null") == MOCK_CPP_INDIVIDUAL_MISSING

    def test_cpp_sis_id_missing(self):
        assert self._count("SELECT COUNT() FROM ContactPointPhone WHERE SIS_ID__c = null") == MOCK_CPP_SIS_ID_MISSING

    def test_cpp_sis_id_covered(self):
        assert self._count("SELECT COUNT() FROM ContactPointPhone WHERE SIS_ID__c != null") == MOCK_CPP_SIS_ID_COVERED

    # ── ContactPointAddress ───────────────────────────────────────────────────

    def test_cpa_total(self):
        assert self._count("SELECT COUNT() FROM ContactPointAddress") == MOCK_CPA_TOTAL

    def test_cpa_parent_missing(self):
        assert self._count("SELECT COUNT() FROM ContactPointAddress WHERE ParentId = null") == MOCK_CPA_PARENT_MISSING

    def test_cpa_individual_missing(self):
        assert self._count("SELECT COUNT() FROM ContactPointAddress WHERE IndividualId = null") == MOCK_CPA_INDIVIDUAL_MISSING

    def test_cpa_sis_id_missing(self):
        assert self._count("SELECT COUNT() FROM ContactPointAddress WHERE SIS_ID__c = null") == MOCK_CPA_SIS_ID_MISSING

    def test_cpa_sis_id_covered(self):
        assert self._count("SELECT COUNT() FROM ContactPointAddress WHERE SIS_ID__c != null") == MOCK_CPA_SIS_ID_COVERED


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2 — Status threshold boundaries
#
# Source: readiness_validator._status, external_id_coverage._field_status
# These functions must agree on exact cutoffs. If someone widens "amber" or
# moves the green threshold, a boundary test will catch it.
# ─────────────────────────────────────────────────────────────────────────────

class TestStatusThresholdBoundaries:
    """Exact boundary conditions for _status and _issue_status."""

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


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3 — Readiness check results with mock data
#
# Each check has a pre-computed expected status given the mock constants above.
# ─────────────────────────────────────────────────────────────────────────────

# Pre-computed expected values
_SIS_PCT    = round(100 * MOCK_SIS_ID_COVERED / MOCK_ACCOUNT_TOTAL, 2)   # ~71.09 → red
_ETHOS_PCT  = round(100 * MOCK_ETHOS_GUID_COVERED / MOCK_ACCOUNT_TOTAL, 2)  # ~91.0 → amber

_CP_TOTAL   = MOCK_CPE_TOTAL + MOCK_CPP_TOTAL + MOCK_CPA_TOTAL            # 11 104
_CP_BROKEN  = MOCK_CPE_PARENT_MISSING + MOCK_CPP_PARENT_MISSING + MOCK_CPA_PARENT_MISSING  # 4 520
_CP_COVERED = _CP_TOTAL - _CP_BROKEN
_CP_PCT     = round(100 * _CP_COVERED / _CP_TOTAL, 2)                     # ~59.29 → red

_INDIV_BROKEN  = MOCK_CPE_INDIVIDUAL_MISSING + MOCK_CPP_INDIVIDUAL_MISSING + MOCK_CPA_INDIVIDUAL_MISSING  # 3 734
_INDIV_COVERED = _CP_TOTAL - _INDIV_BROKEN
_INDIV_PCT     = round(100 * _INDIV_COVERED / _CP_TOTAL, 2)               # ~66.37 → red

# Required fields: mock returns 44 missing (firstname match comes first)
_REQ_MISSING = MOCK_ACCOUNT_FIRSTNAME_MISSING                             # 44
_REQ_PCT     = round(100 * (MOCK_ACCOUNT_TOTAL - _REQ_MISSING) / MOCK_ACCOUNT_TOTAL, 2)  # ~98.98 → amber


class TestReadinessCheckContracts:
    """Each check produces the exact known status/count from mock data."""

    def setup_method(self):
        from sf_provider import MockSalesforce
        self.sf = MockSalesforce('dev')

    def test_sis_id_coverage_total(self):
        from services.readiness_validator import check_sis_id_coverage
        r = check_sis_id_coverage(self.sf)
        assert r['total'] == MOCK_ACCOUNT_TOTAL

    def test_sis_id_coverage_covered(self):
        from services.readiness_validator import check_sis_id_coverage
        r = check_sis_id_coverage(self.sf)
        assert r['covered'] == MOCK_SIS_ID_COVERED

    def test_sis_id_coverage_pct(self):
        from services.readiness_validator import check_sis_id_coverage
        r = check_sis_id_coverage(self.sf)
        assert r['pct'] == _SIS_PCT

    def test_sis_id_coverage_status_is_red(self):
        """71% coverage < 90% threshold → RED."""
        from services.readiness_validator import check_sis_id_coverage
        assert check_sis_id_coverage(self.sf)['status'] == 'red'

    def test_ethos_guid_coverage_total(self):
        from services.readiness_validator import check_ethos_guid_coverage
        r = check_ethos_guid_coverage(self.sf)
        assert r['total'] == MOCK_ACCOUNT_TOTAL

    def test_ethos_guid_coverage_covered(self):
        from services.readiness_validator import check_ethos_guid_coverage
        r = check_ethos_guid_coverage(self.sf)
        assert r['covered'] == MOCK_ETHOS_GUID_COVERED

    def test_ethos_guid_coverage_pct(self):
        from services.readiness_validator import check_ethos_guid_coverage
        r = check_ethos_guid_coverage(self.sf)
        assert r['pct'] == _ETHOS_PCT

    def test_ethos_guid_coverage_status_is_amber(self):
        """~91% coverage ≥ 90% but < 100% → AMBER."""
        from services.readiness_validator import check_ethos_guid_coverage
        assert check_ethos_guid_coverage(self.sf)['status'] == 'amber'

    def test_contactpoint_parents_total(self):
        from services.readiness_validator import check_contactpoint_parents
        r = check_contactpoint_parents(self.sf)
        assert r['total'] == _CP_TOTAL

    def test_contactpoint_parents_covered(self):
        from services.readiness_validator import check_contactpoint_parents
        r = check_contactpoint_parents(self.sf)
        assert r['covered'] == _CP_COVERED

    def test_contactpoint_parents_pct(self):
        from services.readiness_validator import check_contactpoint_parents
        r = check_contactpoint_parents(self.sf)
        assert r['pct'] == _CP_PCT

    def test_contactpoint_parents_status_is_red(self):
        """~59% covered (3204 CPA all broken) → RED."""
        from services.readiness_validator import check_contactpoint_parents
        assert check_contactpoint_parents(self.sf)['status'] == 'red'

    def test_required_fields_total(self):
        from services.readiness_validator import check_required_fields
        r = check_required_fields(self.sf)
        assert r['total'] == MOCK_ACCOUNT_TOTAL

    def test_required_fields_pct(self):
        from services.readiness_validator import check_required_fields
        r = check_required_fields(self.sf)
        assert r['pct'] == _REQ_PCT

    def test_required_fields_status_is_amber(self):
        """~99% (only 44 missing FirstName) → AMBER."""
        from services.readiness_validator import check_required_fields
        assert check_required_fields(self.sf)['status'] == 'amber'

    def test_duplicates_status_is_green(self):
        """Mock generates unique SIS IDs → zero duplicate groups → GREEN."""
        from services.readiness_validator import check_duplicates
        assert check_duplicates(self.sf)['status'] == 'green'

    def test_individual_links_total(self):
        from services.readiness_validator import check_individual_links
        r = check_individual_links(self.sf)
        assert r['total'] == _CP_TOTAL

    def test_individual_links_covered(self):
        from services.readiness_validator import check_individual_links
        r = check_individual_links(self.sf)
        assert r['covered'] == _INDIV_COVERED

    def test_individual_links_pct(self):
        from services.readiness_validator import check_individual_links
        r = check_individual_links(self.sf)
        assert r['pct'] == _INDIV_PCT

    def test_individual_links_status_is_red(self):
        """~66% covered → RED."""
        from services.readiness_validator import check_individual_links
        assert check_individual_links(self.sf)['status'] == 'red'

    def test_overall_readiness_is_red(self):
        """At least three checks are red → overall must be red."""
        from services.readiness_validator import run_full_readiness_check
        result = run_full_readiness_check('dev')
        assert result['overall_status'] == 'red'

    def test_overall_has_exactly_six_checks(self):
        from services.readiness_validator import run_full_readiness_check
        result = run_full_readiness_check('dev')
        assert len(result['checks']) == 6

    def test_overall_check_keys_are_stable(self):
        """check_key values are part of the public contract (used by frontend + DB)."""
        from services.readiness_validator import run_full_readiness_check
        result = run_full_readiness_check('dev')
        keys = {c['check_key'] for c in result['checks']}
        assert keys == {
            'sis_id_coverage',
            'ethos_guid_coverage',
            'contactpoint_parents',
            'required_fields',
            'duplicates',
            'individual_links',
        }


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4 — Conductor mock data contracts
# ─────────────────────────────────────────────────────────────────────────────

class TestConductorMockContracts:
    """MockConductorClient returns exact known counts."""

    def setup_method(self):
        from conductor_provider import MockConductorClient
        self.conductor = MockConductorClient()

    def test_batch_status_total(self):
        s = self.conductor.get_batch_status('SFMigrationWorkflow')
        assert s['total'] == MOCK_CONDUCTOR_TOTAL

    def test_batch_status_completed(self):
        s = self.conductor.get_batch_status('SFMigrationWorkflow')
        assert s['completed'] == MOCK_CONDUCTOR_COMPLETED

    def test_batch_status_failed(self):
        s = self.conductor.get_batch_status('SFMigrationWorkflow')
        assert s['failed'] == MOCK_CONDUCTOR_FAILED

    def test_batch_status_running(self):
        s = self.conductor.get_batch_status('SFMigrationWorkflow')
        assert s['running'] == MOCK_CONDUCTOR_RUNNING

    def test_batch_status_queued(self):
        s = self.conductor.get_batch_status('SFMigrationWorkflow')
        assert s['queued'] == MOCK_CONDUCTOR_QUEUED

    def test_batch_status_timed_out(self):
        s = self.conductor.get_batch_status('SFMigrationWorkflow')
        assert s['timed_out'] == MOCK_CONDUCTOR_TIMED_OUT

    def test_total_equals_sum_of_parts(self):
        # timed_out is a sub-category of failed (those workflows have status=FAILED
        # with a TIMEOUT error code), so it is NOT added separately to the total.
        s = self.conductor.get_batch_status('SFMigrationWorkflow')
        assert s['total'] == s['completed'] + s['failed'] + s['running'] + s['queued']

    def test_timed_out_is_subset_of_failed(self):
        """The 16 TIMEOUT workflows are counted inside failed:91, not separately."""
        s = self.conductor.get_batch_status('SFMigrationWorkflow')
        assert s['timed_out'] <= s['failed']
        assert s['timed_out'] == MOCK_CONDUCTOR_TIMEOUT

    def test_failed_workflow_count(self):
        workflows = self.conductor.search_workflows('SFMigrationWorkflow', 'FAILED')
        assert len(workflows) == MOCK_CONDUCTOR_FAILED

    def test_failed_split_by_error_code(self):
        from services.batch_tracker import extract_sf_error_code
        workflows = self.conductor.search_workflows('SFMigrationWorkflow', 'FAILED')
        codes = [extract_sf_error_code(w.get('reasonForIncompletion', '')) for w in workflows]
        from collections import Counter
        counts = Counter(codes)
        assert counts['DUPLICATE_VALUE'] == MOCK_CONDUCTOR_DUPLICATE_VALUE
        assert counts['FIELD_INTEGRITY_EXCEPTION'] == MOCK_CONDUCTOR_FIELD_INTEGRITY
        assert counts['TIMEOUT'] == MOCK_CONDUCTOR_TIMEOUT


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 5 — Error reconciler contracts
#
# categorize_conductor_failures must group failures into the right error codes,
# sort them largest-first, and carry the right metadata.
# ─────────────────────────────────────────────────────────────────────────────

class TestErrorReconcilerContracts:
    """Error categories, counts, and sort order are stable."""

    def setup_method(self):
        from services.error_reconciler import categorize_conductor_failures
        self.categories = categorize_conductor_failures('SFMigrationWorkflow')

    def test_three_error_categories_produced(self):
        assert len(self.categories) == 3

    def test_sorted_descending_by_count(self):
        counts = [c['count'] for c in self.categories]
        assert counts == sorted(counts, reverse=True)

    def test_first_category_is_duplicate_value(self):
        """DUPLICATE_VALUE (44) is the largest group → must be first."""
        assert self.categories[0]['error_code'] == 'DUPLICATE_VALUE'
        assert self.categories[0]['count'] == MOCK_CONDUCTOR_DUPLICATE_VALUE

    def test_second_category_is_field_integrity(self):
        assert self.categories[1]['error_code'] == 'FIELD_INTEGRITY_EXCEPTION'
        assert self.categories[1]['count'] == MOCK_CONDUCTOR_FIELD_INTEGRITY

    def test_third_category_is_timeout(self):
        assert self.categories[2]['error_code'] == 'TIMEOUT'
        assert self.categories[2]['count'] == MOCK_CONDUCTOR_TIMEOUT

    def test_total_failures_sums_to_known_value(self):
        total = sum(c['count'] for c in self.categories)
        assert total == MOCK_CONDUCTOR_FAILED

    def test_duplicate_value_severity_is_high(self):
        dupe = next(c for c in self.categories if c['error_code'] == 'DUPLICATE_VALUE')
        assert dupe['severity'] == 'high'

    def test_timeout_severity_is_low(self):
        timeout = next(c for c in self.categories if c['error_code'] == 'TIMEOUT')
        assert timeout['severity'] == 'low'

    def test_each_category_has_required_keys(self):
        required = {'error_code', 'count', 'label', 'cause', 'suggested_fix', 'severity',
                    'sis_ids', 'workflow_ids'}
        for cat in self.categories:
            assert required.issubset(cat.keys()), f"Missing keys in {cat['error_code']}"

    def test_sis_ids_are_populated(self):
        dupe = next(c for c in self.categories if c['error_code'] == 'DUPLICATE_VALUE')
        assert len(dupe['sis_ids']) == MOCK_CONDUCTOR_DUPLICATE_VALUE


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 6 — ContactPoint scanner contracts
# ─────────────────────────────────────────────────────────────────────────────

class TestContactPointScannerContracts:
    """Known missing counts and statuses for each CP type."""

    def setup_method(self):
        from services.contactpoint_scanner import scan
        self.result = scan('dev')

    def test_email_total(self):
        assert self.result['ContactPointEmail']['total'] == MOCK_CPE_TOTAL

    def test_email_missing_parent(self):
        assert self.result['ContactPointEmail']['missing_parent'] == MOCK_CPE_PARENT_MISSING

    def test_email_missing_individual(self):
        assert self.result['ContactPointEmail']['missing_individual'] == MOCK_CPE_INDIVIDUAL_MISSING

    def test_email_status_is_red(self):
        assert self.result['ContactPointEmail']['status'] == 'red'

    def test_phone_total(self):
        assert self.result['ContactPointPhone']['total'] == MOCK_CPP_TOTAL

    def test_phone_missing_parent(self):
        assert self.result['ContactPointPhone']['missing_parent'] == MOCK_CPP_PARENT_MISSING

    def test_phone_missing_individual(self):
        assert self.result['ContactPointPhone']['missing_individual'] == MOCK_CPP_INDIVIDUAL_MISSING

    def test_phone_status_is_red(self):
        assert self.result['ContactPointPhone']['status'] == 'red'

    def test_address_total(self):
        assert self.result['ContactPointAddress']['total'] == MOCK_CPA_TOTAL

    def test_address_missing_parent(self):
        assert self.result['ContactPointAddress']['missing_parent'] == MOCK_CPA_PARENT_MISSING

    def test_address_missing_individual(self):
        assert self.result['ContactPointAddress']['missing_individual'] == MOCK_CPA_INDIVIDUAL_MISSING

    def test_address_status_is_red(self):
        assert self.result['ContactPointAddress']['status'] == 'red'

    def test_sample_ids_capped_at_five(self):
        for cp_type in ('ContactPointEmail', 'ContactPointPhone', 'ContactPointAddress'):
            assert len(self.result[cp_type]['sample_ids']) <= 5

    def test_total_issues_equals_sum(self):
        expected = sum(
            self.result[t]['missing_parent'] + self.result[t]['missing_individual']
            for t in ('ContactPointEmail', 'ContactPointPhone', 'ContactPointAddress')
        )
        assert self.result['total_issues'] == expected

    def test_total_issues_known_value(self):
        expected = (
            MOCK_CPE_PARENT_MISSING + MOCK_CPE_INDIVIDUAL_MISSING
            + MOCK_CPP_PARENT_MISSING + MOCK_CPP_INDIVIDUAL_MISSING
            + MOCK_CPA_PARENT_MISSING + MOCK_CPA_INDIVIDUAL_MISSING
        )
        assert self.result['total_issues'] == expected


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 7 — External ID coverage contracts
#
# Source: services.external_id_coverage.run
# ─────────────────────────────────────────────────────────────────────────────

# Expected per-object, per-field results
_EXT_ID_EXPECTED = {
    # object: {field: (covered, total, status)}
    'Account': {
        'SIS_ID__c':    (MOCK_SIS_ID_COVERED,    MOCK_ACCOUNT_TOTAL, 'red'),    # ~71%
        'Ethos_Guid__c': (MOCK_ETHOS_GUID_COVERED, MOCK_ACCOUNT_TOTAL, 'amber'),  # ~91%
    },
    'ContactPointEmail': {
        'SIS_ID__c': (MOCK_CPE_SIS_ID_COVERED, MOCK_CPE_TOTAL, 'red'),          # ~80%
    },
    'ContactPointPhone': {
        'SIS_ID__c': (MOCK_CPP_SIS_ID_COVERED, MOCK_CPP_TOTAL, 'red'),          # ~80%
    },
    'ContactPointAddress': {
        'SIS_ID__c': (MOCK_CPA_SIS_ID_COVERED, MOCK_CPA_TOTAL, 'red'),          # ~80%
    },
}


class TestExternalIdCoverageContracts:

    def setup_method(self):
        from services.external_id_coverage import run
        rows = run('dev')
        self.by_obj = {r['object']: r for r in rows}

    def test_tracked_objects_present(self):
        for obj in _EXT_ID_EXPECTED:
            assert obj in self.by_obj, f"{obj} missing from coverage report"

    @pytest.mark.parametrize('obj,field,covered,total,status', [
        (obj, field, vals[0], vals[1], vals[2])
        for obj, fields in _EXT_ID_EXPECTED.items()
        for field, vals in fields.items()
    ])
    def test_field_covered(self, obj, field, covered, total, status):
        assert self.by_obj[obj]['fields'][field]['covered'] == covered

    @pytest.mark.parametrize('obj,field,covered,total,status', [
        (obj, field, vals[0], vals[1], vals[2])
        for obj, fields in _EXT_ID_EXPECTED.items()
        for field, vals in fields.items()
    ])
    def test_field_total(self, obj, field, covered, total, status):
        assert self.by_obj[obj]['fields'][field]['total'] == total

    @pytest.mark.parametrize('obj,field,covered,total,status', [
        (obj, field, vals[0], vals[1], vals[2])
        for obj, fields in _EXT_ID_EXPECTED.items()
        for field, vals in fields.items()
    ])
    def test_field_status(self, obj, field, covered, total, status):
        assert self.by_obj[obj]['fields'][field]['status'] == status


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 8 — extract_sf_error_code regex contract
#
# Source: services.batch_tracker.extract_sf_error_code
# ─────────────────────────────────────────────────────────────────────────────

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
