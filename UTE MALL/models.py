from extensions import db
from flask_login import UserMixin
from datetime import datetime, timedelta
import secrets

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(50), default='user') # 'admin' or 'user'
    reset_token = db.Column(db.String(100), nullable=True, unique=True)
    reset_token_expires = db.Column(db.DateTime, nullable=True)

    def generate_reset_token(self, expires_minutes: int = 30) -> str:
        """Tạo token reset mật khẩu có thời hạn, lưu vào model."""
        token = secrets.token_urlsafe(48)
        self.reset_token = token
        self.reset_token_expires = datetime.utcnow() + timedelta(minutes=expires_minutes)
        return token

    def clear_reset_token(self):
        """Xóa token sau khi đã dùng."""
        self.reset_token = None
        self.reset_token_expires = None

    def is_reset_token_valid(self) -> bool:
        """Kiểm tra token còn hạn không."""
        if not self.reset_token or not self.reset_token_expires:
            return False
        return datetime.utcnow() < self.reset_token_expires

    carts = db.relationship('Cart', backref='user', lazy=True)
    orders = db.relationship('Order', backref='user', lazy=True)
    reviews = db.relationship('Review', backref='user', lazy=True)


class Shop(db.Model):
    """A seller storefront inside the UTE MALL marketplace."""

    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(120), unique=True, nullable=False, index=True)
    name = db.Column(db.String(180), nullable=False)
    description = db.Column(db.Text, nullable=True)
    logo_url = db.Column(db.String(500), nullable=True)
    cover_url = db.Column(db.String(500), nullable=True)
    location = db.Column(db.String(120), nullable=False, default='TP. Hồ Chí Minh')
    category_label = db.Column(db.String(120), nullable=True)
    rating = db.Column(db.Float, nullable=False, default=4.8)
    follower_count = db.Column(db.Integer, nullable=False, default=0)
    response_rate = db.Column(db.Integer, nullable=False, default=95)
    is_verified = db.Column(db.Boolean, nullable=False, default=False)
    is_sellerpilot = db.Column(db.Boolean, nullable=False, default=False, index=True)
    status = db.Column(db.String(20), nullable=False, default='active', index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    shipping_address = db.Column(db.String(500), nullable=True)
    phone = db.Column(db.String(30), nullable=True)
    contact_email = db.Column(db.String(180), nullable=True)
    vacation_mode = db.Column(db.Boolean, default=False, nullable=False)

    products = db.relationship('Product', backref='seller_shop', lazy=True)

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    slug = db.Column(db.String(120), unique=True, nullable=True, index=True)
    parent_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=True, index=True)
    icon = db.Column(db.String(80), nullable=True)
    image_url = db.Column(db.String(500), nullable=True)
    display_order = db.Column(db.Integer, nullable=False, default=0)

    children = db.relationship('Category', backref=db.backref('parent', remote_side=[id]), lazy=True)

    products = db.relationship('Product', backref='category', lazy=True)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sku = db.Column(db.String(100), unique=True, nullable=True, index=True)
    slug = db.Column(db.String(220), unique=True, nullable=True, index=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    price = db.Column(db.Float, nullable=False)
    old_price = db.Column(db.Float, nullable=True)
    image_url = db.Column(db.String(500), nullable=True)
    extra_images = db.Column(db.Text, nullable=True) # JSON list of URLs
    video_url = db.Column(db.String(500), nullable=True)
    stock = db.Column(db.Integer, default=100)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Catalog provenance. Keeping the source makes imported demo data auditable
    # and lets SellerPilot distinguish local products from marketplace imports.
    source = db.Column(db.String(50), nullable=False, default='manual', index=True)
    source_id = db.Column(db.String(100), nullable=True, index=True)
    source_url = db.Column(db.String(500), nullable=True)
    vendor = db.Column(db.String(150), nullable=True)
    material = db.Column(db.String(300), nullable=True)
    currency = db.Column(db.String(10), nullable=False, default='VND')
    rating = db.Column(db.Float, nullable=True)
    rating_count = db.Column(db.Integer, nullable=False, default=0)
    status = db.Column(db.String(20), nullable=False, default='active', index=True)
    sold_count = db.Column(db.Integer, nullable=False, default=0)
    historical_sold_count = db.Column(db.Integer, nullable=False, default=0)
    location = db.Column(db.String(120), nullable=True)
    attributes_json = db.Column(db.Text, nullable=True)
    is_featured = db.Column(db.Boolean, nullable=False, default=False)

    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=False)
    shop_id = db.Column(db.Integer, db.ForeignKey('shop.id'), nullable=True, index=True)
    subcategory = db.Column(db.String(100), nullable=True)

    is_new = db.Column(db.Boolean, default=False)
    is_on_sale = db.Column(db.Boolean, default=False)
    sizes = db.Column(db.Text, nullable=True)  # JSON list of size strings, e.g. ["S","M","L","XL"] or ["One Size"]

    variants = db.relationship('ProductVariant', backref='product', lazy=True, cascade='all, delete-orphan')
    reviews = db.relationship('Review', backref='product', lazy=True)
    order_items = db.relationship('OrderItem', back_populates='product', lazy=True)


class ProductVariant(db.Model):
    """A sellable SKU such as "Black / M"."""

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False, index=True)
    sku = db.Column(db.String(100), unique=True, nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    size = db.Column(db.String(80), nullable=True)
    color = db.Column(db.String(100), nullable=True)
    price = db.Column(db.Float, nullable=False)
    old_price = db.Column(db.Float, nullable=True)
    stock = db.Column(db.Integer, nullable=False, default=0)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

class Cart(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    items = db.relationship('CartItem', backref='cart', lazy=True, cascade='all, delete-orphan')

class CartItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cart_id = db.Column(db.Integer, db.ForeignKey('cart.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    variant_id = db.Column(db.Integer, db.ForeignKey('product_variant.id'), nullable=True, index=True)
    quantity = db.Column(db.Integer, default=1)

    product = db.relationship('Product')
    variant = db.relationship('ProductVariant')


class WishlistItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('wishlist_items', lazy=True, cascade='all, delete-orphan'))
    product = db.relationship('Product')

    __table_args__ = (
        db.UniqueConstraint('user_id', 'product_id', name='uq_wishlist_user_product'),
    )

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    shop_id = db.Column(db.Integer, db.ForeignKey('shop.id'), nullable=True, index=True)
    checkout_reference = db.Column(db.String(64), nullable=True, index=True)
    shipping_fee = db.Column(db.Float, nullable=False, default=0)
    discount_amount = db.Column(db.Float, nullable=False, default=0)
    total_amount = db.Column(db.Float, nullable=False)
    # Order lifecycle status (fulfillment)
    status = db.Column(db.String(50), default='pending') # pending, paid, shipped, delivered, cancelled
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Shipping/customer info (captured at checkout)
    shipping_name = db.Column(db.String(150), nullable=True)
    shipping_phone = db.Column(db.String(30), nullable=True)
    shipping_address = db.Column(db.String(500), nullable=True)
    note = db.Column(db.String(500), nullable=True)

    # Payment info
    payment_method = db.Column(db.String(50), default='COD')  # COD, BANK_TRANSFER, MOMO, VNPAY
    payment_status = db.Column(db.String(50), default='unpaid')  # unpaid, initiated, paid, failed, cancelled
    payment_ref = db.Column(db.String(200), nullable=True)  # gateway transaction ref

    items = db.relationship('OrderItem', backref='order', lazy=True, cascade='all, delete-orphan')
    seller_shop = db.relationship('Shop', backref=db.backref('orders', lazy=True))

class PaymentTransaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False, index=True)
    provider = db.Column(db.String(50), nullable=False)  # MOMO, VNPAY
    amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(50), default='initiated')  # initiated, paid, failed, cancelled
    provider_ref = db.Column(db.String(200), nullable=True)  # transactionId / vnp_TxnRef
    raw_request = db.Column(db.Text, nullable=True)
    raw_response = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    order = db.relationship('Order', backref=db.backref('transactions', lazy=True, cascade='all, delete-orphan'))


class Coupon(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey('shop.id'), nullable=True, index=True)
    code = db.Column(db.String(50), unique=True, nullable=False, index=True)
    coupon_type = db.Column(db.String(20), nullable=False, default='percent')  # percent, fixed, shipping
    value = db.Column(db.Float, nullable=False, default=0)
    min_subtotal = db.Column(db.Float, nullable=False, default=0)
    is_active = db.Column(db.Boolean, default=True)
    expires_at = db.Column(db.DateTime, nullable=True)
    max_uses = db.Column(db.Integer, nullable=True)
    used_count = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    variant_id = db.Column(db.Integer, db.ForeignKey('product_variant.id'), nullable=True)
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Float, nullable=False) # price at the time of purchase
    sku = db.Column(db.String(100), nullable=True)
    variant_title = db.Column(db.String(200), nullable=True)

    product = db.relationship('Product', back_populates='order_items')
    variant = db.relationship('ProductVariant')

class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    rating = db.Column(db.Integer, nullable=False) # 1 to 5
    comment = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    seller_reply = db.Column(db.Text, nullable=True)
    replied_at = db.Column(db.DateTime, nullable=True)


class ShopMember(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey('shop.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True)
    role = db.Column(db.String(30), nullable=False, default='owner')
    shop = db.relationship('Shop')
    user = db.relationship('User')


class ShopFollow(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey('shop.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    __table_args__ = (db.UniqueConstraint('shop_id', 'user_id'),)


class Conversation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey('shop.id'), nullable=False, index=True)
    buyer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)
    shop = db.relationship('Shop')
    buyer = db.relationship('User')
    messages = db.relationship('Message', backref='conversation', cascade='all, delete-orphan', order_by='Message.created_at')
    __table_args__ = (db.UniqueConstraint('shop_id', 'buyer_id'),)


class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversation.id'), nullable=False, index=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    from_seller = db.Column(db.Boolean, nullable=False, default=False)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ReturnRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False, unique=True)
    reason = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(30), nullable=False, default='pending')
    seller_note = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    order = db.relationship('Order', backref=db.backref('return_request', uselist=False))


class SellerActivity(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey('shop.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    action = db.Column(db.String(500), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Contact(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(150), nullable=False)
    subject = db.Column(db.String(200), nullable=True)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
