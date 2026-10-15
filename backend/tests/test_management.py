import sqlite3
from datetime import datetime, timezone
from app.integrations import management
from app.integrations.ute_mall import UTEMallRepository
from test_shop_tenant_scope import build_marketplace


class FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        instant = cls(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
        return instant.astimezone(tz) if tz else instant.replace(tzinfo=None)


def test_dashboard_uses_vn_hours_and_excludes_future_cancelled_orders(client, monkeypatch):
    monkeypatch.setattr(management, 'datetime', FixedDateTime)
    response = client.get('/api/v1/management/dashboard?days=1')
    assert response.status_code == 200, response.text
    data = response.json()['data']
    assert data['order_value_vnd'] == 100000
    assert data['order_count'] == 1
    assert data['cancelled_count'] == 1
    assert data['series'][0] == {'date': '2026-10-15T00:00', 'value': 100000}
    assert len(data['series']) == 20
    assert sum(point['value'] for point in data['series']) == data['order_value_vnd']
    assert data['active_products'] == 2
    assert data['tasks']['low_stock_products'] == 1
    assert data['order_status_counts'] == {'pending': 1, 'paid': 0, 'shipped': 0, 'delivered': 0, 'cancelled': 1, 'returned': 0}
    assert sum(data['order_status_counts'].values()) == data['order_count'] + data['cancelled_count']
    week = client.get('/api/v1/management/dashboard?days=7').json()['data']
    assert len(week['series']) == 7
    assert week['order_value_vnd'] == 150000
    assert week['order_status_counts']['pending'] == 2
    assert client.get('/api/v1/management/dashboard?days=2').status_code == 422


def test_product_order_filters_and_pagination(client):
    first = client.get('/api/v1/management/products?limit=1').json()['data']
    second = client.get('/api/v1/management/products?limit=1&offset=1').json()['data']
    assert first['total'] == 2
    assert first['items'][0]['id'] != second['items'][0]['id']
    assert client.get('/api/v1/management/products?q=P001').json()['data']['items'][0]['sku'] == 'P001'
    assert client.get('/api/v1/management/products?low=true').json()['data']['total'] == 1
    assert client.get('/api/v1/management/products?q=%25').json()['data']['total'] == 0
    orders = client.get('/api/v1/management/orders?status=pending').json()['data']
    assert orders['total'] == 2
    assert {item['status'] for item in orders['items']} == {'pending'}
    assert client.get('/api/v1/management/orders?status=invalid').status_code == 422
    assert client.get('/api/v1/management/products?limit=10000').status_code == 422


def test_store_catalogue_media_is_available_from_api_origin(client):
    response = client.get('/store-static/catalog/sample.png')
    assert response.status_code == 200
    assert response.headers['content-type'] == 'image/png'
    assert response.content == b'sellerpilot-image'


def test_management_does_not_mix_other_sellers(tmp_path, monkeypatch):
    monkeypatch.setattr(management, 'datetime', FixedDateTime)
    path = tmp_path / 'marketplace.db'
    build_marketplace(path)
    shop = UTEMallRepository(path, 'Asia/Ho_Chi_Minh', 'utech-official')
    assert management.products(shop)['total'] == 1
    assert management.products(shop, query='OTHER')['total'] == 0
    assert management.orders(shop)['total'] == 1
    data = management.dashboard(shop, 1)
    assert data['order_value_vnd'] == 700000
    assert data['active_products'] == 1
    assert data['tasks']['low_stock_products'] == 0
    assert data['tasks']['pending_orders'] == 1
    assert sum(data['order_status_counts'].values()) == 1


def test_order_details_use_purchased_price_and_actual_quantities(client, shop_db_path):
    with sqlite3.connect(shop_db_path) as connection:
        connection.execute('INSERT INTO order_item VALUES (1, 1, 1, 3, 90000)')
        connection.execute('INSERT INTO order_item VALUES (2, 1, 2, 2, 120000)')
    order = client.get('/api/v1/management/orders?q=%231').json()['data']['items'][0]
    assert order['item_count'] == 2
    assert order['quantity'] == 5
    assert order['items'][0]['price_vnd'] == 90000  # catalogue is 150000
    assert order['items'][0]['sku'] == 'P001'
    assert order['payment_status'] is None  # unknown is never displayed as unpaid
    assert order['shipping_fee'] is None


def test_order_items_do_not_join_other_shop_metadata(tmp_path):
    path = tmp_path / 'marketplace.db'
    build_marketplace(path)
    with sqlite3.connect(path) as connection:
        # Even a corrupted foreign key must not reveal another seller's catalogue.
        connection.execute('INSERT INTO order_item VALUES (1, 1, 2, 1, 100000)')
        connection.execute('INSERT INTO order_item VALUES (2, 1, 1, 2, 200000)')
        connection.execute('INSERT INTO order_item VALUES (3, 2, 2, 10, 400000)')
    shop = UTEMallRepository(path, 'Asia/Ho_Chi_Minh', 'utech-official')
    orders = management.orders(shop)
    assert orders['total'] == 1
    order = orders['items'][0]
    assert order['quantity'] == 3
    assert order['items'][0]['name'] is None
    assert order['items'][0]['sku'] is None
    assert order['items'][1]['name'] == 'UTech keyboard'
    assert management.orders(shop, offset=1)['items'] == []
