"""Tests for services.data_backup — CSV snapshot capture, storage, archive."""
import gzip
import io
import zipfile

import pytest

from services import data_backup


# ── Fake DB cursor ────────────────────────────────────────────────────────────

class _FakeCursor:
    def __init__(self, fetchone=None, fetchall=None):
        self._fetchone = fetchone
        self._fetchall = fetchall or []
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchone(self):
        return self._fetchone

    def fetchall(self):
        return self._fetchall


# ── Fake Salesforce client ────────────────────────────────────────────────────

class _StubSF:
    """Returns a controlled describe + query result."""
    def __init__(self, fields, records):
        self._fields = fields
        self._records = records

    def restful(self, path, **kw):
        return {'fields': self._fields}

    def query_all(self, soql):
        return {'records': self._records}


def _default_sf():
    return _StubSF(
        fields=[{'name': 'Id', 'type': 'id'}, {'name': 'Name', 'type': 'string'}],
        records=[{'Id': '001', 'Name': 'Acme'}],
    )


# ── _export_object ────────────────────────────────────────────────────────────

def test_export_object_skips_compound_and_base64_fields():
    sf = _StubSF(
        fields=[
            {'name': 'Id', 'type': 'id'},
            {'name': 'Name', 'type': 'string'},
            {'name': 'Photo', 'type': 'base64'},        # skipped
            {'name': 'BillingAddress', 'type': 'address'},  # skipped
        ],
        records=[{'Id': '001', 'Name': 'Acme'}],
    )
    csv_text, count = data_backup._export_object(sf, 'Account')
    assert count == 1
    header = csv_text.splitlines()[0]
    assert 'Id' in header and 'Name' in header
    assert 'Photo' not in header and 'BillingAddress' not in header


# ── run_backup — no DB ────────────────────────────────────────────────────────

def test_run_backup_builds_manifest(monkeypatch):
    monkeypatch.setattr(data_backup, 'get_sf', lambda org: _default_sf())
    result = data_backup.run_backup('dev', ['Account'])
    assert result['status'] in ('success', 'partial')
    assert result['object_count'] >= 1
    assert result['persisted'] is False        # no DB in the test env
    assert result['objects'][0]['object'] == 'Account'
    assert result['total_records'] >= 1


def test_run_backup_records_per_object_failures(monkeypatch):
    """An object whose export fails is reported in errors, others still run."""
    monkeypatch.setattr(data_backup, 'get_sf', lambda org: _default_sf())
    real_export = data_backup._export_object

    def _flaky(sf, obj):
        if obj == 'BadObject':
            raise RuntimeError('INVALID_TYPE')
        return real_export(sf, obj)

    monkeypatch.setattr(data_backup, '_export_object', _flaky)
    result = data_backup.run_backup('dev', ['Account', 'BadObject'])
    assert result['status'] == 'partial'
    assert any(e['object'] == 'BadObject' for e in result['errors'])
    assert result['object_count'] == 1          # only Account stored


# ── run_backup — with DB (mocked) ─────────────────────────────────────────────

def test_run_backup_persists_when_db_available(monkeypatch):
    monkeypatch.setattr(data_backup, 'get_sf', lambda org: _default_sf())
    monkeypatch.setattr(data_backup, '_export_object',
                        lambda sf, obj: ('Id\n001\n', 1))
    import db
    monkeypatch.setattr(db, 'db_available', lambda: True)
    monkeypatch.setattr(db, 'get_cursor', lambda: _FakeCursor(fetchone={'id': 7}))

    result = data_backup.run_backup('prod', ['Account', 'Contact'])
    assert result['persisted'] is True
    assert result['run_id'] == 7
    assert result['total_records'] == 2


# ── build_archive ─────────────────────────────────────────────────────────────

def test_build_archive_zips_stored_csvs(monkeypatch):
    run_row = {'org': 'prod', 'started_at': None}
    files = [
        {'object_name': 'Account', 'csv_gz': gzip.compress(b'Id\n001\n')},
        {'object_name': 'Contact', 'csv_gz': gzip.compress(b'Id\n003\n')},
    ]
    import db
    monkeypatch.setattr(db, 'db_available', lambda: True)
    # _ensure_tables uses one cursor; the archive query block uses another.
    cursors = iter([_FakeCursor(), _FakeCursor(fetchone=run_row, fetchall=files)])
    monkeypatch.setattr(db, 'get_cursor', lambda: next(cursors))

    zip_bytes, filename = data_backup.build_archive(7)
    assert filename.endswith('.zip')
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        assert set(zf.namelist()) == {'Account.csv', 'Contact.csv'}
        assert zf.read('Account.csv') == b'Id\n001\n'


def test_build_archive_raises_when_no_db():
    with pytest.raises(ValueError, match='not available'):
        data_backup.build_archive(1)


def test_list_backups_returns_empty_without_db():
    assert data_backup.list_backups('dev') == []


# ── Routes ────────────────────────────────────────────────────────────────────

def test_backup_page_renders(client):
    assert client.get('/data-ops/backup').status_code == 200


def test_backup_objects_route(client):
    resp = client.get('/api/v1/data-ops/backup/objects')
    assert resp.status_code == 200
    assert 'Account' in resp.get_json()['data']


def test_backup_run_route(client, monkeypatch):
    monkeypatch.setattr(data_backup, 'get_sf', lambda org: _default_sf())
    resp = client.post('/api/v1/data-ops/backup/run', json={'objects': ['Account']})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['success'] is True
    assert body['data']['object_count'] >= 1


def test_backup_list_route(client):
    resp = client.get('/api/v1/data-ops/backup/list')
    assert resp.status_code == 200
    assert resp.get_json()['success'] is True


def test_backup_download_missing_run_returns_404(client):
    resp = client.get('/api/v1/data-ops/backup/999/download')
    assert resp.status_code == 404


def test_backup_run_error_returns_500(client, monkeypatch):
    import services.data_backup as db_svc
    monkeypatch.setattr(db_svc, 'run_backup',
                        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError('boom')))
    resp = client.post('/api/v1/data-ops/backup/run', json={'objects': ['Account']})
    assert resp.status_code == 500
    assert resp.get_json()['success'] is False
