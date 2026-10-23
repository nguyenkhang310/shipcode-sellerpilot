from __future__ import annotations
import os
from dotenv import load_dotenv
load_dotenv(override=False)
import sqlite3
import uuid
import json
import hmac
import hashlib
import urllib.parse
from urllib.parse import urlparse, urljoin
import unicodedata
import re
from pathlib import Path
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, make_response, abort
from werkzeug.security import generate_password_hash
from password_security import check_password_hash
from werkzeug.utils import secure_filename
from flask_login import login_user, login_required, logout_user, current_user
from sqlalchemy import case, func, or_, text
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import requests
from typing import Optional

from extensions import db, login_manager
from models import User, Shop, Category, Product, ProductVariant, Cart, CartItem, Order, OrderItem, Review, Contact, PaymentTransaction, WishlistItem, Coupon, ShopFollow

app = Flask(__name__, instance_relative_config=True)
os.makedirs(app.instance_path, exist_ok=True)
_env_secret = (os.environ.get('SECRET_KEY') or '').strip()
_is_debug_mode = os.environ.get('FLASK_DEBUG', '').strip().lower() in ['1', 'true', 'yes']
_is_testing_mode = os.environ.get('TESTING', '').strip().lower() in ['1', 'true', 'yes']
if not _env_secret:
    if _is_debug_mode or _is_testing_mode:
        _env_secret = 'dev-secret-key-change-me-before-deploy'
    else:
        raise RuntimeError("SECRET_KEY must be set for all deployed environments.")
elif len(_env_secret) < 32:
    raise RuntimeError("SECRET_KEY must be at least 32 characters long.")

app.config['SECRET_KEY'] = _env_secret
app.config['STORE_DATABASE_PATH'] = os.environ.get('STORE_DATABASE_PATH') or os.path.join(app.instance_path, 'ecommerce.db')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + app.config['STORE_DATABASE_PATH']
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['DEMO_REVIEWS_ENABLED'] = os.environ.get('ENABLE_DEMO_REVIEWS', '1') == '1'
app.config['PREFERRED_URL_SCHEME'] = os.environ.get('PREFERRED_URL_SCHEME', 'https' if os.environ.get('COOKIE_SECURE', '').strip().lower() in ['1', 'true', 'yes'] else 'http')

# Session / cookie hardening (set COOKIE_SECURE=1 when behind HTTPS)
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = os.environ.get('SESSION_COOKIE_SAMESITE', 'Lax')
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('COOKIE_SECURE', '').strip().lower() in ['1', 'true', 'yes']
app.config['REMEMBER_COOKIE_HTTPONLY'] = True
app.config['REMEMBER_COOKIE_SAMESITE'] = os.environ.get('REMEMBER_COOKIE_SAMESITE', 'Lax')
app.config['REMEMBER_COOKIE_SECURE'] = os.environ.get('COOKIE_SECURE', '').strip().lower() in ['1', 'true', 'yes']

# CSRF config for AJAX
app.config['WTF_CSRF_HEADERS'] = ['X-CSRFToken', 'X-CSRF-Token']

# Shared shop config
app.config['SHOP_INFO'] = {
    'name': os.environ.get('SHOP_NAME', 'Shopee').strip() or 'Shopee',
    'tagline': os.environ.get(
        'SHOP_TAGLINE',
        'Mua sắm đa ngành, kết nối hàng nghìn gian hàng.'
    ).strip(),
    'description': os.environ.get(
        'SHOP_DESCRIPTION',
        'Mua sắm thuận tiện, lựa chọn đa dạng, kết nối những gian hàng bạn yêu thích.'
    ).strip(),
    'address': '',
    'phone': '',
    'phone_display': '',
    'email': '',
    'support_email': '',
    'hours': 'Hỗ trợ trực tuyến mỗi ngày',
    'map_embed_url': '',
}

# Payment config (prefer env vars in production)
app.config['BANK_TRANSFER_INFO'] = os.environ.get('BANK_TRANSFER_INFO', '')
app.config['ENABLE_EXTERNAL_PAYMENTS'] = os.environ.get('ENABLE_EXTERNAL_PAYMENTS', '0') == '1'

app.config['MOMO_ENDPOINT'] = os.environ.get('MOMO_ENDPOINT') or 'https://test-payment.momo.vn/v2/gateway/api/create'
app.config['MOMO_PARTNER_CODE'] = os.environ.get('MOMO_PARTNER_CODE') or ''
app.config['MOMO_ACCESS_KEY'] = os.environ.get('MOMO_ACCESS_KEY') or ''
app.config['MOMO_SECRET_KEY'] = os.environ.get('MOMO_SECRET_KEY') or ''

app.config['VNPAY_TMN_CODE'] = os.environ.get('VNPAY_TMN_CODE') or ''
app.config['VNPAY_HASH_SECRET'] = os.environ.get('VNPAY_HASH_SECRET') or ''
app.config['VNPAY_URL'] = os.environ.get('VNPAY_URL') or 'https://sandbox.vnpayment.vn/paymentv2/vpcpay.html'
app.config['PAYMENT_ENV_VARS'] = {
    'MOMO': ['MOMO_ENDPOINT', 'MOMO_PARTNER_CODE', 'MOMO_ACCESS_KEY', 'MOMO_SECRET_KEY'],
    'VNPAY': ['VNPAY_TMN_CODE', 'VNPAY_HASH_SECRET', 'VNPAY_URL'],
    'BANK_TRANSFER': ['BANK_TRANSFER_INFO'],
}

app.config['COUPONS'] = {
    "WELCOME10": {"type": "percent", "value": 10, "min_subtotal": 200000},
    "FREESHIP": {"type": "shipping", "value": 30000, "min_subtotal": 300000},
    "SAVE50K": {"type": "fixed", "value": 50000, "min_subtotal": 600000},
}

# Custom Jinja2 filters
@app.template_filter('enumerate')
def jinja_enumerate(iterable, start=0):
    return enumerate(iterable, start=start)

@app.template_filter('fromjson')
def jinja_fromjson(value):
    if not value:
        return []
    try:
        return json.loads(value)
    except Exception:
        return []

@app.template_filter('mask_username')
def mask_username(value):
    """Protect buyer identity on public review pages."""
    text = str(value or 'Người mua').strip()
    if len(text) <= 2:
        return text[0] + '*' if text else 'Người mua'
    return text[0] + ('*' * min(max(len(text) - 2, 4), 10)) + text[-1]


@app.template_filter('reviewer_name')
def reviewer_name(review):
    name = review.user.username
    return name.rsplit('.demo', 1)[0] if review.is_demo else name


# Upload config
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'mp4', 'mov', 'avi'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def ensure_db_schema():
    db_path = app.config['STORE_DATABASE_PATH']
    if not os.path.exists(db_path):
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(product);")
    existing_columns = {row[1] for row in cursor.fetchall()}

    if 'stock' not in existing_columns:
        cursor.execute("ALTER TABLE product ADD COLUMN stock INTEGER DEFAULT 100")
    if 'created_at' not in existing_columns:
        cursor.execute("ALTER TABLE product ADD COLUMN created_at DATETIME")
        timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute(
            "UPDATE product SET created_at = ? WHERE created_at IS NULL",
            (timestamp,)
        )
    if 'extra_images' not in existing_columns:
        cursor.execute("ALTER TABLE product ADD COLUMN extra_images TEXT")
    if 'video_url' not in existing_columns:
        cursor.execute("ALTER TABLE product ADD COLUMN video_url VARCHAR(500)")
    if 'sizes' not in existing_columns:
        cursor.execute("ALTER TABLE product ADD COLUMN sizes TEXT")
    if 'subcategory' not in existing_columns:
        cursor.execute("ALTER TABLE product ADD COLUMN subcategory VARCHAR(100)")
    product_columns = {
        'sku': 'VARCHAR(100)',
        'slug': 'VARCHAR(220)',
        'source': "VARCHAR(50) DEFAULT 'manual'",
        'source_id': 'VARCHAR(100)',
        'source_url': 'VARCHAR(500)',
        'vendor': 'VARCHAR(150)',
        'material': 'VARCHAR(300)',
        'currency': "VARCHAR(10) DEFAULT 'VND'",
        'rating': 'FLOAT',
        'rating_count': 'INTEGER DEFAULT 0',
        'status': "VARCHAR(20) DEFAULT 'active'",
        'shop_id': 'INTEGER',
        'sold_count': 'INTEGER DEFAULT 0',
        'location': 'VARCHAR(120)',
        'attributes_json': 'TEXT',
        'is_featured': 'BOOLEAN DEFAULT 0',
    }
    for column_name, column_type in product_columns.items():
        if column_name not in existing_columns:
            cursor.execute(f"ALTER TABLE product ADD COLUMN {column_name} {column_type}")
    cursor.execute("UPDATE product SET source='manual' WHERE source IS NULL")
    cursor.execute("UPDATE product SET currency='VND' WHERE currency IS NULL")
    cursor.execute("UPDATE product SET rating_count=0 WHERE rating_count IS NULL")
    cursor.execute("UPDATE product SET status='active' WHERE status IS NULL")
    cursor.execute("UPDATE product SET sold_count=0 WHERE sold_count IS NULL")
    cursor.execute("UPDATE product SET is_featured=0 WHERE is_featured IS NULL")
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_product_sku ON product(sku)")
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_product_slug ON product(slug)")
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_product_source_id ON product(source_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_product_shop_id ON product(shop_id)")

    cursor.execute("PRAGMA table_info(category);")
    category_columns = {row[1] for row in cursor.fetchall()}
    for column_name, column_type in {
        'slug': 'VARCHAR(120)',
        'parent_id': 'INTEGER',
        'icon': 'VARCHAR(80)',
        'image_url': 'VARCHAR(500)',
        'display_order': 'INTEGER DEFAULT 0',
    }.items():
        if column_name not in category_columns:
            cursor.execute(f"ALTER TABLE category ADD COLUMN {column_name} {column_type}")
    cursor.execute("UPDATE category SET display_order=id WHERE display_order IS NULL")
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_category_slug ON category(slug)")
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_category_parent_id ON category(parent_id)")

    conn.commit()
    conn.close()

def ensure_order_schema():
    db_path = app.config['STORE_DATABASE_PATH']
    if not os.path.exists(db_path):
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info('order');")
    cols = {row[1] for row in cursor.fetchall()}

    if 'shipping_name' not in cols:
        cursor.execute("ALTER TABLE 'order' ADD COLUMN shipping_name VARCHAR(150)")
    if 'shipping_phone' not in cols:
        cursor.execute("ALTER TABLE 'order' ADD COLUMN shipping_phone VARCHAR(30)")
    if 'shipping_address' not in cols:
        cursor.execute("ALTER TABLE 'order' ADD COLUMN shipping_address VARCHAR(500)")
    if 'note' not in cols:
        cursor.execute("ALTER TABLE 'order' ADD COLUMN note VARCHAR(500)")
    if 'payment_method' not in cols:
        cursor.execute("ALTER TABLE 'order' ADD COLUMN payment_method VARCHAR(50) DEFAULT 'COD'")
        cursor.execute("UPDATE 'order' SET payment_method='COD' WHERE payment_method IS NULL")
    if 'payment_status' not in cols:
        cursor.execute("ALTER TABLE 'order' ADD COLUMN payment_status VARCHAR(50) DEFAULT 'unpaid'")
        cursor.execute("UPDATE 'order' SET payment_status='unpaid' WHERE payment_status IS NULL")
    if 'payment_ref' not in cols:
        cursor.execute("ALTER TABLE 'order' ADD COLUMN payment_ref VARCHAR(200)")
    if 'shop_id' not in cols:
        cursor.execute("ALTER TABLE 'order' ADD COLUMN shop_id INTEGER")
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_order_shop_id ON 'order'(shop_id)")

    # Same database triggers as the app and simulator. Install after committing
    # the schema above: executescript commits its pending transaction first.
    conn.commit()
    journal = Path(__file__).resolve().parents[1] / 'backend/app/integrations/order_history.sql'
    conn.executescript('BEGIN IMMEDIATE;\n' + journal.read_text(encoding='utf-8') + '\nCOMMIT;')

    cursor.execute("PRAGMA table_info(cart_item);")
    cart_item_cols = {row[1] for row in cursor.fetchall()}
    if 'variant_id' not in cart_item_cols:
        cursor.execute("ALTER TABLE cart_item ADD COLUMN variant_id INTEGER")
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_cart_item_variant_id ON cart_item(variant_id)")

    cursor.execute("PRAGMA table_info(order_item);")
    order_item_cols = {row[1] for row in cursor.fetchall()}
    if 'variant_id' not in order_item_cols:
        cursor.execute("ALTER TABLE order_item ADD COLUMN variant_id INTEGER")
    if 'sku' not in order_item_cols:
        cursor.execute("ALTER TABLE order_item ADD COLUMN sku VARCHAR(100)")
    if 'variant_title' not in order_item_cols:
        cursor.execute("ALTER TABLE order_item ADD COLUMN variant_title VARCHAR(200)")

    conn.commit()
    conn.close()


def ensure_user_schema():
    """Thêm cột reset_token vào bảng user nếu chưa có (dùng schema migration đơn giản)."""
    db_path = app.config['STORE_DATABASE_PATH']
    if not os.path.exists(db_path):
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(user);")
    cols = {row[1] for row in cursor.fetchall()}

    if 'reset_token' not in cols:
        cursor.execute("ALTER TABLE user ADD COLUMN reset_token VARCHAR(100)")
    if 'reset_token_expires' not in cols:
        cursor.execute("ALTER TABLE user ADD COLUMN reset_token_expires DATETIME")

    conn.commit()
    conn.close()


def _hmac_sha256(secret: str, data: str) -> str:
    return hmac.new(secret.encode('utf-8'), data.encode('utf-8'), hashlib.sha256).hexdigest()


def _vnpay_hmac_sha512(secret: str, data: str) -> str:
    return hmac.new(secret.encode('utf-8'), data.encode('utf-8'), hashlib.sha512).hexdigest()


def _absolute_url(endpoint: str, **values) -> str:
    base_url = os.environ.get('PUBLIC_STORE_URL', '').strip()
    if base_url:
        # Nếu có PUBLIC_URL (ngrok), dùng urljoin với base_url
        return urljoin(base_url, url_for(endpoint, **values))
    return url_for(endpoint, _external=True, **values)


def _missing_payment_env_vars() -> dict[str, list[str]]:
    missing: dict[str, list[str]] = {}
    for provider, env_keys in app.config.get('PAYMENT_ENV_VARS', {}).items():
        empty_keys = [key for key in env_keys if not str(app.config.get(key, '')).strip()]
        if empty_keys:
            missing[provider] = empty_keys
    return missing


def _is_safe_redirect_url(target: str) -> bool:
    if not target:
        return False
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ('http', 'https') and ref_url.netloc == test_url.netloc


def _coupon_to_dict(c: Coupon) -> dict:
    return {
        "type": c.coupon_type,
        "value": float(c.value),
        "min_subtotal": float(c.min_subtotal or 0),
    }


def _coupon_is_available(c: Coupon) -> bool:
    if not c or not c.is_active:
        return False
    if c.expires_at and c.expires_at < datetime.utcnow():
        return False
    if c.max_uses is not None and int(c.used_count or 0) >= int(c.max_uses):
        return False
    return True


def _resolve_coupon_by_code(code: str | None) -> tuple[str | None, dict | None, Coupon | None]:
    if not code:
        return None, None, None
    normalized = code.strip().upper()
    if not normalized:
        return None, None, None
    db_coupon = Coupon.query.filter_by(code=normalized).first()
    if db_coupon and _coupon_is_available(db_coupon):
        return normalized, _coupon_to_dict(db_coupon), db_coupon
    if db_coupon: return normalized, None, None
    static_coupon = app.config.get('COUPONS', {}).get(normalized)
    if static_coupon:
        return normalized, static_coupon, None
    return normalized, None, None


db.init_app(app)
login_manager.init_app(app)
login_manager.login_view = 'login'
csrf = CSRFProtect(app)
_redis_url = (os.environ.get('REDIS_URL') or os.environ.get('LIMITER_STORAGE_URI') or '').strip()
_limiter_storage_uri = _redis_url
if not _limiter_storage_uri:
    if _is_debug_mode or _is_testing_mode:
        _limiter_storage_uri = 'memory://'
    else:
        raise RuntimeError("Production rate limiting requires REDIS_URL or LIMITER_STORAGE_URI.")
app.config['RATELIMIT_STORAGE_URI'] = _limiter_storage_uri
app.config['RATELIMIT_STRATEGY'] = 'fixed-window'
limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=["2000 per hour"],
    storage_uri=_limiter_storage_uri,
)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def _session_cart_get() -> dict:
    cart = session.get('cart')
    if isinstance(cart, dict):
        return cart
    cart = {}
    session['cart'] = cart
    return cart


def _session_cart_set(cart: dict) -> None:
    session['cart'] = cart
    session.modified = True


def _cart_key(product_id: int, variant_id: int | None = None) -> str:
    return f"{int(product_id)}:{int(variant_id) if variant_id else 0}"


def _parse_cart_key(value: str) -> tuple[int, int | None]:
    raw = str(value)
    if ':' not in raw:
        return int(raw), None
    product_raw, variant_raw = raw.split(':', 1)
    variant_id = int(variant_raw)
    return int(product_raw), variant_id or None


def _available_stock(product: Product, variant: ProductVariant | None = None) -> int:
    return max(0, int(variant.stock if variant is not None else (product.stock or 0)))


def _unit_price(product: Product, variant: ProductVariant | None = None) -> float:
    return float(variant.price if variant is not None else product.price)


def _build_guest_cart_view(cart_dict: dict):
    """
    Build a lightweight cart-like object for templates:
    - .items: list of { id, product, quantity }
    """
    items = []
    for line_key, qty in cart_dict.items():
        try:
            pid, variant_id = _parse_cart_key(line_key)
            qty_int = int(qty)
        except Exception:
            continue
        if qty_int < 1:
            continue
        product = Product.query.get(pid)
        if not product:
            continue
        variant = ProductVariant.query.get(variant_id) if variant_id else None
        if variant and variant.product_id != product.id:
            continue
        items.append({
            'id': str(line_key),
            'product_id': product.id,
            'variant_id': variant.id if variant else None,
            'product': product,
            'variant': variant,
            'unit_price': _unit_price(product, variant),
            'quantity': min(qty_int, _available_stock(product, variant)),
        })

    class _CartView:
        def __init__(self, items):
            self.items = items

    return _CartView(items)


def _get_or_create_user_cart(user_id: int) -> Cart:
    active_cart = Cart.query.filter_by(user_id=user_id).first()
    if not active_cart:
        active_cart = Cart(user_id=user_id)
        db.session.add(active_cart)
        db.session.commit()
    return active_cart


def _merge_session_cart_into_user_cart(user: User) -> None:
    cart_dict = _session_cart_get()
    if not cart_dict:
        return
    active_cart = _get_or_create_user_cart(user.id)
    for line_key, qty in cart_dict.items():
        try:
            pid, variant_id = _parse_cart_key(line_key)
            qty_int = int(qty)
        except Exception:
            continue
        if qty_int < 1:
            continue
        product = Product.query.get(pid)
        if not product:
            continue
        variant = ProductVariant.query.get(variant_id) if variant_id else None
        if variant and variant.product_id != product.id:
            continue
        stock = _available_stock(product, variant)
        if stock < 1:
            continue
        existing = CartItem.query.filter_by(
            cart_id=active_cart.id,
            product_id=pid,
            variant_id=variant.id if variant else None,
        ).first()
        if existing:
            existing.quantity = min(int(existing.quantity) + qty_int, stock)
        else:
            db.session.add(CartItem(
                cart_id=active_cart.id,
                product_id=pid,
                variant_id=variant.id if variant else None,
                quantity=min(qty_int, stock),
            ))
    _session_cart_set({})
    db.session.commit()


def _normalize_text(value: str) -> str:
    if not value:
        return ""
    value = unicodedata.normalize("NFD", value)
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
    value = value.replace("đ", "d").replace("Đ", "D")
    value = value.lower()
    value = re.sub(r"[^a-z0-9\s]", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _extract_cart_line(item):
    if hasattr(item, "product"):
        return item.product, getattr(item, 'variant', None), int(item.quantity)
    return item.get("product"), item.get("variant"), int(item.get("quantity", 0))


def _compute_totals_from_items(items, coupon_code: str | None = None):
    lines=[_extract_cart_line(item) for item in items]
    groups={}
    for product, variant, qty in lines:
        if not product or qty<1: continue
        groups[product.shop_id]=groups.get(product.shop_id,0)+int(_unit_price(product,variant)*qty)
    subtotal=sum(groups.values())
    shipping_by_shop={shop_id:(0 if value>=500000 else 30000) for shop_id,value in groups.items()}
    shipping_fee=sum(shipping_by_shop.values())
    discount=0;applied_coupon=None
    normalized,coupon,db_coupon=_resolve_coupon_by_code(coupon_code)
    eligible_subtotal=subtotal
    eligible_shipping=shipping_fee
    if db_coupon and db_coupon.shop_id:
        eligible_subtotal=groups.get(db_coupon.shop_id,0)
        eligible_shipping=shipping_by_shop.get(db_coupon.shop_id,0)
    if coupon and eligible_subtotal>0 and eligible_subtotal>=float(coupon.get('min_subtotal',0)):
        value=float(coupon.get('value',0))
        if coupon['type']=='percent': discount=int(eligible_subtotal*value/100)
        elif coupon['type']=='fixed': discount=int(value)
        elif coupon['type']=='shipping': discount=min(int(value),eligible_shipping)
        discount=max(0,min(discount,eligible_shipping if coupon['type']=='shipping' else eligible_subtotal))
        applied_coupon=normalized
    return {'subtotal':int(subtotal),'shipping_fee':int(shipping_fee),'discount':int(discount),
        'grand_total':int(subtotal+shipping_fee-discount),'item_count':sum(q for p,v,q in lines),
        'applied_coupon':applied_coupon,'shipping_by_shop':shipping_by_shop}

@login_manager.user_loader
def load_user(user_id):
    user = db.session.get(User, int(user_id))
    return user if user and user.role != 'demo_reviewer' else None


@app.context_processor
def inject_user_counters():
    wishlist_count = 0
    cart_count = 0
    if current_user.is_authenticated:
        wishlist_count = WishlistItem.query.filter_by(user_id=current_user.id).count()
        cart_count = db.session.query(func.coalesce(func.sum(CartItem.quantity), 0))\
            .join(Cart, Cart.id == CartItem.cart_id)\
            .filter(Cart.user_id == current_user.id).scalar() or 0
    else:
        cart_count = sum(int(qty or 0) for qty in _session_cart_get().values())
    from seller import member_shop
    return {
        "owned_shop": member_shop(),
        "wishlist_count": wishlist_count,
        "cart_count": int(cart_count),
        "shop": app.config.get('SHOP_INFO', {}),
        "marketplace_categories": Category.query.filter_by(parent_id=None).order_by(Category.display_order, Category.id).limit(16).all(),
    }

# --- ROUTES ---

@app.route('/')
def index():
    active_products = Product.query.filter_by(status='active')
    new_products = active_products.order_by(Product.created_at.desc(), Product.id.desc()).limit(18).all()
    sale_products = active_products.filter_by(is_on_sale=True).order_by(Product.sold_count.desc()).limit(12).all()
    if not sale_products:
        sale_products = active_products.order_by(Product.sold_count.desc()).limit(12).all()
    categories = Category.query.filter_by(parent_id=None).order_by(Category.display_order, Category.id).limit(16).all()
    featured_shops = Shop.query.filter_by(status='active').order_by(Shop.is_sellerpilot.desc(), Shop.rating.desc()).limit(6).all()
    sellerpilot_shop = Shop.query.filter_by(is_sellerpilot=True, status='active').first()
    sellerpilot_products = []
    tech_hero_product = None
    if sellerpilot_shop:
        sellerpilot_products = Product.query.filter_by(shop_id=sellerpilot_shop.id, status='active').order_by(
            case((Product.source == 'sellerpilot', 0), else_=1),
            Product.created_at.desc(), Product.is_featured.desc(), Product.sold_count.desc(), Product.id.desc()
        ).limit(8).all()
        tech_hero_product = Product.query.filter(
            Product.shop_id == sellerpilot_shop.id,
            Product.status == 'active',
            Product.subcategory.in_(['Personal Computer', 'Notebook Computer', 'Computer', 'Headphones', 'Keyboards']),
        ).order_by(Product.sold_count.desc()).first()
    return render_template(
        'index.html',
        new_products=new_products,
        sale_products=sale_products,
        categories=categories,
        featured_shops=featured_shops,
        sellerpilot_shop=sellerpilot_shop,
        sellerpilot_products=sellerpilot_products,
        tech_hero_product=tech_hero_product,
    )


@app.route('/robots.txt')
def robots_txt():
    body = "\n".join([
        "User-agent: *",
        "Allow: /",
        f"Sitemap: {_absolute_url('sitemap_xml')}",
        "",
    ])
    resp = make_response(body)
    resp.headers["Content-Type"] = "text/plain; charset=utf-8"
    return resp


@app.route('/sitemap.xml')
def sitemap_xml():
    pages = []
    pages.append((_absolute_url('index'), datetime.utcnow()))
    pages.append((_absolute_url('products'), datetime.utcnow()))
    pages.append((_absolute_url('policy'), datetime.utcnow()))
    pages.append((_absolute_url('contact'), datetime.utcnow()))

    for p in Product.query.filter_by(status='active').with_entities(Product.id, Product.created_at).order_by(Product.id.desc()).all():
        pid, created_at = p
        pages.append((_absolute_url('product_detail', product_id=pid), created_at or datetime.utcnow()))

    for seller in Shop.query.filter_by(status='active').all():
        pages.append((_absolute_url('shop_page', slug=seller.slug), seller.created_at or datetime.utcnow()))

    def _fmt(dt: datetime) -> str:
        try:
            return dt.strftime("%Y-%m-%d")
        except Exception:
            return datetime.utcnow().strftime("%Y-%m-%d")

    urlset = []
    urlset.append('<?xml version="1.0" encoding="UTF-8"?>')
    urlset.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
    for loc, lastmod in pages:
        urlset.append("  <url>")
        urlset.append(f"    <loc>{loc}</loc>")
        urlset.append(f"    <lastmod>{_fmt(lastmod)}</lastmod>")
        urlset.append("  </url>")
    urlset.append("</urlset>")

    resp = make_response("\n".join(urlset))
    resp.headers["Content-Type"] = "application/xml; charset=utf-8"
    return resp

@app.route('/api/search')
def api_search():
    q = request.args.get('q', '').strip()
    if not q:
        return jsonify([])

    q_lower = q.lower()
    q_cap = q.capitalize()
    q_upper = q.upper()

    products = Product.query.filter(Product.status == 'active').filter(
        or_(
            Product.name.contains(q_lower),
            Product.name.contains(q_cap),
            Product.name.contains(q_upper)
        )
    ).order_by(Product.id.desc()).limit(6).all()

    results = []
    for p in products:
        results.append({
            'name': p.name,
            'price': "{:,.0f}đ".format(p.price),
            'image_url': p.image_url,
            'url': url_for('product_detail', product_id=p.id)
        })
    return jsonify(results)

@app.route('/products')
def products():
    query = Product.query.filter(Product.status == 'active')

    category_slug = request.args.get('category')
    category = None
    sale = request.args.get('sale')
    search_q = (request.args.get('q') or '').strip()
    sub = (request.args.get('sub') or '').strip()  # subcategory filter
    sort = request.args.get('sort', 'newest')
    min_price = request.args.get('min_price', type=float)
    max_price = request.args.get('max_price', type=float)

    if category_slug:
        category = Category.query.filter(
            or_(Category.slug == category_slug, Category.name.ilike(f'%{category_slug}%'))
        ).first()
        if category:
            query = query.filter_by(category_id=category.id)

    if request.args.get('mall')=='1':
        query=query.join(Shop,Product.shop_id==Shop.id).filter(Shop.is_verified==True)
    if sale == 'true':
        query = query.filter_by(is_on_sale=True)

    if min_price is not None:
        query = query.filter(Product.price >= min_price)
    if max_price is not None:
        query = query.filter(Product.price <= max_price)

    if sort == 'price_asc':
        query = query.order_by(Product.price.asc())
    elif sort == 'price_desc':
        query = query.order_by(Product.price.desc())
    elif sort == 'bestseller':
        query = query.order_by(Product.sold_count.desc())
    elif sort == 'rating':
        query = query.order_by(Product.rating.desc(), Product.rating_count.desc())
    else:
        query = query.order_by(Product.id.desc())

    page = max(1, request.args.get('page', 1, type=int))
    per_page = 24

    if search_q:
        q_lower = search_q.lower()
        q_cap = search_q.capitalize()
        q_upper = search_q.upper()

        query = query.filter(
            or_(
                Product.name.contains(q_lower),
                Product.name.contains(q_cap),
                Product.name.contains(q_upper)
            )
        )

    if sub:
        sub_lower = sub.lower()
        sub_cap = sub.capitalize()
        sub_upper = sub.upper()
        query = query.filter(
            or_(
                Product.subcategory == sub,
                Product.name.contains(sub_lower),
                Product.name.contains(sub_cap),
                Product.name.contains(sub_upper)
            )
        )

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    categories = Category.query.filter_by(parent_id=None).order_by(Category.display_order, Category.id).all()
    return render_template('products.html', products=pagination.items, pagination=pagination, categories=categories, selected_category=category)


@app.route('/shop/<slug>')
def shop_page(slug):
    seller = Shop.query.filter_by(slug=slug, status='active').first_or_404()
    query = Product.query.filter_by(shop_id=seller.id, status='active')
    search=(request.args.get('q') or '').strip()
    if search: query=query.filter(Product.name.ilike('%'+search+'%'))
    category_slug = (request.args.get('category') or '').strip()
    if category_slug:
        category = Category.query.filter(
            or_(Category.slug == category_slug, Category.name.ilike(f'%{category_slug}%'))
        ).first()
        if category:
            query = query.filter_by(category_id=category.id)
    page = max(1, request.args.get('page', 1, type=int))
    sort_value = (request.args.get('sort') or '').strip()
    if not sort_value:
        sort_value = 'newest' if seller.is_sellerpilot else 'bestseller'
    order_by = {
        'price_asc': Product.price.asc(),
        'price_desc': Product.price.desc(),
        'newest': Product.created_at.desc(),
        'bestseller': Product.sold_count.desc(),
    }.get(sort_value, Product.created_at.desc())
    pagination = query.order_by(order_by, Product.id.desc()).paginate(page=page, per_page=18, error_out=False)
    shop_categories = Category.query.join(Product).filter(
        Product.shop_id == seller.id,
        Product.status == 'active',
    ).distinct().order_by(Category.display_order, Category.name).all()
    return render_template(
        'shop.html',
        seller=seller,
        products=pagination.items,
        pagination=pagination,
        sort_value=sort_value,
        shop_categories=shop_categories,
        following=(ShopFollow.query.filter_by(shop_id=seller.id,user_id=current_user.id).first() is not None) if current_user.is_authenticated else False,
        product_total=Product.query.filter_by(shop_id=seller.id,status='active').count(),
    )

@app.route('/product/<int:product_id>')
def product_detail(product_id):
    product = Product.query.filter_by(id=product_id, status='active').first_or_404()
    variants = sorted(
        (variant for variant in product.variants if variant.is_active),
        key=lambda variant: (variant.stock <= 0, variant.color or '', variant.size or '', variant.id),
    )
    review_stats = db.session.query(Review.rating, func.count(Review.id)).filter_by(product_id=product_id).group_by(Review.rating).all()
    review_counts = dict(review_stats)
    review_query=Review.query.filter_by(product_id=product_id)
    selected_star=request.args.get('stars',type=int)
    if selected_star in range(1,6): review_query=review_query.filter_by(rating=selected_star)
    # Keep submitted buyer feedback visible ahead of generated demo comments.
    review_pagination=review_query.order_by(Review.is_demo.asc(), Review.created_at.desc(), Review.id.desc()).paginate(page=max(1,request.args.get('review_page',1,type=int)),per_page=10,error_out=False)
    display_review_count = sum(review_counts.values())
    if display_review_count:
        display_rating = sum(star * total for star, total in review_stats) / display_review_count
    else:
        display_rating = float(product.rating or 0)
        display_review_count = int(product.rating_count or 0)
    is_in_wishlist = False
    can_review = False
    if current_user.is_authenticated:
        is_in_wishlist = WishlistItem.query.filter_by(user_id=current_user.id, product_id=product_id).first() is not None
        if current_user.role != 'admin':
            can_review = OrderItem.query.join(Order).filter(
                Order.user_id == current_user.id,
                Order.status == 'delivered',
                OrderItem.product_id == product_id
            ).first() is not None

    extra_images_list = json.loads(product.extra_images) if product.extra_images else []
    return render_template(
        'product-detail.html',
        product=product,
        variants=variants,
        reviews=review_pagination.items,
        review_pagination=review_pagination,
        review_counts={star:review_counts.get(star, 0) for star in range(1,6)},
        selected_star=selected_star if selected_star in range(1,6) else None,
        display_rating=display_rating,
        display_review_count=display_review_count,
        is_in_wishlist=is_in_wishlist,
        can_review=can_review,
        extra_images_list=extra_images_list,
    )


@app.route('/wishlist')
@login_required
def wishlist():
    items = WishlistItem.query.filter_by(user_id=current_user.id).order_by(WishlistItem.created_at.desc()).all()
    return render_template('wishlist.html', items=items)


@app.route('/wishlist/toggle/<int:product_id>', methods=['POST'])
@login_required
def wishlist_toggle(product_id):
    if current_user.role == 'admin':
        flash('Tài khoản quản trị không thể dùng danh sách yêu thích.', 'error')
        return redirect(url_for('product_detail', product_id=product_id))
    product = Product.query.get_or_404(product_id)
    item = WishlistItem.query.filter_by(user_id=current_user.id, product_id=product_id).first()
    if item:
        db.session.delete(item)
        db.session.commit()
        flash('Đã bỏ sản phẩm khỏi danh sách yêu thích.', 'info')
    else:
        db.session.add(WishlistItem(user_id=current_user.id, product_id=product_id))
        db.session.commit()
        flash('Đã thêm sản phẩm vào danh sách yêu thích.', 'success')
    return redirect(request.referrer or url_for('product_detail', product_id=product.id))

@app.route('/product/<int:product_id>/review', methods=['POST'])
@login_required
def add_review(product_id):
    # Admin không được phép viết đánh giá sản phẩm
    if current_user.role == 'admin':
        flash('Tài khoản quản trị không thể viết đánh giá sản phẩm.', 'error')
        return redirect(url_for('product_detail', product_id=product_id))

    has_bought = OrderItem.query.join(Order).filter(
        Order.user_id == current_user.id,
        Order.status == 'delivered',
        OrderItem.product_id == product_id
    ).first()

    if not has_bought:
        flash('Bạn cần mua và nhận hàng thành công mới được phép đánh giá.', 'error')
        return redirect(url_for('product_detail', product_id=product_id))

    product = Product.query.get_or_404(product_id)
    rating = request.form.get('rating', 5, type=int) or 5
    rating = max(1, min(5, rating))
    comment = (request.form.get('comment') or '').strip()
    if not comment:
        flash('Vui lòng nhập nội dung đánh giá.', 'error')
        return redirect(url_for('product_detail', product_id=product_id))
    if len(comment)>2000:
        flash('Đánh giá tối đa 2.000 ký tự.','error')
        return redirect(url_for('product_detail',product_id=product_id))
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert
    statement=sqlite_insert(Review).values(product_id=product_id,user_id=current_user.id,rating=rating,comment=comment,created_at=datetime.utcnow())
    db.session.execute(statement.on_conflict_do_update(index_elements=['product_id','user_id'],set_={'rating':rating,'comment':comment}))
    db.session.flush()
    from commerce import refresh_product,refresh_shop
    refresh_product(product);refresh_shop(product.shop_id)
    db.session.commit()
    flash('Cảm ơn bạn! Đánh giá của bạn đã được lưu.','success')
    return redirect(url_for('product_detail',product_id=product_id)+'#reviews')

@app.route('/review/<int:review_id>/delete', methods=['POST'])
@login_required
def delete_review(review_id):
    review = Review.query.get_or_404(review_id)
    product_id = review.product_id
    # Admin được xóa bất kỳ đánh giá nào; user chỉ xóa được đánh giá của mình
    if current_user.role != 'admin' and review.user_id != current_user.id:
        flash('Bạn không có quyền xóa đánh giá này.', 'error')
        return redirect(url_for('product_detail', product_id=product_id))
    review_product=review.product
    db.session.delete(review)
    db.session.flush()
    from commerce import refresh_product, refresh_shop
    refresh_product(review_product); refresh_shop(review_product.shop_id)
    db.session.commit()
    flash('Đã xóa đánh giá thành công.', 'success')
    # Nếu admin đang ở trang admin thì quay lại referrer
    referrer = request.referrer
    if referrer:
        return redirect(referrer)
    return redirect(url_for('product_detail', product_id=product_id))

@app.route('/cart')
def cart():
    if current_user.is_authenticated and current_user.role == 'admin':
        flash('Tài khoản quản trị không thể mua sắm. Vui lòng dùng tài khoản thường.', 'error')
        return redirect(url_for('admin_dashboard'))
    if current_user.is_authenticated:
        active_cart = _get_or_create_user_cart(current_user.id)
        active_coupon_code = session.get('coupon_code')
        totals = _compute_totals_from_items(active_cart.items, active_coupon_code)
        _, _, db_coupon = _resolve_coupon_by_code(active_coupon_code)
        return render_template('cart.html', cart=active_cart, is_guest=False, totals=totals)
    guest_cart = _build_guest_cart_view(_session_cart_get())
    totals = _compute_totals_from_items(guest_cart.items, session.get('coupon_code'))
    return render_template('cart.html', cart=guest_cart, is_guest=True, totals=totals)


@app.route('/cart/coupon', methods=['POST'])
def apply_coupon():
    code = (request.form.get('coupon_code') or '').strip().upper()
    if not code:
        session.pop('coupon_code', None)
        flash('Đã bỏ mã giảm giá.', 'info')
        return redirect(url_for('cart'))

    cart_obj = _get_or_create_user_cart(current_user.id) if current_user.is_authenticated else _build_guest_cart_view(_session_cart_get())
    totals = _compute_totals_from_items(cart_obj.items, code)
    if not totals.get("applied_coupon"):
        flash('Mã giảm giá không hợp lệ hoặc chưa đạt giá trị tối thiểu.', 'error')
        return redirect(url_for('cart'))

    session['coupon_code'] = totals["applied_coupon"]
    session.modified = True
    flash(f'Áp dụng mã {totals["applied_coupon"]} thành công.', 'success')
    return redirect(url_for('cart'))

@app.route('/cart/add/<int:product_id>', methods=['POST'])
def add_to_cart(product_id):
    if current_user.is_authenticated and current_user.role == 'admin':
        flash('Tài khoản quản trị không thể mua sắm.', 'error')
        return redirect(url_for('product_detail', product_id=product_id))
    quantity = request.form.get('quantity', 1, type=int)
    if quantity is None:
        flash('Số lượng không hợp lệ.', 'error')
        return redirect(url_for('cart'))
    if quantity < 1:
        quantity = 1
    product = Product.query.get_or_404(product_id)
    if product.status != 'active' or (product.seller_shop and product.seller_shop.vacation_mode):
        flash('Sản phẩm đang ngừng bán hoặc Shop đang tạm nghỉ.', 'info')
        return redirect(url_for('cart'))
    variant_id = request.form.get('variant_id', type=int)
    variant = ProductVariant.query.filter_by(id=variant_id, product_id=product.id, is_active=True).first() if variant_id else None
    if variant_id and variant is None:
        flash('Phân loại sản phẩm không còn hoạt động. Vui lòng chọn lại.', 'error')
        return redirect(url_for('product_detail', product_id=product_id))
    active_variants = [item for item in product.variants if item.is_active]
    if active_variants and variant is None:
        variant = next((item for item in active_variants if item.stock > 0), active_variants[0])
    stock = _available_stock(product, variant)
    if quantity > stock:
        flash(f'Sản phẩm "{product.name}" không đủ tồn kho (còn {stock}).', 'error')
        return redirect(url_for('product_detail', product_id=product_id))
    if stock < 1:
        flash(f'Sản phẩm "{product.name}" đang hết hàng.', 'error')
        return redirect(url_for('product_detail', product_id=product_id))

    if current_user.is_authenticated:
        active_cart = _get_or_create_user_cart(current_user.id)
        existing = CartItem.query.filter_by(
            cart_id=active_cart.id,
            product_id=product_id,
            variant_id=variant.id if variant else None,
        ).first()
        if existing:
            new_qty = int(existing.quantity) + quantity
            if new_qty > stock:
                new_qty = stock
                flash(f'Giỏ hàng đã được cập nhật tới tối đa tồn kho ({stock}).', 'info')
            existing.quantity = new_qty
        else:
            db.session.add(CartItem(
                cart_id=active_cart.id,
                product_id=product_id,
                variant_id=variant.id if variant else None,
                quantity=quantity,
            ))
        db.session.commit()
    else:
        cart_dict = _session_cart_get()
        line_key = _cart_key(product_id, variant.id if variant else None)
        current_qty = int(cart_dict.get(line_key, 0) or 0)
        new_qty = current_qty + quantity
        if new_qty > stock:
            new_qty = stock
            flash(f'Giỏ hàng đã được cập nhật tới tối đa tồn kho ({stock}).', 'info')
        cart_dict[line_key] = int(new_qty)
        _session_cart_set(cart_dict)

    flash('Đã thêm sản phẩm vào giỏ hàng!', 'success')
    next_url = request.form.get('next', '').strip()
    if next_url and _is_safe_redirect_url(next_url):
        return redirect(next_url)
    return redirect(url_for('cart'))


@app.route('/cart/item/<item_id>/quantity', methods=['POST'])
def update_cart_item_quantity(item_id):
    qty = None
    if request.is_json:
        qty = request.json.get('quantity')
    else:
        qty = request.form.get('quantity')
    try:
        qty = int(qty)
    except Exception:
        return jsonify({'ok': False, 'error': 'invalid_quantity'}), 400

    if qty < 1:
        qty = 1
    if current_user.is_authenticated:
        try:
            numeric_item_id = int(item_id)
        except (TypeError, ValueError):
            return jsonify({'ok': False, 'error': 'invalid_item'}), 400
        item = CartItem.query.get_or_404(numeric_item_id)
        if item.cart.user_id != current_user.id:
            return jsonify({'ok': False, 'error': 'forbidden'}), 403
        stock = _available_stock(item.product, item.variant)
        if qty > stock:
            qty = stock
        item.quantity = qty
        db.session.commit()
        return jsonify({'ok': True, 'quantity': item.quantity})
    # Guest mode: item_id is the session line key: product_id:variant_id.
    try:
        product_id, variant_id = _parse_cart_key(item_id)
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'error': 'invalid_item'}), 400
    product = Product.query.get_or_404(product_id)
    variant = ProductVariant.query.filter_by(id=variant_id, product_id=product.id).first() if variant_id else None
    stock = _available_stock(product, variant)
    if qty > stock:
        qty = stock
    cart_dict = _session_cart_get()
    cart_dict[str(item_id)] = int(qty)
    _session_cart_set(cart_dict)
    return jsonify({'ok': True, 'quantity': int(qty)})

@app.route('/cart/remove/<item_id>', methods=['POST'])
def remove_from_cart(item_id):
    if current_user.is_authenticated:
        try:
            numeric_item_id = int(item_id)
        except (TypeError, ValueError):
            flash('Sản phẩm trong giỏ hàng không hợp lệ.', 'error')
            return redirect(url_for('cart'))
        item = CartItem.query.get_or_404(numeric_item_id)
        if item.cart.user_id == current_user.id:
            db.session.delete(item)
            db.session.commit()
            flash('Đã xóa sản phẩm khỏi giỏ hàng.', 'info')
        return redirect(url_for('cart'))
    # Guest mode: item_id is the session line key.
    cart_dict = _session_cart_get()
    cart_dict.pop(str(item_id), None)
    _session_cart_set(cart_dict)
    flash('Đã xóa sản phẩm khỏi giỏ hàng.', 'info')
    return redirect(url_for('cart'))

@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    if current_user.is_authenticated and current_user.role == 'admin':
        flash('Tài khoản quản trị không thể mua sắm. Vui lòng dùng tài khoản thường.', 'error')
        return redirect(url_for('admin_dashboard'))
    if current_user.is_authenticated:
        active_cart = _get_or_create_user_cart(current_user.id)
        is_guest = False
    else:
        active_cart = _build_guest_cart_view(_session_cart_get())
        is_guest = True
    if not active_cart or len(list(active_cart.items)) == 0:
        flash('Giỏ hàng của bạn đang trống.', 'error')
        return redirect(url_for('cart'))
    coupon_code = session.get('coupon_code')
    totals_preview = _compute_totals_from_items(active_cart.items, coupon_code)
    if request.method == 'POST':
        shipping_name = request.form.get('shipping_name', '').strip()
        shipping_phone = request.form.get('shipping_phone', '').strip()
        shipping_address = request.form.get('shipping_address', '').strip()
        guest_email = request.form.get('guest_email', '').strip().lower()
        note = request.form.get('note', '').strip()
        payment_method = (request.form.get('payment_method') or 'COD').strip().upper()
        if payment_method != 'COD' and not app.config.get('ENABLE_EXTERNAL_PAYMENTS'):
            flash('Phương thức thanh toán này chưa được kích hoạt. Vui lòng chọn COD.', 'error')
            return redirect(url_for('checkout'))
        if payment_method not in ['COD', 'BANK_TRANSFER', 'MOMO', 'VNPAY']: payment_method='COD'

        # Basic validation
        if not shipping_name or not shipping_phone or not shipping_address:
            flash('Vui lòng nhập đầy đủ Họ tên, SĐT và Địa chỉ nhận hàng.', 'error')
            return redirect(url_for('checkout'))
        if not re.fullmatch(r'(0|\+84)\d{9,10}', shipping_phone):
            flash('Số điện thoại không hợp lệ.', 'error')
            return redirect(url_for('checkout'))
        if is_guest and not guest_email:
            flash('Vui lòng nhập Email để nhận thông tin đơn hàng.', 'error')
            return redirect(url_for('checkout'))
        if is_guest and not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', guest_email):
            flash('Email không hợp lệ.', 'error')
            return redirect(url_for('checkout'))

        # Stock check
        for item in active_cart.items:
            qty_item = int(item.quantity) if hasattr(item, 'quantity') else int(item.get('quantity', 0))
            product = item.product if hasattr(item, 'product') else item.get('product')
            variant = getattr(item, 'variant', None) if hasattr(item, 'product') else item.get('variant')
            if qty_item < 1:
                flash('Số lượng sản phẩm không hợp lệ.', 'error')
                return redirect(url_for('cart'))
            if product.status!='active' or (variant and not variant.is_active) or (product.seller_shop and product.seller_shop.vacation_mode):
                flash('Một sản phẩm đã ngừng bán hoặc shop đang tạm nghỉ. Vui lòng cập nhật giỏ hàng.','error')
                return redirect(url_for('cart'))
            stock = _available_stock(product, variant)
            if qty_item > stock:
                flash(f'Sản phẩm "{product.name}" không đủ tồn kho (còn {stock}).', 'error')
                return redirect(url_for('cart'))
        totals = _compute_totals_from_items(active_cart.items, session.get('coupon_code'))
        _, _, db_coupon = _resolve_coupon_by_code(session.get('coupon_code'))


        if is_guest:
            # Handle guest checkout securely
            user = User.query.filter_by(email=guest_email).first()
            if user:
                flash('Email này đã có tài khoản. Vui lòng đăng nhập — giỏ hàng của bạn sẽ được giữ nguyên!', 'error')
                return redirect(url_for('login', next=url_for('checkout')))

            uname = f"guest_{uuid.uuid4().hex[:8]}"
            # Create a random password hash (user can later add real password if you implement it)
            rand_pw = uuid.uuid4().hex + uuid.uuid4().hex
            user = User(
                username=uname,
                email=guest_email,
                password_hash=generate_password_hash(rand_pw, method='pbkdf2:sha256'),
            )
            db.session.add(user)
            db.session.commit()

            login_user(user)
            _merge_session_cart_into_user_cart(user)
            active_cart = _get_or_create_user_cart(user.id)
            is_guest = False

        cart_lines=list(active_cart.items)
        grouped={}
        for item in cart_lines: grouped.setdefault(item.product.shop_id,[]).append(item)
        checkout_reference=uuid.uuid4().hex[:16]
        created_orders=[]
        try:
            # Conditional writes protect the last unit from simultaneous checkouts.
            for item in cart_lines:
                updated=db.session.execute(text("UPDATE product SET stock=stock-:qty WHERE id=:pid AND stock>=:qty AND status='active'"),{'qty':item.quantity,'pid':item.product_id})
                if updated.rowcount!=1: raise ValueError('Tồn kho vừa thay đổi. Vui lòng kiểm tra lại giỏ hàng.')
                if item.variant_id:
                    updated=db.session.execute(text('UPDATE product_variant SET stock=stock-:qty WHERE id=:vid AND stock>=:qty AND is_active=1'),{'qty':item.quantity,'vid':item.variant_id})
                    if updated.rowcount!=1: raise ValueError('SKU vừa hết hàng. Vui lòng kiểm tra lại giỏ hàng.')
            remaining_discount=int(totals['discount'])
            eligible_shops=[shop_id for shop_id in grouped if not db_coupon or not db_coupon.shop_id or shop_id==db_coupon.shop_id]
            shipping_coupon=db_coupon and db_coupon.coupon_type=='shipping' or totals.get('applied_coupon')=='FREESHIP'
            bases={shop_id:(totals['shipping_by_shop'].get(shop_id,0) if shipping_coupon else sum(int(_unit_price(i.product,i.variant)*i.quantity) for i in grouped[shop_id])) for shop_id in eligible_shops}
            eligible_shops=[shop_id for shop_id in eligible_shops if bases[shop_id]>0]
            eligible_total=sum(bases[shop_id] for shop_id in eligible_shops)
            for shop_id,items in grouped.items():
                subtotal=sum(int(_unit_price(i.product,i.variant)*i.quantity) for i in items)
                shipping=totals['shipping_by_shop'].get(shop_id,0)
                discount=0
                if shop_id in eligible_shops:
                    discount=remaining_discount if shop_id==eligible_shops[-1] else int(totals['discount']*bases[shop_id]/max(1,eligible_total))
                    remaining_discount-=discount
                order=Order(user_id=current_user.id,shop_id=shop_id,checkout_reference=checkout_reference,
                    total_amount=subtotal+shipping-discount,shipping_fee=shipping,discount_amount=discount,
                    status='pending',shipping_name=shipping_name,shipping_phone=shipping_phone,
                    shipping_address=shipping_address,note=note,payment_method=payment_method,payment_status='unpaid')
                db.session.add(order);db.session.flush();created_orders.append(order)
                for item in items:
                    variant=item.variant
                    db.session.add(OrderItem(order_id=order.id,product_id=item.product_id,
                        variant_id=variant.id if variant else None,quantity=item.quantity,
                        price=_unit_price(item.product,variant),sku=variant.sku if variant else item.product.sku,
                        variant_title=variant.title if variant else None))
            if db_coupon and totals.get('applied_coupon'):
                update=db.session.execute(text('UPDATE coupon SET used_count=used_count+1 WHERE id=:cid AND is_active=1 AND (max_uses IS NULL OR used_count<max_uses)'),{'cid':db_coupon.id})
                if update.rowcount!=1: raise ValueError('Voucher vừa hết lượt dùng. Vui lòng chọn lại.')
        except ValueError as error:
            db.session.rollback();flash(str(error),'error');return redirect(url_for('cart'))
        # Clear cart
        for item in list(active_cart.items):
            db.session.delete(item)
        session.pop('coupon_code', None)
        db.session.commit()
        flash('Đã tạo '+str(len(created_orders))+' đơn hàng thành công. Đơn được tách theo từng shop.', 'success')
        return redirect(url_for('order_detail', order_id=created_orders[0].id))

    response = make_response(render_template('checkout.html', cart=active_cart, is_guest=is_guest, totals=totals_preview, coupon_code=coupon_code))
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '-1'
    return response


@app.route('/order/<int:order_id>')
@login_required
def order_detail(order_id):
    order = Order.query.get_or_404(order_id)
    if order.user_id != current_user.id and current_user.role != 'admin':
        flash('Bạn không có quyền xem đơn hàng này.', 'error')
        return redirect(url_for('index'))
    bank_info = app.config.get('BANK_TRANSFER_INFO', '')
    related_orders=Order.query.filter_by(checkout_reference=order.checkout_reference,user_id=current_user.id).all() if order.checkout_reference else []
    from commerce import order_tracking
    return render_template('order-detail.html', order=order, bank_info=bank_info, related_orders=related_orders, tracking=order_tracking(order))


@app.route('/order/lookup', methods=['GET', 'POST'])
def order_lookup():
    found_order = None
    status_steps = []
    if request.method == 'POST':
        email = (request.form.get('email') or '').strip().lower()
        phone = (request.form.get('phone') or '').strip()
        order_id = request.form.get('order_id', type=int)
        if not email or not phone or not order_id:
            flash('Vui lòng nhập email, số điện thoại và mã đơn.', 'error')
            return render_template('order-lookup.html', found_order=None)
        found_order = Order.query.join(User, Order.user_id == User.id).filter(
            Order.id == order_id,
            User.email == email,
            Order.shipping_phone == phone
        ).first()
        if not found_order:
            flash('Không tìm thấy đơn hàng phù hợp.', 'error')
        else:
            flash('Đã tìm thấy đơn hàng.', 'success')
            steps = ['pending', 'paid', 'shipped', 'delivered']
            reached = found_order.status
            if reached == 'cancelled':
                status_steps = [{'id': 'cancelled', 'label': 'Đã huỷ', 'done': True}]
            else:
                for step in steps:
                    status_steps.append({
                        'id': step,
                        'label': {
                            'pending': 'Chờ xử lý',
                            'paid': 'Đã xác nhận',
                            'shipped': 'Đang giao',
                            'delivered': 'Hoàn tất',
                        }[step],
                        'done': steps.index(step) <= steps.index(reached) if reached in steps else False
                    })
    return render_template('order-lookup.html', found_order=found_order, status_steps=status_steps)


def _mark_order_paid(order: Order, payment_ref: Optional[str] = None):
    # A late/replayed payment must never move a shipped/delivered order backwards.
    if order.status == 'pending':
        from commerce import change_order_status
        change_order_status(order, 'paid')
    order.payment_status = 'paid'
    if payment_ref:
        order.payment_ref = payment_ref
    db.session.commit()


@app.route('/payment/momo/create/<int:order_id>')
@login_required
@limiter.limit("30 per minute")
def momo_create(order_id):
    order = Order.query.get_or_404(order_id)
    if order.user_id != current_user.id and current_user.role != 'admin':
        flash('Bạn không có quyền thanh toán đơn hàng này.', 'error')
        return redirect(url_for('index'))
    if order.payment_status == 'paid':
        return redirect(url_for('order_detail', order_id=order.id))
    if order.payment_method != 'MOMO':
        flash('Đơn hàng này không chọn MoMo.', 'error')
        return redirect(url_for('order_detail', order_id=order.id))

    partner_code = app.config.get('MOMO_PARTNER_CODE', '')
    access_key = app.config.get('MOMO_ACCESS_KEY', '')
    secret_key = app.config.get('MOMO_SECRET_KEY', '')
    endpoint = app.config.get('MOMO_ENDPOINT')
    if not partner_code or not access_key or not secret_key:
        flash('Chưa cấu hình MoMo merchant (MOMO_PARTNER_CODE/MOMO_ACCESS_KEY/MOMO_SECRET_KEY).', 'error')
        return redirect(url_for('order_detail', order_id=order.id))

    request_id = f"{order.id}-{uuid.uuid4().hex}"
    momo_order_id = f"UTE{order.id}"
    amount = int(round(order.total_amount))
    order_info = f"Thanh toan don hang #{order.id}"
    redirect_url = _absolute_url('momo_return')
    ipn_url = _absolute_url('momo_ipn')
    request_type = "captureWallet"
    extra_data = ""

    # Ép kiểu amount thành string của số nguyên
    amount_str = str(int(amount))

    # Thứ tự phải chuẩn 100% như thế này
    raw_signature = (
        f"accessKey={access_key}"
        f"&amount={amount_str}"
        f"&extraData={extra_data}"
        f"&ipnUrl={ipn_url}"
        f"&orderId={momo_order_id}"
        f"&orderInfo={order_info}"
        f"&partnerCode={partner_code}"
        f"&redirectUrl={redirect_url}"
        f"&requestId={request_id}"
        f"&requestType={request_type}"
    )
    signature = _hmac_sha256(secret_key, raw_signature)

    payload = {
        "partnerCode": partner_code,
        "partnerName": "Test Store", # Thêm dòng này cho chắc
        "storeId": "MomoTestStore",  # Thêm dòng này cho chắc
        "requestId": request_id,
        "amount": amount_str,        # Dùng amount_str đã ép kiểu ở trên
        "orderId": momo_order_id,
        "orderInfo": order_info,
        "redirectUrl": redirect_url,
        "ipnUrl": ipn_url,
        "lang": "vi",
        "extraData": extra_data,
        "requestType": request_type,
        "signature": signature,
    }

    tx = PaymentTransaction(
        order_id=order.id,
        provider='MOMO',
        amount=float(amount),
        status='initiated',
        provider_ref=momo_order_id,
        raw_request=json.dumps(payload, ensure_ascii=False),
    )
    db.session.add(tx)
    db.session.commit()

    try:
        resp = requests.post(endpoint, json=payload, timeout=20)
        data = resp.json()
    except Exception:
        tx.status = 'failed'
        db.session.commit()
        flash('Không kết nối được MoMo. Vui lòng thử lại.', 'error')
        return redirect(url_for('order_detail', order_id=order.id))

    tx.raw_response = json.dumps(data, ensure_ascii=False)
    db.session.commit()

    pay_url = data.get('payUrl') or data.get('deeplink') or data.get('qrCodeUrl')
    if not pay_url or int(data.get('resultCode', -1)) != 0:
        tx.status = 'failed'
        db.session.commit()
        flash('Tạo thanh toán MoMo thất bại. Vui lòng thử lại.', 'error')
        return redirect(url_for('order_detail', order_id=order.id))

    order.payment_status = 'initiated'
    db.session.commit()
    return redirect(pay_url)


@app.route('/payment/momo/return')
@login_required
def momo_return():
    # This is browser return URL. Final confirmation should rely on IPN.
    order_id = request.args.get('orderId', '')
    # orderId is like UTH123; extract numeric part if possible
    num = ''.join([c for c in order_id if c.isdigit()])
    if num.isdigit():
        return redirect(url_for('order_detail', order_id=int(num)))
    flash('Không xác định được đơn hàng từ MoMo.', 'error')
    return redirect(url_for('index'))


@app.route('/payment/momo/ipn', methods=['POST'])
@csrf.exempt
@limiter.exempt
def momo_ipn():
    data = request.get_json(silent=True) or {}
    signature = data.get('signature', '')

    partner_code = app.config.get('MOMO_PARTNER_CODE', '')
    access_key = app.config.get('MOMO_ACCESS_KEY', '')
    secret_key = app.config.get('MOMO_SECRET_KEY', '')
    if not partner_code or not access_key or not secret_key:
        return jsonify({"message": "not_configured"}), 500

    # Build signature string according to MoMo IPN docs
    raw_signature = (
        f"accessKey={access_key}"
        f"&amount={data.get('amount','')}"
        f"&extraData={data.get('extraData','')}"
        f"&message={data.get('message','')}"
        f"&orderId={data.get('orderId','')}"
        f"&orderInfo={data.get('orderInfo','')}"
        f"&orderType={data.get('orderType','')}"
        f"&partnerCode={data.get('partnerCode','')}"
        f"&payType={data.get('payType','')}"
        f"&requestId={data.get('requestId','')}"
        f"&responseTime={data.get('responseTime','')}"
        f"&resultCode={data.get('resultCode','')}"
        f"&transId={data.get('transId','')}"
    )
    expected = _hmac_sha256(secret_key, raw_signature)
    if signature != expected:
        return jsonify({"message": "invalid_signature"}), 400

    order_id = data.get('orderId', '')
    num = ''.join([c for c in order_id if c.isdigit()])
    if not num.isdigit():
        return jsonify({"message": "invalid_order"}), 400
    order = Order.query.get(int(num))
    if not order:
        return jsonify({"message": "order_not_found"}), 404

    # Persist tx log
    tx = PaymentTransaction(
        order_id=order.id,
        provider='MOMO',
        amount=float(data.get('amount') or 0),
        status='paid' if int(data.get('resultCode', -1)) == 0 else 'failed',
        provider_ref=str(data.get('transId') or data.get('orderId') or ''),
        raw_response=json.dumps(data, ensure_ascii=False),
    )
    db.session.add(tx)

    if int(data.get('resultCode', -1)) == 0:
        # amount check
        try:
            paid_amount = int(data.get('amount', 0))
        except Exception:
            paid_amount = 0
        if int(round(order.total_amount)) == paid_amount:
            _mark_order_paid(order, payment_ref=str(data.get('transId') or ''))
            tx.status = 'paid'
        else:
            order.payment_status = 'failed'
            tx.status = 'failed'
            db.session.commit()
            return jsonify({"message": "amount_mismatch"}), 400

    db.session.commit()
    return jsonify({"message": "received"}), 200


@app.route('/payment/vnpay/create/<int:order_id>')
@login_required
@limiter.limit("30 per minute")
def vnpay_create(order_id):
    order = Order.query.get_or_404(order_id)
    if order.user_id != current_user.id and current_user.role != 'admin':
        flash('Bạn không có quyền thanh toán đơn hàng này.', 'error')
        return redirect(url_for('index'))
    if order.payment_status == 'paid':
        return redirect(url_for('order_detail', order_id=order.id))
    if order.payment_method != 'VNPAY':
        flash('Đơn hàng này không chọn VNPAY.', 'error')
        return redirect(url_for('order_detail', order_id=order.id))

    tmn_code = app.config.get('VNPAY_TMN_CODE', '')
    hash_secret = app.config.get('VNPAY_HASH_SECRET', '')
    vnp_url = app.config.get('VNPAY_URL', '')
    if not tmn_code or not hash_secret:
        flash('Chưa cấu hình VNPAY merchant (VNPAY_TMN_CODE/VNPAY_HASH_SECRET).', 'error')
        return redirect(url_for('order_detail', order_id=order.id))

    amount = int(round(order.total_amount)) * 100  # VNPAY uses smallest unit
    create_date = (datetime.utcnow() + timedelta(hours=7)).strftime("%Y%m%d%H%M%S")
    expire_date = (datetime.utcnow() + timedelta(hours=7, minutes=15)).strftime("%Y%m%d%H%M%S")
    vnp_params = {
        "vnp_Version": "2.1.0",
        "vnp_Command": "pay",
        "vnp_TmnCode": tmn_code,
        "vnp_Amount": str(amount),
        "vnp_CurrCode": "VND",
        "vnp_TxnRef": f"{order.id}",
        "vnp_OrderInfo": f"Thanh toan don hang #{order.id}",
        "vnp_OrderType": "other",
        "vnp_Locale": "vn",
        "vnp_ReturnUrl": _absolute_url('vnpay_return'),
        "vnp_IpAddr": request.headers.get('X-Forwarded-For', request.remote_addr) or "127.0.0.1",
        "vnp_CreateDate": create_date,
        "vnp_ExpireDate": expire_date,
    }
    # Build signed query
    sorted_items = sorted(vnp_params.items())
    hashdata = "&".join([f"{k}={urllib.parse.quote_plus(str(v))}" for k, v in sorted_items])
    secure_hash = _vnpay_hmac_sha512(hash_secret, hashdata)
    query = urllib.parse.urlencode(sorted_items, quote_via=urllib.parse.quote_plus)
    pay_url = f"{vnp_url}?{query}&vnp_SecureHash={secure_hash}"

    tx = PaymentTransaction(
        order_id=order.id,
        provider='VNPAY',
        amount=float(int(round(order.total_amount))),
        status='initiated',
        provider_ref=str(order.id),
        raw_request=json.dumps(vnp_params, ensure_ascii=False),
    )
    db.session.add(tx)
    order.payment_status = 'initiated'
    db.session.commit()
    return redirect(pay_url)


@app.route('/payment/vnpay/return')
@login_required
def vnpay_return():
    args = dict(request.args)
    secure_hash = args.pop('vnp_SecureHash', '')
    args.pop('vnp_SecureHashType', None)

    hash_secret = app.config.get('VNPAY_HASH_SECRET', '')
    if not hash_secret:
        flash('Chưa cấu hình VNPAY.', 'error')
        return redirect(url_for('index'))

    sorted_items = sorted(args.items())
    hashdata = "&".join([f"{k}={urllib.parse.quote_plus(str(v))}" for k, v in sorted_items])
    expected = _vnpay_hmac_sha512(hash_secret, hashdata)
    if secure_hash != expected:
        flash('Chữ ký VNPAY không hợp lệ.', 'error')
        return redirect(url_for('index'))

    txn_ref = args.get('vnp_TxnRef')
    if txn_ref and str(txn_ref).isdigit():
        return redirect(url_for('order_detail', order_id=int(txn_ref)))
    flash('Không xác định được đơn hàng từ VNPAY.', 'error')
    return redirect(url_for('index'))


@app.route('/payment/vnpay/ipn', methods=['GET'])
@csrf.exempt
@limiter.exempt
def vnpay_ipn():
    # VNPAY calls IPN via GET
    args = dict(request.args)
    secure_hash = args.pop('vnp_SecureHash', '')
    args.pop('vnp_SecureHashType', None)

    hash_secret = app.config.get('VNPAY_HASH_SECRET', '')
    if not hash_secret:
        return "not_configured", 500

    sorted_items = sorted(args.items())
    hashdata = "&".join([f"{k}={urllib.parse.quote_plus(str(v))}" for k, v in sorted_items])
    expected = _vnpay_hmac_sha512(hash_secret, hashdata)
    if secure_hash != expected:
        return "invalid_signature", 400

    txn_ref = args.get('vnp_TxnRef')
    resp_code = args.get('vnp_ResponseCode')
    amount = args.get('vnp_Amount')
    trans_no = args.get('vnp_TransactionNo')
    if not txn_ref or not str(txn_ref).isdigit():
        return "invalid_order", 400
    order = Order.query.get(int(txn_ref))
    if not order:
        return "order_not_found", 404

    tx = PaymentTransaction(
        order_id=order.id,
        provider='VNPAY',
        amount=float(int(amount or 0) / 100),
        status='paid' if resp_code == '00' else 'failed',
        provider_ref=str(trans_no or txn_ref),
        raw_response=json.dumps(args, ensure_ascii=False),
    )
    db.session.add(tx)

    if resp_code == '00':
        try:
            paid = int(amount or 0) // 100
        except Exception:
            paid = 0
        if int(round(order.total_amount)) == int(paid):
            _mark_order_paid(order, payment_ref=str(trans_no or ''))
            tx.status = 'paid'
        else:
            order.payment_status = 'failed'
            db.session.commit()
            return "amount_mismatch", 400
    else:
        order.payment_status = 'failed'

    db.session.commit()
    return "ok", 200

@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("20 per minute")
def login():
    if current_user.is_authenticated:
        next_page=request.args.get('next')
        if next_page and _is_safe_redirect_url(next_page): return redirect(next_page)
        from seller import member_shop
        return redirect(url_for('seller.dashboard') if member_shop() else url_for('shop_page',slug='utech-official'))
    if request.method == 'POST':
        login_id = (request.form.get('login_id') or '').strip()
        password = request.form.get('password') or ''

        # Tìm user theo email hoặc username không phân biệt chữ hoa, chữ thường
        # Đảm bảo người dùng gõ sai hoa/thường vẫn tìm ra tài khoản (chuẩn UX/Security chống trùng lặp)
        user = User.query.filter(
            (func.lower(User.username) == login_id.lower()) |
            (func.lower(User.email) == login_id.lower())
        ).first()

        if user and user.role != 'demo_reviewer' and check_password_hash(user.password_hash, password):
            remember_me = bool(request.form.get('remember'))
            login_user(user, remember=remember_me)
            _merge_session_cart_into_user_cart(user)
            next_page = request.args.get('next')
            if next_page and _is_safe_redirect_url(next_page):
                return redirect(next_page)
            from seller import member_shop
            return redirect(url_for('seller.dashboard') if member_shop() else url_for('shop_page',slug='utech-official'))
        else:
            flash('Email/Tên đăng nhập hoặc mật khẩu không đúng.', 'error')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
@limiter.limit("20 per minute")
def register():
    if current_user.is_authenticated:
        return redirect(url_for('shop_page',slug='utech-official'))
    if request.method=='POST':
        name=(request.form.get('name') or '').strip()
        email=(request.form.get('email') or '').strip().lower()
        password=request.form.get('password') or ''
        confirm=request.form.get('confirm_password') or ''
        error=None
        if not 3<=len(name)<=100: error='Tên đăng nhập cần từ 3 đến 100 ký tự.'
        elif not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+',email): error='Email không hợp lệ.'
        elif len(password)<8 or len(password)>128: error='Mật khẩu cần từ 8 đến 128 ký tự.'
        elif password!=confirm: error='Xác nhận mật khẩu không khớp.'
        elif User.query.filter(or_(func.lower(User.email)==email,func.lower(User.username)==name.lower())).first(): error='Email hoặc tên đăng nhập đã được sử dụng.'
        if error: flash(error,'error'); return render_template('login.html',register_mode=True)
        user=User(username=name,email=email,password_hash=generate_password_hash(password,method='pbkdf2:sha256'),role='user')
        db.session.add(user); db.session.commit(); login_user(user)
        _merge_session_cart_into_user_cart(user)
        flash('Chào mừng bạn đến với Shopee!','success')
        return redirect(url_for('shop_page',slug='utech-official'))
    return render_template('login.html',register_mode=True)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Đã đăng xuất thành công.', 'info')
    return redirect(url_for('index'))


@app.route('/forgot-password', methods=['GET', 'POST'])
@limiter.limit("10 per hour")
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for('profile'))
    if request.method=='POST':
        email=(request.form.get('email') or '').strip().lower()
        if not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+',email):
            flash('Vui lòng nhập địa chỉ email hợp lệ.','error')
        else:
            user=User.query.filter(func.lower(User.email)==email).first()
            if user:
                token=user.generate_reset_token(expires_minutes=30)
                db.session.commit()
                # Local delivery adapter: never expose a reset token to the requester.
                outbox=app.config.get('MAIL_OUTBOX_DIR') or os.path.join(app.instance_path,'mailbox')
                os.makedirs(outbox,exist_ok=True)
                message={'to':user.email,'subject':'Đặt lại mật khẩu Shopee','reset_url':url_for('reset_password',token=token,_external=True),'expires_in_minutes':30}
                with open(os.path.join(outbox,uuid.uuid4().hex+'.json'),'w',encoding='utf-8') as file:
                    json.dump(message,file,ensure_ascii=False,indent=2)
            flash('Đã tiếp nhận yêu cầu. Bản demo lưu thư khôi phục vào hộp thư thử nghiệm cục bộ.','success')
            return redirect(url_for('login'))
    return render_template('forgot-password.html')


@app.route('/reset-password/<token>', methods=['GET', 'POST'])
@limiter.limit("20 per hour")
def reset_password(token):
    """Xác thực token và cho phép đặt lại mật khẩu."""
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    user = User.query.filter_by(reset_token=token).first()

    if not user or not user.is_reset_token_valid():
        flash('Liên kết đặt lại mật khẩu không hợp lệ hoặc đã hết hạn. Vui lòng thử lại.', 'error')
        return redirect(url_for('forgot_password'))

    if request.method == 'POST':
        new_pw = request.form.get('password', '')
        confirm_pw = request.form.get('confirm_password', '')

        if not 8 <= len(new_pw) <= 128:
            flash('Mật khẩu phải có ít nhất 8 ký tự.', 'error')
            return render_template('reset-password.html', token=token)

        pw_pattern = re.compile(r'^(?=.*\d)(?=.*[a-z])(?=.*[A-Z]).{8,}$')
        if not pw_pattern.match(new_pw):
            flash('Mật khẩu cần có ít nhất 1 chữ HOA, 1 chữ thường và 1 chữ số.', 'error')
            return render_template('reset-password.html', token=token)

        if new_pw != confirm_pw:
            flash('Xác nhận mật khẩu không khớp.', 'error')
            return render_template('reset-password.html', token=token)

        user.password_hash = generate_password_hash(new_pw, method='pbkdf2:sha256')
        user.clear_reset_token()
        db.session.commit()
        flash('Đặt lại mật khẩu thành công! Vui lòng đăng nhập.', 'success')
        return redirect(url_for('login'))

    return render_template('reset-password.html', token=token)


@app.route('/contact', methods=['GET', 'POST'])
@limiter.limit("30 per hour")
def contact():
    if request.method == 'POST':
        name = (request.form.get('name') or '').strip()[:150]
        email = (request.form.get('email') or '').strip()[:150]
        subject = (request.form.get('subject') or '').strip()[:200]
        message = (request.form.get('message') or '').strip()[:4000]
        if not name or not message or not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+',email):
            flash('Vui lòng nhập họ tên, email hợp lệ và nội dung hỗ trợ.', 'error')
            return redirect(url_for('contact'))
        contact_entry = Contact(name=name, email=email, subject=subject, message=message)
        db.session.add(contact_entry)
        db.session.commit()
        flash('Cảm ơn bạn! Chúng tôi sẽ phản hồi sớm nhất.', 'success')
        return redirect(url_for('contact'))
    return render_template('contact.html')

@app.route('/policy')
def policy():
    return render_template('policy.html')

# --- ADMIN ROUTES ---

def get_analytics_data():
    """Tổng hợp dữ liệu analytics cho admin dashboard"""
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Orders stats
    orders_count = Order.query.count()
    orders_today = Order.query.filter(Order.created_at >= today_start).count()
    orders_month = Order.query.filter(Order.created_at >= month_start).count()

    # Revenue
    total_revenue_row = db.session.query(func.sum(Order.total_amount)).filter(Order.status != 'cancelled').scalar()
    total_revenue = total_revenue_row or 0

    revenue_month_row = db.session.query(func.sum(Order.total_amount)).filter(
        Order.status != 'cancelled',
        Order.created_at >= month_start
    ).scalar()
    revenue_month = revenue_month_row or 0

    revenue_today_row = db.session.query(func.sum(Order.total_amount)).filter(
        Order.status != 'cancelled',
        Order.created_at >= today_start
    ).scalar()
    revenue_today = revenue_today_row or 0

    # Doanh thu 7 ngày gần nhất
    revenue_7days = []
    labels_7days = []
    for i in range(6, -1, -1):
        day = now - timedelta(days=i)
        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        rev = db.session.query(func.sum(Order.total_amount)).filter(
            Order.status != 'cancelled',
            Order.created_at >= day_start,
            Order.created_at < day_end
        ).scalar() or 0
        revenue_7days.append(float(rev))
        labels_7days.append(day.strftime('%d/%m'))

    # Đơn hàng 30 ngày
    orders_30days = []
    labels_30days = []
    for i in range(29, -1, -1):
        day = now - timedelta(days=i)
        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        cnt = Order.query.filter(
            Order.created_at >= day_start,
            Order.created_at < day_end
        ).count()
        orders_30days.append(cnt)
        labels_30days.append(day.strftime('%d/%m'))

    # Top sản phẩm bán chạy
    top_products_raw = db.session.query(
        Product.name,
        func.sum(OrderItem.quantity).label('total_sold'),
        func.sum(OrderItem.quantity * OrderItem.price).label('revenue')
    ).join(OrderItem, Product.id == OrderItem.product_id)\
     .join(Order, Order.id == OrderItem.order_id)\
     .filter(Order.status != 'cancelled')\
     .group_by(Product.id)\
     .order_by(func.sum(OrderItem.quantity).desc())\
     .limit(5).all()

    top_products = [{'name': r[0], 'sold': int(r[1] or 0), 'revenue': float(r[2] or 0)} for r in top_products_raw]

    # Phân bổ doanh thu theo danh mục
    category_revenue_raw = db.session.query(
        Category.name,
        func.sum(OrderItem.quantity * OrderItem.price).label('revenue')
    ).join(Product, Category.id == Product.category_id)\
     .join(OrderItem, Product.id == OrderItem.product_id)\
     .join(Order, Order.id == OrderItem.order_id)\
     .filter(Order.status != 'cancelled')\
     .group_by(Category.id)\
     .order_by(func.sum(OrderItem.quantity * OrderItem.price).desc())\
     .all()
    category_labels = [r[0] for r in category_revenue_raw]
    category_data = [float(r[1] or 0) for r in category_revenue_raw]

    # Đơn hàng gần đây
    recent_orders = Order.query.order_by(Order.created_at.desc()).limit(10).all()

    # Order status breakdown
    status_counts = {
        'pending': Order.query.filter_by(status='pending').count(),
        'paid': Order.query.filter_by(status='paid').count(),
        'shipped': Order.query.filter_by(status='shipped').count(),
        'delivered': Order.query.filter_by(status='delivered').count(),
        'cancelled': Order.query.filter_by(status='cancelled').count(),
    }

    return {
        'orders_count': orders_count,
        'orders_today': orders_today,
        'orders_month': orders_month,
        'total_revenue': total_revenue,
        'revenue_month': revenue_month,
        'revenue_today': revenue_today,
        'revenue_7days': revenue_7days,
        'labels_7days': labels_7days,
        'orders_30days': orders_30days,
        'labels_30days': labels_30days,
        'top_products': top_products,
        'category_labels': category_labels,
        'category_data': category_data,
        'recent_orders': recent_orders,
        'status_counts': status_counts,
    }


@app.route('/admin')
@login_required
def admin_dashboard():
    if current_user.role != 'admin':
        flash('Bạn không có quyền truy cập trang này.', 'error')
        return redirect(url_for('index'))
    products_count = Product.query.count()
    users_count = User.query.count()
    all_products = Product.query.order_by(Product.id.desc()).all()
    contacts = Contact.query.order_by(Contact.created_at.desc()).all()
    categories = Category.query.all()
    coupons = Coupon.query.order_by(Coupon.created_at.desc()).all()
    payment_transactions = PaymentTransaction.query.order_by(PaymentTransaction.created_at.desc()).limit(30).all()
    analytics = get_analytics_data()

    return render_template('admin.html',
                           products_count=products_count,
                           users_count=users_count,
                           products=all_products,
                           contacts=contacts,
                           categories=categories,
                           coupons=coupons,
                           payment_transactions=payment_transactions,
                           now=datetime.now(),
                           analytics=analytics)


@app.route('/admin/product/add', methods=['POST'])
@login_required
def admin_add_product():
    if current_user.role != 'admin':
        return redirect(url_for('index'))

    name = (request.form.get('name') or '').strip()
    sku = (request.form.get('sku') or '').strip().upper() or f"UTE-{uuid.uuid4().hex[:8].upper()}"
    if Product.query.filter(func.lower(Product.sku) == sku.lower()).first():
        flash(f'SKU {sku} đã tồn tại.', 'error')
        return redirect(url_for('admin_dashboard') + '?tab=products')
    price = float(request.form.get('price', 0))
    old_price_str = request.form.get('old_price', '')
    old_price = float(old_price_str) if old_price_str else None
    description = request.form.get('description', '')

    category_action = request.form.get('category_action', '1|')
    cat_parts = category_action.split('|')
    category_id = int(cat_parts[0])
    subcategory = cat_parts[1] if len(cat_parts) > 1 and cat_parts[1] else None

    is_new = bool(request.form.get('is_new'))
    is_on_sale = bool(request.form.get('is_on_sale'))
    stock = int(request.form.get('stock', 100))

    # Xử lý sizes tùy chỉnh
    sizes_raw = request.form.get('sizes_input', '').strip()
    sizes_list = []
    if sizes_raw:
        sizes_list = [s.strip() for s in sizes_raw.replace('\n', ',').split(',') if s.strip()]
    sizes_json = json.dumps(sizes_list, ensure_ascii=False) if sizes_list else None

    # Xử lý upload ảnh (tối đa 5 ảnh)
    image_url = request.form.get('image_url', '')
    files = request.files.getlist('image_files')
    extra_urls = []

    # Process multiple image files
    for file in files:
        if file and file.filename and allowed_file(file.filename):
            ext = file.filename.rsplit('.', 1)[1].lower()
            filename = f"{uuid.uuid4().hex}.{ext}"
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            url = url_for('static', filename=f'uploads/{filename}')
            if not image_url:
                image_url = url
            else:
                extra_urls.append(url)

    # Xử lý upload video
    video_url = request.form.get('video_url', '')
    video_file = request.files.get('video_file')
    if video_file and video_file.filename and allowed_file(video_file.filename):
        ext = video_file.filename.rsplit('.', 1)[1].lower()
        filename = f"vid_{uuid.uuid4().hex}.{ext}"
        video_file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        video_url = url_for('static', filename=f'uploads/{filename}')

    # Giới hạn mảng ảnh phụ (tối đa 8 ảnh phụ + 1 ảnh chính = 9)
    extra_urls = extra_urls[:8]
    extra_images_json = json.dumps(extra_urls) if extra_urls else None

    product = Product(
        sku=sku, name=name, price=price, old_price=old_price,
        image_url=image_url, extra_images=extra_images_json, video_url=video_url,
        description=description, sizes=sizes_json,
        category_id=category_id, subcategory=subcategory, is_new=is_new, is_on_sale=is_on_sale,
        stock=stock, source='manual', currency='VND', status='active'
    )
    db.session.add(product)
    db.session.flush()
    sellable_sizes = sizes_list or [None]
    remaining_stock = stock
    for index, size in enumerate(sellable_sizes):
        slots_left = len(sellable_sizes) - index
        variant_stock = remaining_stock // slots_left if slots_left else 0
        remaining_stock -= variant_stock
        suffix = re.sub(r'[^A-Z0-9]+', '-', (size or 'DEFAULT').upper()).strip('-')
        db.session.add(ProductVariant(
            product_id=product.id,
            sku=f"{sku}-{suffix}" if size else sku,
            title=size or 'Mặc định',
            size=size,
            price=price,
            old_price=old_price,
            stock=variant_stock,
            is_active=True,
        ))
    db.session.commit()
    flash(f'Đã thêm sản phẩm "{name}" thành công!', 'success')
    return redirect(url_for('admin_dashboard') + '?tab=products')


@app.route('/admin/product/edit/<int:product_id>', methods=['POST'])
@login_required
def admin_edit_product(product_id):
    if current_user.role != 'admin':
        return redirect(url_for('index'))

    product = Product.query.get_or_404(product_id)

    product.name = request.form.get('name', product.name).strip()
    new_sku = (request.form.get('sku') or product.sku or '').strip().upper()
    sku_owner = Product.query.filter(func.lower(Product.sku) == new_sku.lower(), Product.id != product.id).first() if new_sku else None
    if sku_owner:
        flash(f'SKU {new_sku} đã thuộc sản phẩm khác.', 'error')
        return redirect(url_for('admin_dashboard') + '?tab=products')
    product.sku = new_sku or product.sku
    product.price = float(request.form.get('price', product.price) or 0)
    old_price_str = request.form.get('old_price', '').strip()
    product.old_price = float(old_price_str) if old_price_str else None
    product.description = request.form.get('description', '').strip()

    category_action = request.form.get('category_action', f"{product.category_id}|{product.subcategory or ''}")
    cat_parts = category_action.split('|')
    product.category_id = int(cat_parts[0])
    product.subcategory = cat_parts[1] if len(cat_parts) > 1 and cat_parts[1] else None

    product.stock = int(request.form.get('stock', product.stock or 100))
    product.is_new = bool(request.form.get('is_new'))
    product.is_on_sale = bool(request.form.get('is_on_sale'))

    # Update image if new ones uploaded
    files = request.files.getlist('image_files')
    extra_urls = []
    has_new_images = False

    for file in files:
        if file and file.filename and allowed_file(file.filename):
            ext = file.filename.rsplit('.', 1)[1].lower()
            filename = f"{uuid.uuid4().hex}.{ext}"
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            url = url_for('static', filename=f'uploads/{filename}')
            if not has_new_images:
                product.image_url = url
                has_new_images = True
            else:
                extra_urls.append(url)

    if extra_urls:
        product.extra_images = json.dumps(extra_urls)

    # Allow setting a direct URL if provided
    direct_image_url = request.form.get('direct_image_url', '').strip()
    if direct_image_url:
        product.image_url = direct_image_url

    # Sizes
    sizes_raw = request.form.get('sizes_input', '').strip()
    if sizes_raw:
        sizes_list = [s.strip() for s in sizes_raw.replace('\n', ',').split(',') if s.strip()]
        product.sizes = json.dumps(sizes_list, ensure_ascii=False) if sizes_list else None
    else:
        product.sizes = None

    # The quick editor applies the displayed price and total inventory across
    # every active variant. SellerPilot can later target an individual SKU.
    active_variants = [variant for variant in product.variants if variant.is_active]
    if active_variants:
        remaining_stock = product.stock
        for index, variant in enumerate(active_variants):
            slots_left = len(active_variants) - index
            variant.stock = remaining_stock // slots_left if slots_left else 0
            remaining_stock -= variant.stock
            variant.price = product.price
            variant.old_price = product.old_price

    db.session.commit()
    flash(f'Đã cập nhật sản phẩm "{product.name}" thành công!', 'success')
    return redirect(url_for('admin_dashboard') + '?tab=products')


@app.route('/admin/coupon/add', methods=['POST'])
@login_required
def admin_add_coupon():
    if current_user.role != 'admin':
        return redirect(url_for('index'))
    code = (request.form.get('code') or '').strip().upper()
    coupon_type = (request.form.get('coupon_type') or 'percent').strip().lower()
    value = float(request.form.get('value') or 0)
    min_subtotal = float(request.form.get('min_subtotal') or 0)
    max_uses_raw = (request.form.get('max_uses') or '').strip()
    expires_raw = (request.form.get('expires_at') or '').strip()

    if not code:
        flash('Mã coupon không được để trống.', 'error')
        return redirect(url_for('admin_dashboard') + '?tab=marketing')
    if coupon_type not in ['percent', 'fixed', 'shipping']:
        coupon_type = 'percent'
    if value <= 0:
        flash('Giá trị coupon phải lớn hơn 0.', 'error')
        return redirect(url_for('admin_dashboard') + '?tab=marketing')
    if Coupon.query.filter_by(code=code).first():
        flash('Mã coupon đã tồn tại trong hệ thống.', 'error')
        return redirect(url_for('admin_dashboard') + '?tab=marketing')
    if code in app.config.get('COUPONS', {}):
        flash('Mã coupon này là mã mặc định của hệ thống, không thể tạo trùng.', 'error')
        return redirect(url_for('admin_dashboard') + '?tab=marketing')


    max_uses = int(max_uses_raw) if max_uses_raw.isdigit() else None
    expires_at = None
    if expires_raw:
        try:
            expires_at = datetime.strptime(expires_raw, '%Y-%m-%dT%H:%M')
        except Exception:
            flash('Định dạng ngày hết hạn không hợp lệ.', 'error')
            return redirect(url_for('admin_dashboard') + '?tab=marketing')

    coupon = Coupon(
        code=code,
        coupon_type=coupon_type,
        value=value,
        min_subtotal=min_subtotal,
        max_uses=max_uses,
        expires_at=expires_at,
        is_active=True,
    )
    db.session.add(coupon)
    db.session.commit()
    flash(f'Đã tạo coupon {code}.', 'success')
    return redirect(url_for('admin_dashboard') + '?tab=marketing')


@app.route('/admin/coupon/delete/<int:coupon_id>', methods=['POST'])
@login_required
def admin_delete_coupon(coupon_id):
    if current_user.role != 'admin':
        return redirect(url_for('index'))
    coupon = Coupon.query.get_or_404(coupon_id)
    db.session.delete(coupon)
    db.session.commit()
    flash('Đã xóa coupon.', 'info')
    return redirect(url_for('admin_dashboard') + '?tab=marketing')


@app.route('/admin/product/delete/<int:product_id>', methods=['POST'])
@login_required
def admin_delete_product(product_id):
    if current_user.role != 'admin':
        return redirect(url_for('index'))
    product = Product.query.get_or_404(product_id)
    if OrderItem.query.filter_by(product_id=product.id).first():
        product.status = 'archived'
        product.stock = 0
        for variant in product.variants:
            variant.stock = 0
            variant.is_active = False
        CartItem.query.filter_by(product_id=product.id).delete()
        WishlistItem.query.filter_by(product_id=product.id).delete()
        db.session.commit()
        flash('Sản phẩm đã có lịch sử đơn hàng nên được lưu trữ thay vì xóa.', 'info')
        return redirect(url_for('admin_dashboard') + '?tab=products')
    # Xóa ảnh upload nếu có
    if product.image_url and '/static/uploads/' in product.image_url:
        filename = product.image_url.split('/static/uploads/')[-1]
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if os.path.exists(filepath):
            os.remove(filepath)

    # Ngăn rác dữ liệu/crash trang web của người dùng bằng cách xoá sản phẩm khỏi giỏ hàng/wishlist
    CartItem.query.filter_by(product_id=product.id).delete()
    WishlistItem.query.filter_by(product_id=product.id).delete()
    Review.query.filter_by(product_id=product.id).delete()

    db.session.delete(product)
    db.session.commit()
    flash('Đã xóa sản phẩm và cập nhật giỏ hàng khách hàng.', 'info')
    return redirect(url_for('admin_dashboard') + '?tab=products')


@app.route('/admin/order/<int:order_id>/status', methods=['POST'])
@login_required
def admin_update_order_status(order_id):
    if current_user.role != 'admin':
        return redirect(url_for('index'))
    order = Order.query.get_or_404(order_id)
    new_status = request.form.get('status')
    try:
        from commerce import change_order_status
        change_order_status(order, new_status)
        db.session.commit()
        flash(f'Đã cập nhật trạng thái đơn hàng #{order_id}.', 'success')
    except ValueError as error:
        db.session.rollback()
        flash(str(error), 'error')
    return redirect(url_for('admin_dashboard') + '?tab=orders')


# ── MY ORDERS ──────────────────────────────────────────────────────────────────
@app.route('/my-orders')
@login_required
def my_orders():
    query=Order.query.filter_by(user_id=current_user.id)
    selected=request.args.get('status')
    if selected in ['pending','paid','shipped','delivered','cancelled','returned']: query=query.filter_by(status=selected)
    orders=query.order_by(Order.created_at.desc()).all()
    return render_template('my-orders.html', orders=orders)


# ── PROFILE ─────────────────────────────────────────────────────────────────────
@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        action = request.form.get('action', '')

        if action == 'update_info':
            username = request.form.get('username', '').strip()
            email    = request.form.get('email', '').strip().lower()
            if not 3 <= len(username) <= 100 or not email or len(email)>150:
                flash('Vui lòng điền đầy đủ thông tin.', 'error')
                return redirect(url_for('profile'))
            if not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', email):
                flash('Email không hợp lệ.', 'error')
                return redirect(url_for('profile'))
            if User.query.filter(User.username == username, User.id != current_user.id).first():
                flash('Tên đăng nhập đã được sử dụng bởi tài khoản khác.', 'error')
                return redirect(url_for('profile'))
            if User.query.filter(User.email == email, User.id != current_user.id).first():
                flash('Email đã được sử dụng bởi tài khoản khác.', 'error')
                return redirect(url_for('profile'))
            current_user.username = username
            current_user.email    = email
            db.session.commit()
            flash('Cập nhật thông tin thành công!', 'success')

        elif action == 'change_password':
            current_pw  = request.form.get('current_password', '')
            new_pw      = request.form.get('new_password', '')
            confirm_pw  = request.form.get('confirm_password', '')
            if not check_password_hash(current_user.password_hash, current_pw):
                flash('Mật khẩu hiện tại không đúng.', 'error')
                return redirect(url_for('profile'))
            if not 8 <= len(new_pw) <= 128:
                flash('Mật khẩu mới phải có ít nhất 8 ký tự.', 'error')
                return redirect(url_for('profile'))
            pw_pattern = re.compile(r'^(?=.*\d)(?=.*[a-z])(?=.*[A-Z]).{8,}$')
            if not pw_pattern.match(new_pw):
                flash('Mật khẩu mới cần có ít nhất 1 chữ HOA, 1 chữ thường và 1 chữ số.', 'error')
                return redirect(url_for('profile'))
            if new_pw != confirm_pw:
                flash('Xác nhận mật khẩu không khớp.', 'error')
                return redirect(url_for('profile'))
            current_user.password_hash = generate_password_hash(new_pw, method='pbkdf2:sha256')
            db.session.commit()
            flash('Đổi mật khẩu thành công!', 'success')

        return redirect(url_for('profile'))

    order_count = Order.query.filter_by(user_id=current_user.id).count()
    return render_template('profile.html', order_count=order_count)


from seller import bp as seller_blueprint
app.register_blueprint(seller_blueprint)
from marketplace_setup import initialize_marketplace
with app.app_context():
    db.create_all()
    ensure_db_schema()
    ensure_order_schema()
    ensure_user_schema()
initialize_marketplace(app)


@app.before_request
def prepare_demo_catalog_reviews():
    if request.endpoint == 'static' and (request.view_args or {}).get('filename', '').startswith('uploads/sellerpilot/'):
        # Draft originals are private; published product pictures are public.
        url = '/static/' + request.view_args['filename']
        published = Product.query.filter(or_(Product.image_url == url, Product.extra_images.contains(url))).all()
        def has_public_image(product):
            if product.image_url == url: return True
            try:
                extras = json.loads(product.extra_images or '[]')
                return isinstance(extras, list) and url in extras
            except (ValueError, TypeError): return False
        if not any(has_public_image(product) for product in published):
            abort(404)
    # SellerPilot can publish directly to the shared DB while the store stays
    # running. Backfill only unmarked products before catalog/review rendering.
    if request.method == 'GET' and request.endpoint in {
        'index', 'products', 'product_detail', 'shop_page', 'seller.products', 'seller.reviews',
    }:
        from demo_reviews import ensure_demo_reviews
        ensure_demo_reviews()

@app.errorhandler(404)
def not_found(error):
    return render_template('error.html',code=404,message='Trang hoặc sản phẩm này không còn tồn tại.'),404

@app.errorhandler(403)
def forbidden(error):
    return render_template('error.html',code=403,message='Bạn không có quyền truy cập nội dung này.'),403

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        ensure_db_schema()
        ensure_order_schema()
        ensure_user_schema()
        missing_payment_env = _missing_payment_env_vars() if app.config.get('ENABLE_EXTERNAL_PAYMENTS') else {}
        if missing_payment_env and not _is_debug_mode:
            raise RuntimeError(f"Missing payment environment variables: {missing_payment_env}")
    debug = os.environ.get('FLASK_DEBUG', '').strip() in ['1', 'true', 'True']
    port = int(os.environ.get('PORT', '5011'))
    app.run(debug=debug, host=os.environ.get('HOST', '127.0.0.1'), port=port)
