"""Atomic confirmed edits in the local store, scoped to the linked seller."""
import hashlib
import json
import sqlite3
from datetime import datetime

from app.integrations.management import _scope, _columns
from app.integrations.ute_mall import ShopDatabaseError, ShopItemNotFoundError


class StaleProductEditError(RuntimeError):
    pass


def editable_product(shop, sku):
    item = shop.get_item_by_sku(sku)
    try:
        with shop._connect() as connection:
            scope, params = _scope(connection, shop, 'product', 'p')
            description = 'p.description' if 'description' in _columns(connection,'product') else 'NULL'
            row = connection.execute(f'SELECT p.name, {description} AS description, '
                '(SELECT COUNT(*) FROM product_variant v WHERE v.product_id=p.id) AS variants '
                f'FROM product p WHERE p.id=? AND {scope}',[item['product_id'],*params]).fetchone()
            if not row:
                raise ShopItemNotFoundError(sku)
            return {**item, 'name':row['name'],'description':row['description'], 'variant_count':row['variants']}
    except sqlite3.Error as error:
        raise ShopDatabaseError('Cannot read editable product') from error


def apply_product_edit(shop, proposal):
    before, after = json.loads(proposal.before_json), json.loads(proposal.after_json)
    if not after or set(after) - {'name','description','price_vnd','stock'}:
        raise ShopDatabaseError('Invalid edit fields')
    request = json.dumps({'shop':proposal.shop_slug,'sku':proposal.sku,'product':proposal.product_id,
        'variant':proposal.variant_id,'before':before,'after':after},sort_keys=True,ensure_ascii=False)
    digest = hashlib.sha256(request.encode()).hexdigest()
    try:
        with shop._connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            scope, params = _scope(connection,shop,'product','p')
            columns = _columns(connection,'product')
            description = 'p.description' if 'description' in columns else 'NULL'
            product = connection.execute(f'SELECT p.*, {description} AS current_description '
                f'FROM product p WHERE p.id=? AND {scope}',[proposal.product_id,*params]).fetchone()
            if not product:
                raise ShopItemNotFoundError(proposal.sku)
            variant = None
            if proposal.target_kind == 'variant':
                variant = connection.execute('SELECT * FROM product_variant WHERE id=? AND product_id=? AND UPPER(sku)=UPPER(?)',
                    (proposal.variant_id,proposal.product_id,proposal.sku)).fetchone()
                if not variant:
                    raise ShopItemNotFoundError(proposal.sku)
            elif proposal.target_kind != 'product' or str(product['sku']).upper() != proposal.sku.upper():
                raise ShopItemNotFoundError(proposal.sku)
            connection.execute('''CREATE TABLE IF NOT EXISTS sellerpilot_product_edit_receipt (
                operation_id TEXT PRIMARY KEY, request_digest TEXT NOT NULL,
                shop_slug TEXT NOT NULL, created_at TEXT NOT NULL)''')
            receipt = connection.execute('SELECT * FROM sellerpilot_product_edit_receipt WHERE operation_id=?',
                (proposal.operation_id,)).fetchone()
            if receipt:
                if receipt['request_digest'] != digest or receipt['shop_slug'] != proposal.shop_slug:
                    raise StaleProductEditError('Operation identity conflict')
                return True
            target = variant or product
            current = {'name':product['name'],'description':product['current_description'],
                       'price_vnd':round(target['price']),'stock':target['stock']}
            if any(current[key] != before[key] for key in after):
                raise StaleProductEditError('Sản phẩm đã thay đổi. Hãy tạo đề xuất mới trước khi xác nhận.')
            if 'description' in after and 'description' not in columns:
                raise ShopDatabaseError('Store is missing product description column')
            content = {key:value for key,value in after.items() if key in {'name','description'}}
            if content:
                connection.execute('UPDATE product SET '+', '.join(f'{key}=?' for key in content)+' WHERE id=?',
                    [*content.values(),proposal.product_id])
            commerce = {('price' if key == 'price_vnd' else key):value for key,value in after.items() if key in {'price_vnd','stock'}}
            if commerce:
                table, target_id = ('product_variant',proposal.variant_id) if variant else ('product',proposal.product_id)
                assignments = [f'{key}=?' for key in commerce]
                if 'price' in commerce:
                    assignments.append('old_price=price')
                connection.execute(f'UPDATE {table} SET '+', '.join(assignments)+' WHERE id=?',
                    [*commerce.values(),target_id])
                if variant:
                    if 'price' in commerce:
                        connection.execute('UPDATE product SET price=COALESCE((SELECT MIN(price) FROM product_variant '
                            'WHERE product_id=? AND is_active=1),price) WHERE id=?',(proposal.product_id,proposal.product_id))
                    if 'stock' in commerce:
                        connection.execute('UPDATE product SET stock=COALESCE((SELECT SUM(stock) FROM product_variant '
                            'WHERE product_id=? AND is_active=1),0) WHERE id=?',(proposal.product_id,proposal.product_id))
            connection.execute('INSERT INTO sellerpilot_product_edit_receipt VALUES (?,?,?,?)',
                (proposal.operation_id,digest,proposal.shop_slug,datetime.utcnow().isoformat()))
            connection.commit()
            return False
    except sqlite3.Error as error:
        raise ShopDatabaseError('Cannot apply product edit') from error
