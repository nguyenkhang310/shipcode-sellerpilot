import sqlite3
import pytest
from app.integrations import management
from app.api.v1.endpoints import management as endpoint
from test_management import FixedDateTime


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    monkeypatch.setattr(management, 'datetime', FixedDateTime)
    monkeypatch.setattr(endpoint, 'datetime', FixedDateTime)


def test_selected_day_is_full_vietnam_calendar_day_with_exact_boundaries(client, shop_db_path):
    with sqlite3.connect(shop_db_path) as connection:
        connection.executemany('INSERT INTO "order" VALUES(?,?,?,?)', [
            (5, 25000, 'pending', '2026-10-13 16:59:59'),
            (6, 75000, 'pending', '2026-10-13 17:00:00'),
            (7, 20000, 'delivered', '2026-10-14 16:59:58'),
        ])
    response = client.get('/api/v1/management/dashboard?date=2026-10-14')
    assert response.status_code == 200, response.text
    data = response.json()['data']
    assert data['days'] == 1
    assert data['from_date'] == data['to_date'] == data['selected_date'] == '2026-10-14'
    assert data['order_value_vnd'] == 145000
    assert data['order_count'] == 3
    assert data['delivered_value_vnd'] == 20000
    assert data['previous_value_vnd'] == 25000
    assert data['change_percent'] == 480
    assert len(data['series']) == 24
    assert data['series'][0] == {'date': '2026-10-14T00:00', 'value': 75000}
    assert data['series'][-1] == {'date': '2026-10-14T23:00', 'value': 70000}
    assert sum(point['value'] for point in data['series']) == data['order_value_vnd']
    assert sum(data['order_status_counts'].values()) == 3


def test_selected_today_retains_partial_day_comparison_and_future_exclusion(client):
    selected = client.get('/api/v1/management/dashboard?days=1&date=2026-10-15').json()['data']
    today = client.get('/api/v1/management/dashboard?days=1').json()['data']
    for key in ('series', 'order_count', 'order_value_vnd', 'previous_value_vnd', 'change_percent'):
        assert selected[key] == today[key]
    assert len(selected['series']) == 20
    assert today['selected_date'] is None


def test_empty_day_and_leap_day_do_not_invent_growth(client):
    data = client.get('/api/v1/management/dashboard?date=2024-02-29').json()['data']
    assert data['order_value_vnd'] == data['order_count'] == 0
    assert data['change_percent'] is None
    assert len(data['series']) == 24


@pytest.mark.parametrize('query', ['date=2026-10-16', 'date=1969-12-31', 'date=2026-02-29', 'date=wrong',
                                  'date=2026-10-14&days=7', 'date=2026-10-14&days=30', 'days=0', 'days=2'])
def test_invalid_or_future_dates_and_ambiguous_ranges_rejected(client, query):
    assert client.get('/api/v1/management/dashboard?' + query).status_code == 422
