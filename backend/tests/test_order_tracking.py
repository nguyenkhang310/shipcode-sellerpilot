import sqlite3
from uuid import uuid4
import pytest
from test_order_management import ledger, detail, patch


def test_timeline_is_persisted_in_order_with_no_duplicate_events_on_retry(ledger):
    client, _ = ledger
    assert detail(client)['events'] == []
    assert not detail(client)['unrecorded_status_change']
    version = detail(client)['version']
    operation = str(uuid4())
    assert patch(client, status='paid', version=version, request_id=operation).status_code == 200
    assert patch(client, status='paid', version=version, request_id=operation).json()['data']['replayed']
    assert patch(client, shipping_carrier='SPX Express', tracking_number='VN123456').status_code == 200
    assert patch(client, status='shipped').status_code == 200
    assert patch(client, status='delivered').status_code == 200
    order = detail(client)
    assert [event['to_status'] for event in order['events']] == ['delivered', 'shipped', 'paid', 'paid']
    assert order['events'][2]['changed_fields'] == ['shipping_carrier', 'tracking_number']
    assert all(event['created_at'] for event in order['events'])
    assert order['shipping_carrier'] == 'SPX Express' and order['tracking_number'] == 'VN123456'
    assert not order['unrecorded_status_change']
    assert 'tracking_number' not in order['editable_fields']
    assert patch(client, tracking_number='VN999999').status_code == 409


def test_shipping_edits_are_atomic_and_guarded_by_version(ledger):
    client, _ = ledger
    old = detail(client)
    assert patch(client, shipping_carrier='SPX').status_code == 409
    assert detail(client)['events'] == []
    assert patch(client, shipping_carrier='SPX', tracking_number='VN-123').status_code == 200
    assert patch(client, version=old['version'], note='Stale').status_code == 409
    assert patch(client, shipping_carrier='', tracking_number='').status_code == 200
    data = detail(client)
    assert data['shipping_carrier'] == data['tracking_number'] == ''
    assert len(data['events']) == 2


def test_external_changes_share_the_transactional_status_journal(ledger):
    client, path = ledger
    assert patch(client, status='paid').status_code == 200
    with sqlite3.connect(path) as db:
        db.execute("UPDATE 'order' SET status='shipped' WHERE id=1")
    data = detail(client)
    assert data['status'] == 'shipped' and not data['unrecorded_status_change']
    assert len(data['events']) == 2
    assert data['events'][0]['to_status'] == 'shipped'
    assert data['events'][0]['kind'] == 'status'
    assert patch(client, note='Ghi chú sau bàn giao').status_code == 200
    assert not detail(client)['unrecorded_status_change']


def test_legacy_missing_history_never_invents_timestamps(ledger):
    client, path = ledger
    with sqlite3.connect(path) as db:
        db.execute('DROP TRIGGER sellerpilot_order_status_history')
        db.execute("UPDATE 'order' SET status='delivered' WHERE id=1")
    data = detail(client)
    assert data['status'] == 'delivered' and data['unrecorded_status_change']
    assert data['events'] == []


def test_external_noop_and_rollback_do_not_append_history(ledger):
    client, path = ledger
    with sqlite3.connect(path) as db:
        db.execute("UPDATE 'order' SET status=status WHERE id=1")
        db.execute("UPDATE 'order' SET status='paid' WHERE id=1")
        db.rollback()
    assert detail(client)['events'] == []
    assert detail(client)['status'] == 'pending'


def test_deleting_order_cleans_history_and_waybill_before_an_id_can_be_reused(ledger):
    client, path = ledger
    assert patch(client, shipping_carrier='SPX', tracking_number='VN123').status_code == 200
    with sqlite3.connect(path) as db:
        db.execute('DELETE FROM order_item WHERE order_id=1')
        db.execute('DELETE FROM "order" WHERE id=1')
        db.execute('INSERT INTO "order"(id,shop_id,total_amount,status,created_at) VALUES(1,1,100000,\'pending\',\'2026-10-21\')')
    data = detail(client)
    assert data['events'] == [] and data['tracking_number'] == ''
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT COUNT(*) FROM sellerpilot_order_receipt WHERE order_id=1').fetchone()[0] == 0


def test_tracking_and_event_rows_are_seller_scoped(ledger):
    client, path = ledger
    assert patch(client, shipping_carrier='SPX', tracking_number='VN123').status_code == 200
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO sellerpilot_order_shipping VALUES('other',1,'Private carrier','PRIVATE','2026-10-20')")
        db.execute("INSERT INTO sellerpilot_order_event(operation_id,shop_slug,order_id,from_status,to_status,changed_fields,created_at) VALUES('foreign','other',1,'pending','cancelled','[]','2026-10-20')")
    data = detail(client)
    assert data['tracking_number'] == 'VN123'
    assert len(data['events']) == 1
    assert client.get('/api/v1/management/orders/2').status_code == 404


def test_filter_counts_are_for_current_query_and_never_another_seller(ledger):
    client, _ = ledger
    data = client.get('/api/v1/management/orders?status=pending').json()['data']
    assert data['status_counts'] == {'pending': 1}
    assert client.get('/api/v1/management/orders?q=Private').json()['data']['status_counts'] == {}
    assert patch(client, status='paid').status_code == 200
    data = client.get('/api/v1/management/orders?status=pending').json()['data']
    assert data['total'] == 0 and data['status_counts'] == {'paid': 1}


@pytest.mark.parametrize('changes', [{'tracking_number': 'a'}, {'tracking_number': 'VN 123'},
    {'tracking_number': '\x00'}, {'tracking_number': None}, {'shipping_carrier': None}, {'shipping_carrier': 'x' * 81}, {'shipping_carrier': 'SPX\nExpress'}])
def test_invalid_tracking_is_rejected_before_any_write(ledger, changes):
    client, _ = ledger
    before = detail(client)
    assert patch(client, **changes).status_code == 422
    assert detail(client)['version'] == before['version']
