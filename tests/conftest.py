"""Shared fixtures for all test modules."""
import os
import pytest

# Force mock mode so tests never need real credentials
os.environ.setdefault('SF_MOCK', 'true')
os.environ.setdefault('CONDUCTOR_MOCK', 'true')
os.environ.setdefault('SECRET_KEY', 'test-secret')
os.environ.setdefault('DATABASE_URL', '')
os.environ.setdefault('SCHEDULER_ENABLED', 'false')


@pytest.fixture
def mock_sf():
    from sf_provider import MockSalesforce
    return MockSalesforce('dev')


@pytest.fixture
def mock_conductor():
    from conductor_provider import MockConductorClient
    return MockConductorClient()


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
