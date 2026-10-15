"""Generate deterministic, clearly synthetic operating data for UTech Official."""
from __future__ import annotations
import random
import secrets
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from werkzeug.security import generate_password_hash

from app import app, ensure_db_schema, ensure_order_schema, ensure_user_schema
from extensions import db
from models import Order, OrderItem, Product, ProductVariant, Shop, User

SEED_NOTE = '[UTECH-DEMO-V1]'
VN_TZ = ZoneInfo('Asia/Ho_Chi_Minh')


def to_utc_naive(day: date, hour: int, minute: int):
    local = datetime.combine(day, time(hour, minute), tzinfo=VN_TZ)
    return local.astimezone(timezone.utc).replace(tzinfo=None)


def main():
    rng = random.Random(20261015)
    now_vn = datetime.now(VN_TZ)
    today = now_vn.date()
    with app.app_context():
        db.create_all(); ensure_db_schema(); ensure_order_schema(); ensure_user_schema()
        shop = Shop.query.filter_by(slug='utech-official').one()
        products = Product.query.filter_by(shop_id=shop.id, status='active').order_by(Product.id).all()
        if len(products) < 50:
            raise SystemExit('UTech catalog chưa đủ để seed dữ liệu vận hành.')

        # Idempotent: replace only records carrying the explicit synthetic seed marker.
        old_orders = Order.query.filter(Order.note.like(f'{SEED_NOTE}%')).all()
        for order in old_orders: db.session.delete(order)
        db.session.commit()

        buyers = []
        password_hash = generate_password_hash(secrets.token_urlsafe(32), method='pbkdf2:sha256')
        for index in range(1, 451):
            email = f'buyer.utech.{index:04d}@example.test'
            user = User.query.filter_by(email=email).first()
            if not user:
                user = User(username=f'ute_buyer_{index:04d}', email=email, password_hash=password_hash, role='user')
                db.session.add(user)
            buyers.append(user)
        db.session.flush()

        statuses = ['delivered']*68 + ['shipped']*11 + ['paid']*7 + ['pending']*8 + ['cancelled']*6
        payment_methods = ['COD']*52 + ['MOMO']*22 + ['VNPAY']*16 + ['BANK_TRANSFER']*10
        cities = ['TP. Hồ Chí Minh', 'Hà Nội', 'Đà Nẵng', 'Bình Dương', 'Đồng Nai', 'Cần Thơ']
        order_count = 1500
        item_count = 0
        for index in range(order_count):
            # Ensure today has a useful live dashboard; spread the rest over the previous year.
            days_ago = 0 if index < 14 else int((index-14) * 365 / (order_count-14))
            day = today - timedelta(days=days_ago)
            hour = rng.choices([9,11,14,16,20,22], weights=[12,15,18,16,26,13])[0]
            minute = rng.randrange(0, 60)
            if days_ago == 0:
                hour = min(hour, now_vn.hour)
                if hour == now_vn.hour:
                    minute = min(minute, now_vn.minute)
            created_at = to_utc_naive(day, hour, minute)
            today_statuses = ['delivered']*6 + ['pending']*3 + ['paid']*2 + ['shipped']*2 + ['cancelled']
            status = today_statuses[index] if index < len(today_statuses) else statuses[(index*17 + 9) % len(statuses)]
            payment = payment_methods[(index*13 + 5) % len(payment_methods)]
            buyer = buyers[(index*29 + 7) % len(buyers)]
            chosen = rng.sample(products, k=1 + (1 if index % 4 == 0 else 0) + (1 if index % 13 == 0 else 0))
            lines = []
            subtotal = 0
            for product in chosen:
                qty = 2 if index % 17 == 0 else 1
                variant = ProductVariant.query.filter_by(product_id=product.id, is_active=True).first()
                unit_price = float(variant.price if variant else product.price)
                subtotal += unit_price * qty
                lines.append((product, variant, qty, unit_price))
            order = Order(
                user_id=buyer.id, shop_id=shop.id, total_amount=subtotal,
                status=status, created_at=created_at,
                shipping_name=f'Khách hàng demo {buyer.id}',
                shipping_phone=f'09{(index*7919)%100000000:08d}',
                shipping_address=f'{12 + index%180} Đường Demo, {cities[index % len(cities)]}',
                note=f'{SEED_NOTE} dữ liệu mô phỏng, không chứa PII thật',
                payment_method=payment,
                payment_status='paid' if status in {'paid','shipped','delivered'} else ('cancelled' if status=='cancelled' else 'unpaid'),
            )
            db.session.add(order); db.session.flush()
            for product, variant, qty, unit_price in lines:
                db.session.add(OrderItem(
                    order_id=order.id, product_id=product.id,
                    variant_id=variant.id if variant else None,
                    quantity=qty, price=unit_price,
                    sku=variant.sku if variant else product.sku,
                    variant_title=variant.title if variant else None,
                ))
                item_count += 1
            if index and index % 250 == 0: db.session.commit()
        db.session.commit()
        print({'shop':shop.slug,'orders':order_count,'order_items':item_count,'buyers':len(buyers),'today':today.isoformat()})

if __name__ == '__main__': main()
