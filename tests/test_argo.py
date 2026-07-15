"""Tests for services.argo — CronWorkflow generation + cron validation."""
import pytest

from config import Config
from services import argo


class TestValidateCron:
    @pytest.mark.parametrize('cron', ['0 6 * * 0', '*/15 * * * *', '0 0 1 1 *',
                                      '0 6 * * 1-5', '0 6,18 * * *'])
    def test_accepts_valid(self, cron):
        assert argo.validate_cron(cron) == cron

    def test_trims(self):
        assert argo.validate_cron('  0 6 * * 0  ') == '0 6 * * 0'

    @pytest.mark.parametrize('cron', ['', '   ', '0 6 * *', '0 6 * * 0 extra',
                                      'not a cron'])
    def test_rejects_invalid(self, cron):
        with pytest.raises(ValueError):
            argo.validate_cron(cron)


class TestSlug:
    def test_dns_safe(self):
        assert argo._slug('PTAT Weekly Load!') == 'ptat-weekly-load'

    def test_empty_falls_back(self):
        assert argo._slug('') == 'scenario'


class TestGenerateCronWorkflow:
    def test_contains_key_fields(self, monkeypatch):
        monkeypatch.setattr(Config, 'PUBLIC_BASE_URL',
                            'https://du-int.doane.edu/prod/sf-mission-control')
        out = argo.generate_cronworkflow(42, 'PTAT Weekly', '0 6 * * 0')
        assert 'kind: CronWorkflow' in out
        assert 'schedule: "0 6 * * 0"' in out
        assert 'sf-mc-scenario-42-ptat-weekly' in out
        assert '/api/v1/scenarios/42/scheduled-run' in out
        assert 'X-MC-Scheduler-Token: $MC_TOKEN' in out
        assert 'secretKeyRef' in out
        assert 'key: scheduler-token' in out
        assert 'namespace: prod' in out

    def test_curl_follows_redirects(self, monkeypatch):
        # -L is load-bearing: a manifest generated before the /api/v1 move
        # still targets the old bare path, which now only 308-redirects.
        # Without -L, `curl -f` treats a bare 3xx as success and the
        # CronWorkflow would report green having never run the scenario.
        out = argo.generate_cronworkflow(1, 'X', '0 0 * * *')
        assert 'curl -fsS -L -X POST' in out

    def test_uses_configured_base_url(self, monkeypatch):
        monkeypatch.setattr(Config, 'PUBLIC_BASE_URL', 'https://example.test/app/')
        out = argo.generate_cronworkflow(1, 'X', '0 0 * * *')
        # trailing slash trimmed, no double slash
        assert 'https://example.test/app/api/v1/scenarios/1/scheduled-run' in out

    def test_invalid_cron_raises(self):
        with pytest.raises(ValueError):
            argo.generate_cronworkflow(1, 'X', 'bad')

    def test_name_capped(self):
        out = argo.generate_cronworkflow(7, 'A' * 200, '0 0 * * *')
        # workflow name line stays reasonable (<= 52 chars after the prefix logic)
        name_line = [l for l in out.splitlines() if l.strip().startswith('name:')][0]
        wf_name = name_line.split('name:')[1].strip()
        assert len(wf_name) <= 52
        assert not wf_name.endswith('-')


class TestConfigDrivenDefaults:
    """namespace/timezone/secret_name/secret_key/image default to Config.ARGO_*
    -- resolved at call time so a Config change (or peer-institution env
    override) takes effect without needing this module reloaded."""

    def test_defaults_come_from_config(self, monkeypatch):
        monkeypatch.setattr(Config, 'ARGO_NAMESPACE', 'staging')
        monkeypatch.setattr(Config, 'ARGO_TIMEZONE', 'America/New_York')
        monkeypatch.setattr(Config, 'ARGO_SECRET_NAME', 'other-secrets')
        monkeypatch.setattr(Config, 'ARGO_SECRET_KEY', 'other-key')
        monkeypatch.setattr(Config, 'ARGO_IMAGE', 'curlimages/curl:9.0.0')
        out = argo.generate_cronworkflow(1, 'X', '0 0 * * *')
        assert 'namespace: staging' in out
        assert 'timezone: "America/New_York"' in out
        assert 'name: other-secrets' in out
        assert 'key: other-key' in out
        assert 'image: curlimages/curl:9.0.0' in out

    def test_explicit_kwargs_override_config(self, monkeypatch):
        monkeypatch.setattr(Config, 'ARGO_NAMESPACE', 'staging')
        out = argo.generate_cronworkflow(1, 'X', '0 0 * * *', namespace='dev')
        assert 'namespace: dev' in out
