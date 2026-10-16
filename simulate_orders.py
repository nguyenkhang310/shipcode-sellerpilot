"""Tạo đơn mô phỏng liên tục cho UTech Official, không gọi thanh toán/vận chuyển.

Từ root: backend/.venv/bin/python simulate_orders.py
Ctrl+C để dừng; --count 10 để tạo hữu hạn, --interval 5 để đổi nhịp.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import math
import os
from pathlib import Path
import random
import secrets
import sqlite3
import time
from uuid import uuid4
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
MARKER = '[SELLERPILOT-LIVE-DEMO]'
VN = ZoneInfo('Asia/Ho_Chi_Minh')


def connect_shop(database: Path) -> sqlite3.Connection:
    database = database.expanduser().resolve()
    if not database.is_file():
        raise ValueError('Chưa có database shop. Chạy bootstrap UTE MALL theo README trước.')
    connection = sqlite3.connect(database.as_uri() + '?mode=rw', uri=True, timeout=8, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys=ON')
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not {'shop', 'product', 'product_variant', 'user', 'order', 'order_item'} <= tables:
        connection.close()
        raise ValueError('Database không đúng schema UTE MALL.')
    return connection


def _buyer(connection):
    email, username = 'sellerpilot.order.simulator@example.test', 'sellerpilot_order_demo'
    row = connection.execute('SELECT id,username FROM user WHERE email=?', (email,)).fetchone()
    if row:
        if row['username'] != username:
            raise ValueError('Email mô phỏng đã thuộc tài khoản khác. Không sửa tài khoản đó.')
        return row['id']
    # Unrecoverable random password, encoded in the same format as Werkzeug.
    salt = secrets.token_hex(12)
    digest = hashlib.pbkdf2_hmac('sha256', secrets.token_bytes(32), salt.encode(), 600000).hex()
    result = connection.execute('INSERT INTO user(username,email,password_hash,role) VALUES (?,?,?,?)',
        (username, email, f'pbkdf2:sha256:600000${salt}${digest}', 'user'))
    return result.lastrowid


def create_order(connection: sqlite3.Connection, *, shop_slug='utech-official', rng=None,
                 status='mixed', max_items=2, now=None) -> dict:
    """One SQLite write transaction reserves stock and saves the complete order."""
    if status not in {'mixed', 'pending', 'paid', 'shipped', 'delivered'}:
        raise ValueError('Trạng thái đơn không hợp lệ.')
    if not 1 <= max_items <= 5:
        raise ValueError('Mỗi đơn chỉ mô phỏng từ 1 đến 5 dòng hàng.')
    rng = rng or random.Random()
    connection.execute('BEGIN IMMEDIATE')
    try:
        shop = connection.execute('SELECT id,is_sellerpilot,vacation_mode FROM shop WHERE slug=? AND status=\'active\'', (shop_slug,)).fetchone()
        if not shop:
            raise ValueError('Không tìm thấy shop đang hoạt động: ' + shop_slug)
        if shop['vacation_mode']:
            raise ValueError('Shop đang tạm nghỉ. Bật lại shop trước khi mô phỏng đơn.')
        candidates = connection.execute('''
            SELECT p.id AS product_id,p.name,p.stock AS product_stock,p.price AS product_price,p.sku AS product_sku,
                   v.id AS variant_id,v.title,v.sku,v.price,v.stock
            FROM product p LEFT JOIN product_variant v ON v.product_id=p.id AND v.is_active=1 AND v.stock>0 AND v.price>0
            WHERE p.shop_id=? AND p.status='active' AND p.stock>0 AND p.price>0
              AND (v.id IS NOT NULL OR NOT EXISTS(SELECT 1 FROM product_variant all_v WHERE all_v.product_id=p.id))
        ''', (shop['id'],)).fetchall()
        rng.shuffle(candidates)
        chosen, seen = [], set()
        for row in candidates:
            if row['product_id'] in seen:
                continue
            seen.add(row['product_id']); chosen.append(row)
        if not chosen:
            raise ValueError('Shop đã hết sản phẩm có thể bán; không tạo đơn vượt tồn kho.')
        chosen = chosen[:rng.randint(1, min(max_items, len(chosen)))]
        buyer = _buyer(connection)
        state = rng.choices(['pending', 'paid', 'shipped', 'delivered'], [45, 20, 15, 20])[0] if status == 'mixed' else status
        payment = 'unpaid' if state == 'pending' else 'paid'
        created = now or datetime.now(timezone.utc)
        if created.tzinfo is None:
            raise ValueError('Thời gian phải có múi giờ.')
        timestamp = created.astimezone(timezone.utc).replace(tzinfo=None).isoformat(sep=' ', timespec='microseconds')
        reference = uuid4().hex
        order_id = connection.execute('''INSERT INTO "order"
            (user_id,shop_id,checkout_reference,shipping_fee,discount_amount,total_amount,status,created_at,
             shipping_name,shipping_phone,shipping_address,note,payment_method,payment_status)
            VALUES (?,?,?,0,0,0,?,?,?,?,?,?,?,?)''',
            (buyer, shop['id'], reference, state, timestamp,
             'Khách demo ' + rng.choice(['Minh An', 'Bảo Ngọc', 'Gia Huy', 'Thùy Linh', 'Hoàng Nam']),
             '', 'Địa chỉ mô phỏng — không giao hàng', MARKER + ' ' + reference, 'COD', payment)).lastrowid
        total, quantity, lines = 0, 0, []
        for row in chosen:
            stock = min(row['product_stock'], row['stock']) if row['variant_id'] else row['product_stock']
            amount = rng.randint(1, min(2, stock))
            price = row['price'] if row['variant_id'] else row['product_price']
            if not math.isfinite(price) or price <= 0:
                raise ValueError('Giá sản phẩm không hợp lệ.')
            reserved = connection.execute('UPDATE product SET stock=stock-? WHERE id=? AND shop_id=? AND stock>=?',
                (amount, row['product_id'], shop['id'], amount))
            if reserved.rowcount != 1:
                raise ValueError('Tồn kho sản phẩm vừa thay đổi, không tạo đơn.')
            if row['variant_id']:
                reserved = connection.execute('UPDATE product_variant SET stock=stock-? WHERE id=? AND is_active=1 AND stock>=?',
                    (amount, row['variant_id'], amount))
                if reserved.rowcount != 1:
                    raise ValueError('Tồn kho phân loại vừa thay đổi, không tạo đơn.')
            connection.execute('''INSERT INTO order_item(order_id,product_id,variant_id,quantity,price,sku,variant_title)
                VALUES (?,?,?,?,?,?,?)''', (order_id, row['product_id'], row['variant_id'], amount, price,
                row['sku'] if row['variant_id'] else row['product_sku'], row['title']))
            total += price * amount; quantity += amount
            lines.append({'sku': row['sku'] or row['product_sku'], 'quantity': amount})
            if state == 'delivered':
                fulfilled = connection.execute('''SELECT COALESCE(SUM(oi.quantity),0) FROM order_item oi
                    JOIN "order" o ON o.id=oi.order_id WHERE oi.product_id=? AND o.status='delivered' ''', (row['product_id'],)).fetchone()[0]
                connection.execute('UPDATE product SET sold_count=?+CASE WHEN ? THEN 0 ELSE COALESCE(historical_sold_count,0) END WHERE id=?',
                    (fulfilled, shop['is_sellerpilot'], row['product_id']))
        connection.execute('UPDATE "order" SET total_amount=? WHERE id=?', (total, order_id))
        connection.commit()
        return {'id': order_id, 'status': state, 'total_vnd': total, 'quantity': quantity, 'items': lines,
                'created_at': created.astimezone(VN).isoformat()}
    except BaseException:
        connection.rollback()
        raise


def main():
    parser = argparse.ArgumentParser(description='Tạo đơn giả lập trực tiếp trong UTE MALL; Ctrl+C để dừng.')
    parser.add_argument('--interval', type=float, default=8, help='Số giây giữa hai đơn, mặc định 8 (tối thiểu 1).')
    parser.add_argument('--count', type=int, default=0, help='Số đơn; 0 = chạy liên tục đến khi Ctrl+C.')
    parser.add_argument('--status', choices=['mixed','pending','paid','shipped','delivered'], default='mixed')
    parser.add_argument('--shop', default='utech-official')
    parser.add_argument('--database', type=Path)
    parser.add_argument('--seed', type=int)
    args = parser.parse_args()
    if not math.isfinite(args.interval) or args.interval < 1 or args.count < 0:
        parser.error('--interval phải ít nhất 1 giây, --count không âm.')
    try:
        from dotenv import dotenv_values
        configured = dotenv_values(ROOT / 'UTE MALL' / '.env').get('STORE_DATABASE_PATH')
    except ImportError:
        configured = None
    selected = args.database or os.environ.get('STORE_DATABASE_PATH') or configured
    database = Path(selected).expanduser() if selected else ROOT / 'UTE MALL/instance/ecommerce.db'
    if not database.is_absolute():
        database = (Path.cwd() if args.database else ROOT / 'UTE MALL') / database
    rng = random.Random(args.seed)
    connection = None
    try:
        connection = connect_shop(database)
        print(f'MÔ PHỎNG · {args.shop} · mỗi {args.interval:g}s · Ctrl+C để dừng', flush=True)
        count = 0
        while not args.count or count < args.count:
            result = create_order(connection, shop_slug=args.shop, rng=rng, status=args.status)
            count += 1
            money = f"{result['total_vnd']:,.0f}".replace(',', '.')
            print(f"[{result['created_at'][:19]}] Đơn #{result['id']} · {result['status']} · {result['quantity']} sản phẩm · {money}đ", flush=True)
            if not args.count or count < args.count:
                time.sleep(args.interval)
    except KeyboardInterrupt:
        print('\nĐã dừng mô phỏng. Các đơn đã tạo vẫn nằm trong shop.', flush=True)
    except (sqlite3.Error, ValueError) as error:
        parser.exit(1, 'Không tạo được đơn: ' + str(error) + '\n')
    finally:
        if connection is not None:
            connection.close()


if __name__ == '__main__':
    main()
