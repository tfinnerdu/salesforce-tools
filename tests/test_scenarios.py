"""Tests for services.scenarios — validation, CRUD shape, run dispatch."""
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

import services
from services import scenarios as svc


# ── In-memory DB double ─────────────────────────────────────────────────────

class FakeCursor:
    def __init__(self, store):
        self.store = store
        self.rowcount = 0
        self._result = None

    def execute(self, sql, params=None):
        params = params or ()
        sql_l = sql.lower().strip()
        if sql_l.startswith('insert into scenarios'):
            name, description, org, steps_json, created_by = params
            row = {'id': self.store['next_id'], 'name': name, 'description': description,
                   'org': org, 'steps_json': steps_json, 'created_by': created_by,
                   'created_at': 'now', 'updated_at': 'now'}
            self.store['scenarios'][row['id']] = row
            self.store['next_id'] += 1
            self._result = row; self.rowcount = 1
        elif sql_l.startswith('select id, name, description, org, steps_json, created_by'):
            if 'where id = %s' in sql_l:
                self._result = self.store['scenarios'].get(params[0])
            else:
                rows = list(self.store['scenarios'].values())
                if 'where org = %s' in sql_l:
                    rows = [r for r in rows if r['org'] == params[0]]
                self._result = rows
        elif sql_l.startswith('update scenarios'):
            name, description, steps_json, scenario_id = params
            row = self.store['scenarios'].get(scenario_id)
            if row:
                row.update({'name': name, 'description': description,
                            'steps_json': steps_json, 'updated_at': 'now'})
                self._result = row; self.rowcount = 1
            else:
                self._result = None; self.rowcount = 0
        elif sql_l.startswith('delete from scenarios'):
            scenario_id = params[0]
            self.rowcount = 1 if self.store['scenarios'].pop(scenario_id, None) else 0
        elif sql_l.startswith('insert into scenario_runs'):
            # The SQL bakes status='running' as a literal, so only two
            # bound params come through.
            scenario_id, org = params
            run = {'id': self.store['next_run_id'], 'scenario_id': scenario_id,
                   'org': org, 'status': 'running', 'step_results': []}
            self.store['runs'][run['id']] = run
            self.store['next_run_id'] += 1
            self._result = run
        elif sql_l.startswith('update scenario_runs'):
            status, step_results, run_id = params
            run = self.store['runs'].get(run_id)
            if run:
                run.update({'status': status, 'step_results': step_results})

    def fetchone(self):
        if isinstance(self._result, list):
            return self._result[0] if self._result else None
        return self._result

    def fetchall(self):
        return self._result if isinstance(self._result, list) else []


@pytest.fixture
def fake_db(monkeypatch):
    store = {'scenarios': {}, 'runs': {}, 'next_id': 1, 'next_run_id': 1}

    @contextmanager
    def fake_cursor():
        yield FakeCursor(store)

    monkeypatch.setattr(svc, 'db_available', lambda: True)
    monkeypatch.setattr(svc, 'get_cursor', fake_cursor)
    return store


# ── validate_steps ──────────────────────────────────────────────────────────

class TestValidateSteps:
    def test_rejects_non_list(self):
        with pytest.raises(ValueError, match='must be a list'):
            svc.validate_steps('nope')

    def test_rejects_unknown_step_type(self):
        with pytest.raises(ValueError, match='unknown step type'):
            svc.validate_steps([{'type': 'launch_missile', 'params': {}}])

    def test_rejects_missing_required_params(self):
        with pytest.raises(ValueError, match='missing required params'):
            svc.validate_steps([{'type': 'delete', 'params': {'object': 'Account'}}])

    def test_accepts_complete_step(self):
        steps = [{'type': 'delete',
                  'params': {'object': 'Account', 'where_clause': 'Id != null'}}]
        assert svc.validate_steps(steps) is steps

    def test_validates_each_step(self):
        steps = [
            {'type': 'delete', 'params': {'object': 'A', 'where_clause': 'x'}},
            {'type': 'modify', 'params': {'object': 'A'}},  # missing field, value, where
        ]
        with pytest.raises(ValueError, match='Step 2'):
            svc.validate_steps(steps)


# ── CRUD ────────────────────────────────────────────────────────────────────

class TestScenarioCRUD:
    def _good_steps(self):
        return [{'type': 'delete', 'params': {'object': 'Account', 'where_clause': 'Id != null'}}]

    def test_create_round_trips(self, fake_db):
        saved = svc.create_scenario('Weekly cleanup', 'desc', 'dev', self._good_steps())
        assert saved['id'] == 1
        assert saved['name'] == 'Weekly cleanup'
        assert saved['steps'][0]['type'] == 'delete'

    def test_create_requires_name(self, fake_db):
        with pytest.raises(ValueError, match='name is required'):
            svc.create_scenario('  ', 'd', 'dev', self._good_steps())

    def test_create_validates_steps(self, fake_db):
        with pytest.raises(ValueError, match='missing required params'):
            svc.create_scenario('x', 'd', 'dev', [{'type': 'delete', 'params': {}}])

    def test_list_filters_by_org(self, fake_db):
        svc.create_scenario('a', '', 'dev', self._good_steps())
        svc.create_scenario('b', '', 'prod', self._good_steps())
        dev_only = svc.list_scenarios(org='dev')
        assert [s['name'] for s in dev_only] == ['a']

    def test_get_returns_none_when_missing(self, fake_db):
        assert svc.get_scenario(999) is None

    def test_update_changes_name_and_steps(self, fake_db):
        saved = svc.create_scenario('old', '', 'dev', self._good_steps())
        updated = svc.update_scenario(saved['id'], 'new', 'new desc',
                                       [{'type': 'modify',
                                         'params': {'object': 'A', 'where_clause': 'x',
                                                    'field': 'F', 'value': 'V'}}])
        assert updated['name'] == 'new'
        assert updated['steps'][0]['type'] == 'modify'

    def test_update_missing_returns_none(self, fake_db):
        assert svc.update_scenario(999, 'n', '', self._good_steps()) is None

    def test_delete_returns_true_when_present(self, fake_db):
        saved = svc.create_scenario('a', '', 'dev', self._good_steps())
        assert svc.delete_scenario(saved['id']) is True

    def test_delete_returns_false_when_missing(self, fake_db):
        assert svc.delete_scenario(999) is False


class TestNoDbBehavior:
    def test_list_returns_empty_without_db(self, monkeypatch):
        monkeypatch.setattr(svc, 'db_available', lambda: False)
        assert svc.list_scenarios() == []

    def test_get_returns_none_without_db(self, monkeypatch):
        monkeypatch.setattr(svc, 'db_available', lambda: False)
        assert svc.get_scenario(1) is None

    def test_create_raises_without_db(self, monkeypatch):
        monkeypatch.setattr(svc, 'db_available', lambda: False)
        with pytest.raises(RuntimeError, match='database connection'):
            svc.create_scenario('n', '', 'dev', [
                {'type': 'delete', 'params': {'object': 'A', 'where_clause': 'x'}}
            ])


# ── Run dispatcher ──────────────────────────────────────────────────────────

class TestRunScenario:
    def _seed(self, fake_db, steps, on_error_per_step=None):
        scenario = svc.create_scenario('s', '', 'dev', steps)
        if on_error_per_step:
            for i, oe in enumerate(on_error_per_step):
                scenario['steps'][i]['on_error'] = oe
            svc.update_scenario(scenario['id'], scenario['name'], '', scenario['steps'])
        return scenario['id']

    def test_run_dispatches_each_step(self, fake_db, monkeypatch):
        steps = [
            {'type': 'delete',
             'params': {'object': 'Account', 'where_clause': 'Id != null'}},
            {'type': 'modify',
             'params': {'object': 'Account', 'where_clause': 'Status__c = null',
                        'field': 'Status__c', 'value': 'new'}},
        ]
        sid = self._seed(fake_db, steps)

        fake_bulk = MagicMock()
        fake_bulk.bulk_delete_execute.return_value = {'deleted': 5, 'errors': 0}
        fake_bulk.bulk_modify_execute.return_value = {'updated': 3, 'errors': 0}
        monkeypatch.setattr(services, 'bulk_ops', fake_bulk)
        result = svc.run_scenario(sid, 'dev')

        assert result['status'] == 'success'
        assert len(result['step_results']) == 2
        assert result['step_results'][0]['detail']['deleted'] == 5
        assert result['step_results'][1]['detail']['updated'] == 3
        fake_bulk.bulk_delete_execute.assert_called_once_with(
            'dev', 'Account', 'Id != null', False,
        )

    def test_run_stops_on_step_failure_by_default(self, fake_db, monkeypatch):
        steps = [
            {'type': 'delete',
             'params': {'object': 'A', 'where_clause': 'x'}},
            {'type': 'delete',
             'params': {'object': 'B', 'where_clause': 'y'}},
        ]
        sid = self._seed(fake_db, steps)

        fake_bulk = MagicMock()
        fake_bulk.bulk_delete_execute.side_effect = RuntimeError('boom')
        monkeypatch.setattr(services, 'bulk_ops', fake_bulk)
        result = svc.run_scenario(sid, 'dev')

        assert result['status'] == 'failed'
        # Only the first step actually ran; the second one was skipped.
        assert len(result['step_results']) == 1
        assert result['step_results'][0]['status'] == 'failed'
        assert 'boom' in result['step_results'][0]['detail']['error']

    def test_run_continues_when_on_error_continue(self, fake_db, monkeypatch):
        steps = [
            {'type': 'delete', 'params': {'object': 'A', 'where_clause': 'x'}},
            {'type': 'delete', 'params': {'object': 'B', 'where_clause': 'y'}},
        ]
        sid = self._seed(fake_db, steps, on_error_per_step=['continue', 'stop'])

        fake_bulk = MagicMock()
        fake_bulk.bulk_delete_execute.side_effect = [RuntimeError('boom'),
                                                     {'deleted': 7, 'errors': 0}]
        monkeypatch.setattr(services, 'bulk_ops', fake_bulk)
        result = svc.run_scenario(sid, 'dev')

        assert result['status'] == 'partial'
        statuses = [r['status'] for r in result['step_results']]
        assert statuses == ['failed', 'success']

    def test_run_missing_scenario_raises(self, fake_db):
        with pytest.raises(ValueError, match='not found'):
            svc.run_scenario(999, 'dev')

    def test_run_empty_steps_raises(self, fake_db, monkeypatch):
        # bypass validate_steps so we can land an empty step list
        monkeypatch.setattr(svc, 'validate_steps', lambda s: s)
        sid = svc.create_scenario('e', '', 'dev', [])['id']
        with pytest.raises(ValueError, match='no steps'):
            svc.run_scenario(sid, 'dev')


# ── Dispatch coverage for each step type ────────────────────────────────────

class TestDispatchPerStepType:
    @pytest.mark.parametrize('step_type, params, attr_name, fn_name, expected_extra', [
        ('delete',
         {'object': 'A', 'where_clause': 'x'},
         'bulk_ops', 'bulk_delete_execute',
         ('dev', 'A', 'x', False)),
        ('modify',
         {'object': 'A', 'where_clause': 'x', 'field': 'F', 'value': 'V'},
         'bulk_ops', 'bulk_modify_execute',
         ('dev', 'A', 'x', 'F', 'V', False)),
        ('reassign',
         {'object': 'A', 'where_clause': 'x', 'new_owner_id': '005000'},
         'bulk_ops', 'bulk_reassign_execute',
         ('dev', 'A', 'x', '005000', False)),
    ])
    def test_dispatch_calls_expected_service(self, fake_db, monkeypatch, step_type,
                                              params, attr_name, fn_name, expected_extra):
        sid = svc.create_scenario('s', '', 'dev',
            [{'type': step_type, 'params': params}])['id']
        fake_mod = MagicMock()
        getattr(fake_mod, fn_name).return_value = {'ok': True}
        monkeypatch.setattr(services, attr_name, fake_mod)
        result = svc.run_scenario(sid, 'dev')
        getattr(fake_mod, fn_name).assert_called_once_with(*expected_extra)
        assert result['status'] == 'success'

    def test_bulk_update_passes_dry_run(self, fake_db, monkeypatch):
        sid = svc.create_scenario('s', '', 'dev', [{
            'type': 'bulk_update',
            'params': {'object': 'A', 'where_clause': 'x', 'field': 'F',
                       'value': 'V', 'dry_run': True},
        }])['id']
        fake_mod = MagicMock()
        fake_mod.bulk_update.return_value = {'updated': 0}
        monkeypatch.setattr(services, 'bulk_dml', fake_mod)
        svc.run_scenario(sid, 'dev')
        kwargs = fake_mod.bulk_update.call_args.kwargs
        assert kwargs['dry_run'] is True
        assert kwargs['bypass_triggers'] is False

    def test_tune_passes_field_rules(self, fake_db, monkeypatch):
        rules = {'FirstName': ['trim']}
        sid = svc.create_scenario('s', '', 'dev', [{
            'type': 'tune',
            'params': {'object': 'A', 'where_clause': 'x', 'field_rules': rules},
        }])['id']
        fake_mod = MagicMock()
        fake_mod.apply_tune.return_value = {'updated': 0}
        monkeypatch.setattr(services, 'data_tuner', fake_mod)
        svc.run_scenario(sid, 'dev')
        args, kwargs = fake_mod.apply_tune.call_args
        assert args[3] == rules
