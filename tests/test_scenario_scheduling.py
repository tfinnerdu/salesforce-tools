"""Route tests for scenario scheduling — approve, argo-manifest, scheduled-run.

Service layer is patched (it's unit-tested in test_scenarios.py); these verify
the token gating, approval gating, run-status → HTTP-status mapping, and the
manifest endpoint wiring.
"""
import pytest

from config import Config
import routes.scenarios as route

TOKEN = 'sekret-token'


@pytest.fixture
def with_token(monkeypatch):
    monkeypatch.setattr(Config, 'SCHEDULER_TOKEN', TOKEN)


# ── approve ──────────────────────────────────────────────────────────────────

class TestApprove:
    def test_approve_sets_flag(self, client, monkeypatch):
        monkeypatch.setattr(route.scenarios_svc, 'set_schedule_approved',
                            lambda i, a: {'id': i, 'schedule_approved': a})
        resp = client.post('/scenarios/3/approve', json={'approved': True})
        assert resp.status_code == 200
        assert resp.get_json()['data']['schedule_approved'] is True

    def test_approve_404_when_missing(self, client, monkeypatch):
        monkeypatch.setattr(route.scenarios_svc, 'set_schedule_approved',
                            lambda i, a: None)
        assert client.post('/scenarios/9/approve', json={'approved': True}).status_code == 404


# ── argo-manifest ────────────────────────────────────────────────────────────

class TestArgoManifest:
    def test_generates_yaml(self, client, monkeypatch):
        monkeypatch.setattr(route.scenarios_svc, 'get_scenario',
                            lambda i: {'id': i, 'name': 'PTAT Weekly'})
        resp = client.post('/scenarios/5/argo-manifest', json={'schedule': '0 6 * * 0'})
        assert resp.status_code == 200
        manifest = resp.get_json()['data']['manifest']
        assert 'kind: CronWorkflow' in manifest
        assert '/scenarios/5/scheduled-run' in manifest

    def test_bad_cron_400(self, client, monkeypatch):
        monkeypatch.setattr(route.scenarios_svc, 'get_scenario',
                            lambda i: {'id': i, 'name': 'X'})
        resp = client.post('/scenarios/5/argo-manifest', json={'schedule': 'nope'})
        assert resp.status_code == 400

    def test_404_when_scenario_missing(self, client, monkeypatch):
        monkeypatch.setattr(route.scenarios_svc, 'get_scenario', lambda i: None)
        assert client.post('/scenarios/5/argo-manifest',
                           json={'schedule': '0 6 * * 0'}).status_code == 404


# ── scheduled-run (token + approval gating) ──────────────────────────────────

class TestScheduledRun:
    def test_401_without_token(self, client, with_token):
        # No header → unauthorized.
        resp = client.post('/scenarios/1/scheduled-run')
        assert resp.status_code == 401
        assert resp.get_json()['code'] == 'SCHEDULER_UNAUTHORIZED'

    def test_401_with_wrong_token(self, client, with_token):
        resp = client.post('/scenarios/1/scheduled-run',
                           headers={'X-MC-Scheduler-Token': 'wrong'})
        assert resp.status_code == 401

    def test_disabled_when_no_token_configured(self, client, monkeypatch):
        monkeypatch.setattr(Config, 'SCHEDULER_TOKEN', '')
        resp = client.post('/scenarios/1/scheduled-run',
                           headers={'X-MC-Scheduler-Token': 'anything'})
        assert resp.status_code == 401

    def test_403_when_not_approved(self, client, with_token, monkeypatch):
        monkeypatch.setattr(route.scenarios_svc, 'get_scenario',
                            lambda i: {'id': i, 'name': 'X', 'org': 'dev',
                                       'schedule_approved': False})
        resp = client.post('/scenarios/1/scheduled-run',
                           headers={'X-MC-Scheduler-Token': TOKEN})
        assert resp.status_code == 403
        assert resp.get_json()['code'] == 'NOT_SCHEDULE_APPROVED'

    def test_404_when_missing(self, client, with_token, monkeypatch):
        monkeypatch.setattr(route.scenarios_svc, 'get_scenario', lambda i: None)
        resp = client.post('/scenarios/1/scheduled-run',
                           headers={'X-MC-Scheduler-Token': TOKEN})
        assert resp.status_code == 404

    def test_success_returns_200(self, client, with_token, monkeypatch):
        monkeypatch.setattr(route.scenarios_svc, 'get_scenario',
                            lambda i: {'id': i, 'name': 'PTAT', 'org': 'prod',
                                       'schedule_approved': True})
        monkeypatch.setattr(route.scenarios_svc, 'run_scenario',
                            lambda i, org: {'run_id': 9, 'status': 'success',
                                            'step_results': [{'status': 'success'}]})
        resp = client.post('/scenarios/1/scheduled-run',
                           headers={'X-MC-Scheduler-Token': TOKEN})
        assert resp.status_code == 200
        assert resp.get_json()['success'] is True

    def test_failed_run_returns_500_for_argo_visibility(self, client, with_token, monkeypatch):
        monkeypatch.setattr(route.scenarios_svc, 'get_scenario',
                            lambda i: {'id': i, 'name': 'PTAT', 'org': 'prod',
                                       'schedule_approved': True})
        monkeypatch.setattr(route.scenarios_svc, 'run_scenario',
                            lambda i, org: {'run_id': 9, 'status': 'failed',
                                            'step_results': [{'status': 'failed'}]})
        resp = client.post('/scenarios/1/scheduled-run',
                           headers={'X-MC-Scheduler-Token': TOKEN})
        # Non-clean run → 500 so `curl -f` fails and Argo flags the workflow.
        assert resp.status_code == 500
        assert resp.get_json()['success'] is False

    def test_uses_scenario_org_not_session(self, client, with_token, monkeypatch):
        captured = {}
        monkeypatch.setattr(route.scenarios_svc, 'get_scenario',
                            lambda i: {'id': i, 'name': 'X', 'org': 'sandbox',
                                       'schedule_approved': True})
        def _run(i, org):
            captured['org'] = org
            return {'run_id': 1, 'status': 'success', 'step_results': []}
        monkeypatch.setattr(route.scenarios_svc, 'run_scenario', _run)
        client.post('/scenarios/1/scheduled-run',
                    headers={'X-MC-Scheduler-Token': TOKEN})
        assert captured['org'] == 'sandbox'
