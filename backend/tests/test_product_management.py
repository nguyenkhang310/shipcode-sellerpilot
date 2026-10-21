import sqlite3
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
import pytest
from app.integrations.product_management import product_detail, update_product
from app.integrations.ute_mall import UTEMallRepository, ShopItemNotFoundError
from app.schemas.product_management import ProductUpdate
from test_shop_tenant_scope import build_marketplace


def details(client, product_id=1):
    response = client.get(f'/api/v1/management/products/{product_id}')
    assert response.status_code == 200, response.text
    return response.json()['data']


def payload(client, changes, product_id=1, **kwargs):
    return {'expected_version': details(client, product_id)['version'], 'request_id': str(uuid4()), **changes, **kwargs}


def test_manual_multi_field_edit_is_atomic_and_replay_safe(client, shop_db_path):
    with sqlite3.connect(shop_db_path) as connection:
        connection.execute('ALTER TABLE product ADD COLUMN description TEXT')
        connection.execute("UPDATE product SET description='Mô tả cũ'")
    body = payload(client, {'name': 'Áo thun mới', 'description': 'Mô tả mới\nDo chủ shop viết.', 'price_vnd': 500000, 'stock': 0})
    first = client.patch('/api/v1/management/products/1', json=body)
    assert first.status_code == 200, first.text
    data = first.json()['data']
    assert data['stock'] == 0 and data['price_vnd'] == 500000 and data['name'] == 'Áo thun mới'
    assert data['version'] != body['expected_version'] and not data['replayed']
    assert client.patch('/api/v1/management/products/1', json=body).json()['data']['replayed']
    with sqlite3.connect(shop_db_path) as connection:
        assert connection.execute('SELECT old_price FROM product WHERE id=1').fetchone()[0] == 150000
        assert connection.execute('SELECT COUNT(*) FROM sellerpilot_manual_product_receipt').fetchone()[0] == 1
    assert client.patch('/api/v1/management/products/1', json={**body, 'stock': 10}).status_code == 409


def test_stale_write_does_not_partially_change_content(client, shop_db_path):
    body = payload(client, {'name': 'Tên không được ghi đè', 'stock': 6})
    with sqlite3.connect(shop_db_path) as connection:
        connection.execute('UPDATE product SET stock=3 WHERE id=1')
    assert client.patch('/api/v1/management/products/1', json=body).status_code == 409
    assert details(client)['name'] == 'Áo thun trơn'
    assert details(client)['stock'] == 3


def test_variant_edits_preserve_sibling_and_recompute_parent(client):
    body = payload(client, {'name': 'Giày mới', 'price_vnd': 120000, 'stock': 0}, 2)
    assert client.patch('/api/v1/management/products/2', json=body).status_code == 409
    assert client.patch('/api/v1/management/products/2', json={**body, 'variant_id': 999}).status_code == 409
    response = client.patch('/api/v1/management/products/2', json={**body, 'variant_id': 1})
    assert response.status_code == 200, response.text
    data = response.json()['data']
    assert (data['stock'], data['price_vnd'], data['name']) == (10, 120000, 'Giày mới')
    assert (data['variants'][0]['stock'], data['variants'][0]['price_vnd']) == (0, 120000)
    assert (data['variants'][1]['stock'], data['variants'][1]['price_vnd']) == (10, 200000)


def test_sibling_change_invalidates_whole_product_version(client, shop_db_path):
    body = payload(client, {'name': 'Tên stale'}, 2, variant_id=1)
    with sqlite3.connect(shop_db_path) as connection:
        connection.execute('UPDATE product_variant SET stock=2 WHERE id=2')
    assert client.patch('/api/v1/management/products/2', json=body).status_code == 409


@pytest.mark.parametrize('changes', [{}, {'name': '  '}, {'name': None}, {'description': None}, {'price_vnd': 999},
    {'price_vnd': 1_000_000_001}, {'price_vnd': True}, {'price_vnd': 1500.5}, {'stock': -1}, {'stock': True},
    {'stock': 1_000_001}, {'variant_id': 0, 'stock': 2}, {'sql': 'DROP TABLE product'}])
def test_invalid_changes_never_write(client, changes):
    body = payload(client, changes)
    assert client.patch('/api/v1/management/products/1', json=body).status_code == 422
    assert details(client)['stock'] == 4


def test_unsupported_description_and_noop_are_rejected(client):
    assert client.patch('/api/v1/management/products/1', json=payload(client, {'description': 'x', 'name': 'Không lưu'})).status_code == 409
    assert details(client)['name'] == 'Áo thun trơn'
    assert client.patch('/api/v1/management/products/1', json=payload(client, {'stock': 4})).status_code == 409


def test_concurrent_writes_from_one_version_only_apply_once(client):
    one = payload(client, {'stock': 6})
    two = {**one, 'request_id': str(uuid4()), 'stock': 7}
    with ThreadPoolExecutor(max_workers=2) as pool:
        codes = list(pool.map(lambda body: client.patch('/api/v1/management/products/1', json=body).status_code, [one, two]))
    assert sorted(codes) == [200, 409]
    assert details(client)['stock'] in (6, 7)


def test_reads_and_writes_are_seller_scoped(tmp_path):
    path = tmp_path / 'marketplace.db'
    build_marketplace(path)
    shop = UTEMallRepository(path, 'Asia/Ho_Chi_Minh', 'utech-official')
    own = product_detail(shop, 1)
    with pytest.raises(ShopItemNotFoundError):
        product_detail(shop, 2)
    with pytest.raises(ShopItemNotFoundError):
        update_product(shop, 2, ProductUpdate(expected_version=own['version'], request_id=uuid4(), stock=0))
