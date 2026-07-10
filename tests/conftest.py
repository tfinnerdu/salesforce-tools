"""Shared fixtures for all test modules.

There is no mock-data layer. Tests that exercise Salesforce or Conductor patch
`get_sf` / `get_conductor_client` in the service module under test and supply a
`unittest.mock` double configured for that test. See tests/test_platform_events.py
for the canonical pattern.
"""
import os
import pytest

os.environ.setdefault('SECRET_KEY', 'test-secret')
os.environ.setdefault('DATABASE_URL', '')
os.environ.setdefault('SCHEDULER_ENABLED', 'false')


@pytest.fixture
def app():
    from app import create_app
    application = create_app()
    application.config['TESTING'] = True
    return application


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def session_client(client):
    """Client with active_org set in session."""
    with client.session_transaction() as sess:
        sess['active_org'] = 'dev'
    return client
