"""Focused tests for the SHOW_MOCK env flag.

These tests verify the all-or-nothing opt-in semantics across the provider
layer AND the demo-only fallback paths gated on Config.SHOW_MOCK. Each test
toggles Config.SHOW_MOCK with monkeypatch; the rest of the suite is unaffected.
"""
from unittest.mock import MagicMock, patch

import pytest

from config import Config


# ── Provider toggles ─────────────────────────────────────────────────────────

class TestGetSfHonorsShowMock:
    def test_show_mock_true_returns_mock_salesforce(self, monkeypatch):
        monkeypatch.setattr(Config, 'SHOW_MOCK', True)
        from sf_provider import get_sf, MockSalesforce
        assert isinstance(get_sf('dev'), MockSalesforce)

    def test_show_mock_true_returns_mock_for_any_org(self, monkeypatch):
        monkeypatch.setattr(Config, 'SHOW_MOCK', True)
        from sf_provider import get_sf, MockSalesforce
        for org in ('dev', 'prod', 'sandbox', 'made-up-org'):
            assert isinstance(get_sf(org), MockSalesforce)

    def test_show_mock_false_unconfigured_org_raises(self, monkeypatch):
        monkeypatch.setattr(Config, 'SHOW_MOCK', False)
        import sf_provider
        monkeypatch.setattr(sf_provider, '_configured', lambda org: False)
        with pytest.raises(RuntimeError) as exc_info:
            sf_provider.get_sf('dev')
        msg = str(exc_info.value)
        assert 'no Salesforce credentials' in msg
        assert 'SHOW_MOCK=true' in msg  # error message points operators at the demo flag

    def test_show_mock_false_configured_org_builds_real_client(self, monkeypatch):
        monkeypatch.setattr(Config, 'SHOW_MOCK', False)
        import sf_provider
        import sys
        monkeypatch.setattr(sf_provider, '_configured', lambda org: True)
        monkeypatch.setattr(sf_provider, 'get_org_config', lambda org: {
            'username': 'u', 'password': 'p', 'security_token': 't',
            'domain': 'login', 'api_version': '59.0',
        })
        fake_sf = MagicMock()
        fake_sf.sf_instance = 'na123.salesforce.com'
        # Stub the simple_salesforce package wholesale — cffi/cryptography
        # aren't necessarily present in CI, and we only care that get_sf
        # invokes the Salesforce constructor and returns its result.
        fake_module = MagicMock()
        fake_module.Salesforce = MagicMock(return_value=fake_sf)
        monkeypatch.setitem(sys.modules, 'simple_salesforce', fake_module)
        result = sf_provider.get_sf('dev')
        fake_module.Salesforce.assert_called_once()
        assert result is fake_sf


class TestGetConductorClientHonorsShowMock:
    def test_show_mock_true_returns_mock_client(self, monkeypatch):
        monkeypatch.setattr(Config, 'SHOW_MOCK', True)
        from conductor_provider import get_conductor_client, MockConductorClient
        assert isinstance(get_conductor_client(), MockConductorClient)

    def test_show_mock_false_unconfigured_raises(self, monkeypatch):
        monkeypatch.setattr(Config, 'SHOW_MOCK', False)
        monkeypatch.setattr(Config, 'CONDUCTOR_URL', '')
        monkeypatch.setattr(Config, 'CONDUCTOR_API_KEY', '')
        from conductor_provider import get_conductor_client
        with pytest.raises(RuntimeError) as exc_info:
            get_conductor_client()
        msg = str(exc_info.value)
        assert 'Conductor is not configured' in msg
        assert 'SHOW_MOCK=true' in msg

    def test_show_mock_false_configured_returns_real_client(self, monkeypatch):
        monkeypatch.setattr(Config, 'SHOW_MOCK', False)
        monkeypatch.setattr(Config, 'CONDUCTOR_URL', 'http://conductor:8080')
        monkeypatch.setattr(Config, 'CONDUCTOR_API_KEY', 'k')
        from conductor_provider import get_conductor_client, ConductorClient
        client = get_conductor_client()
        assert isinstance(client, ConductorClient)
        assert client.base_url == 'http://conductor:8080'


# ── Helper functions follow Config.SHOW_MOCK ─────────────────────────────────

class TestOrgIsMocked:
    """org_is_mocked is `Config.SHOW_MOCK or not _configured(org)` — used by
    the diff-picker UX to also flag orgs with no credentials as 'mock-like'."""

    def test_true_when_show_mock_on(self, monkeypatch):
        monkeypatch.setattr(Config, 'SHOW_MOCK', True)
        import sf_provider
        monkeypatch.setattr(sf_provider, '_configured', lambda org: True)
        assert sf_provider.org_is_mocked('dev') is True

    def test_false_when_show_mock_off_and_org_configured(self, monkeypatch):
        monkeypatch.setattr(Config, 'SHOW_MOCK', False)
        import sf_provider
        monkeypatch.setattr(sf_provider, '_configured', lambda org: True)
        assert sf_provider.org_is_mocked('dev') is False

    def test_true_when_show_mock_off_but_unconfigured(self, monkeypatch):
        monkeypatch.setattr(Config, 'SHOW_MOCK', False)
        import sf_provider
        monkeypatch.setattr(sf_provider, '_configured', lambda org: False)
        # The OR-with-_configured branch lets diff pickers treat an
        # unconfigured org as "mock-equivalent" without flipping SHOW_MOCK.
        assert sf_provider.org_is_mocked('dev') is True


class TestAssertOrgsComparable:
    def test_show_mock_true_never_raises(self, monkeypatch):
        monkeypatch.setattr(Config, 'SHOW_MOCK', True)
        import sf_provider
        monkeypatch.setattr(sf_provider, '_configured', lambda org: False)
        sf_provider.assert_orgs_comparable('dev', 'prod')  # no raise

    def test_show_mock_false_both_configured_no_raise(self, monkeypatch):
        monkeypatch.setattr(Config, 'SHOW_MOCK', False)
        import sf_provider
        monkeypatch.setattr(sf_provider, '_configured', lambda org: True)
        sf_provider.assert_orgs_comparable('dev', 'prod')

    def test_show_mock_false_one_unconfigured_raises(self, monkeypatch):
        monkeypatch.setattr(Config, 'SHOW_MOCK', False)
        import sf_provider
        monkeypatch.setattr(sf_provider, '_configured',
                            lambda org: org == 'dev')
        with pytest.raises(ValueError) as exc_info:
            sf_provider.assert_orgs_comparable('dev', 'prod')
        assert "'prod'" in str(exc_info.value)


class TestAvailableOrgs:
    def test_show_mock_true_returns_all_candidates(self, monkeypatch):
        monkeypatch.setattr(Config, 'SHOW_MOCK', True)
        from sf_provider import available_orgs
        assert available_orgs() == ['dev', 'prod', 'sandbox']

    def test_show_mock_false_filters_to_configured(self, monkeypatch):
        monkeypatch.setattr(Config, 'SHOW_MOCK', False)
        import sf_provider
        monkeypatch.setattr(sf_provider, '_configured',
                            lambda org: org in ('dev', 'sandbox'))
        assert sf_provider.available_orgs() == ['dev', 'sandbox']

    def test_show_mock_false_none_configured_returns_empty(self, monkeypatch):
        monkeypatch.setattr(Config, 'SHOW_MOCK', False)
        import sf_provider
        monkeypatch.setattr(sf_provider, '_configured', lambda org: False)
        assert sf_provider.available_orgs() == []


# ── All-or-nothing demo fallbacks — only active when SHOW_MOCK is true ──────

class TestDuplicateRadarMergeGating:
    def test_attribute_error_treated_as_success_in_mock(self, monkeypatch):
        monkeypatch.setattr(Config, 'SHOW_MOCK', True)
        from services import duplicate_radar
        fake_sf = MagicMock()
        fake_sf.Account.merge.side_effect = AttributeError("no merge method")
        monkeypatch.setattr(duplicate_radar, 'get_sf', lambda org: fake_sf)
        result = duplicate_radar.merge('dev', '001AAA', '001BBB')
        assert result['success'] is True

    def test_attribute_error_is_failure_in_real_mode(self, monkeypatch):
        monkeypatch.setattr(Config, 'SHOW_MOCK', False)
        from services import duplicate_radar
        fake_sf = MagicMock()
        fake_sf.Account.merge.side_effect = AttributeError("no merge method")
        monkeypatch.setattr(duplicate_radar, 'get_sf', lambda org: fake_sf)
        result = duplicate_radar.merge('dev', '001AAA', '001BBB')
        assert result['success'] is False


class TestRequeueBatchGating:
    def test_show_mock_returns_synthesized_success(self, monkeypatch):
        monkeypatch.setattr(Config, 'SHOW_MOCK', True)
        from services import error_reconciler
        result = error_reconciler.requeue_batch('batch-001', 'dev')
        assert result['status'] == 'queued'
        assert result['batch_id'] == 'batch-001'

    def test_real_mode_raises_runtime_error(self, monkeypatch):
        monkeypatch.setattr(Config, 'SHOW_MOCK', False)
        from services import error_reconciler
        with pytest.raises(RuntimeError) as exc_info:
            error_reconciler.requeue_batch('batch-001', 'dev')
        assert 'batch_id=batch-001' in str(exc_info.value)


class TestBatchTrackerRateGating:
    @staticmethod
    def _stub_status():
        return {
            'total': 100, 'completed': 50, 'failed': 5,
            'running': 30, 'queued': 15, 'timed_out': 0,
        }

    def test_mock_mode_synthesizes_rate(self, monkeypatch):
        monkeypatch.setattr(Config, 'SHOW_MOCK', True)
        from services import batch_tracker
        fake_co = MagicMock()
        fake_co.get_batch_status.return_value = self._stub_status()
        monkeypatch.setattr(batch_tracker, 'get_conductor_client', lambda: fake_co)
        s = batch_tracker.get_batch_status('wf')
        assert s['rate_per_min'] == 48
        assert s['eta_minutes'] is not None

    def test_real_mode_leaves_rate_null(self, monkeypatch):
        monkeypatch.setattr(Config, 'SHOW_MOCK', False)
        from services import batch_tracker
        fake_co = MagicMock()
        fake_co.get_batch_status.return_value = self._stub_status()
        monkeypatch.setattr(batch_tracker, 'get_conductor_client', lambda: fake_co)
        s = batch_tracker.get_batch_status('wf')
        assert s['rate_per_min'] is None
        assert s['eta_minutes'] is None


class TestMigrationVelocityGating:
    def test_mock_mode_returns_synthetic_velocity(self, monkeypatch):
        monkeypatch.setattr(Config, 'SHOW_MOCK', True)
        from services import migration_velocity
        result = migration_velocity.get_velocity_data('dev', days=7)
        assert result['target'] == migration_velocity.TOTAL_RECORDS_TARGET == 4312
        assert result['total_migrated'] > 0
        assert result['velocity_avg'] > 0
        assert len(result['daily']) == 8  # days=7 inclusive of today

    def test_real_mode_returns_empty_when_no_batches(self, monkeypatch):
        monkeypatch.setattr(Config, 'SHOW_MOCK', False)
        monkeypatch.setattr(Config, 'MIGRATION_RECORD_TARGET', 0)
        from services import migration_velocity
        monkeypatch.setattr(migration_velocity, '_get_batches_from_db', lambda org: [])
        result = migration_velocity.get_velocity_data('dev', days=7)
        assert result['total_migrated'] == 0
        assert result['velocity_avg'] == 0
        assert result['target'] == 0
        assert all(d['records'] == 0 for d in result['daily'])


class TestSchemaSnapshotGating:
    def test_list_returns_mock_when_no_db_and_mock(self, monkeypatch):
        monkeypatch.setattr(Config, 'SHOW_MOCK', True)
        from services import schema_snapshot
        monkeypatch.setattr(schema_snapshot, 'db_available', lambda: False)
        monkeypatch.setattr(schema_snapshot, '_ensure_table', lambda: None)
        result = schema_snapshot.list_snapshots()
        assert isinstance(result, list) and len(result) >= 1
        assert 'snapshot_label' in result[0]

    def test_list_returns_empty_when_no_db_and_real(self, monkeypatch):
        monkeypatch.setattr(Config, 'SHOW_MOCK', False)
        from services import schema_snapshot
        monkeypatch.setattr(schema_snapshot, 'db_available', lambda: False)
        monkeypatch.setattr(schema_snapshot, '_ensure_table', lambda: None)
        assert schema_snapshot.list_snapshots() == []

    def test_diff_returns_mock_when_no_db_and_mock(self, monkeypatch):
        monkeypatch.setattr(Config, 'SHOW_MOCK', True)
        from services import schema_snapshot
        monkeypatch.setattr(schema_snapshot, 'db_available', lambda: False)
        monkeypatch.setattr(schema_snapshot, '_ensure_table', lambda: None)
        result = schema_snapshot.diff_snapshots(1, 2)
        assert 'added' in result and 'removed' in result and 'summary' in result

    def test_diff_raises_when_no_db_and_real(self, monkeypatch):
        monkeypatch.setattr(Config, 'SHOW_MOCK', False)
        from services import schema_snapshot
        monkeypatch.setattr(schema_snapshot, 'db_available', lambda: False)
        monkeypatch.setattr(schema_snapshot, '_ensure_table', lambda: None)
        with pytest.raises(RuntimeError):
            schema_snapshot.diff_snapshots(1, 2)


class TestCrosswalkDivergenceGating:
    """The synthesized EDA/EC divergence in run_live_check only applies when
    SHOW_MOCK is on. In real mode the actual SF counts stand."""

    @staticmethod
    def _fake_sf(count):
        sf = MagicMock()
        sf.query.return_value = {'totalSize': count}
        return sf

    def test_mock_mode_applies_divergence(self, monkeypatch):
        monkeypatch.setattr(Config, 'SHOW_MOCK', True)
        from services import crosswalk_diff
        monkeypatch.setattr(crosswalk_diff, 'get_sf', lambda org: self._fake_sf(100))
        mappings = [{
            'status': 'Mapped',
            'eda_object': 'Account', 'eda_field': 'SIS_ID__c',
            'ec_object': 'Account', 'ec_field': 'SIS_ID__c',
        }]
        results = crosswalk_diff.run_live_check('dev', mappings)
        # Both sides query the same fake SF, but mock-mode divergence kicks in
        # because eda_covered == ec_covered triggers _mock_coverage.
        assert results[0]['eda_pct'] != results[0]['ec_pct']
        assert results[0]['gap'] != 0

    def test_real_mode_uses_actual_counts(self, monkeypatch):
        monkeypatch.setattr(Config, 'SHOW_MOCK', False)
        from services import crosswalk_diff
        monkeypatch.setattr(crosswalk_diff, 'get_sf', lambda org: self._fake_sf(100))
        mappings = [{
            'status': 'Mapped',
            'eda_object': 'Account', 'eda_field': 'SIS_ID__c',
            'ec_object': 'Account', 'ec_field': 'SIS_ID__c',
        }]
        results = crosswalk_diff.run_live_check('dev', mappings)
        # Identical counts on both sides + no mock-mode synthesis → gap is 0.
        assert results[0]['eda_pct'] == results[0]['ec_pct']
        assert results[0]['gap'] == 0


# ── UI signal context ────────────────────────────────────────────────────────

class TestShowMockTemplateContext:
    """The amber MOCK badge / show-mock meta tag in base.html keys off the
    show_mock_mode context variable, which mirrors Config.SHOW_MOCK."""

    def test_show_mock_mode_true_propagates_to_template_context(self, app, monkeypatch):
        monkeypatch.setattr(Config, 'SHOW_MOCK', True)
        ctx = {}
        with app.test_request_context('/'):
            app.update_template_context(ctx)  # mutates ctx in place
        assert ctx.get('show_mock_mode') is True

    def test_show_mock_mode_false_propagates_to_template_context(self, app, monkeypatch):
        monkeypatch.setattr(Config, 'SHOW_MOCK', False)
        ctx = {}
        with app.test_request_context('/'):
            app.update_template_context(ctx)
        assert ctx.get('show_mock_mode') is False
