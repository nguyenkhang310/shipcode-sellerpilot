"""Create a fresh, reproducible team demo without copying a developer database."""
from __future__ import annotations

import argparse
import getpass
import gzip
import json
import os
from pathlib import Path
import secrets
import sqlite3
from dotenv import dotenv_values, load_dotenv, set_key

ROOT = Path(__file__).resolve().parent


def ensure_local_configuration(root: Path):
    """Generate only a missing key; never rotate an existing shop session key."""
    env_path = root / '.env'
    if not env_path.exists():
        with env_path.open('x') as stream:
            stream.write('FLASK_DEBUG=0\nENABLE_EXTERNAL_PAYMENTS=0\n')
        env_path.chmod(0o600)
    values = dotenv_values(env_path)
    secret = (os.environ.get('SECRET_KEY') or values.get('SECRET_KEY') or '').strip()
    if not secret:
        secret = secrets.token_urlsafe(48)
        set_key(str(env_path), 'SECRET_KEY', secret)
        env_path.chmod(0o600)
    os.environ['SECRET_KEY'] = secret
    storage = (os.environ.get('REDIS_URL') or values.get('REDIS_URL')
               or os.environ.get('LIMITER_STORAGE_URI') or values.get('LIMITER_STORAGE_URI') or '').strip()
    if not storage:
        # This bootstrap is for a single-process local demo, with debugging off.
        # Keep deployed Redis settings intact; app.py still requires configured storage.
        set_key(str(env_path), 'LIMITER_STORAGE_URI', 'memory://')
        env_path.chmod(0o600)
        os.environ['LIMITER_STORAGE_URI'] = 'memory://'


def main():
    parser = argparse.ArgumentParser(description='Khởi tạo UTE MALL trên database trống; không ghi đè shop đang dùng.')
    parser.add_argument('--check', action='store_true', help='Chỉ kiểm tra database đã khởi tạo')
    args = parser.parse_args()
    load_dotenv(ROOT / '.env', override=False)
    database = Path(os.environ.get('STORE_DATABASE_PATH') or ROOT / 'instance/ecommerce.db').resolve()
    if args.check:
        if not database.is_file():
            raise SystemExit('Chưa có database. Chạy bootstrap_demo.py trước.')
        with sqlite3.connect(f'file:{database}?mode=ro', uri=True) as connection:
            print({'integrity': connection.execute('PRAGMA quick_check').fetchone()[0],
                   'products': connection.execute('SELECT count(*) FROM product').fetchone()[0],
                   'orders': connection.execute('SELECT count(*) FROM "order"').fetchone()[0],
                   'shops': connection.execute('SELECT count(*) FROM shop').fetchone()[0]})
        return
    if database.is_file():
        with sqlite3.connect(f'file:{database}?mode=ro', uri=True) as connection:
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if 'product' in tables and connection.execute('SELECT count(*) FROM product').fetchone()[0]:
                raise SystemExit('Database đã có sản phẩm. Không ghi đè. Dùng --check để kiểm tra hoặc STORE_DATABASE_PATH để tạo demo ở đường dẫn mới.')
    password = os.environ.get('DEMO_SELLER_PASSWORD')
    if not password:
        password = getpass.getpass('Đặt mật khẩu cho tài khoản chủ shop utech (ít nhất 12 ký tự): ')
        if password != getpass.getpass('Nhập lại mật khẩu: '):
            raise SystemExit('Mật khẩu không khớp.')
    if len(password) < 12:
        raise SystemExit('Mật khẩu cần ít nhất 12 ký tự.')
    os.environ['DEMO_SELLER_PASSWORD'] = password
    os.environ['STORE_DATABASE_PATH'] = str(database)
    ensure_local_configuration(ROOT)
    database.parent.mkdir(parents=True, exist_ok=True)
    # Import only after runtime configuration is ready. Startup creates schema,
    # not accounts/data from a checked-in developer database.
    from app import app
    from extensions import db
    from marketplace_setup import initialize_marketplace
    from seed_utech_operations import main as seed_operations
    with gzip.open(ROOT / 'data/demo-catalog.json.gz', 'rt', encoding='utf-8') as stream:
        catalog = json.load(stream)
    if catalog.get('schema_version') != 1:
        raise SystemExit('Phiên bản catalog chưa được hỗ trợ.')
    with app.app_context():
        with sqlite3.connect(database) as connection:
            connection.execute('PRAGMA foreign_keys=ON')
            for table in ('category', 'shop', 'product', 'product_variant'):
                allowed = {row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')}
                for record in catalog[table]:
                    fields = [name for name in record if name in allowed]
                    columns = ','.join('"' + name + '"' for name in fields)
                    placeholders = ','.join('?' for _ in fields)
                    connection.execute(f'INSERT INTO "{table}" ({columns}) VALUES ({placeholders})', [record[name] for name in fields])
        db.session.expire_all()
    seed_operations()
    initialize_marketplace(app)
    print('Đã tạo UTE MALL: 24 shop, catalog đa ngành và dữ liệu vận hành mô phỏng.')
    print('Chủ shop: utech. Dùng mật khẩu vừa đặt. Không có mật khẩu mặc định trong source.')


if __name__ == '__main__':
    main()
