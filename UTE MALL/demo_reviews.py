"""Repeatable demo comments for every catalog product, separate from order metrics.

Only review/user/seed records and rating aggregates are written. No purchases,
inventory, sold quantities or revenue are invented by this module.
"""
from datetime import datetime, timedelta
import random
import secrets
import unicodedata

from flask import current_app
from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert
from werkzeug.security import generate_password_hash

from extensions import db
from models import DemoReviewSeed, Product, Review, User
from commerce import refresh_shop

POOL_SIZE = 36
USER_NAMES = ('minh.anh', 'thao.nguyen', 'khang.tran', 'linh.pham', 'bao.han',
              'quoc.bao', 'ngoc.mai', 'tuan.kiet', 'khanh.vy', 'hoang.nam',
              'ha.trang', 'gia.huy', 'thuy.linh', 'duc.minh', 'yen.nhi',
              'phuong.thao', 'anh.khoa', 'hai.yen')
OPENINGS = (
    'Đã nhận hàng, đúng mẫu mình chọn.', 'Sản phẩm giống hình shop đăng.',
    'Đóng gói cẩn thận, nhận đủ số lượng.', 'Mình mua lần đầu, nhìn chung khá hài lòng.',
    'Giá phù hợp với nhu cầu của mình.', 'Shop chuẩn bị hàng nhanh và đúng phân loại.',
    'Nhận hàng nguyên vẹn, kiểm tra bên ngoài không bị lỗi.',
    'Mình đã dùng vài hôm rồi mới quay lại đánh giá.',
)
CLOSINGS = ('Shop trả lời tin nhắn khá nhanh.', 'Lần sau có nhu cầu mình sẽ ghé lại.',
            'Ảnh và thông tin trên trang giúp mình chọn dễ hơn.', 'Giao đến đúng địa chỉ, hàng được bọc kỹ.',
            'Mình chọn theo mô tả và nhận được đúng mẫu.', 'Đóng gói gọn gàng, không bị thiếu hàng.')
DETAILS = {
    'fashion': ('Đường may khá gọn, chất vải mặc thoải mái.', 'Màu bên ngoài gần với ảnh, chọn theo bảng size là vừa.', 'Form dễ phối đồ, mặc đi học hoặc đi làm đều tiện.'),
    'shoes': ('Đế đi khá êm, size mình chọn vừa chân.', 'Keo và đường may nhìn gọn, màu dễ phối.', 'Mang thử thấy vừa, nên xem bảng kích thước trước khi đặt.'),
    'bags': ('Ngăn đựng đồ bố trí hợp lý, khóa kéo trơn.', 'Màu dễ phối, đường may chắc chắn.', 'Kích thước vừa đồ dùng hằng ngày của mình.'),
    'audio': ('Âm thanh nghe rõ khi mình thử, thao tác kết nối đơn giản.', 'Dùng nghe nhạc và họp hằng ngày khá tiện.', 'Hoàn thiện bên ngoài ổn, phụ kiện nhận được đúng mô tả.'),
    'keyboard': ('Phím bấm dễ làm quen, dùng gõ tài liệu khá thoải mái.', 'Bố cục hợp với góc làm việc, thao tác ổn.', 'Mẫu và màu đúng lựa chọn, dùng làm việc hằng ngày tiện.'),
    'mouse': ('Cầm vừa tay, thao tác khá thoải mái.', 'Kích thước hợp nhu cầu làm việc của mình.', 'Di chuột ổn trên bàn làm việc, mẫu đúng như ảnh.'),
    'tech': ('Dùng thử các thao tác cơ bản thấy ổn.', 'Thông tin phân loại rõ, mình chọn được đúng loại cần dùng.', 'Sản phẩm gọn, phù hợp góc làm việc của mình.'),
    'home': ('Kích thước hợp chỗ mình định đặt.', 'Màu sắc dễ phối với đồ dùng trong nhà.', 'Dùng trong sinh hoạt hằng ngày khá tiện.'),
    'beauty': ('Bao bì nhận được sạch và còn nguyên vẹn.', 'Mình chọn đúng loại theo thông tin trên trang.', 'Dung tích và mẫu mã đúng phân loại mình đặt.'),
    'health': ('Bao bì và thông tin sử dụng được ghi rõ.', 'Mẫu nhận được đúng loại mình chọn.', 'Shop tư vấn rõ cách kiểm tra sản phẩm khi nhận.'),
    'grocery': ('Số lượng đủ, bao bì nguyên vẹn khi nhận.', 'Quy cách đóng gói đúng như mình đặt.', 'Đóng gói riêng khá cẩn thận, tiện dùng trong gia đình.'),
    'sports': ('Kích thước vừa nhu cầu tập luyện của mình.', 'Mẫu gọn và dễ mang theo.', 'Dùng thử cơ bản thấy phù hợp, đúng mẫu mình chọn.'),
    'baby': ('Bao bì sạch, kích thước và màu đúng lựa chọn.', 'Shop gói riêng từng món khá cẩn thận.', 'Thông tin phân loại rõ nên mình chọn đúng mẫu cần mua.'),
    'pets': ('Mẫu và số lượng đúng đơn mình chọn.', 'Kích thước đúng thông tin trên trang.', 'Đồ nhận được sạch và được đóng gói cẩn thận.'),
    'auto': ('Kích thước đúng loại mình đã kiểm tra trước khi đặt.', 'Phụ kiện nhận được nguyên vẹn, đúng mẫu.', 'Shop tư vấn phân loại rõ, mình chọn đúng món cần dùng.'),
    'books': ('Trang giấy và bìa còn phẳng, không bị quăn góc.', 'Nội dung/mẫu nhận được đúng lựa chọn.', 'Được bọc kỹ, nhận đủ số lượng mình đặt.'),
    'toys': ('Màu và mẫu đúng lựa chọn, chi tiết bên ngoài ổn.', 'Hộp được bọc kỹ, nhận đủ các món.', 'Kích thước đúng mô tả, mình khá hài lòng với mẫu này.'),
    'general': ('Mẫu nhận được đúng nhu cầu và phân loại mình chọn.', 'Kích thước, màu sắc đúng thông tin trên trang.', 'Kiểm tra hàng khi nhận thấy đủ và nguyên vẹn.'),
}


def _plain(value):
    return ''.join(c for c in unicodedata.normalize('NFD', value.lower()) if unicodedata.category(c) != 'Mn').replace('đ', 'd')


def comment_kind(product):
    category = product.category
    while category and category.parent:
        category = category.parent
    label = _plain(category.name if category else '')
    name = _plain(product.name)
    groups = (('thoi trang', 'fashion'), ('giay', 'shoes'), ('tui', 'bags'),
              ('nha cua', 'home'), ('sac dep', 'beauty'), ('suc khoe', 'health'),
              ('bach hoa', 'grocery'), ('the thao', 'sports'), ('me & be', 'baby'),
              ('thu cung', 'pets'), ('o to', 'auto'), ('nha sach', 'books'), ('do choi', 'toys'))
    for term, kind in groups:
        if term in label:
            return kind
    if any(term in label for term in ('dien thoai', 'may tinh', 'dien tu', 'cong nghe')):
        for terms, kind in ((('tai nghe', 'headphone', 'earphone', 'speaker', 'loa '), 'audio'),
                            (('ban phim', 'keyboard'), 'keyboard'), (('chuot', 'mouse'), 'mouse')):
            if any(term in name for term in terms):
                return kind
        return 'tech'
    return 'general'


def _reviewers():
    emails = [f'reviewer.{index:02d}@sellerpilot-demo.invalid' for index in range(POOL_SIZE)]
    existing = {user.email: user for user in User.query.filter(User.email.in_(emails)).all()}
    missing = [email for email in emails if email not in existing]
    if missing:
        # Non-login synthetic identities, unrelated to real Shopee accounts.
        password_hash = generate_password_hash(secrets.token_urlsafe(64), method='pbkdf2:sha256')
        db.session.execute(insert(User).values([
            {'username': f'{USER_NAMES[index % len(USER_NAMES)]}.demo{index + 1:02d}',
             'email': email, 'password_hash': password_hash, 'role': 'demo_reviewer'}
            for index, email in enumerate(emails) if email not in existing
        ]).on_conflict_do_nothing(index_elements=['email']))
        existing = {user.email: user for user in User.query.filter(User.email.in_(emails)).all()}
    return [existing[email] for email in emails]


def ensure_demo_reviews():
    """Seed unmarked active products, atomically and once, including new uploads."""
    if not current_app.config.get('DEMO_REVIEWS_ENABLED'):
        return {'products': 0, 'reviews': 0}
    products = Product.query.filter(Product.status == 'active', ~select(DemoReviewSeed.product_id).where(
        DemoReviewSeed.product_id == Product.id).exists()).order_by(Product.id).all()
    if not products:
        return {'products': 0, 'reviews': 0}
    reviewers = _reviewers()
    now = datetime.utcnow()
    affected, rows = [], []
    for start in range(0, len(products), 200):
        batch = products[start:start + 200]
        # The receipt and comments share a transaction; racing processes cannot
        # seed twice. A deleted comment is not recreated on the next page view.
        claimed = set(db.session.execute(insert(DemoReviewSeed).values([
            {'product_id': p.id, 'created_at': now} for p in batch
        ]).on_conflict_do_nothing(index_elements=['product_id']).returning(DemoReviewSeed.product_id)).scalars())
        for product in batch:
            if product.id not in claimed:
                continue
            rng = random.Random(f'shopee-demo-reviews-v1:{product.id}:{product.sku}')
            kind = comment_kind(product)
            age = max(0, min(180, (now - (product.created_at or now)).days))
            for i, user in enumerate(rng.sample(reviewers, rng.randint(16, 32))):
                rating = 4 if i == 0 else rng.choices([2, 3, 4, 5], [1, 4, 21, 74])[0]
                opening = rng.choice(OPENINGS)
                detail = rng.choice(DETAILS[kind])
                if rating <= 3:
                    detail = rng.choice(('Hộp bên ngoài hơi móp, bên trong vẫn đủ đồ.',
                                         'Shop nên bổ sung thêm ảnh chi tiết để dễ lựa chọn hơn.',
                                         'Mình thấy thời gian chuẩn bị hàng còn có thể cải thiện.'))
                comment = opening + ' ' + detail + (' ' + rng.choice(CLOSINGS) if rng.random() < .55 else '')
                created = now - timedelta(days=rng.randint(0, age), minutes=rng.randint(0, 59) if age else 0)
                created = max(min(product.created_at or now, now), created)
                reply = rng.random() < .42
                rows.append({'product_id': product.id, 'user_id': user.id, 'rating': rating,
                             'comment': comment, 'created_at': created, 'is_demo': True,
                             'seller_reply': 'Shop cảm ơn phản hồi của bạn. Nếu cần hỗ trợ thêm, bạn cứ nhắn shop nhé!' if reply else None,
                             'replied_at': min(now, created + timedelta(hours=rng.randint(2, 24))) if reply else None})
            affected.append(product.id)
        if rows:
            db.session.execute(insert(Review), rows)
            rows.clear()
    if affected:
        aggregates = dict((pid, (total, round(float(average or 0), 1))) for pid, total, average in
                          db.session.query(Review.product_id, func.count(Review.id), func.avg(Review.rating))
                          .filter(Review.product_id.in_(affected)).group_by(Review.product_id).all())
        for product in products:
            if product.id in aggregates:
                product.rating_count, product.rating = aggregates[product.id]
        db.session.flush()
        for shop_id in {p.shop_id for p in products if p.id in aggregates and p.shop_id}:
            refresh_shop(shop_id)
    db.session.commit()
    return {'products': len(affected), 'reviews': int(db.session.query(func.count(Review.id)).filter(
        Review.product_id.in_(affected), Review.is_demo.is_(True)).scalar() or 0) if affected else 0}
