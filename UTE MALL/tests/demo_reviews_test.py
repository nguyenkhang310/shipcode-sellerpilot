"""Catalog-wide demo reviews on an isolated database; never changes the shop."""
from pathlib import Path
import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
TEMP = tempfile.TemporaryDirectory(prefix='shopee-reviews-test-')
DATABASE = Path(TEMP.name) / 'store.db'
SOURCE = Path(os.environ.get('COMMERCE_SOURCE_DATABASE') or ROOT / 'instance/ecommerce.db')
with sqlite3.connect(f'file:{SOURCE}?mode=ro', uri=True) as source, sqlite3.connect(DATABASE) as target:
    source.backup(target)
    BEFORE_ORDERS = target.execute('SELECT count(*),sum(total_amount) FROM "order"').fetchone()
    BEFORE_STOCK = target.execute('SELECT id,stock,sold_count,price FROM product ORDER BY id').fetchall()
    BEFORE_REVIEWS = target.execute('SELECT id,product_id,user_id,rating,comment,seller_reply FROM review').fetchall()
os.environ.update(STORE_DATABASE_PATH=str(DATABASE), TESTING='1', LIMITER_STORAGE_URI='memory://', ENABLE_DEMO_REVIEWS='1')
from app import app, limiter
from extensions import db
from models import DemoReviewSeed, Product, Review, User
from demo_reviews import comment_kind, ensure_demo_reviews
app.config.update(TESTING=True, WTF_CSRF_ENABLED=False, RATELIMIT_ENABLED=False)
limiter.enabled = False


class DemoReviewTests(unittest.TestCase):
    def test_every_active_product_has_persisted_consistent_comments(self):
        with app.app_context():
            active = Product.query.filter_by(status='active').all()
            self.assertGreater(len(active), 100)
            for product in active:
                reviews = Review.query.filter_by(product_id=product.id).all()
                self.assertGreaterEqual(len(reviews), 16, product.id)
                self.assertTrue(all(r.comment and 1 <= r.rating <= 5 for r in reviews))
                self.assertEqual(product.rating_count, len(reviews), product.id)
                self.assertEqual(product.rating, round(sum(r.rating for r in reviews) / len(reviews), 1))
                self.assertIsNotNone(db.session.get(DemoReviewSeed, product.id))

    def test_seed_never_changes_orders_stock_price_or_existing_comments(self):
        with sqlite3.connect(DATABASE) as connection:
            self.assertEqual(connection.execute('SELECT count(*),sum(total_amount) FROM "order"').fetchone(), BEFORE_ORDERS)
            actual = dict((row[0], row[1:]) for row in connection.execute('SELECT id,stock,sold_count,price FROM product'))
            for row in BEFORE_STOCK:
                self.assertEqual(actual[row[0]], row[1:])
            actual_reviews = dict((row[0], row[1:]) for row in connection.execute('SELECT id,product_id,user_id,rating,comment,seller_reply FROM review'))
            for row in BEFORE_REVIEWS:
                self.assertEqual(actual_reviews[row[0]], row[1:])

    def test_repeated_seed_and_deleted_comment_are_not_recreated(self):
        with app.app_context():
            template = Product.query.filter_by(status='active').first()
            product = Product(name='QA delete review', sku='QA-DELETE-REVIEW', price=10000,
                              stock=1, category_id=template.category_id, shop_id=template.shop_id,
                              status='active')
            db.session.add(product); db.session.commit()
            ensure_demo_reviews()
            before = Review.query.count()
            self.assertEqual(ensure_demo_reviews(), {'products': 0, 'reviews': 0})
            self.assertEqual(Review.query.count(), before)
            review = Review.query.filter_by(is_demo=True, product_id=product.id).first()
            pid = review.product_id
            db.session.delete(review); db.session.commit()
            self.assertEqual(ensure_demo_reviews()['products'], 0)
            self.assertEqual(Review.query.count(), before - 1)
            # Match real deletion semantics: counters are refreshed after removal.
            from commerce import refresh_product
            refresh_product(db.session.get(Product, pid)); db.session.commit()

    def test_new_sellerpilot_product_is_enriched_before_storefront_render(self):
        with app.app_context():
            template = Product.query.filter_by(status='active').first()
            product = Product(name='Sản phẩm mô phỏng vừa đăng', sku='QA-REVIEW-NEW', price=123000,
                              stock=7, category_id=template.category_id, shop_id=template.shop_id,
                              source='sellerpilot', status='active', created_at=datetime.utcnow())
            db.session.add(product); db.session.commit(); pid = product.id
        response = app.test_client().get('/product/' + str(pid))
        self.assertEqual(response.status_code, 200)
        self.assertIn('ĐÁNH GIÁ SẢN PHẨM'.encode(), response.data)
        with app.app_context():
            product = db.session.get(Product, pid)
            self.assertGreaterEqual(product.rating_count, 16)
            self.assertEqual(product.stock, 7); self.assertEqual(product.sold_count, 0)
            self.assertEqual(product.price, 123000)

    def test_filters_pagination_branding_and_synthetic_identity(self):
        client = app.test_client()
        with app.app_context():
            review = Review.query.filter_by(is_demo=True, rating=4).first()
            pid, username = review.product_id, review.user.username
        response = client.get(f'/product/{pid}?stars=4')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'aria-current="page"', response.data)
        self.assertIn(b'shopee-logo-white.svg', response.data)
        self.assertNotIn(b'UTE MALL', response.data)
        self.assertNotIn('Mô phỏng'.encode(), response.data)
        self.assertEqual(client.get(f'/product/{pid}?review_page=2').status_code, 200)
        # Demo reviewer identities cannot authenticate even with a replaced hash.
        with app.app_context():
            from werkzeug.security import generate_password_hash
            user = User.query.filter_by(username=username).one()
            user.password_hash = generate_password_hash('Synthetic-Only-123', method='pbkdf2:sha256')
            db.session.commit()
        result = client.post('/login', data={'login_id': username, 'password': 'Synthetic-Only-123'})
        self.assertEqual(result.status_code, 200)
        with client.session_transaction() as session:
            self.assertNotIn('_user_id', session)

    def test_disable_and_category_matching(self):
        with app.app_context():
            app.config['DEMO_REVIEWS_ENABLED'] = False
            self.assertEqual(ensure_demo_reviews(), {'products': 0, 'reviews': 0})
            app.config['DEMO_REVIEWS_ENABLED'] = True
            kinds = {comment_kind(p) for p in Product.query.filter_by(status='active').all()}
            self.assertTrue({'fashion', 'tech', 'home', 'beauty', 'pets'}.issubset(kinds), kinds)


if __name__ == '__main__':
    unittest.main(verbosity=2)
