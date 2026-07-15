"""Tests targeting specific coverage gaps identified in pytest --cov output.

Covers: app.py, config.py, db.py, scheduler.py, sf_provider.py,
conductor_provider.py, and all service-layer exception/edge-case branches.

There is no mock-data layer — every Salesforce / Conductor interaction here is
exercised through a `unittest.mock` double patched into the service under test.
"""
import json
import os
import time
from contextlib import contextmanager
from unittest.mock import MagicMock, patch, call

import pytest

# ---------------------------------------------------------------------------
# app.py gaps
# ---------------------------------------------------------------------------

class TestAppLogout:
    def test_logout_clears_session_and_redirects(self, client):
        """Lines 42-44: logout route clears session and redirects."""
        with client.session_transaction() as sess:
            sess['active_org'] = 'prod'
        resp = client.get('/logout')
        assert resp.status_code == 302
        assert '/migration' in resp.headers['Location']
        with client.session_transaction() as sess:
            assert 'active_org' not in sess


class TestAppInitDb:
    def test_init_db_success_logs_info(self):
        """Line 48: init_db success path logs 'DB initialized'."""
        with patch('db.psycopg2.connect') as mock_connect:
            mock_conn = MagicMock()
            mock_cur = MagicMock()
            mock_conn.cursor.return_value.__enter__.return_value = mock_cur
            mock_conn.cursor.return_value.__exit__.return_value = False
            mock_connect.return_value = mock_conn
            with patch('app.logger') as mock_logger:
                from app import create_app
                create_app()
                # logger.info called with 'DB initialized' string at some point
                calls = [str(c) for c in mock_logger.info.call_args_list]
                assert any('DB initialized' in c or 'initialized' in c.lower() for c in calls)


class TestAppScheduler:
    def test_scheduler_enabled_calls_init_scheduler(self, monkeypatch):
        """When SCHEDULER_ENABLED is true, create_app calls init_scheduler."""
        from config import Config
        monkeypatch.setattr(Config, 'SCHEDULER_ENABLED', True)
        with patch('scheduler.init_scheduler') as mock_init_sched, \
             patch('app.init_db'):
            from app import create_app
            create_app()
            mock_init_sched.assert_called_once()


# ---------------------------------------------------------------------------
# config.py gaps
# ---------------------------------------------------------------------------

class TestGetOrgConfig:
    def test_get_org_config_returns_dict_for_prod(self):
        """Lines 9-10: get_org_config('prod') exercises the prefix logic."""
        from config import get_org_config
        result = get_org_config('prod')
        assert 'username' in result
        assert 'password' in result
        assert 'security_token' in result
        assert 'domain' in result

    def test_get_org_config_reads_env_vars(self):
        """Lines 9-10: get_org_config uses prefixed env vars."""
        with patch.dict(os.environ, {
            'SF_STAGING_USERNAME': 'user@test.com',
            'SF_STAGING_PASSWORD': 'pass123',
            'SF_STAGING_TOKEN': 'tok456',
            'SF_STAGING_DOMAIN': 'test',
        }):
            from config import get_org_config
            result = get_org_config('staging')
        assert result['username'] == 'user@test.com'
        assert result['password'] == 'pass123'
        assert result['security_token'] == 'tok456'
        assert result['domain'] == 'test'


# ---------------------------------------------------------------------------
# db.py gaps
# ---------------------------------------------------------------------------

class TestGetCursor:
    def _make_mock_conn(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_conn.cursor.return_value.__exit__.return_value = False
        return mock_conn, mock_cur

    def test_get_cursor_commits_on_success(self):
        """Lines 22-25: get_cursor commits the connection on normal exit."""
        mock_conn, mock_cur = self._make_mock_conn()
        with patch('db.psycopg2.connect', return_value=mock_conn):
            # Force reimport to get fresh module
            import importlib
            import db
            importlib.reload(db)
            with db.get_cursor() as cur:
                pass
            mock_conn.commit.assert_called_once()
            mock_conn.close.assert_called_once()

    def test_get_cursor_rollback_on_exception(self):
        """Lines 26-28: get_cursor rolls back when an exception occurs inside."""
        mock_conn, mock_cur = self._make_mock_conn()
        with patch('db.psycopg2.connect', return_value=mock_conn):
            import importlib
            import db
            importlib.reload(db)
            with pytest.raises(RuntimeError):
                with db.get_cursor() as cur:
                    raise RuntimeError("test error")
            mock_conn.rollback.assert_called_once()

    def test_get_cursor_always_closes(self):
        """Line 30: get_cursor closes connection in finally block even on error."""
        mock_conn, mock_cur = self._make_mock_conn()
        with patch('db.psycopg2.connect', return_value=mock_conn):
            import importlib
            import db
            importlib.reload(db)
            try:
                with db.get_cursor() as cur:
                    raise ValueError("boom")
            except ValueError:
                pass
            mock_conn.close.assert_called_once()


class TestInitDb:
    def test_init_db_success_logs_message(self):
        """Lines 71-72: init_db logs success message on normal execution."""
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_conn.cursor.return_value.__exit__.return_value = False
        with patch('db.psycopg2.connect', return_value=mock_conn):
            import importlib
            import db
            importlib.reload(db)
            with patch.object(db.logger, 'info') as mock_info:
                db.init_db()
                mock_info.assert_called_once_with("Database tables initialised.")


class TestDbAvailable:
    def test_db_available_returns_true_on_success(self):
        """Lines 82-83: db_available returns True when connection succeeds."""
        mock_conn = MagicMock()
        with patch('db.psycopg2.connect', return_value=mock_conn):
            import importlib
            import db
            importlib.reload(db)
            result = db.db_available()
        assert result is True
        mock_conn.close.assert_called_once()

    def test_db_available_returns_false_on_failure(self):
        """Line 85: db_available returns False when connection raises."""
        with patch('db.psycopg2.connect', side_effect=Exception("connection refused")):
            import importlib
            import db
            importlib.reload(db)
            result = db.db_available()
        assert result is False


# ---------------------------------------------------------------------------
# scheduler.py gaps
# ---------------------------------------------------------------------------

class TestScheduler:
    def test_init_scheduler_creates_background_scheduler(self):
        """Lines 23-35: init_scheduler creates BackgroundScheduler and starts it."""
        import importlib
        import scheduler as sched_mod
        importlib.reload(sched_mod)

        mock_app = MagicMock()
        with patch('scheduler.BackgroundScheduler') as mock_bs_class:
            mock_bs = MagicMock()
            mock_bs_class.return_value = mock_bs
            sched_mod.init_scheduler(mock_app)
            mock_bs_class.assert_called_once_with(timezone='America/Chicago')
            mock_bs.add_job.assert_called_once()
            mock_bs.start.assert_called_once()

    def test_init_scheduler_registers_cron_trigger_at_0600(self):
        """Lines 25-33: job is registered with cron trigger at hour=6, minute=0."""
        import importlib
        import scheduler as sched_mod
        importlib.reload(sched_mod)

        mock_app = MagicMock()
        with patch('scheduler.BackgroundScheduler') as mock_bs_class:
            mock_bs = MagicMock()
            mock_bs_class.return_value = mock_bs
            sched_mod.init_scheduler(mock_app)
            call_kwargs = mock_bs.add_job.call_args[1]
            assert call_kwargs['trigger'] == 'cron'
            assert call_kwargs['hour'] == 6
            assert call_kwargs['minute'] == 0
            assert call_kwargs['id'] == 'daily_readiness'

    def test_shutdown_scheduler_when_running(self):
        """Line 40: shutdown_scheduler calls shutdown when scheduler is running."""
        import importlib
        import scheduler as sched_mod
        importlib.reload(sched_mod)

        mock_bs = MagicMock()
        mock_bs.running = True
        sched_mod._scheduler = mock_bs
        sched_mod.shutdown_scheduler()
        mock_bs.shutdown.assert_called_once_with(wait=False)

    def test_shutdown_scheduler_when_not_running(self):
        """Line 39: shutdown_scheduler does not call shutdown when not running."""
        import importlib
        import scheduler as sched_mod
        importlib.reload(sched_mod)

        mock_bs = MagicMock()
        mock_bs.running = False
        sched_mod._scheduler = mock_bs
        sched_mod.shutdown_scheduler()
        mock_bs.shutdown.assert_not_called()

    def test_shutdown_scheduler_when_none(self):
        """Line 39: shutdown_scheduler does nothing when _scheduler is None."""
        import importlib
        import scheduler as sched_mod
        importlib.reload(sched_mod)

        sched_mod._scheduler = None
        # Should not raise
        sched_mod.shutdown_scheduler()

    def test_daily_readiness_run_calls_services(self):
        """Lines 11-19: _daily_readiness_run runs check and save within app context."""
        import importlib
        import scheduler as sched_mod
        importlib.reload(sched_mod)

        mock_app = MagicMock()
        mock_ctx = MagicMock()
        mock_app.app_context.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_app.app_context.return_value.__exit__ = MagicMock(return_value=False)

        mock_result = {'overall_pct': 95.0}
        # readiness_validator is imported inside the function body; patch via services package
        mock_rv = MagicMock()
        mock_rv.run_full_readiness_check.return_value = mock_result
        # Inject mock into sys.modules so the local import picks it up
        with patch.dict('sys.modules', {'services.readiness_validator': mock_rv,
                                         'services': MagicMock(readiness_validator=mock_rv)}):
            sched_mod._daily_readiness_run(mock_app)
        mock_rv.run_full_readiness_check.assert_called_once()
        mock_rv.save_run.assert_called_once()

    def test_daily_readiness_run_handles_exception(self):
        """Lines 18-19: _daily_readiness_run catches and logs exceptions."""
        import importlib
        import scheduler as sched_mod
        importlib.reload(sched_mod)

        mock_app = MagicMock()
        mock_app.app_context.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_app.app_context.return_value.__exit__ = MagicMock(return_value=False)

        mock_rv = MagicMock()
        mock_rv.run_full_readiness_check.side_effect = Exception("SF down")
        with patch.dict('sys.modules', {'services.readiness_validator': mock_rv,
                                         'services': MagicMock(readiness_validator=mock_rv)}):
            # Should not raise — exception is caught internally
            sched_mod._daily_readiness_run(mock_app)


# ---------------------------------------------------------------------------
# sf_provider.py gaps
# ---------------------------------------------------------------------------

class TestSfProviderConfigured:
    def test_configured_returns_false_without_credentials(self):
        """_configured returns False when env vars are absent."""
        from sf_provider import _configured
        with patch('sf_provider.get_org_config', return_value={'username': '', 'password': ''}):
            result = _configured('dev')
        assert result is False

    def test_configured_returns_true_with_credentials(self):
        """_configured returns True when both username and password are present."""
        from sf_provider import _configured
        with patch('sf_provider.get_org_config', return_value={
            'username': 'u@test.com', 'password': 'pass123'
        }):
            result = _configured('dev')
        assert result is True


class TestGetSfUnconfigured:
    def test_get_sf_raises_when_org_has_no_credentials(self):
        """get_sf raises RuntimeError for an org with no credentials — never fakes data."""
        import sf_provider
        with patch('sf_provider._configured', return_value=False):
            with pytest.raises(RuntimeError, match='no Salesforce credentials'):
                sf_provider.get_sf('dev')


class TestGetSfRealConnection:
    def test_get_sf_builds_real_salesforce_client_when_configured(self):
        """get_sf connects via simple_salesforce.Salesforce when the org is configured."""
        import sys
        import sf_provider

        # Salesforce is imported locally inside get_sf(); inject a stub module
        # so no real network connection is attempted.
        mock_sf_instance = MagicMock()
        mock_sf_class = MagicMock(return_value=mock_sf_instance)
        mock_simple_sf_module = MagicMock()
        mock_simple_sf_module.Salesforce = mock_sf_class

        cfg = {
            'username': 'u@test.com', 'password': 'pass', 'security_token': 'tok',
            'domain': 'login', 'api_version': '59.0',
        }
        with patch('sf_provider._configured', return_value=True), \
             patch('sf_provider.get_org_config', return_value=cfg), \
             patch.dict(sys.modules, {'simple_salesforce': mock_simple_sf_module}):
            result = sf_provider.get_sf('dev')

        mock_sf_class.assert_called_once()
        assert result is mock_sf_instance


class TestAvailableOrgs:
    def test_available_orgs_only_returns_configured_orgs(self):
        """available_orgs filters the candidate list to orgs with credentials."""
        import sf_provider
        with patch('sf_provider._configured', side_effect=lambda o: o == 'prod'):
            assert sf_provider.available_orgs() == ['prod']

    def test_available_orgs_empty_when_nothing_configured(self):
        import sf_provider
        with patch('sf_provider._configured', return_value=False):
            assert sf_provider.available_orgs() == []


# ---------------------------------------------------------------------------
# conductor_provider.py gaps
# ---------------------------------------------------------------------------

class TestConductorConfigured:
    def test_configured_returns_false_without_api_key(self):
        """Line 18: _configured returns False when CONDUCTOR_API_KEY is empty."""
        from conductor_provider import _configured
        with patch('conductor_provider.Config') as mock_cfg:
            mock_cfg.CONDUCTOR_URL = 'http://conductor:8080'
            mock_cfg.CONDUCTOR_API_KEY = ''
            result = _configured()
        assert result is False

    def test_configured_returns_true_with_credentials(self):
        """Line 18: _configured returns True when both URL and API key are present."""
        from conductor_provider import _configured
        with patch('conductor_provider.Config') as mock_cfg:
            mock_cfg.CONDUCTOR_URL = 'http://conductor:8080'
            mock_cfg.CONDUCTOR_API_KEY = 'my-api-key'
            result = _configured()
        assert result is True


class TestConductorClientInit:
    def test_init_strips_trailing_slash(self):
        """Lines 27-28: ConductorClient strips trailing slash from url."""
        from conductor_provider import ConductorClient
        client = ConductorClient('http://conductor:8080/', 'key123')
        assert client.base_url == 'http://conductor:8080'

    def test_init_sets_headers(self):
        """Lines 27-28: ConductorClient sets authorization header."""
        from conductor_provider import ConductorClient
        client = ConductorClient('http://conductor:8080', 'key123')
        assert client._headers['X-Authorization'] == 'key123'
        assert 'Content-Type' in client._headers


class TestConductorClientGet:
    def test_get_returns_json(self):
        """Lines 35-42: ConductorClient._get issues GET and returns parsed JSON."""
        import responses as responses_lib

        from conductor_provider import ConductorClient
        client = ConductorClient('http://conductor:8080', 'key123')

        with responses_lib.RequestsMock() as rsps:
            rsps.add(
                responses_lib.GET,
                'http://conductor:8080/api/test',
                json={'result': 'ok'},
                status=200,
            )
            result = client._get('/api/test')
        assert result == {'result': 'ok'}

    def test_get_raises_on_error_status(self):
        """Lines 35-42: _get raises HTTPError on non-2xx status."""
        import responses as responses_lib
        import requests

        from conductor_provider import ConductorClient
        client = ConductorClient('http://conductor:8080', 'key123')

        with responses_lib.RequestsMock() as rsps:
            rsps.add(
                responses_lib.GET,
                'http://conductor:8080/api/test',
                json={'error': 'not found'},
                status=404,
            )
            with pytest.raises(requests.exceptions.HTTPError):
                client._get('/api/test')


class TestConductorClientPost:
    def test_post_returns_json(self):
        """Lines 46-53: ConductorClient._post issues POST and returns parsed JSON."""
        import responses as responses_lib

        from conductor_provider import ConductorClient
        client = ConductorClient('http://conductor:8080', 'key123')

        with responses_lib.RequestsMock() as rsps:
            rsps.add(
                responses_lib.POST,
                'http://conductor:8080/api/workflow/start',
                json={'workflowId': 'wf-001'},
                status=200,
            )
            result = client._post('/api/workflow/start', json={'name': 'test'})
        assert result == {'workflowId': 'wf-001'}

    def test_post_raises_on_error_status(self):
        """Lines 46-53: _post raises HTTPError on non-2xx status."""
        import responses as responses_lib
        import requests

        from conductor_provider import ConductorClient
        client = ConductorClient('http://conductor:8080', 'key123')

        with responses_lib.RequestsMock() as rsps:
            rsps.add(
                responses_lib.POST,
                'http://conductor:8080/api/workflow/start',
                json={'error': 'bad request'},
                status=400,
            )
            with pytest.raises(requests.exceptions.HTTPError):
                client._post('/api/workflow/start')


class TestConductorClientGetBatchStatus:
    def test_get_batch_status_counts_statuses(self):
        """Lines 57-76: get_batch_status aggregates status counts."""
        import responses as responses_lib

        from conductor_provider import ConductorClient
        client = ConductorClient('http://conductor:8080', 'key123')

        mock_results = [
            {'status': 'COMPLETED'},
            {'status': 'COMPLETED'},
            {'status': 'FAILED'},
            {'status': 'RUNNING'},
            {'status': 'TIMED_OUT'},
            {'status': 'SCHEDULED'},
            {'status': 'PAUSED'},
            {'status': 'UNKNOWN_STATUS'},
        ]

        with responses_lib.RequestsMock() as rsps:
            rsps.add(
                responses_lib.GET,
                'http://conductor:8080/api/workflow/search',
                json={'results': mock_results},
                status=200,
            )
            result = client.get_batch_status('TestWorkflow')

        assert result['completed'] == 2
        assert result['failed'] == 1
        assert result['running'] == 1
        assert result['timed_out'] == 1
        assert result['queued'] == 2
        assert result['total'] == 7  # UNKNOWN_STATUS is not counted in any bucket

    def test_get_batch_status_with_start_time(self):
        """Lines 58-59: start_time_ms is passed as param when provided."""
        import responses as responses_lib

        from conductor_provider import ConductorClient
        client = ConductorClient('http://conductor:8080', 'key123')

        with responses_lib.RequestsMock() as rsps:
            rsps.add(
                responses_lib.GET,
                'http://conductor:8080/api/workflow/search',
                json={'results': []},
                status=200,
            )
            result = client.get_batch_status('TestWorkflow', start_time_ms=1700000000000)
            request_params = rsps.calls[0].request.url
            assert 'startTime' in request_params

        assert result['total'] == 0


class TestConductorClientSearchWorkflows:
    def test_search_workflows_returns_results_list(self):
        """Lines 81-89: search_workflows returns list from results key."""
        import responses as responses_lib

        from conductor_provider import ConductorClient
        client = ConductorClient('http://conductor:8080', 'key123')

        mock_wfs = [
            {'workflowId': 'wf-001', 'status': 'FAILED'},
            {'workflowId': 'wf-002', 'status': 'FAILED'},
        ]

        with responses_lib.RequestsMock() as rsps:
            rsps.add(
                responses_lib.GET,
                'http://conductor:8080/api/workflow/search',
                json={'results': mock_wfs},
                status=200,
            )
            result = client.search_workflows('TestWorkflow', 'FAILED')

        assert len(result) == 2
        assert result[0]['workflowId'] == 'wf-001'

    def test_search_workflows_with_start_time(self):
        """Lines 87: startTimeFrom param is added when start_time_ms provided."""
        import responses as responses_lib

        from conductor_provider import ConductorClient
        client = ConductorClient('http://conductor:8080', 'key123')

        with responses_lib.RequestsMock() as rsps:
            rsps.add(
                responses_lib.GET,
                'http://conductor:8080/api/workflow/search',
                json={'results': []},
                status=200,
            )
            client.search_workflows('TestWorkflow', 'FAILED', start_time_ms=1700000000000)
            request_url = rsps.calls[0].request.url
            assert 'startTimeFrom' in request_url


class TestConductorClientGetWorkflowDetail:
    def test_get_workflow_detail_returns_detail(self):
        """Line 94: get_workflow_detail hits the correct endpoint."""
        import responses as responses_lib

        from conductor_provider import ConductorClient
        client = ConductorClient('http://conductor:8080', 'key123')

        mock_detail = {'workflowId': 'wf-001', 'status': 'FAILED', 'tasks': []}

        with responses_lib.RequestsMock() as rsps:
            rsps.add(
                responses_lib.GET,
                'http://conductor:8080/api/workflow/wf-001',
                json=mock_detail,
                status=200,
            )
            result = client.get_workflow_detail('wf-001')

        assert result['workflowId'] == 'wf-001'


class TestConductorClientRetryWorkflow:
    def test_retry_workflow_returns_status_code(self):
        """Lines 99-104: retry_workflow returns dict with workflow_id and status_code."""
        import responses as responses_lib

        from conductor_provider import ConductorClient
        client = ConductorClient('http://conductor:8080', 'key123')

        with responses_lib.RequestsMock() as rsps:
            rsps.add(
                responses_lib.POST,
                'http://conductor:8080/api/workflow/wf-001/retry',
                json={},
                status=200,
            )
            result = client.retry_workflow('wf-001')

        assert result['workflow_id'] == 'wf-001'
        assert result['status_code'] == 200


class TestGetConductorClientUnconfigured:
    def test_get_conductor_client_raises_when_not_configured(self):
        """get_conductor_client raises RuntimeError when Conductor is not configured."""
        import conductor_provider
        with patch('conductor_provider._configured', return_value=False):
            with pytest.raises(RuntimeError, match='not configured'):
                conductor_provider.get_conductor_client()


class TestGetConductorClientRealPath:
    def test_get_conductor_client_returns_real_client_when_configured(self):
        """get_conductor_client returns a live ConductorClient when configured."""
        import conductor_provider
        from conductor_provider import ConductorClient
        with patch('conductor_provider._configured', return_value=True), \
             patch('conductor_provider.Config') as mock_cfg:
            mock_cfg.CONDUCTOR_URL = 'http://conductor:8080'
            mock_cfg.CONDUCTOR_API_KEY = 'real-key'
            mock_cfg.SHOW_MOCK = False
            result = conductor_provider.get_conductor_client()
        assert isinstance(result, ConductorClient)
        assert result.base_url == 'http://conductor:8080'


# ---------------------------------------------------------------------------
# services/batch_tracker.py gaps
# ---------------------------------------------------------------------------

class TestBatchTrackerFailureReasonsJsonError:
    def test_get_failure_reasons_handles_invalid_json_input(self):
        """Lines 59-60: json.loads exception is caught and workflow_id used as fallback."""
        from services.batch_tracker import get_failure_reasons
        bad_workflow = {
            'workflowId': 'wf-bad-json',
            'status': 'FAILED',
            'reasonForIncompletion': 'TIMEOUT',
            'input': '{invalid json!!!',
        }
        mock_client = MagicMock()
        mock_client.search_workflows.return_value = [bad_workflow]
        with patch('services.batch_tracker.get_conductor_client', return_value=mock_client):
            result = get_failure_reasons('TestWorkflow')
        assert result['total_failures'] == 1
        # SIS ID fallback is the workflowId
        assert 'TIMEOUT' in result['breakdown']
        sis_ids = result['sis_ids_by_error']['TIMEOUT']
        assert 'wf-bad-json' in sis_ids


class TestBatchTrackerRerunException:
    def test_rerun_workflows_exception_returns_500_entry(self):
        """Lines 81-83: exception during retry is caught, 500 entry added."""
        from services.batch_tracker import rerun_workflows
        mock_client = MagicMock()
        mock_client.retry_workflow.side_effect = Exception("connection refused")
        with patch('services.batch_tracker.get_conductor_client', return_value=mock_client):
            with patch('services.batch_tracker.time') as mock_time:
                mock_time.sleep = MagicMock()
                results = rerun_workflows(['wf-fail-001'])
        assert len(results) == 1
        assert results[0]['success'] is False
        assert results[0]['status_code'] == 500
        assert results[0]['workflow_id'] == 'wf-fail-001'


# ---------------------------------------------------------------------------
# services/contactpoint_scanner.py gaps
# ---------------------------------------------------------------------------

class TestContactpointScannerErrorBranch:
    def test_scan_error_branch_on_exception(self):
        """Lines 51-53: scan() catches exception and sets status=error for that type."""
        from services.contactpoint_scanner import scan
        mock_sf = MagicMock()
        mock_sf.query.side_effect = Exception("SF query failed")
        with patch('services.contactpoint_scanner.get_sf', return_value=mock_sf):
            result = scan('dev')
        # All three CP types should have error status
        for cp_type in ['ContactPointEmail', 'ContactPointPhone', 'ContactPointAddress']:
            assert result[cp_type]['status'] == 'error'
            assert 'error' in result[cp_type]


# ---------------------------------------------------------------------------
# services/duplicate_radar.py gaps
# ---------------------------------------------------------------------------

class TestDuplicateRadarNameDobDupes:
    def test_scan_same_name_dob_records_with_dupes(self):
        """Lines 48-49: records list is populated when actual dupes found."""
        from services.duplicate_radar import _scan_same_name_dob
        mock_sf = MagicMock()
        # Two records with same name and DOB
        mock_sf.query_all.return_value = {
            'totalSize': 2,
            'done': True,
            'records': [
                {'Id': '001AAA', 'Name': 'John Smith', 'PersonBirthdate': '1990-01-01'},
                {'Id': '001BBB', 'Name': 'John Smith', 'PersonBirthdate': '1990-01-01'},
            ],
        }
        result = _scan_same_name_dob(mock_sf)
        assert result['count'] == 1
        assert len(result['records']) == 1
        assert result['records'][0]['name'] == 'john smith'
        assert result['records'][0]['dob'] == '1990-01-01'
        assert result['status'] == 'red'


class TestDuplicateRadarMergeExceptions:
    def test_merge_attribute_error_returns_failure(self):
        """An AttributeError raised by Account.merge is caught and reported as a failure."""
        from services.duplicate_radar import merge
        mock_sf = MagicMock()
        # Make Account.merge raise AttributeError
        mock_sf.Account.merge.side_effect = AttributeError("no merge method")
        with patch('services.duplicate_radar.get_sf', return_value=mock_sf):
            result = merge('dev', '001AAA', '001BBB')
        assert result['success'] is False

    def test_merge_general_exception_returns_failure(self):
        """Lines 115-117: general exception sets success=False."""
        from services.duplicate_radar import merge
        mock_sf = MagicMock()
        mock_sf.Account.merge.side_effect = RuntimeError("server error")
        with patch('services.duplicate_radar.get_sf', return_value=mock_sf):
            result = merge('dev', '001AAA', '001BBB')
        assert result['success'] is False


# ---------------------------------------------------------------------------
# services/error_reconciler.py gaps
# ---------------------------------------------------------------------------

class TestErrorReconcilerJsonError:
    def test_categorize_failures_handles_invalid_json(self):
        """Lines 72-73: json.loads exception in categorize sets empty sis_id."""
        from services.error_reconciler import categorize_conductor_failures
        bad_workflow = {
            'workflowId': 'wf-bad',
            'status': 'FAILED',
            'reasonForIncompletion': 'DUPLICATE_VALUE: something',
            'input': 'NOT_JSON',
        }
        mock_client = MagicMock()
        mock_client.search_workflows.return_value = [bad_workflow]
        with patch('services.error_reconciler.get_conductor_client', return_value=mock_client):
            result = categorize_conductor_failures('TestWorkflow')
        assert len(result) > 0
        # sis_ids list should be empty for this entry since json failed
        dup_entry = next((c for c in result if c['error_code'] == 'DUPLICATE_VALUE'), None)
        assert dup_entry is not None
        assert dup_entry['count'] == 1
        assert dup_entry['sis_ids'] == []


class TestErrorReconcilerRerunException:
    def test_rerun_workflows_exception_returns_500_entry(self):
        """Lines 109-111: exception during retry is caught and 500 entry returned."""
        from services.error_reconciler import rerun_workflows
        mock_client = MagicMock()
        mock_client.retry_workflow.side_effect = Exception("network error")
        with patch('services.error_reconciler.get_conductor_client', return_value=mock_client):
            with patch('services.error_reconciler.time') as mock_time:
                mock_time.sleep = MagicMock()
                results = rerun_workflows(['wf-err-001'])
        assert len(results) == 1
        assert results[0]['success'] is False
        assert results[0]['status_code'] == 500


# ---------------------------------------------------------------------------
# services/readiness_validator.py gaps
# ---------------------------------------------------------------------------

class TestReadinessValidatorCheckDuplicatesZeroTotal:
    def test_check_duplicates_zero_total_returns_100(self):
        """Lines 181-184: when total is 0, pct defaults to 100.0."""
        from services.readiness_validator import check_duplicates
        mock_sf = MagicMock()
        mock_sf.query_all.return_value = {
            'totalSize': 0,
            'done': True,
            'records': [],
        }
        result = check_duplicates(mock_sf)
        assert result['pct'] == 100.0
        assert result['total'] == 0


class TestReadinessValidatorSaveRunSuccess:
    def test_save_run_executes_insert_when_db_available(self):
        """Line 196: save_run executes INSERT when DB cursor works."""
        from services.readiness_validator import save_run
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_conn.cursor.return_value.__exit__.return_value = False
        with patch('db.psycopg2.connect', return_value=mock_conn):
            import importlib
            import db
            importlib.reload(db)
            save_run('dev', {'overall_pct': 95.0, 'checks': []})
        mock_cur.execute.assert_called_once()
        call_args = mock_cur.execute.call_args[0]
        assert 'INSERT INTO readiness_runs' in call_args[0]


class TestReadinessValidatorGetHistorySuccess:
    def test_get_history_returns_rows_when_db_available(self):
        """Lines 207-213: get_history returns list of dicts on success."""
        from services.readiness_validator import get_history
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        # fetchall returns list of dict-like rows
        mock_cur.fetchall.return_value = [
            {'id': 1, 'org': 'dev', 'run_at': '2024-01-01', 'results': '{}', 'overall_pct': 95.0},
        ]
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_conn.cursor.return_value.__exit__.return_value = False
        with patch('db.psycopg2.connect', return_value=mock_conn):
            import importlib
            import db
            importlib.reload(db)
            result = get_history('dev')
        assert len(result) == 1
        assert result[0]['org'] == 'dev'

    def test_get_history_returns_empty_list_on_exception(self):
        """Line 216: get_history returns [] on exception."""
        from services.readiness_validator import get_history
        with patch('db.psycopg2.connect', side_effect=Exception("no db")):
            import importlib
            import db
            importlib.reload(db)
            result = get_history('dev')
        assert result == []


# ---------------------------------------------------------------------------
# services/schema_diff.py gaps
# ---------------------------------------------------------------------------

class TestSchemaDiffRunDiffException:
    def test_run_diff_exception_stored_as_error(self):
        """Lines 104-106: when get_object_schema raises, error is stored in results."""
        from services.schema_diff import run_diff
        mock_sf = MagicMock()
        mock_sf.restful.side_effect = Exception("describe failed")
        # run_diff calls assert_orgs_comparable first — both orgs must look configured.
        with patch('sf_provider._configured', return_value=True), \
             patch('services.schema_diff.get_sf', return_value=mock_sf):
            result = run_diff('dev', 'prod', objects=['Account'])
        assert 'Account' in result['objects']
        assert 'error' in result['objects']['Account']
        assert 'describe failed' in result['objects']['Account']['error']


# ---------------------------------------------------------------------------
# Additional readiness status branches
# ---------------------------------------------------------------------------

class TestReadinessValidatorAmberAndGreenStatus:
    def _make_amber_sf(self):
        """Return a mock SF where all pct checks land at 95% (amber range)."""
        mock_sf = MagicMock()
        # check_duplicates uses query_all — return 100 unique SIS IDs (0 dupes → green for dupes)
        mock_sf.query_all.return_value = {
            'totalSize': 100,
            'done': True,
            'records': [{'Id': f'001{i:015d}', 'SIS_ID__c': f'STU{i:05d}'} for i in range(100)],
        }
        # All sf.query() calls: total COUNT returns 100, covered-count queries return 95
        def mock_query(soql):
            soql_lower = soql.lower()
            if 'where' not in soql_lower:
                return {'totalSize': 100, 'done': True, 'records': []}
            # Queries using "= null" (missing) return 5; "!= null" (covered) return 95
            if '= null' in soql_lower and '!= null' not in soql_lower:
                return {'totalSize': 5, 'done': True, 'records': []}
            return {'totalSize': 95, 'done': True, 'records': []}
        mock_sf.query.side_effect = mock_query
        return mock_sf

    def test_run_full_readiness_check_amber_status(self):
        """overall_status='amber' when no red but some amber."""
        from services.readiness_validator import run_full_readiness_check
        mock_sf = self._make_amber_sf()
        with patch('services.readiness_validator.get_sf', return_value=mock_sf):
            result = run_full_readiness_check('dev')
        assert result['overall_status'] == 'amber'

    def test_run_full_readiness_check_green_status(self):
        """overall_status='green' when all checks are 100%."""
        from services.readiness_validator import run_full_readiness_check
        mock_sf = MagicMock()
        def mock_query_green(soql):
            soql_lower = soql.lower()
            if 'where' not in soql_lower:
                return {'totalSize': 100, 'done': True, 'records': []}
            # Missing queries (= null) return 0; covered queries (!= null) return 100
            if '= null' in soql_lower and '!= null' not in soql_lower:
                return {'totalSize': 0, 'done': True, 'records': []}
            return {'totalSize': 100, 'done': True, 'records': []}
        mock_sf.query.side_effect = mock_query_green
        mock_sf.query_all.return_value = {
            'totalSize': 100,
            'done': True,
            'records': [{'Id': f'001{i:015d}', 'SIS_ID__c': f'STU{i:05d}'} for i in range(100)],
        }
        with patch('services.readiness_validator.get_sf', return_value=mock_sf):
            result = run_full_readiness_check('dev')
        assert result['overall_status'] == 'green'


class TestDuplicateRadarMergeSuccessLine111:
    def test_merge_succeeds_without_exception(self):
        """duplicate_radar.py line 111: success=True set after merge() completes normally."""
        from services.duplicate_radar import merge
        mock_sf = MagicMock()
        # Account.merge returns normally (no exception)
        mock_sf.Account.merge.return_value = None
        with patch('services.duplicate_radar.get_sf', return_value=mock_sf):
            result = merge('dev', '001AAA', '001BBB')
        assert result['success'] is True
        mock_sf.Account.merge.assert_called_once_with('001AAA', ['001BBB'])


# ---------------------------------------------------------------------------
# conftest.py fixture coverage
# ---------------------------------------------------------------------------

def test_session_client_fixture_sets_active_org(session_client):
    """tests/conftest.py: session_client fixture sets active_org in session."""
    # Simply using the fixture exercises the fixture body
    resp = session_client.get('/migration/readiness')
    assert resp.status_code == 200


class TestSettingsCollectionsCreateJsonException:
    def test_collections_create_json_exception_returns_500(self, client):
        """routes/settings_routes.py lines 75-77: exception in create_collection."""
        with patch(
            'routes.settings_routes.collection_manager.create_collection',
            side_effect=Exception("db write failed"),
        ):
            resp = client.post(
                '/api/v1/settings/collections',
                json={
                    'name': 'Test Collection',
                    'collection_json': {'info': {'name': 'test'}, 'item': []},
                },
            )
        assert resp.status_code == 500
        d = resp.get_json()
        assert d['success'] is False
        assert 'db write failed' in d['error']
