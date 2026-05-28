"""Tests for services.ingest — source_spec → list[dict]."""
import json

import pytest

from services import ingest


# ── inline ───────────────────────────────────────────────────────────────────

class TestInlineMode:
    def test_returns_rows(self):
        rows = ingest.load_source_rows({'mode': 'inline', 'rows': [{'a': 1}, {'a': 2}]})
        assert rows == [{'a': 1}, {'a': 2}]

    def test_copies_rows(self):
        original = [{'a': 1}]
        rows = ingest.load_source_rows({'mode': 'inline', 'rows': original})
        rows[0]['a'] = 99
        assert original[0]['a'] == 1  # caller's data untouched

    def test_requires_list(self):
        with pytest.raises(ValueError, match='rows must be a list'):
            ingest.load_source_rows({'mode': 'inline', 'rows': 'nope'})


# ── json ─────────────────────────────────────────────────────────────────────

class TestJsonMode:
    def test_top_level_list(self):
        data = json.dumps([{'id': '1'}, {'id': '2'}])
        rows = ingest.load_source_rows({'mode': 'json', 'data': data})
        assert rows == [{'id': '1'}, {'id': '2'}]

    def test_single_object_is_one_row(self):
        data = json.dumps({'id': '1', 'name': 'x'})
        rows = ingest.load_source_rows({'mode': 'json', 'data': data})
        assert rows == [{'id': '1', 'name': 'x'}]

    def test_dict_with_single_list_value(self):
        data = json.dumps({'applicants': [{'id': '1'}, {'id': '2'}]})
        rows = ingest.load_source_rows({'mode': 'json', 'data': data})
        assert rows == [{'id': '1'}, {'id': '2'}]

    def test_records_path_navigates(self):
        data = json.dumps({'result': {'rows': [{'id': '1'}]}})
        rows = ingest.load_source_rows(
            {'mode': 'json', 'data': data, 'records_path': 'result.rows'})
        assert rows == [{'id': '1'}]

    def test_records_path_not_a_list_raises(self):
        data = json.dumps({'result': {'rows': 'scalar'}})
        with pytest.raises(ValueError, match='did not resolve to a list'):
            ingest.load_source_rows(
                {'mode': 'json', 'data': data, 'records_path': 'result.rows'})

    def test_flattens_nested_objects_to_dotted_keys(self):
        data = json.dumps([{'id': '1', 'name': {'first': 'Ada', 'last': 'L'}}])
        rows = ingest.load_source_rows({'mode': 'json', 'data': data})
        assert rows[0] == {'id': '1', 'name.first': 'Ada', 'name.last': 'L'}

    def test_nested_array_kept_as_value(self):
        data = json.dumps([{'id': '1', 'tags': ['a', 'b']}])
        rows = ingest.load_source_rows({'mode': 'json', 'data': data})
        assert rows[0]['tags'] == ['a', 'b']

    def test_accepts_already_parsed_payload(self):
        rows = ingest.load_source_rows(
            {'mode': 'json', 'data': [{'id': '1'}]})
        assert rows == [{'id': '1'}]

    def test_invalid_json_raises(self):
        with pytest.raises(ValueError, match='not valid JSON'):
            ingest.load_source_rows({'mode': 'json', 'data': '{not json'})

    def test_missing_data_raises(self):
        with pytest.raises(ValueError, match='source.data'):
            ingest.load_source_rows({'mode': 'json'})


# ── mode validation ──────────────────────────────────────────────────────────

class TestModeValidation:
    def test_spec_must_be_dict(self):
        with pytest.raises(ValueError, match='must be an object'):
            ingest.load_source_rows('nope')

    def test_mode_required(self):
        with pytest.raises(ValueError, match='mode is required'):
            ingest.load_source_rows({'rows': []})

    def test_unknown_mode_raises(self):
        with pytest.raises(ValueError, match='Unknown source mode'):
            ingest.load_source_rows({'mode': 'telepathy'})


# ── csv ──────────────────────────────────────────────────────────────────────

class TestCsvMode:
    def test_comma_delimited(self):
        text = 'id,name\n1,Ada\n2,Babbage'
        rows = ingest.load_source_rows({'mode': 'csv', 'data': text})
        assert rows == [{'id': '1', 'name': 'Ada'}, {'id': '2', 'name': 'Babbage'}]

    def test_tab_delimited(self):
        text = 'id\tname\n1\tAda'
        rows = ingest.load_source_rows({'mode': 'csv', 'data': text})
        assert rows == [{'id': '1', 'name': 'Ada'}]

    def test_trims_whitespace(self):
        text = 'id, name\n1, Ada '
        rows = ingest.load_source_rows({'mode': 'csv', 'data': text})
        assert rows[0]['name'] == 'Ada'

    def test_empty_raises(self):
        with pytest.raises(ValueError, match='CSV/TSV text'):
            ingest.load_source_rows({'mode': 'csv', 'data': '   '})


# ── sql ──────────────────────────────────────────────────────────────────────

class TestSqlMode:
    def test_runs_read_only_query(self, monkeypatch):
        from services import sqlserver
        calls = {}
        def _fake_run(query, max_rows):
            calls['query'] = query
            calls['max_rows'] = max_rows
            return [{'TERMS_ID': '23/AUTM'}]
        monkeypatch.setattr(sqlserver, 'run_query', _fake_run)
        rows = ingest.load_source_rows(
            {'mode': 'sql', 'query': 'SELECT TERMS_ID FROM dbo.PTAT', 'max_rows': 500})
        assert rows == [{'TERMS_ID': '23/AUTM'}]
        assert calls['max_rows'] == 500

    def test_requires_query(self):
        with pytest.raises(ValueError, match='source.query is required'):
            ingest.load_source_rows({'mode': 'sql'})

    def test_rejects_write_query(self, monkeypatch):
        # assert_read_only runs before any connection attempt.
        with pytest.raises(ValueError, match='Only SELECT'):
            ingest.load_source_rows(
                {'mode': 'sql', 'query': 'DELETE FROM dbo.PTAT'})
