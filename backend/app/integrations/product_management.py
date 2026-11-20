"""Manual seller edits: one transaction, optimistic version and replay receipt."""
import hashlib
import json
import sqlite3
from datetime import datetime

from app.integrations.management import _scope, _columns
from app.integrations.ute_mall import ShopDatabaseError, ShopItemNotFoundError


class ProductConflictError(RuntimeError):
    pass


def _read(connection, shop, product_id):
    scope, params = _scope(connection, shop, 'product', 'p')
    row = connection.execute(f'SELECT p.* FROM product p WHERE p.id=? AND {scope}', [product_id, *params]).fetchone()
    if row is None:
        raise ShopItemNotFoundError(product_id)
    raw = dict(row)
    variants = [dict(item) for item in connection.execute('SELECT * FROM product_variant WHERE product_id=? ORDER BY id', (product_id,))]
    version = hashlib.sha256(json.dumps([raw, variants], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    editable = [] if raw['status'] == 'archived' else ['name'] + (['description'] if 'description' in raw else []) + ['price_vnd', 'stock']
    return {'id': raw['id'], 'sku': raw['sku'], 'name': raw['name'], 'description': raw.get('description'),
            'price_vnd': round(raw['price']), 'stock': raw['stock'], 'image_url': raw.get('image_url'),
            'status': raw['status'], 'version': version, 'editable_fields': editable,
            'variants': [{'id': item['id'], 'sku': item['sku'], 'title': item.get('title') or item['sku'],
                          'price_vnd': round(item['price']), 'stock': item['stock'], 'is_active': bool(item.get('is_active', 1))} for item in variants]}


def product_detail(shop, product_id):
    try:
        with shop._connect() as connection:
            connection.execute('BEGIN')
            return _read(connection, shop, product_id)
    except sqlite3.Error as error:
        raise ShopDatabaseError('Cannot read product details') from error


def update_product(shop, product_id, payload):
    fields = {'name', 'description', 'price_vnd', 'stock'}
    changes = {key: getattr(payload, key) for key in payload.model_fields_set & fields}
    slug = shop.seller_shop_slug or 'local'
    digest = hashlib.sha256(json.dumps({'shop': slug, 'id': product_id, 'version': payload.expected_version,
        'variant': payload.variant_id, 'changes': changes}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    try:
        with shop._connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            before = _read(connection, shop, product_id)
            if _replayed(connection, payload.request_id, digest, slug, product_id):
                return {**before, 'replayed': True}
            if before['status'] == 'archived':
                raise ProductConflictError('Sản phẩm đã được xóa khỏi gian hàng.')
            if before['version'] != payload.expected_version:
                raise ProductConflictError('Sản phẩm vừa thay đổi. Tải lại chi tiết trước khi lưu.')
            if changes.keys() - set(before['editable_fields']):
                raise ProductConflictError('Shop chưa hỗ trợ lưu trường này.')
            target = before
            if payload.variant_id is not None:
                target = next((item for item in before['variants'] if item['id'] == payload.variant_id), None)
                if target is None:
                    raise ProductConflictError('Phân loại không thuộc sản phẩm này hoặc đã bị xóa.')
            elif before['variants'] and changes.keys() & {'price_vnd', 'stock'}:
                raise ProductConflictError('Chọn phân loại cụ thể để sửa giá hoặc tồn kho.')
            actual = {key: value for key, value in changes.items() if value != (before if key in ('name', 'description') else target).get(key)}
            if not actual:
                raise ProductConflictError('Không có thay đổi mới để lưu.')
            content = {key: value for key, value in actual.items() if key in ('name', 'description')}
            if content:
                connection.execute('UPDATE product SET ' + ','.join(f'{key}=?' for key in content) + ' WHERE id=?', [*content.values(), product_id])
            commerce = {('price' if key == 'price_vnd' else key): value for key, value in actual.items() if key in ('price_vnd', 'stock')}
            if commerce:
                table, target_id = ('product_variant', payload.variant_id) if payload.variant_id is not None else ('product', product_id)
                assignments = [f'{key}=?' for key in commerce]
                if 'price' in commerce and 'old_price' in _columns(connection, table):
                    assignments.append('old_price=price')
                connection.execute(f'UPDATE {table} SET ' + ','.join(assignments) + ' WHERE id=?', [*commerce.values(), target_id])
                if payload.variant_id is not None:
                    active = ' AND is_active=1' if 'is_active' in _columns(connection, 'product_variant') else ''
                    if 'price' in commerce:
                        connection.execute('UPDATE product SET price=COALESCE((SELECT MIN(price) FROM product_variant WHERE product_id=?' + active + '),price) WHERE id=?', (product_id, product_id))
                    if 'stock' in commerce:
                        connection.execute('UPDATE product SET stock=COALESCE((SELECT SUM(stock) FROM product_variant WHERE product_id=?' + active + '),0) WHERE id=?', (product_id, product_id))
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if 'seller_activity' in tables:
                connection.execute('INSERT INTO seller_activity(shop_id,user_id,action,created_at) VALUES(?,NULL,?,?)',
                    (shop._resolve_shop_id(connection), f'SellerPilot · Sửa sản phẩm #{product_id}: ' + ', '.join(sorted(actual)), datetime.utcnow().isoformat()))
            connection.execute('INSERT INTO sellerpilot_manual_product_receipt VALUES(?,?,?,?,?)', (str(payload.request_id), digest, slug, product_id, datetime.utcnow().isoformat()))
            result = _read(connection, shop, product_id)
            connection.commit()
            return {**result, 'replayed': False}
    except sqlite3.Error as error:
        raise ShopDatabaseError('Cannot update product') from error


def _replayed(connection, request_id, digest, slug, product_id):
    connection.execute('''CREATE TABLE IF NOT EXISTS sellerpilot_manual_product_receipt (
        operation_id TEXT PRIMARY KEY, request_digest TEXT NOT NULL, shop_slug TEXT NOT NULL,
        product_id INTEGER NOT NULL, created_at TEXT NOT NULL)''')
    receipt = connection.execute('SELECT * FROM sellerpilot_manual_product_receipt WHERE operation_id=?',
                                 (str(request_id),)).fetchone()
    if receipt and (receipt['request_digest'], receipt['shop_slug'], receipt['product_id']) != (digest, slug, product_id):
        raise ProductConflictError('Mã yêu cầu đã được dùng cho một thay đổi khác.')
    return receipt is not None


def archive_product(shop, product_id, payload):
    """Remove the listing atomically while retaining historical order references."""
    slug = shop.seller_shop_slug or 'local'
    digest = hashlib.sha256(f'archive:{slug}:{product_id}:{payload.expected_version}'.encode()).hexdigest()
    try:
        with shop._connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            before = _read(connection, shop, product_id)
            if _replayed(connection, payload.request_id, digest, slug, product_id):
                return {**before, 'replayed': True}
            if before['status'] == 'archived' or before['version'] != payload.expected_version:
                raise ProductConflictError('Sản phẩm vừa thay đổi. Tải lại chi tiết trước khi xóa.')
            connection.execute("UPDATE product SET status='archived', stock=0 WHERE id=?", (product_id,))
            connection.execute('UPDATE product_variant SET is_active=0, stock=0 WHERE product_id=?', (product_id,))
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for table in ('cart_item', 'wishlist_item'):
                if table in tables:
                    connection.execute(f'DELETE FROM {table} WHERE product_id=?', (product_id,))
            now = datetime.utcnow().isoformat()
            if 'seller_activity' in tables:
                connection.execute('INSERT INTO seller_activity(shop_id,user_id,action,created_at) VALUES(?,NULL,?,?)',
                                   (shop._resolve_shop_id(connection), f'SellerPilot · Xóa sản phẩm #{product_id}', now))
            connection.execute('INSERT INTO sellerpilot_manual_product_receipt VALUES(?,?,?,?,?)',
                               (str(payload.request_id), digest, slug, product_id, now))
            result = _read(connection, shop, product_id)
            connection.commit()
            return {**result, 'replayed': False}
    except sqlite3.Error as error:
        raise ShopDatabaseError('Cannot archive product') from error
