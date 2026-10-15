"""Idempotent upgrade and demo content. Does not overwrite seller edits on startup."""
import random
import os
import secrets
from datetime import datetime, timedelta
from sqlalchemy import text, func
from werkzeug.security import generate_password_hash
from extensions import db
from models import (User, Shop, ShopMember, Product, Order, OrderItem, Review,
                    Coupon, Conversation, Message, SellerActivity)
from commerce import refresh_product, refresh_shop


def _enrich_demo_reviews(shop):
    """Add a deterministic, purchase-backed review set once for the demo shop."""
    action = 'Bổ sung đánh giá mô phỏng UTech v2'
    if SellerActivity.query.filter_by(shop_id=shop.id, action=action).first():
        return

    general = [
        'Sản phẩm đúng mô tả, đóng gói cẩn thận và dùng ổn định.',
        'Mình đã dùng vài ngày, chất lượng tốt trong tầm giá.',
        'Hàng nhận được nguyên vẹn, thao tác cài đặt khá đơn giản.',
        'Shop chuẩn bị hàng nhanh, sản phẩm giống hình và đúng phân loại.',
        'Ngoại hình hoàn thiện tốt, phụ kiện đi kèm đầy đủ.',
        'Dùng cho học tập và làm việc hằng ngày rất tiện.',
        'Chất lượng ổn, tư vấn rõ ràng, sẽ tiếp tục ủng hộ shop.',
        'Nhận hàng đúng hẹn, kiểm tra các chức năng đều hoạt động bình thường.',
        'Đóng gói chắc tay, hộp sạch và sản phẩm không bị trầy xước.',
        'Giá hợp lý, trải nghiệm thực tế đúng với thông tin shop đăng.',
    ]
    tech = [
        'Kết nối nhanh, tín hiệu ổn định và chưa gặp lỗi khi sử dụng.',
        'Hoạt động tốt với máy tính của mình, nhận thiết bị ngay khi cắm.',
        'Phụ kiện hoàn thiện chắc chắn, dùng liên tục vẫn ổn.',
        'Thông số đúng mô tả, tốc độ phản hồi đáp ứng tốt nhu cầu hằng ngày.',
        'Thiết bị gọn, dễ mang theo và tương thích tốt với máy mình.',
        'Cài đặt nhanh, kết nối ổn và không bị ngắt quãng.',
    ]
    audio = [
        'Âm thanh rõ, kết nối nhanh, nghe họp và giải trí đều ổn.',
        'Đeo khá thoải mái, âm lượng tốt và không bị rè.',
        'Mic thu tiếng rõ hơn mong đợi, dùng họp trực tuyến rất tiện.',
    ]
    input_devices = [
        'Phím bấm êm, phản hồi tốt và bố cục dễ làm quen.',
        'Cầm vừa tay, thao tác chính xác và kết nối ổn định.',
        'Dùng làm việc nhiều giờ vẫn thoải mái, hoàn thiện chắc chắn.',
    ]
    storage = [
        'Sao chép dữ liệu ổn định, dung lượng nhận đủ và ít nóng.',
        'Tốc độ đáp ứng tốt nhu cầu lưu tài liệu và ảnh cá nhân.',
        'Máy nhận ổ nhanh, truyền tệp lớn ổn định trong lúc thử.',
    ]
    service = [
        'Giao hàng đúng hẹn, shop phản hồi tin nhắn nhanh.',
        'Nhân viên tư vấn đúng nhu cầu, đóng gói nhiều lớp.',
        'Mình cần hỏi thêm cách sử dụng và shop hỗ trợ khá nhiệt tình.',
        'Thời gian giao hợp lý, sản phẩm được bọc chống va đập kỹ.',
    ]
    replies = [
        'UTech cảm ơn bạn đã đánh giá. Shop luôn sẵn sàng hỗ trợ trong quá trình sử dụng!',
        'Cảm ơn bạn đã tin tưởng UTech Official. Chúc bạn có trải nghiệm thật tốt với sản phẩm!',
        'Shop cảm ơn phản hồi của bạn và sẽ tiếp tục cải thiện chất lượng phục vụ.',
        'UTech đã ghi nhận đánh giá. Nếu cần hướng dẫn hoặc bảo hành, bạn hãy nhắn shop nhé!',
    ]

    existing = {(row.product_id, row.user_id) for row in Review.query.all()}
    rows = (db.session.query(OrderItem, Order, Product)
            .join(Order, Order.id == OrderItem.order_id)
            .join(Product, Product.id == OrderItem.product_id)
            .filter(Order.status == 'delivered', Product.shop_id == shop.id)
            .order_by(Order.created_at.asc(), OrderItem.id.asc()).all())
    rng = random.Random(20261016)
    affected = set()
    added = 0
    for item, order, product in rows:
        key = (product.id, order.user_id)
        if key in existing:
            continue
        name = product.name.lower()
        detail_pool = tech
        if any(word in name for word in ('tai nghe', 'headphone', 'earphone', 'loa', 'micro')):
            detail_pool = audio
        elif any(word in name for word in ('bàn phím', 'keyboard', 'chuột', 'mouse')):
            detail_pool = input_devices
        elif any(word in name for word in ('ổ cứng', 'hard drive', 'ssd', 'usb', 'storage')):
            detail_pool = storage
        comment = rng.choice(general) + ' ' + rng.choice(detail_pool)
        if rng.random() < .52:
            comment += ' ' + rng.choice(service)
        created = min(order.created_at + timedelta(days=rng.randint(2, 14), hours=rng.randint(1, 20)), datetime.utcnow())
        review = Review(
            product_id=product.id,
            user_id=order.user_id,
            rating=rng.choices([3, 4, 5], [4, 24, 72])[0],
            comment=comment,
            created_at=created,
        )
        if rng.random() < .38:
            review.seller_reply = rng.choice(replies)
            review.replied_at = min(created + timedelta(hours=rng.randint(2, 30)), datetime.utcnow())
        db.session.add(review)
        existing.add(key)
        affected.add(product.id)
        added += 1
        if added >= 420:
            break

    db.session.flush()
    for product in Product.query.filter(Product.id.in_(affected)).all():
        refresh_product(product)
    refresh_shop(shop.id)
    db.session.add(SellerActivity(shop_id=shop.id, action=action))
    db.session.commit()


def initialize_marketplace(app):
    with app.app_context():
        additions = {
            'product': {'historical_sold_count':'INTEGER NOT NULL DEFAULT 0'},
            'shop': {'shipping_address':'VARCHAR(500)', 'phone':'VARCHAR(30)', 'contact_email':'VARCHAR(180)', 'vacation_mode':'BOOLEAN NOT NULL DEFAULT 0'},
            'order': {'checkout_reference':'VARCHAR(64)', 'shipping_fee':'FLOAT NOT NULL DEFAULT 0', 'discount_amount':'FLOAT NOT NULL DEFAULT 0'},
            'coupon': {'shop_id':'INTEGER'},
            'review': {'seller_reply':'TEXT', 'replied_at':'DATETIME'},
        }
        # Existing tables must be upgraded before ORM queries touch new fields.
        for table, columns in additions.items():
            known = {row[1] for row in db.session.execute(text('PRAGMA table_info("%s")' % table))}
            if not known: continue
            for name, sql_type in columns.items():
                if name not in known:
                    db.session.execute(text('ALTER TABLE "%s" ADD COLUMN %s %s' % (table, name, sql_type)))
                    if table=='product' and name=='historical_sold_count':
                        db.session.execute(text('''UPDATE product SET historical_sold_count = CASE
                            WHEN shop_id IN (SELECT id FROM shop WHERE is_sellerpilot=1) THEN 0
                            ELSE MAX(0, COALESCE(sold_count,0) - COALESCE((
                                SELECT SUM(oi.quantity) FROM order_item oi JOIN "order" o ON o.id=oi.order_id
                                WHERE oi.product_id=product.id AND o.status='delivered'),0)) END'''))
        db.session.commit()
        db.create_all()
        db.session.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS uq_review_buyer_product ON review(product_id,user_id)'))
        db.session.commit()
        shop = Shop.query.filter_by(slug='utech-official').first()
        if not shop: return
        _enrich_demo_reviews(shop)
        marker = SellerActivity.query.filter_by(shop_id=shop.id,action='Khởi tạo Kênh Người Bán UTE MALL').first()
        if marker: return
        owner = User.query.filter_by(username='utech').first()
        if not owner:
            owner = User(username='utech', email='utech@example.test', password_hash=generate_password_hash(os.environ.get('DEMO_SELLER_PASSWORD') or secrets.token_urlsafe(32),method='pbkdf2:sha256'), role='seller')
            db.session.add(owner); db.session.flush()
        if not ShopMember.query.filter_by(user_id=owner.id).first():
            db.session.add(ShopMember(shop_id=shop.id,user_id=owner.id,role='owner'))
        admin = User.query.filter_by(username='admin').first()
        if admin and not ShopMember.query.filter_by(user_id=admin.id).first():
            db.session.add(ShopMember(shop_id=shop.id,user_id=admin.id,role='owner'))
        shop.description = 'Thiết bị và phụ kiện công nghệ cho học tập, làm việc và giải trí. Đổi trả trong 7 ngày, hỗ trợ bảo hành theo từng sản phẩm.'
        shop.shipping_address = 'Kho UTech · TP. Hồ Chí Minh'
        shop.contact_email = 'utech@example.test'
        rng = random.Random(20261015)
        # Seed reviews only for verified delivered purchases, at most one per buyer/product.
        comments = [
            'Đóng gói chắc chắn, sản phẩm đúng mô tả. Dùng ổn sau vài ngày.',
            'Giao hàng đúng hẹn. Phụ kiện đầy đủ, shop hỗ trợ nhanh.',
            'Chất lượng tốt trong tầm giá, sẽ tiếp tục ủng hộ shop.',
            'Sản phẩm hoạt động ổn, ngoại hình như ảnh. Mình khá hài lòng.',
            'Shop tư vấn rõ ràng. Nhận hàng và kiểm tra mọi chức năng đều ổn.',
            'Hàng đúng mẫu đã đặt. Hộp hơi móp nhưng sản phẩm vẫn nguyên vẹn.',
        ]
        pairs=set((r.product_id,r.user_id) for r in Review.query.all())
        delivered = Order.query.filter_by(shop_id=shop.id,status='delivered').order_by(Order.id).all()
        for order in delivered:
            for item in order.items:
                key=(item.product_id,order.user_id)
                if key in pairs or rng.random()>.48: continue
                review=Review(product_id=item.product_id,user_id=order.user_id,rating=rng.choices([3,4,5],[3,22,75])[0],comment=rng.choice(comments),created_at=min(order.created_at+timedelta(days=4),datetime.utcnow()))
                if rng.random()<.45:
                    review.seller_reply='UTech cảm ơn bạn đã tin tưởng. Shop luôn sẵn sàng hỗ trợ khi bạn cần!'
                    review.replied_at=review.created_at+timedelta(hours=3)
                db.session.add(review); pairs.add(key)
        db.session.flush()
        for product in Product.query.filter_by(shop_id=shop.id).all(): refresh_product(product)
        refresh_shop(shop.id)
        # Reconcile displayed rating counts throughout the marketplace with review rows.
        for product in Product.query.filter(Product.shop_id != shop.id).all():
            count,average=db.session.query(func.count(Review.id),func.avg(Review.rating)).filter_by(product_id=product.id).one()
            product.rating_count=count; product.rating=round(float(average or 0),1)
        for code,kind,value,minimum,seller_id in [
            ('WELCOME10','percent',10,200000,None), ('FREESHIP','shipping',30000,0,None),
            ('SAVE50K','fixed',50000,600000,None), ('UTECH50','fixed',50000,500000,shop.id),
        ]:
            if not Coupon.query.filter_by(code=code).first():
                db.session.add(Coupon(code=code,coupon_type=kind,value=value,min_subtotal=minimum,shop_id=seller_id,is_active=True))
        for order in delivered[:5]:
            convo=Conversation.query.filter_by(shop_id=shop.id,buyer_id=order.user_id).first()
            if not convo:
                convo=Conversation(shop_id=shop.id,buyer_id=order.user_id,updated_at=datetime.utcnow()-timedelta(minutes=order.id%90))
                db.session.add(convo); db.session.flush()
                db.session.add(Message(conversation_id=convo.id,sender_id=order.user_id,from_seller=False,body='Shop ơi, sản phẩm mình mua được bảo hành như thế nào ạ?'))
        db.session.add(SellerActivity(shop_id=shop.id,user_id=owner.id,action='Khởi tạo Kênh Người Bán UTE MALL'))
        db.session.commit()
