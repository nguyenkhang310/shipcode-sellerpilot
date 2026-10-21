import importlib.util
from datetime import datetime, timezone
from pathlib import Path
import random
import sqlite3
import subprocess
import sys

import pytest

from app.integrations import management
from app.integrations.ute_mall import UTEMallRepository
from app.integrations.order_management import order_detail
from test_product_drafts import build_shop

SCRIPT = Path(__file__).resolve().parents[2] / 'simulate_orders.py'
spec = importlib.util.spec_from_file_location('order_simulator', SCRIPT)
simulator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(simulator)


@pytest.fixture
def database(tmp_path):
    path = tmp_path / 'shop.db'
    build_shop(path)
    with sqlite3.connect(path) as connection:
        connection.executescript('''
            ALTER TABLE shop ADD COLUMN is_sellerpilot INTEGER DEFAULT 1;
            ALTER TABLE shop ADD COLUMN vacation_mode INTEGER DEFAULT 0;
            CREATE TABLE user(id INTEGER PRIMARY KEY,username TEXT UNIQUE,email TEXT UNIQUE,password_hash TEXT,role TEXT);
            ALTER TABLE "order" ADD COLUMN user_id INTEGER;
            ALTER TABLE "order" ADD COLUMN checkout_reference TEXT;
            ALTER TABLE "order" ADD COLUMN shipping_fee REAL;
            ALTER TABLE "order" ADD COLUMN discount_amount REAL;
            ALTER TABLE "order" ADD COLUMN shipping_name TEXT;
            ALTER TABLE "order" ADD COLUMN shipping_phone TEXT;
            ALTER TABLE "order" ADD COLUMN shipping_address TEXT;
            ALTER TABLE "order" ADD COLUMN note TEXT;
            ALTER TABLE "order" ADD COLUMN payment_method TEXT;
            ALTER TABLE "order" ADD COLUMN payment_status TEXT;
            ALTER TABLE order_item ADD COLUMN variant_id INTEGER;
            ALTER TABLE order_item ADD COLUMN sku TEXT;
            ALTER TABLE order_item ADD COLUMN variant_title TEXT;
            INSERT INTO shop(id,slug,name,status) VALUES(2,'other','Other','active');
            INSERT INTO product(id,name,price,category_id,stock,sku,status,shop_id,sold_count,historical_sold_count)
            VALUES(3,'Foreign',123000,4,100,'FOREIGN','active',2,0,0);
        ''')
    return path


def test_simulation_updates_today_dashboard_and_reserves_actual_variant_stock(database):
    shop = UTEMallRepository(database, 'Asia/Ho_Chi_Minh', 'utech-official')
    before = management.dashboard(shop, 1)
    connection = simulator.connect_shop(database)
    try:
        results = [simulator.create_order(connection, rng=random.Random(seed), status='delivered') for seed in range(3)]
        after = management.dashboard(shop, 1)
        assert after['order_count'] == before['order_count'] + 3
        assert after['order_value_vnd'] == before['order_value_vnd'] + sum(row['total_vnd'] for row in results)
        assert after['delivered_value_vnd'] == sum(row['total_vnd'] for row in results)
        assert connection.execute('SELECT COUNT(*) FROM user').fetchone()[0] == 1
        assert connection.execute('SELECT stock FROM product WHERE id=3').fetchone()[0] == 100
        for row in connection.execute('SELECT * FROM product WHERE shop_id=1'):
            sold = connection.execute('SELECT COALESCE(SUM(quantity),0) FROM order_item WHERE product_id=?', (row['id'],)).fetchone()[0]
            initial = 8 if row['id'] == 1 else 6
            assert row['stock'] == initial - sold and row['sold_count'] == sold
            assert row['stock'] == connection.execute('SELECT stock FROM product_variant WHERE product_id=?', (row['id'],)).fetchone()[0]
        for row in connection.execute('SELECT * FROM "order"'):
            assert row['total_amount'] == connection.execute('SELECT SUM(quantity*price) FROM order_item WHERE order_id=?', (row['id'],)).fetchone()[0]
            assert row['payment_status'] == 'paid' and simulator.MARKER in row['note']
            recorded = order_detail(shop, row['id'])
            assert not recorded['unrecorded_status_change']
            assert len(recorded['events']) == 1
            assert recorded['events'][0]['kind'] == 'initial'
            assert recorded['events'][0]['from_status'] == recorded['events'][0]['to_status'] == 'delivered'
    finally:
        connection.close()


def test_failed_line_insert_rolls_back_order_buyer_and_both_stocks(database):
    connection = simulator.connect_shop(database)
    try:
        connection.execute("CREATE TRIGGER fail_item BEFORE INSERT ON order_item BEGIN SELECT RAISE(ABORT,'simulated failure'); END")
        with pytest.raises(sqlite3.IntegrityError):
            simulator.create_order(connection, rng=random.Random(1))
        assert not connection.in_transaction
        assert connection.execute('SELECT COUNT(*) FROM "order"').fetchone()[0] == 0
        assert connection.execute('SELECT COUNT(*) FROM user').fetchone()[0] == 0
        assert [row[0] for row in connection.execute('SELECT stock FROM product WHERE shop_id=1 ORDER BY id')] == [8, 6]
        assert [row[0] for row in connection.execute('SELECT stock FROM product_variant ORDER BY id')] == [8, 6]
    finally:
        connection.close()


@pytest.mark.parametrize('status', ['pending', 'paid', 'shipped'])
def test_simulated_cod_is_not_collected_before_delivery(database, status):
    connection = simulator.connect_shop(database)
    try:
        order = simulator.create_order(connection, rng=random.Random(1), status=status)
        assert connection.execute('SELECT payment_status FROM "order" WHERE id=?', (order['id'],)).fetchone()[0] == 'unpaid'
    finally:
        connection.close()


def test_simulator_never_oversells_or_uses_inactive_variants(database):
    connection = simulator.connect_shop(database)
    try:
        connection.execute('UPDATE product SET stock=1 WHERE shop_id=1')
        connection.execute('UPDATE product_variant SET stock=1')
        simulator.create_order(connection, rng=random.Random(2))
        while connection.execute('SELECT SUM(stock) FROM product WHERE shop_id=1').fetchone()[0]:
            simulator.create_order(connection, rng=random.Random(3))
        with pytest.raises(ValueError, match='hết sản phẩm'):
            simulator.create_order(connection)
        assert connection.execute('SELECT MIN(stock) FROM product').fetchone()[0] == 0
        connection.execute('UPDATE product SET stock=5 WHERE shop_id=1')
        connection.execute('UPDATE product_variant SET stock=5,is_active=0')
        with pytest.raises(ValueError, match='hết sản phẩm'):
            simulator.create_order(connection)
    finally:
        connection.close()


def test_cli_creates_requested_count_in_explicit_relative_database(database):
    result = subprocess.run([sys.executable, str(SCRIPT), '--database', database.name,
        '--count', '2', '--interval', '1', '--status', 'pending', '--seed', '12'],
        cwd=database.parent, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert result.stdout.count('Đơn #') == 2
    with sqlite3.connect(database) as connection:
        assert connection.execute('SELECT COUNT(*) FROM "order" WHERE status=\'pending\' AND payment_status=\'unpaid\'').fetchone()[0] == 2


def test_vn_midnight_orders_are_counted_for_the_right_day(database, monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            instant = cls(2026, 10, 17, 17, 1, tzinfo=timezone.utc)
            return instant.astimezone(tz) if tz else instant.replace(tzinfo=None)
    monkeypatch.setattr(management, 'datetime', Clock)
    connection = simulator.connect_shop(database)
    try:
        simulator.create_order(connection, now=datetime(2026, 10, 17, 16, 59, tzinfo=timezone.utc))
        new = simulator.create_order(connection, now=datetime(2026, 10, 17, 17, 0, tzinfo=timezone.utc))
        result = management.dashboard(UTEMallRepository(database, 'Asia/Ho_Chi_Minh', 'utech-official'), 1)
        assert result['to_date'] == '2026-10-18'
        assert result['order_count'] == 1 and result['order_value_vnd'] == new['total_vnd']
    finally:
        connection.close()


def test_wrong_or_paused_shop_does_not_create_orders(database, tmp_path):
    with pytest.raises(ValueError):
        simulator.connect_shop(tmp_path / 'missing.db')
    assert not (tmp_path / 'missing.db').exists()
    connection = simulator.connect_shop(database)
    try:
        with pytest.raises(ValueError, match='Không tìm thấy shop'):
            simulator.create_order(connection, shop_slug='missing')
        connection.execute('UPDATE shop SET vacation_mode=1 WHERE id=1')
        with pytest.raises(ValueError, match='tạm nghỉ'):
            simulator.create_order(connection)
        assert connection.execute('SELECT COUNT(*) FROM "order"').fetchone()[0] == 0
        assert connection.execute('SELECT COUNT(*) FROM user').fetchone()[0] == 0
    finally:
        connection.close()
