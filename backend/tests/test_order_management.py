"""Exercise writes against disposable shop ledgers, never the working shop."""
import sqlite3
from uuid import uuid4

import pytest

from test_product_drafts import make_client


@pytest.fixture
def ledger(tmp_path):
    client, path, _ = make_client(tmp_path)
    with sqlite3.connect(path) as db:
        for definition in ['shipping_name TEXT', 'shipping_phone TEXT', 'shipping_address TEXT', 'note TEXT',
                           'payment_method TEXT', 'payment_status TEXT', 'shipping_fee INTEGER', 'discount_amount INTEGER']:
            db.execute('ALTER TABLE "order" ADD COLUMN ' + definition)
        db.execute('ALTER TABLE order_item ADD COLUMN variant_id INTEGER')
        db.execute('ALTER TABLE order_item ADD COLUMN sku TEXT')
        db.execute('ALTER TABLE order_item ADD COLUMN variant_title TEXT')
        db.execute('ALTER TABLE shop ADD COLUMN is_sellerpilot INTEGER DEFAULT 1')
        db.execute("INSERT INTO shop(id,slug,name,status) VALUES(2,'other','Other','active')")
        db.execute("INSERT INTO product(id,name,price,category_id,stock,sku,shop_id,sold_count) VALUES(3,'Private',10000,3,100,'PRIVATE',2,0)")
        db.execute('''INSERT INTO "order"(id,shop_id,total_amount,status,created_at,shipping_name,shipping_phone,shipping_address,note,payment_status,payment_method)
          VALUES(1,1,2000000,'pending','2026-10-20 01:00:00','Nguyễn An','0901234567','123 Nguyễn Văn A','Giao giờ hành chính','unpaid','COD'),
                (2,2,10000,'pending','2026-10-20 01:00:00','Private','0909999999','Private address','','unpaid','COD')''')
        db.execute("INSERT INTO order_item VALUES(1,1,1,2,1000000,1,'PURCHASED-SKU','Đen')")
    with client:
        yield client, path


def detail(client, id=1):
    result = client.get(f'/api/v1/management/orders/{id}')
    assert result.status_code == 200, result.text
    return result.json()['data']


def patch(client, *, version=None, request_id=None, id=1, **changes):
    return client.patch(f'/api/v1/management/orders/{id}', json={
        'request_id': request_id or str(uuid4()), 'expected_version': version or detail(client, id)['version'], **changes})


def test_detail_is_scoped_and_uses_purchased_values(ledger):
    client, _ = ledger
    order = detail(client)
    assert order['allowed_statuses'] == ['paid', 'cancelled']
    assert set(order['editable_fields']) == {'shipping_name', 'shipping_phone', 'shipping_address', 'note'}
    assert order['items'][0]['sku'] == 'PURCHASED-SKU'
    assert order['items'][0]['quantity'] == 2
    assert order['total_vnd'] == 2000000
    assert client.get('/api/v1/management/orders/2').status_code == 404
    assert client.get('/api/v1/management/orders/999').status_code == 404
    assert client.patch('/api/v1/management/orders/2', json={'request_id': str(uuid4()), 'expected_version': order['version'], 'status': 'paid'}).status_code == 404


def test_delivery_transitions_and_sold_units_are_consistent(ledger):
    client, path = ledger
    result = patch(client, status='paid', shipping_name='Nguyễn Bình', note='Gọi trước khi giao')
    assert result.status_code == 200, result.text
    assert result.json()['data']['payment_status'] == 'unpaid'
    assert patch(client, status='delivered').status_code == 409
    assert patch(client, status='shipped').status_code == 200
    assert patch(client, shipping_address='456 Đường khác').status_code == 409
    assert patch(client, note='Khách nhận buổi tối').status_code == 200
    assert patch(client, status='delivered').status_code == 200
    assert detail(client)['payment_status'] == 'paid'
    assert patch(client, status='cancelled').status_code == 409
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT stock,sold_count FROM product WHERE id=1').fetchone() == (8, 2)
        db.execute('UPDATE "order" SET payment_status=\'refunded\' WHERE id=1')
    assert patch(client, note='Ghi nhận đối soát').json()['data']['payment_status'] == 'refunded'


def test_cancellation_and_retry_restore_stock_exactly_once(ledger):
    client, path = ledger
    version = detail(client)['version']
    request_id = str(uuid4())
    first = patch(client, status='cancelled', version=version, request_id=request_id)
    assert first.status_code == 200, first.text
    assert not first.json()['data']['replayed']
    retry = patch(client, status='cancelled', version=version, request_id=request_id)
    assert retry.status_code == 200 and retry.json()['data']['replayed']
    assert patch(client, status='paid', version=version, request_id=request_id).status_code == 409
    assert patch(client, status='cancelled', version=version).status_code == 409
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT stock FROM product WHERE id=1').fetchone()[0] == 10
        assert db.execute('SELECT stock FROM product_variant WHERE id=1').fetchone()[0] == 10
        assert db.execute('SELECT count(*) FROM sellerpilot_order_receipt').fetchone()[0] == 1
        assert db.execute('SELECT count(*) FROM seller_activity').fetchone()[0] == 1


def test_stale_version_never_overwrites_another_edit(ledger):
    client, _ = ledger
    version = detail(client)['version']
    assert patch(client, version=version, note='Người khác đã sửa').status_code == 200
    assert patch(client, version=version, note='Ghi đè').status_code == 409
    assert detail(client)['note'] == 'Người khác đã sửa'


@pytest.mark.parametrize('changes', [{'shipping_phone': 'abc'}, {'shipping_phone': '123'}, {'shipping_address': 'x'},
    {'shipping_name': ''}, {'note': None}, {'status': 'returned'}, {'total_amount': 1}, {'items': []}, {}, {'note': '\x00'}])
def test_invalid_or_unoffered_edits_are_rejected(ledger, changes):
    client, _ = ledger
    before = detail(client)
    assert patch(client, **changes).status_code == 422
    assert detail(client)['version'] == before['version']


@pytest.mark.parametrize('damage', ['foreign_product', 'foreign_variant', 'bad_quantity'])
def test_corrupt_line_rolls_back_all_inventory_and_status(ledger, damage):
    client, path = ledger
    with sqlite3.connect(path) as db:
        product, quantity, variant = (3, 1, None) if damage == 'foreign_product' else (2, 1, 1) if damage == 'foreign_variant' else (2, -1, 2)
        db.execute('INSERT INTO order_item(id,order_id,product_id,quantity,price,variant_id) VALUES(2,1,?,?,10000,?)', (product, quantity, variant))
    assert patch(client, status='cancelled').status_code == 409
    assert detail(client)['status'] == 'pending'
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT stock FROM product WHERE id=1').fetchone()[0] == 8
        assert db.execute('SELECT stock FROM product_variant WHERE id=1').fetchone()[0] == 8
        assert db.execute('SELECT count(*) FROM seller_activity').fetchone()[0] == 0


def test_foreign_product_metadata_not_exposed(ledger):
    client, path = ledger
    with sqlite3.connect(path) as db:
        db.execute('UPDATE order_item SET product_id=3,sku=NULL,variant_id=NULL WHERE id=1')
    line = detail(client)['items'][0]
    assert line['name'] is None and line['sku'] is None


@pytest.mark.parametrize('damage', ['empty_order', 'unknown_stock', 'negative_variant_stock'])
def test_unreliable_inventory_cannot_be_silently_cancelled(ledger, damage):
    client, path = ledger
    with sqlite3.connect(path) as db:
        if damage == 'empty_order':
            db.execute('DELETE FROM order_item WHERE order_id=1')
        elif damage == 'unknown_stock':
            db.execute('UPDATE product SET stock=NULL WHERE id=1')
        else:
            db.execute('UPDATE product_variant SET stock=-2 WHERE id=1')
    assert patch(client, status='cancelled').status_code == 409
    assert detail(client)['status'] == 'pending'


def test_simultaneous_sellers_cannot_cancel_twice(ledger):
    from concurrent.futures import ThreadPoolExecutor
    from app.integrations.ute_mall import UTEMallRepository
    from app.integrations.order_management import update_order, OrderConflictError
    from app.schemas.order_management import OrderUpdate
    client, path = ledger
    version = detail(client)['version']
    shop = UTEMallRepository(path, 'Asia/Ho_Chi_Minh', 'utech-official')
    def cancel():
        try:
            return update_order(shop, 1, OrderUpdate(request_id=uuid4(), expected_version=version, status='cancelled'))['status']
        except OrderConflictError:
            return 'conflict'
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: cancel(), range(2))) == ['cancelled', 'conflict']
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT stock FROM product WHERE id=1').fetchone()[0] == 10
