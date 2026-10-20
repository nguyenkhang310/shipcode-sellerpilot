"""Seller-scoped order edits and fulfillment, atomic with inventory and receipts."""
import hashlib
import json
import sqlite3
from datetime import datetime

from app.integrations.management import _scope, _columns
from app.integrations.ute_mall import ShopDatabaseError, ShopItemNotFoundError

TRANSITIONS = {'pending': ['paid', 'cancelled'], 'paid': ['shipped', 'cancelled'],
               'shipped': ['delivered'], 'delivered': [], 'cancelled': [], 'returned': []}
ADDRESS_FIELDS = {'shipping_name', 'shipping_phone', 'shipping_address'}


class OrderConflictError(RuntimeError):
    pass


def _read(connection, shop, order_id):
    scope, params = _scope(connection, shop, 'order', 'o')
    row = connection.execute(f'SELECT o.* FROM "order" o WHERE o.id=? AND {scope}', [order_id, *params]).fetchone()
    if row is None:
        raise ShopItemNotFoundError(order_id)
    raw = dict(row)
    columns = _columns(connection, 'order_item')
    product_scope, product_params = _scope(connection, shop, 'product', 'p')
    image = 'p.image_url' if 'image_url' in _columns(connection, 'product') else 'NULL'
    variant = 'i.variant_title' if 'variant_title' in columns else 'NULL'
    sku = 'COALESCE(i.sku,p.sku)' if 'sku' in columns else 'p.sku'
    lines = [dict(item) for item in connection.execute(
        f'SELECT i.*,p.name,{sku} AS display_sku,{image} AS image_url,{variant} AS variant_title '
        f'FROM order_item i LEFT JOIN product p ON p.id=i.product_id AND {product_scope} '
        'WHERE i.order_id=? ORDER BY i.id', [*product_params, order_id])]
    version = hashlib.sha256(json.dumps([raw, lines], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return {'id': raw['id'], 'status': raw['status'], 'total_vnd': raw['total_amount'],
            'created_at': raw['created_at'], 'version': version,
            **{key: raw.get(key) for key in ADDRESS_FIELDS | {'note', 'payment_status', 'payment_method', 'shipping_fee', 'discount_amount'}},
            'allowed_statuses': TRANSITIONS.get(raw['status'], []),
            'editable_fields': sorted((ADDRESS_FIELDS if raw['status'] in ('pending', 'paid') else set()) & raw.keys()
                                     | ({'note'} if 'note' in raw else set())),
            'items': [{'id': item['id'], 'name': item['name'], 'sku': item['display_sku'],
                       'variant_title': item['variant_title'], 'image_url': item['image_url'],
                       'quantity': item['quantity'], 'price_vnd': item['price']} for item in lines]}


def order_detail(shop, order_id):
    try:
        with shop._connect() as connection:
            connection.execute('BEGIN')
            return _read(connection, shop, order_id)
    except sqlite3.Error as error:
        raise ShopDatabaseError('Cannot read order details') from error


def update_order(shop, order_id, payload):
    changes = payload.model_dump(exclude_unset=True, exclude={'request_id', 'expected_version'})
    slug = shop.seller_shop_slug or 'local'
    digest = hashlib.sha256(json.dumps({'shop': slug, 'id': order_id, 'version': payload.expected_version,
                                       'changes': changes}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    try:
        with shop._connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            before = _read(connection, shop, order_id)
            connection.execute('''CREATE TABLE IF NOT EXISTS sellerpilot_order_receipt (
                operation_id TEXT PRIMARY KEY, request_digest TEXT NOT NULL,
                shop_slug TEXT NOT NULL, order_id INTEGER NOT NULL, created_at TEXT NOT NULL)''')
            receipt = connection.execute('SELECT * FROM sellerpilot_order_receipt WHERE operation_id=?',
                                         (str(payload.request_id),)).fetchone()
            if receipt:
                if receipt['request_digest'] != digest or receipt['shop_slug'] != slug or receipt['order_id'] != order_id:
                    raise OrderConflictError('Mã yêu cầu đã được dùng cho một thay đổi khác.')
                return {**before, 'replayed': True}
            if before['version'] != payload.expected_version:
                raise OrderConflictError('Đơn hàng vừa thay đổi. Tải lại chi tiết trước khi lưu.')
            if changes.keys() - ({'status'} | set(before['editable_fields'])):
                raise OrderConflictError('Thông tin nhận hàng chỉ được sửa trước khi bàn giao vận chuyển.')
            next_status = changes.get('status', before['status'])
            if 'status' in changes and next_status not in before['allowed_statuses']:
                raise OrderConflictError('Không thể chuyển trạng thái đơn theo yêu cầu này.')
            changes = {key: value for key, value in changes.items() if value != before.get(key)}
            if not changes:
                raise OrderConflictError('Không có thay đổi mới để lưu.')
            purchased = list(connection.execute('SELECT * FROM order_item WHERE order_id=?', (order_id,)))
            product_ids = set()
            if next_status != before['status']:
                if not purchased:
                    raise OrderConflictError('Đơn không có sản phẩm hợp lệ để xử lý. Chưa thay đổi đơn.')
                scope, params = _scope(connection, shop, 'product', 'p')
                for item in purchased:
                    product = connection.execute(f'SELECT p.id,p.stock FROM product p WHERE p.id=? AND {scope}',
                                                 [item['product_id'], *params]).fetchone()
                    if not product or not isinstance(item['quantity'], int) or item['quantity'] <= 0:
                        raise OrderConflictError('Có dòng sản phẩm không hợp lệ hoặc không thuộc shop. Chưa thay đổi đơn.')
                    product_ids.add(product['id'])
                    if next_status == 'cancelled' and (not isinstance(product['stock'], int) or product['stock'] < 0):
                        raise OrderConflictError('Tồn kho sản phẩm chưa hợp lệ để hoàn hàng. Chưa thay đổi đơn.')
                    if 'variant_id' in item.keys() and item['variant_id'] is not None:
                        variant = connection.execute('SELECT id,stock FROM product_variant WHERE id=? AND product_id=?',
                                                     (item['variant_id'], item['product_id'])).fetchone()
                        if not variant:
                            raise OrderConflictError('Phân loại sản phẩm trong đơn không còn khớp. Chưa thay đổi đơn.')
                        if next_status == 'cancelled':
                            if not isinstance(variant['stock'], int) or variant['stock'] < 0:
                                raise OrderConflictError('Tồn kho phân loại chưa hợp lệ để hoàn hàng. Chưa thay đổi đơn.')
                            connection.execute('UPDATE product_variant SET stock=stock+? WHERE id=?',
                                               (item['quantity'], item['variant_id']))
                    if next_status == 'cancelled':
                        connection.execute('UPDATE product SET stock=stock+? WHERE id=?', (item['quantity'], item['product_id']))
            if next_status != before['status'] and 'payment_status' in _columns(connection, 'order'):
                if next_status == 'cancelled':
                    changes['payment_status'] = 'cancelled'
                elif next_status == 'delivered':
                    changes['payment_status'] = 'paid'
            connection.execute('UPDATE "order" SET ' + ','.join(f'{field}=?' for field in changes) + ' WHERE id=?',
                               [*changes.values(), order_id])
            if 'sold_count' in _columns(connection, 'product'):
                # Match store counters: fulfilled units, plus historical baseline
                # only for catalogue shops that do not use SellerPilot's ledger.
                tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                baseline = False
                if 'shop' in tables and 'is_sellerpilot' in _columns(connection, 'shop'):
                    tenant = connection.execute('SELECT is_sellerpilot FROM shop WHERE slug=?', (slug,)).fetchone()
                    baseline = bool(tenant and not tenant['is_sellerpilot'])
                order_scope, order_params = _scope(connection, shop, 'order', 'o')
                for product_id in product_ids:
                    units = connection.execute('SELECT COALESCE(SUM(i.quantity),0) FROM order_item i '
                        f'JOIN "order" o ON o.id=i.order_id WHERE i.product_id=? AND o.status=\'delivered\' AND {order_scope}',
                        [product_id, *order_params]).fetchone()[0]
                    history = 0
                    if baseline and 'historical_sold_count' in _columns(connection, 'product'):
                        history = connection.execute('SELECT COALESCE(historical_sold_count,0) FROM product WHERE id=?', (product_id,)).fetchone()[0]
                    connection.execute('UPDATE product SET sold_count=? WHERE id=?', (history + units, product_id))
            if 'seller_activity' in {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}:
                connection.execute('INSERT INTO seller_activity(shop_id,user_id,action,created_at) VALUES(?,NULL,?,?)',
                    (shop._resolve_shop_id(connection), f'SellerPilot · Cập nhật đơn #{order_id}: ' + ', '.join(changes), datetime.utcnow().isoformat()))
            connection.execute('INSERT INTO sellerpilot_order_receipt VALUES(?,?,?,?,?)',
                               (str(payload.request_id), digest, slug, order_id, datetime.utcnow().isoformat()))
            result = _read(connection, shop, order_id)
            connection.commit()
            return {**result, 'replayed': False}
    except sqlite3.Error as error:
        raise ShopDatabaseError('Cannot update order') from error
