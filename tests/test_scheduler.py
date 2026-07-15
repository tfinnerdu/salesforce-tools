"""Tests for scheduler.py — APScheduler wiring.

TESTING.md previously claimed this file was already unit-tested ("Scheduler
init tests (BackgroundScheduler mocked)") but no such test file existed. This
closes that gap for real.
"""
from unittest.mock import MagicMock, patch

import scheduler
from config import Config


def _fake_app():
    app = MagicMock()
    app.app_context.return_value.__enter__ = MagicMock()
    app.app_context.return_value.__exit__ = MagicMock(return_value=False)
    return app


def test_init_scheduler_uses_configured_timezone(monkeypatch):
    monkeypatch.setattr(Config, 'SCHEDULER_TIMEZONE', 'America/New_York')
    monkeypatch.setattr(Config, 'BACKUP_ENABLED', False)
    with patch('scheduler.BackgroundScheduler') as MockScheduler:
        instance = MockScheduler.return_value
        instance.running = False
        scheduler.init_scheduler(_fake_app())
    MockScheduler.assert_called_once_with(timezone='America/New_York')


def test_init_scheduler_registers_daily_readiness_job():
    with patch('scheduler.BackgroundScheduler') as MockScheduler:
        instance = MockScheduler.return_value
        scheduler.init_scheduler(_fake_app())
    job_ids = [c.kwargs.get('id') for c in instance.add_job.call_args_list]
    assert 'daily_readiness' in job_ids


def test_init_scheduler_skips_backup_job_when_disabled(monkeypatch):
    monkeypatch.setattr(Config, 'BACKUP_ENABLED', False)
    with patch('scheduler.BackgroundScheduler') as MockScheduler:
        instance = MockScheduler.return_value
        scheduler.init_scheduler(_fake_app())
    job_ids = [c.kwargs.get('id') for c in instance.add_job.call_args_list]
    assert 'nightly_backup' not in job_ids


def test_init_scheduler_registers_backup_job_when_enabled(monkeypatch):
    monkeypatch.setattr(Config, 'BACKUP_ENABLED', True)
    with patch('scheduler.BackgroundScheduler') as MockScheduler:
        instance = MockScheduler.return_value
        scheduler.init_scheduler(_fake_app())
    job_ids = [c.kwargs.get('id') for c in instance.add_job.call_args_list]
    assert 'nightly_backup' in job_ids


def test_init_scheduler_starts_the_scheduler():
    with patch('scheduler.BackgroundScheduler') as MockScheduler:
        instance = MockScheduler.return_value
        scheduler.init_scheduler(_fake_app())
    instance.start.assert_called_once()


def test_shutdown_scheduler_stops_running_scheduler():
    with patch('scheduler.BackgroundScheduler') as MockScheduler:
        instance = MockScheduler.return_value
        instance.running = True
        scheduler.init_scheduler(_fake_app())
        scheduler.shutdown_scheduler()
    instance.shutdown.assert_called_once_with(wait=False)


def test_shutdown_scheduler_noop_when_not_running():
    with patch('scheduler.BackgroundScheduler') as MockScheduler:
        instance = MockScheduler.return_value
        instance.running = False
        scheduler.init_scheduler(_fake_app())
        scheduler.shutdown_scheduler()
    instance.shutdown.assert_not_called()


def test_daily_readiness_run_calls_readiness_validator():
    app = _fake_app()
    with patch('services.readiness_validator.run_full_readiness_check',
               return_value={'overall_pct': 87}) as run_check, \
            patch('services.readiness_validator.save_run') as save_run:
        scheduler._daily_readiness_run(app)
    run_check.assert_called_once_with(Config.DEFAULT_ORG)
    save_run.assert_called_once_with(Config.DEFAULT_ORG, {'overall_pct': 87})


def test_daily_readiness_run_swallows_exceptions():
    app = _fake_app()
    with patch('services.readiness_validator.run_full_readiness_check',
               side_effect=RuntimeError('boom')):
        scheduler._daily_readiness_run(app)  # must not raise


def test_nightly_backup_run_calls_data_backup():
    app = _fake_app()
    with patch('services.data_backup.run_backup',
               return_value={'run_id': 1, 'total_records': 10}) as run_backup:
        scheduler._nightly_backup_run(app)
    run_backup.assert_called_once_with(Config.DEFAULT_ORG, trigger='scheduled')


def test_nightly_backup_run_swallows_exceptions():
    app = _fake_app()
    with patch('services.data_backup.run_backup', side_effect=RuntimeError('boom')):
        scheduler._nightly_backup_run(app)  # must not raise
