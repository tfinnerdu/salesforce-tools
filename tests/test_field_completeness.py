"""Tests for services.field_completeness and its routes."""
import pytest
from unittest.mock import MagicMock, patch


def _make_sf_mock(total=1000, populated=950):
    """Return a mock SF where every COUNT() query alternates total/populated."""
    sf = MagicMock()
    call_count = [0]

    def side_effect(soql):
        call_count[0] += 1
        # Odd calls = total, even calls = populated (per-check pair)
        if call_count[0] % 2 == 1:
            return {'totalSize': total, 'done': True, 'records': []}
        return {'totalSize': populated, 'done': True, 'records': []}

    sf.query.side_effect = side_effect
    return sf


def test_run_returns_list():
    with patch('services.field_completeness.get_sf', return_value=_make_sf_mock()):
        from services.field_completeness import run
        result = run('dev')
    assert isinstance(result, list)


def test_run_has_correct_number_of_checks():
    from services.field_completeness import run, CHECKS
    with patch('services.field_completeness.get_sf', return_value=_make_sf_mock()):
        result = run('dev')
    assert len(result) == len(CHECKS)


def test_run_result_structure():
    with patch('services.field_completeness.get_sf', return_value=_make_sf_mock()):
        from services.field_completeness import run
        result = run('dev')
    for item in result:
        assert 'object' in item
        assert 'field' in item
        assert 'label' in item
        assert 'total' in item
        assert 'populated' in item
        assert 'missing' in item
        assert 'pct' in item
        assert 'status' in item


def test_run_status_green():
    from services.field_completeness import run
    with patch('services.field_completeness.get_sf') as mock_get_sf:
        sf = _make_sf_mock(total=1000, populated=980)
        mock_get_sf.return_value = sf
        result = run('dev')
        # 980/1000 = 98% -> green
        assert all(r['status'] == 'green' for r in result)


def test_run_status_amber():
    from services.field_completeness import run
    with patch('services.field_completeness.get_sf') as mock_get_sf:
        sf = _make_sf_mock(total=1000, populated=800)
        mock_get_sf.return_value = sf
        result = run('dev')
        # 800/1000 = 80% -> amber
        assert all(r['status'] == 'amber' for r in result)


def test_run_status_red():
    from services.field_completeness import run
    with patch('services.field_completeness.get_sf') as mock_get_sf:
        sf = _make_sf_mock(total=1000, populated=500)
        mock_get_sf.return_value = sf
        result = run('dev')
        # 500/1000 = 50% -> red
        assert all(r['status'] == 'red' for r in result)


def test_run_pct_calculation():
    from services.field_completeness import run
    with patch('services.field_completeness.get_sf') as mock_get_sf:
        sf = _make_sf_mock(total=200, populated=150)
        mock_get_sf.return_value = sf
        result = run('dev')
        for r in result:
            assert r['pct'] == pytest.approx(75.0, abs=0.01)
            assert r['total'] == 200
            assert r['populated'] == 150
            assert r['missing'] == 50


def test_run_zero_total_no_divide_by_zero():
    from services.field_completeness import run
    with patch('services.field_completeness.get_sf') as mock_get_sf:
        sf = _make_sf_mock(total=0, populated=0)
        mock_get_sf.return_value = sf
        result = run('dev')
        for r in result:
            assert r['pct'] == 0.0
            assert r['status'] == 'red'


def test_run_handles_per_check_exception():
    from services.field_completeness import run
    with patch('services.field_completeness.get_sf') as mock_get_sf:
        sf = MagicMock()
        call_count = [0]

        def side_effect(soql):
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception('Object not accessible')
            return {'totalSize': 100, 'done': True, 'records': []}

        sf.query.side_effect = side_effect
        mock_get_sf.return_value = sf
        result = run('dev')
        assert len(result) > 0
        errored = [r for r in result if r['status'] == 'error']
        assert len(errored) == 1
        assert 'error' in errored[0]


def test_run_end_to_end_with_mocked_sf():
    """End-to-end run over a configured SF double — every row has a valid shape."""
    from services.field_completeness import run
    with patch('services.field_completeness.get_sf',
               return_value=_make_sf_mock(total=1000, populated=900)):
        result = run('dev')
    assert isinstance(result, list)
    assert len(result) > 0
    for r in result:
        assert r['status'] in ('green', 'amber', 'red', 'error')
        if r['status'] != 'error':
            assert 0.0 <= r['pct'] <= 100.0


# ── Route tests ───────────────────────────────────────────────────────────────

def test_completeness_page_returns_200(client):
    resp = client.get('/validation/completeness')
    assert resp.status_code == 200


def test_completeness_run_returns_success(session_client):
    with patch('services.field_completeness.get_sf', return_value=_make_sf_mock()):
        resp = session_client.get('/validation/completeness/run')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert isinstance(data['data'], list)


def test_completeness_run_data_structure(session_client):
    with patch('services.field_completeness.get_sf', return_value=_make_sf_mock()):
        resp = session_client.get('/validation/completeness/run')
    data = resp.get_json()
    for item in data['data']:
        assert 'object' in item
        assert 'field' in item
        assert 'pct' in item
        assert 'status' in item
