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
        assert '/scenarios/42/scheduled-run' in out
        assert 'X-MC-Scheduler-Token: $MC_TOKEN' in out
        assert 'secretKeyRef' in out
        assert 'key: scheduler-token' in out
        assert 'namespace: prod' in out

    def test_uses_configured_base_url(self, monkeypatch):
        monkeypatch.setattr(Config, 'PUBLIC_BASE_URL', 'https://example.test/app/')
        out = argo.generate_cronworkflow(1, 'X', '0 0 * * *')
        # trailing slash trimmed, no double slash
        assert 'https://example.test/app/scenarios/1/scheduled-run' in out

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
