"""Tests for services.collection_manager."""
import json
import pytest
import responses as responses_lib
from contextlib import contextmanager
from unittest.mock import MagicMock, patch


# ── cursor helpers ────────────────────────────────────────────────────────────

def _make_cursor(rows=None, one=None):
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = rows if rows is not None else []
    mock_cur.fetchone.return_value = one

    @contextmanager
    def _cm():
        yield mock_cur

    return _cm, mock_cur


def _fail_cursor():
    @contextmanager
    def _cm():
        raise Exception("DB unavailable")
        yield  # pragma: no cover
    return _cm


# ── substitute_variables ──────────────────────────────────────────────────────

def test_substitute_variables_basic():
    from services.collection_manager import substitute_variables
    result = substitute_variables("Hello {{NAME}}", {'NAME': 'World'})
    assert result == "Hello World"


def test_substitute_variables_multiple():
    from services.collection_manager import substitute_variables
    result = substitute_variables("{{A}} and {{B}}", {'A': 'foo', 'B': 'bar'})
    assert result == "foo and bar"


def test_substitute_variables_missing_key_kept():
    from services.collection_manager import substitute_variables
    result = substitute_variables("{{MISSING}}", {})
    assert result == "{{MISSING}}"


def test_substitute_variables_no_placeholders():
    from services.collection_manager import substitute_variables
    result = substitute_variables("plain text", {'KEY': 'val'})
    assert result == "plain text"


def test_substitute_variables_empty_string():
    from services.collection_manager import substitute_variables
    assert substitute_variables("", {}) == ""


# ── _apply_env ────────────────────────────────────────────────────────────────

def test_apply_env_string():
    from services.collection_manager import _apply_env
    result = _apply_env("{{HOST}}", {'HOST': 'example.com'})
    assert result == "example.com"


def test_apply_env_dict():
    from services.collection_manager import _apply_env
    result = _apply_env({'url': '{{BASE_URL}}/path'}, {'BASE_URL': 'https://api.test'})
    assert result == {'url': 'https://api.test/path'}


def test_apply_env_list():
    from services.collection_manager import _apply_env
    result = _apply_env(['{{A}}', '{{B}}'], {'A': '1', 'B': '2'})
    assert result == ['1', '2']


def test_apply_env_passthrough_int():
    from services.collection_manager import _apply_env
    result = _apply_env(42, {'A': '1'})
    assert result == 42


def test_apply_env_passthrough_none():
    from services.collection_manager import _apply_env
    result = _apply_env(None, {'A': '1'})
    assert result is None


def test_apply_env_nested():
    from services.collection_manager import _apply_env
    data = {'headers': [{'key': '{{HEADER_KEY}}', 'value': '{{HEADER_VAL}}'}]}
    result = _apply_env(data, {'HEADER_KEY': 'Authorization', 'HEADER_VAL': 'Bearer xyz'})
    assert result['headers'][0]['key'] == 'Authorization'
    assert result['headers'][0]['value'] == 'Bearer xyz'


# ── _extract_url ──────────────────────────────────────────────────────────────

def test_extract_url_string():
    from services.collection_manager import _extract_url
    assert _extract_url("https://example.com/api") == "https://example.com/api"


def test_extract_url_dict_with_raw():
    from services.collection_manager import _extract_url
    obj = {'raw': 'https://example.com/api', 'host': ['example', 'com']}
    assert _extract_url(obj) == "https://example.com/api"


def test_extract_url_dict_reconstruct_from_parts():
    from services.collection_manager import _extract_url
    obj = {'protocol': 'https', 'host': ['api', 'example', 'com'], 'path': ['v1', 'users']}
    result = _extract_url(obj)
    assert result == "https://api.example.com/v1/users"


def test_extract_url_dict_no_raw_no_parts():
    from services.collection_manager import _extract_url
    obj = {}
    result = _extract_url(obj)
    assert isinstance(result, str)


def test_extract_url_empty_string():
    from services.collection_manager import _extract_url
    assert _extract_url("") == ""


def test_extract_url_non_str_non_dict_returns_empty():
    from services.collection_manager import _extract_url
    assert _extract_url(42) == ''
    assert _extract_url(None) == ''


# ── import_collection ─────────────────────────────────────────────────────────

def test_import_collection_valid_json():
    from services.collection_manager import import_collection
    data = {'info': {'name': 'My Collection'}, 'item': []}
    content = json.dumps(data)
    mock_row = {'id': 1, 'name': 'My Collection', 'collection_json': data, 'created_at': None, 'updated_at': None}
    mock_cur = MagicMock()
    mock_cur.fetchone.return_value = mock_row

    @contextmanager
    def _cm():
        yield mock_cur

    with patch('services.collection_manager.get_cursor', _cm):
        result = import_collection(content)
    assert isinstance(result, dict)


def test_import_collection_invalid_json_raises():
    from services.collection_manager import import_collection
    with pytest.raises(ValueError, match="Invalid JSON"):
        import_collection("not valid json {{{")


def test_import_collection_uses_info_name():
    from services.collection_manager import import_collection
    data = {'info': {'name': 'Custom Name'}, 'item': []}
    content = json.dumps(data)
    mock_cur = MagicMock()
    mock_cur.fetchone.return_value = {'id': 1, 'name': 'Custom Name', 'collection_json': data, 'created_at': None, 'updated_at': None}

    @contextmanager
    def _cm():
        yield mock_cur

    with patch('services.collection_manager.get_cursor', _cm):
        result = import_collection(content)
    # create_collection is called with the correct name
    call_args = mock_cur.execute.call_args
    assert 'Custom Name' in str(call_args)


def test_import_collection_missing_info_uses_default():
    from services.collection_manager import import_collection
    data = {'item': []}
    content = json.dumps(data)
    mock_cur = MagicMock()
    mock_cur.fetchone.return_value = {'id': 1, 'name': 'Imported Collection', 'collection_json': data, 'created_at': None, 'updated_at': None}

    @contextmanager
    def _cm():
        yield mock_cur

    with patch('services.collection_manager.get_cursor', _cm):
        result = import_collection(content)
    call_args = mock_cur.execute.call_args
    assert 'Imported Collection' in str(call_args)


# ── create_collection ─────────────────────────────────────────────────────────

def test_create_collection_returns_dict():
    from services.collection_manager import create_collection
    mock_row = {'id': 1, 'name': 'Test', 'collection_json': {}, 'created_at': None, 'updated_at': None}
    cm, mock_cur = _make_cursor(one=mock_row)
    with patch('services.collection_manager.get_cursor', cm):
        result = create_collection('Test', {})
    assert isinstance(result, dict)


def test_create_collection_fetchone_none_returns_empty():
    from services.collection_manager import create_collection
    cm, mock_cur = _make_cursor(one=None)
    with patch('services.collection_manager.get_cursor', cm):
        result = create_collection('Test', {})
    assert result == {}


def test_create_collection_db_failure_returns_empty():
    from services.collection_manager import create_collection
    with patch('services.collection_manager.get_cursor', _fail_cursor()):
        result = create_collection('Test', {})
    assert result == {}


# ── list_collections ──────────────────────────────────────────────────────────

def test_list_collections_returns_list():
    from services.collection_manager import list_collections
    rows = [
        {'id': 1, 'name': 'A', 'created_at': None, 'updated_at': None},
        {'id': 2, 'name': 'B', 'created_at': None, 'updated_at': None},
    ]
    cm, _ = _make_cursor(rows=rows)
    with patch('services.collection_manager.get_cursor', cm):
        result = list_collections()
    assert isinstance(result, list)
    assert len(result) == 2


def test_list_collections_db_failure_returns_empty():
    from services.collection_manager import list_collections
    with patch('services.collection_manager.get_cursor', _fail_cursor()):
        result = list_collections()
    assert result == []


# ── delete_collection ─────────────────────────────────────────────────────────

def test_delete_collection_calls_execute():
    from services.collection_manager import delete_collection
    cm, mock_cur = _make_cursor()
    with patch('services.collection_manager.get_cursor', cm):
        delete_collection(5)
    mock_cur.execute.assert_called_once()


def test_delete_collection_db_failure_non_fatal():
    from services.collection_manager import delete_collection
    with patch('services.collection_manager.get_cursor', _fail_cursor()):
        delete_collection(5)  # Should not raise


# ── run_collection ────────────────────────────────────────────────────────────

def test_run_collection_db_fetch_failure_returns_empty():
    from services.collection_manager import run_collection
    with patch('services.collection_manager.get_cursor', _fail_cursor()):
        result = run_collection(1, {})
    assert result == []


def test_run_collection_not_found_returns_empty():
    from services.collection_manager import run_collection
    cm, _ = _make_cursor(one=None)
    with patch('services.collection_manager.get_cursor', cm):
        result = run_collection(999, {})
    assert result == []


def test_run_collection_empty_items():
    from services.collection_manager import run_collection
    col_data = {'item': []}
    mock_row = {'collection_json': col_data}
    cm, _ = _make_cursor(one=mock_row)
    with patch('services.collection_manager.get_cursor', cm):
        result = run_collection(1, {})
    assert result == []


def test_run_collection_str_json_parsed():
    """collection_json stored as string should be parsed."""
    from services.collection_manager import run_collection
    col_data = {'item': []}
    mock_row = {'collection_json': json.dumps(col_data)}
    cm, _ = _make_cursor(one=mock_row)
    with patch('services.collection_manager.get_cursor', cm):
        result = run_collection(1, {})
    assert result == []


def test_run_collection_invalid_str_json_returns_empty():
    from services.collection_manager import run_collection
    mock_row = {'collection_json': 'not-valid-json'}
    cm, _ = _make_cursor(one=mock_row)
    with patch('services.collection_manager.get_cursor', cm):
        result = run_collection(1, {})
    assert result == []


@responses_lib.activate
def test_run_collection_success():
    from services.collection_manager import run_collection
    responses_lib.add(responses_lib.GET, 'https://httpbin.org/get', json={'ok': True}, status=200)

    col_data = {
        'item': [{
            'name': 'Test Request',
            'request': {
                'method': 'GET',
                'url': 'https://httpbin.org/get',
                'header': [],
                'body': {},
            }
        }]
    }
    mock_row = {'collection_json': col_data}
    cm, _ = _make_cursor(one=mock_row)
    with patch('services.collection_manager.get_cursor', cm):
        result = run_collection(1, {})
    assert len(result) == 1
    assert result[0]['passed'] is True
    assert result[0]['status_code'] == 200
    assert result[0]['name'] == 'Test Request'


@responses_lib.activate
def test_run_collection_status_400_not_passed():
    from services.collection_manager import run_collection
    responses_lib.add(responses_lib.POST, 'https://api.example.com/data', json={'error': 'bad'}, status=400)

    col_data = {
        'item': [{
            'name': 'Bad Request',
            'request': {
                'method': 'POST',
                'url': 'https://api.example.com/data',
                'header': [],
                'body': {'mode': 'raw', 'raw': '{"key": "val"}'},
            }
        }]
    }
    mock_row = {'collection_json': col_data}
    cm, _ = _make_cursor(one=mock_row)
    with patch('services.collection_manager.get_cursor', cm):
        result = run_collection(1, {})
    assert result[0]['passed'] is False
    assert result[0]['status_code'] == 400


@responses_lib.activate
def test_run_collection_request_exception():
    from services.collection_manager import run_collection
    responses_lib.add(responses_lib.GET, 'https://api.example.com/fail',
                      body=Exception("Connection refused"))

    col_data = {
        'item': [{
            'name': 'Failing Request',
            'request': {
                'method': 'GET',
                'url': 'https://api.example.com/fail',
                'header': [],
            }
        }]
    }
    mock_row = {'collection_json': col_data}
    cm, _ = _make_cursor(one=mock_row)
    with patch('services.collection_manager.get_cursor', cm):
        result = run_collection(1, {})
    assert result[0]['passed'] is False
    assert result[0]['status_code'] == 0
    assert result[0]['error'] is not None


@responses_lib.activate
def test_run_collection_urlencoded_body():
    from services.collection_manager import run_collection
    responses_lib.add(responses_lib.POST, 'https://api.example.com/form', json={}, status=200)

    col_data = {
        'item': [{
            'name': 'Form Post',
            'request': {
                'method': 'POST',
                'url': 'https://api.example.com/form',
                'header': [],
                'body': {
                    'mode': 'urlencoded',
                    'urlencoded': [
                        {'key': 'field1', 'value': 'val1'},
                        {'key': 'field2', 'value': 'val2'},
                    ]
                },
            }
        }]
    }
    mock_row = {'collection_json': col_data}
    cm, _ = _make_cursor(one=mock_row)
    with patch('services.collection_manager.get_cursor', cm):
        result = run_collection(1, {})
    assert result[0]['passed'] is True
    # Verify urlencoded body was sent
    sent_body = responses_lib.calls[0].request.body
    assert 'field1=val1' in sent_body
    assert 'field2=val2' in sent_body


@responses_lib.activate
def test_run_collection_variable_substitution_in_url():
    from services.collection_manager import run_collection
    responses_lib.add(responses_lib.GET, 'https://api.prod.com/v1/users', json={}, status=200)

    col_data = {
        'item': [{
            'name': 'Dynamic URL',
            'request': {
                'method': 'GET',
                'url': '{{BASE_URL}}/v1/users',
                'header': [],
            }
        }]
    }
    mock_row = {'collection_json': col_data}
    cm, _ = _make_cursor(one=mock_row)
    with patch('services.collection_manager.get_cursor', cm):
        result = run_collection(1, {'BASE_URL': 'https://api.prod.com'})
    assert result[0]['url'] == 'https://api.prod.com/v1/users'
    assert result[0]['passed'] is True


@responses_lib.activate
def test_run_collection_header_substitution():
    from services.collection_manager import run_collection
    responses_lib.add(responses_lib.GET, 'https://api.example.com/protected', json={}, status=200)

    col_data = {
        'item': [{
            'name': 'Auth Request',
            'request': {
                'method': 'GET',
                'url': 'https://api.example.com/protected',
                'header': [
                    {'key': 'Authorization', 'value': 'Bearer {{TOKEN}}'},
                    {'key': 'X-Custom', 'value': 'static'},
                ],
            }
        }]
    }
    mock_row = {'collection_json': col_data}
    cm, _ = _make_cursor(one=mock_row)
    with patch('services.collection_manager.get_cursor', cm):
        result = run_collection(1, {'TOKEN': 'abc123'})
    sent_headers = responses_lib.calls[0].request.headers
    assert sent_headers.get('Authorization') == 'Bearer abc123'
    assert sent_headers.get('X-Custom') == 'static'


@responses_lib.activate
def test_run_collection_postman_url_object():
    """URL as Postman dict object with 'raw' key should be extracted."""
    from services.collection_manager import run_collection
    responses_lib.add(responses_lib.GET, 'https://api.example.com/info', json={}, status=200)

    col_data = {
        'item': [{
            'name': 'Dict URL',
            'request': {
                'method': 'GET',
                'url': {'raw': 'https://api.example.com/info', 'host': ['api', 'example', 'com']},
                'header': [],
            }
        }]
    }
    mock_row = {'collection_json': col_data}
    cm, _ = _make_cursor(one=mock_row)
    with patch('services.collection_manager.get_cursor', cm):
        result = run_collection(1, {})
    assert result[0]['passed'] is True


@responses_lib.activate
def test_run_collection_response_preview_truncated():
    """Response preview should be at most 500 chars."""
    from services.collection_manager import run_collection
    long_body = 'x' * 1000
    responses_lib.add(responses_lib.GET, 'https://api.example.com/long', body=long_body, status=200)

    col_data = {
        'item': [{
            'name': 'Long Response',
            'request': {'method': 'GET', 'url': 'https://api.example.com/long', 'header': []},
        }]
    }
    mock_row = {'collection_json': col_data}
    cm, _ = _make_cursor(one=mock_row)
    with patch('services.collection_manager.get_cursor', cm):
        result = run_collection(1, {})
    assert len(result[0]['response_preview']) <= 500


@responses_lib.activate
def test_run_collection_multiple_items():
    from services.collection_manager import run_collection
    responses_lib.add(responses_lib.GET, 'https://api.example.com/a', json={}, status=200)
    responses_lib.add(responses_lib.GET, 'https://api.example.com/b', json={}, status=404)

    col_data = {
        'item': [
            {'name': 'A', 'request': {'method': 'GET', 'url': 'https://api.example.com/a', 'header': []}},
            {'name': 'B', 'request': {'method': 'GET', 'url': 'https://api.example.com/b', 'header': []}},
        ]
    }
    mock_row = {'collection_json': col_data}
    cm, _ = _make_cursor(one=mock_row)
    with patch('services.collection_manager.get_cursor', cm):
        result = run_collection(1, {})
    assert len(result) == 2
    assert result[0]['passed'] is True
    assert result[1]['passed'] is False
