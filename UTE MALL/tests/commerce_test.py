"""Exercise the complete local marketplace on an isolated SQLite copy."""
from pathlib import Path
import os
import re
import sqlite3
import sys
import tempfile
import secrets
import unittest
import uuid
import subprocess
import json
from datetime import datetime, timedelta
from html.parser import HTMLParser
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
TEMP=tempfile.TemporaryDirectory(prefix='ute-commerce-test-')
DB=Path(TEMP.name)/'commerce.db'
with sqlite3.connect(Path(os.environ.get('COMMERCE_SOURCE_DATABASE') or ROOT/'instance/ecommerce.db')) as source, sqlite3.connect(DB) as target: source.backup(target)
os.environ['STORE_DATABASE_PATH']=str(DB)
os.environ['TESTING']='1'
TEST_SELLER_PASSWORD=secrets.token_urlsafe(24)
from app import app, _compute_totals_from_items, limiter
from extensions import db
from models import User, Product, ProductVariant, Shop, Order, OrderItem, Coupon, Review, ReturnRequest, Conversation, Message, Cart, CartItem, ShopMember
app.config.update(TESTING=True,WTF_CSRF_ENABLED=False,RATELIMIT_ENABLED=False)
# The extension reads enabled state during app initialization, before this test config.
limiter.enabled=False
with app.app_context():
    from werkzeug.security import generate_password_hash
    owner=User.query.filter_by(username='utech').one()
    owner.password_hash=generate_password_hash(TEST_SELLER_PASSWORD, method='pbkdf2:sha256')
    db.session.commit()



class Links(HTMLParser):
    def __init__(self): super().__init__(); self.links=set()
    def handle_starttag(self,tag,attrs):
        if tag=='a':
            href=dict(attrs).get('href','')
            if href.startswith('/') and not href.startswith('//'): self.links.add(href.split('#')[0])


class CommerceTests(unittest.TestCase):
    def app_order(self, order_id, changes=None):
        """A separate process avoids Flask app.py/backend app package collisions."""
        script = '''
import json,sys
from pathlib import Path
from uuid import uuid4
from app.integrations.ute_mall import UTEMallRepository
from app.integrations.order_management import order_detail,update_order
from app.integrations.management import dashboard
from app.schemas.order_management import OrderUpdate
shop=UTEMallRepository(Path(sys.argv[1]),'Asia/Ho_Chi_Minh','utech-official')
row=order_detail(shop,int(sys.argv[2]))
changes=json.loads(sys.argv[3])
if changes:
    row=update_order(shop,row['id'],OrderUpdate(request_id=uuid4(),expected_version=row['version'],**changes))
print(json.dumps({'order':row,'stats':{str(days):dashboard(shop,days) for days in (1,7,30)}},default=str))
'''
        # CI jobs have independent filesystems. The marketplace job prepares
        # this API environment too; a backend job cannot provide it for us.
        api_python=Path(os.environ.get('SELLERPILOT_API_PYTHON') or
                        ROOT.parent/'backend/.venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python'))
        self.assertTrue(api_python.is_file(),
                        'Missing API Python: prepare backend/.venv or set SELLERPILOT_API_PYTHON.')
        result = subprocess.run([str(api_python), '-c', script, str(DB), str(order_id), json.dumps(changes or {})],
            cwd=ROOT.parent/'backend', capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def setUp(self):
        self.seller=app.test_client()
        response=self.seller.post('/login?next=/seller',data={'login_id':'utech','password':TEST_SELLER_PASSWORD})
        self.assertEqual(response.location,'/seller')
        self.buyer=app.test_client(); self.email='buyer-'+uuid.uuid4().hex[:10]+'@example.test'
        response=self.buyer.post('/register',data={'name':'test_'+uuid.uuid4().hex[:9],'email':self.email,'password':'Test@2026','confirm_password':'Test@2026'})
        self.assertEqual(response.location,'/shop/utech-official')
        with app.app_context():
            self.shop_id=Shop.query.filter_by(slug='utech-official').one().id
            self.buyer_id=User.query.filter_by(email=self.email).one().id
            self.category_id=Product.query.filter_by(shop_id=self.shop_id).first().category_id

    def listing(self,price=100000,stock=12):
        sku='QA-'+uuid.uuid4().hex[:10].upper()
        response=self.seller.post('/seller/products/new',data={'name':'Bàn phím kiểm thử UTech '+sku,'sku':sku,'category_id':self.category_id,'price':price,'stock':stock,'status':'active','image_url':'/static/ute-mall.svg','description':'Sản phẩm kiểm thử trong database tạm.'})
        self.assertEqual(response.status_code,302)
        with app.app_context():
            p=Product.query.filter_by(sku=sku).one(); return p.id,p.variants[0].id,sku

    def add(self,pid,vid=None,client=None):
        response=(client or self.buyer).post('/cart/add/'+str(pid),data={'quantity':1,'variant_id':vid or ''})
        self.assertEqual(response.status_code,302)

    def checkout(self):
        response=self.buyer.post('/checkout',data={'shipping_name':'Khách kiểm thử','shipping_phone':'0901234567','shipping_address':'Địa chỉ kiểm thử, TP. Hồ Chí Minh','payment_method':'COD'})
        self.assertRegex(response.location or '',r'/order/\d+$')
        return int(response.location.rsplit('/',1)[-1])

    def test_auth_validation_and_permissions(self):
        guest=app.test_client()
        self.assertIn('/login?next=',guest.get('/seller').location)
        self.assertEqual(self.buyer.get('/seller').location,'/seller/access')
        self.assertEqual(self.buyer.get('/seller/access').status_code,200)
        response=guest.post('/register',data={'name':'x','email':'bad','password':'x','confirm_password':'no'})
        self.assertEqual(response.status_code,200)
        with app.app_context(): self.assertIsNone(User.query.filter_by(email='bad').first())
        self.assertEqual(self.seller.get('/login?next=https://example.com').location.rstrip('/'),'/seller')
        with app.app_context():
            foreign=Product.query.filter(Product.shop_id!=self.shop_id).first();foreign_id=foreign.id
            # The test owns its foreign-tenant fixture; a fresh demo need not
            # already contain orders from another shop.
            foreign_order=Order(user_id=self.buyer_id,shop_id=foreign.shop_id,total_amount=foreign.price,status='pending')
            db.session.add(foreign_order);db.session.commit();foreign_order_id=foreign_order.id
        self.assertEqual(self.seller.get('/seller/products/'+str(foreign_id)+'/edit').status_code,404)
        self.assertEqual(self.seller.get('/seller/orders/'+str(foreign_order_id)).status_code,404)
        self.assertEqual(self.buyer.post('/seller/products/'+str(foreign_id)+'/visibility').status_code,302)

    def test_catalog_counters_and_sku_prices_match(self):
        with app.app_context():
            for product in Product.query.filter_by(shop_id=self.shop_id,status='active').all():
                active=[v for v in product.variants if v.is_active]
                self.assertTrue(active,product.sku)
                self.assertEqual(product.stock,sum(v.stock for v in active),product.sku)
                self.assertEqual(product.price,min(v.price for v in active),product.sku)
                self.assertEqual(product.rating_count,Review.query.filter_by(product_id=product.id).count(),product.sku)
                fulfilled=sum(item.quantity for item in OrderItem.query.join(Order).filter(OrderItem.product_id==product.id,Order.status=='delivered').all())
                self.assertEqual(product.sold_count,fulfilled,product.sku)

    def test_checkout_multi_shop_totals_and_stock(self):
        pid,vid,_=self.listing(price=200000)
        with app.app_context():
            foreign=Product.query.filter(Product.shop_id!=self.shop_id,Product.stock>2,Product.status=='active').first()
            fvid=next((v.id for v in foreign.variants if v.is_active and v.stock>1),None)
            fid=foreign.id
            self.add(pid,vid);self.add(fid,fvid)
            cart=Cart.query.filter_by(user_id=self.buyer_id).one()
            expected=_compute_totals_from_items(cart.items,'WELCOME10')
        self.buyer.post('/cart/coupon',data={'coupon_code':'WELCOME10'})
        oid=self.checkout()
        with app.app_context():
            order=db.session.get(Order,oid)
            group=Order.query.filter_by(checkout_reference=order.checkout_reference).all()
            self.assertEqual(len(group),2)
            self.assertEqual(sum(o.total_amount for o in group),expected['grand_total'])
            for o in group: self.assertTrue(all(i.product.shop_id==o.shop_id for i in o.items))
            self.assertEqual(db.session.get(Product,pid).stock,11)
            self.assertEqual(db.session.get(ProductVariant,vid).stock,11)
        self.assertEqual(self.buyer.get('/order/'+str(oid)).status_code,200)

    def test_deliver_review_reply_and_return(self):
        pid,vid,sku=self.listing();self.add(pid,vid);oid=self.checkout()
        self.seller.post('/seller/orders/'+str(oid),data={'status':'paid'})
        self.seller.post('/seller/orders/'+str(oid),data={'status':'shipped'})
        self.buyer.post('/order/'+str(oid)+'/received')
        self.buyer.post('/product/'+str(pid)+'/review',data={'rating':5,'comment':'Sản phẩm rất tốt, giao hàng đúng hẹn.'})
        with app.app_context():
            p=db.session.get(Product,pid);self.assertEqual(p.sold_count,1);self.assertEqual(p.rating_count,1);self.assertEqual(p.rating,5)
            review=Review.query.filter_by(product_id=pid,user_id=self.buyer_id).one();rid=review.id
        self.seller.post('/seller/reviews',data={'review_id':rid,'reply':'Cảm ơn bạn đã tin tưởng UTech!'})
        body=self.buyer.get('/product/'+str(pid)).data.decode();self.assertIn('Cảm ơn bạn đã tin tưởng UTech!',body)
        self.buyer.post('/order/'+str(oid)+'/return',data={'reason':'Sản phẩm không tương thích với thiết bị của tôi.'})
        with app.app_context(): ticket=ReturnRequest.query.filter_by(order_id=oid).one();tid=ticket.id
        self.seller.post('/seller/returns',data={'ticket_id':tid,'decision':'approved','seller_note':'Đã kiểm tra và nhận lại hàng.'})
        self.seller.post('/seller/returns',data={'ticket_id':tid,'decision':'approved'})
        with app.app_context():
            self.assertEqual(db.session.get(Order,oid).status,'returned')
            self.assertEqual(db.session.get(Product,pid).stock,12)
            self.assertEqual(db.session.get(Product,pid).sold_count,0)

    def test_app_seller_buyer_share_history_waybill_totals_and_late_payment(self):
        from seller import chart_data
        from app import _mark_order_paid
        pid,vid,_=self.listing();self.add(pid,vid);oid=self.checkout()
        self.seller.post('/seller/orders/'+str(oid),data={'status':'paid'})
        data=self.app_order(oid,{'shipping_carrier':'SPX Express','tracking_number':'VN-SYNC-123'})
        self.assertEqual(data['order']['status'],'paid')
        for client,url in [(self.seller,'/seller/orders/'+str(oid)),(self.buyer,'/order/'+str(oid))]:
            page=client.get(url).data.decode()
            self.assertIn('VN-SYNC-123',page)
            self.assertIn('Cập nhật vận đơn',page)
        shipping={'action':'waybill','shipping_carrier':'GHN','tracking_number':'GHN-SYNC-456',
                  'expected_carrier':'SPX Express','expected_number':'VN-SYNC-123'}
        self.seller.post('/seller/orders/'+str(oid),data=shipping)
        self.assertEqual(self.app_order(oid)['order']['tracking_number'],'GHN-SYNC-456')
        # A stale web form cannot overwrite the waybill saved by another session.
        self.seller.post('/seller/orders/'+str(oid),data={**shipping,'tracking_number':'STALE-999'})
        self.assertEqual(self.app_order(oid)['order']['tracking_number'],'GHN-SYNC-456')
        # App -> seller web; buyer -> app, all on the same SQLite copy.
        self.app_order(oid,{'status':'shipped'})
        self.seller.post('/seller/orders/'+str(oid),data={**shipping,'expected_carrier':'GHN','expected_number':'GHN-SYNC-456','tracking_number':'LATE-999'})
        self.assertEqual(self.app_order(oid)['order']['tracking_number'],'GHN-SYNC-456')
        self.assertIn('Đang giao',self.seller.get('/seller/orders/'+str(oid)).data.decode())
        self.buyer.post('/order/'+str(oid)+'/received')
        result=self.app_order(oid);order=result['order']
        self.assertEqual(order['status'],'delivered')
        self.assertFalse(order['unrecorded_status_change'])
        self.assertEqual([e['to_status'] for e in order['events'] if e['kind']=='status'],['delivered','shipped','paid'])
        with app.app_context():
            saved=db.session.get(Order,oid)
            _mark_order_paid(saved,'repeated-callback')
            self.assertEqual(saved.status,'delivered')
            self.assertEqual(db.session.get(Product,pid).sold_count,1)
            self.assertEqual(db.session.get(Product,pid).stock,11)
            for days in (1,7,30):
                web=chart_data(self.shop_id,days);api=result['stats'][str(days)]
                self.assertEqual(web['orders'],api['order_count'])
                self.assertEqual(web['total'],api['order_value_vnd'])
        self.assertEqual(len(self.app_order(oid)['order']['events']),len(order['events']))

    def test_cancel_is_safe_and_inventory_validation(self):
        pid,vid,_=self.listing(stock=4);self.add(pid,vid);oid=self.checkout()
        for _ in range(2): self.buyer.post('/order/'+str(oid)+'/cancel')
        with app.app_context(): self.assertEqual(db.session.get(Product,pid).stock,4)
        self.seller.post('/seller/inventory',data={'product_id':pid,'stock_'+str(vid):'-5'})
        with app.app_context(): self.assertEqual(db.session.get(Product,pid).stock,4)
        self.seller.post('/seller/inventory',data={'product_id':pid,'stock_'+str(vid):'9'})
        with app.app_context(): self.assertEqual(db.session.get(Product,pid).stock,9)
        self.assertEqual(self.buyer.post('/cart/add/'+str(pid),data={'quantity':'oops'}).status_code,302)

    def test_product_variants_add_and_aggregate(self):
        pid,vid,sku=self.listing()
        response=self.seller.post('/seller/products/'+str(pid)+'/edit',data={'name':'Thiết bị kiểm thử nhiều phiên bản','sku':sku,'category_id':self.category_id,'price':100000,'stock':12,'status':'active','image_url':'/static/ute-mall.svg','standard_variant_title':'128 GB','new_variant_title':'512 GB','new_variant_sku':sku+'-512','new_variant_price':150000,'new_variant_stock':3})
        self.assertEqual(response.status_code,302)
        with app.app_context():
            product=db.session.get(Product,pid)
            self.assertEqual(len(product.variants),2)
            self.assertEqual(product.stock,15)
            self.assertEqual(product.price,100000)
            second=ProductVariant.query.filter_by(sku=sku+'-512').one().id
        self.assertIn('512 GB',self.buyer.get('/product/'+str(pid)).data.decode())
        self.seller.post('/seller/inventory',data={'product_id':pid,'stock_'+str(vid):1,'stock_'+str(second):7})
        with app.app_context(): self.assertEqual(db.session.get(Product,pid).stock,8)

    def test_voucher_scope_expiry_and_quota(self):
        pid,vid,_=self.listing(price=250000);self.add(pid,vid)
        code='QAV'+uuid.uuid4().hex[:7].upper()
        expiry=(datetime.utcnow()+timedelta(days=3)).strftime('%Y-%m-%d')
        self.seller.post('/seller/marketing',data={'code':code,'coupon_type':'fixed','value':50000,'min_subtotal':200000,'max_uses':1,'expires_at':expiry})
        with app.app_context():
            cart=Cart.query.filter_by(user_id=self.buyer_id).one()
            self.assertEqual(_compute_totals_from_items(cart.items,code)['discount'],50000)
            voucher=Coupon.query.filter_by(code=code).one();cid=voucher.id
        self.buyer.post('/cart/coupon',data={'coupon_code':code});self.checkout()
        self.add(pid,vid)
        with app.app_context():
            self.assertIsNone(_compute_totals_from_items(Cart.query.filter_by(user_id=self.buyer_id).one().items,code)['applied_coupon'])
        self.seller.post('/seller/marketing/'+str(cid)+'/toggle')
        with app.app_context(): self.assertFalse(db.session.get(Coupon,cid).is_active)
        self.assertEqual(self.buyer.get('/vouchers').status_code,200)

    def test_inbox_follow_and_profile(self):
        self.buyer.post('/messages?shop=utech-official',data={'body':'Tôi cần tư vấn bàn phím.'})
        with app.app_context(): c=Conversation.query.filter_by(shop_id=self.shop_id,buyer_id=self.buyer_id).one();cid=c.id
        self.seller.post('/seller/inbox?conversation='+str(cid),data={'conversation_id':cid,'body':'UTech hỗ trợ bạn ngay.'})
        self.assertIn('UTech hỗ trợ bạn ngay.',self.buyer.get('/messages?shop=utech-official').data.decode())
        for _ in range(2): self.assertEqual(self.buyer.post('/shop/utech-official/follow').status_code,302)
        response=self.seller.post('/seller/settings',data={'name':'UTech Official','description':'Thông tin giới thiệu được cập nhật','location':'TP. Hồ Chí Minh','contact_email':'utech@example.test','shipping_address':'Kho UTech TP. Hồ Chí Minh'})
        self.assertEqual(response.status_code,302)
        self.assertIn('Thông tin giới thiệu được cập nhật',self.buyer.get('/shop/utech-official').data.decode())

    def test_product_create_edit_hide_validation(self):
        pid,vid,sku=self.listing()
        invalid={'name':'Bàn phím kiểm thử','sku':sku,'category_id':self.category_id,'price':'NaN','stock':10,'image_url':'/static/ute-mall.svg','status':'active'}
        self.assertEqual(self.seller.post('/seller/products/'+str(pid)+'/edit',data=invalid).status_code,200)
        with app.app_context(): self.assertEqual(db.session.get(Product,pid).price,100000)
        invalid['price']=120000
        self.assertEqual(self.seller.post('/seller/products/'+str(pid)+'/edit',data=invalid).status_code,302)
        with app.app_context(): self.assertEqual(db.session.get(ProductVariant,vid).price,120000)
        self.seller.post('/seller/products/'+str(pid)+'/visibility')
        self.assertEqual(self.buyer.get('/product/'+str(pid)).status_code,404)
        self.seller.post('/seller/products/'+str(pid)+'/visibility')
        self.assertEqual(self.buyer.get('/product/'+str(pid)).status_code,200)

    def test_sellerpilot_product_is_visible_on_home_and_shop_by_default(self):
        pid,_vid,sku=self.listing()
        with app.app_context():
            product=db.session.get(Product,pid)
            product.source='sellerpilot'
            product.source_id='sellerpilot-test:'+sku
            product.is_new=True
            product.created_at=datetime.utcnow()+timedelta(seconds=1)
            name=product.name
            db.session.commit()
        home=self.buyer.get('/').data.decode()
        storefront=self.buyer.get('/shop/utech-official').data.decode()
        self.assertIn(name,home)
        self.assertIn(name,storefront)
        self.assertIn('value="newest" selected',storefront)

    def test_navigation_links_and_downloads(self):
        roots=['/seller','/seller/products','/seller/products/new','/seller/orders','/seller/shipping','/seller/returns','/seller/inventory','/seller/marketing','/seller/analytics','/seller/finance','/seller/reviews','/seller/inbox','/seller/settings','/seller/activity']
        links=set()
        for route in roots:
            response=self.seller.get(route);self.assertEqual(response.status_code,200,route)
            parser=Links();parser.feed(response.data.decode());links.update(parser.links)
        checked=0
        for href in sorted(links):
            if href.startswith(('/logout','/static','/payment')): continue
            response=self.seller.get(href)
            self.assertLess(response.status_code,400,href)
            checked+=1
        print('Verified',checked,'seller navigation links')
        for kind in ['products','orders']:
            response=self.seller.get('/seller/export/'+kind)
            self.assertEqual(response.status_code,200);self.assertIn('attachment',response.headers['Content-Disposition'])

    def test_last_unit_cannot_be_sold_twice(self):
        pid,vid,_=self.listing(stock=1)
        self.add(pid,vid)
        other=app.test_client()
        other.post('/register',data={'name':'last_unit_'+uuid.uuid4().hex[:8],'email':'last_'+uuid.uuid4().hex[:8]+'@example.test','password':'Test@2026','confirm_password':'Test@2026'})
        self.add(pid,vid,client=other)
        self.checkout()
        response=other.post('/checkout',data={'shipping_name':'Người mua thứ hai','shipping_phone':'0901234567','shipping_address':'Địa chỉ thử nghiệm','payment_method':'COD'})
        self.assertEqual(response.location,'/cart')
        with app.app_context():
            self.assertEqual(db.session.get(Product,pid).stock,0)
            self.assertEqual(db.session.get(ProductVariant,vid).stock,0)
            self.assertEqual(OrderItem.query.filter_by(product_id=pid).count(),1)

    def test_password_recovery_keeps_token_private(self):
        client=app.test_client()
        app.config['MAIL_OUTBOX_DIR']=str(Path(TEMP.name)/'mailbox')
        response=client.post('/forgot-password',data={'email':self.email},follow_redirects=True)
        with app.app_context(): token=User.query.filter_by(email=self.email).one().reset_token
        self.assertTrue(token)
        self.assertNotIn(token,response.data.decode())
        self.assertEqual(client.get('/reset-password/'+token).status_code,200)
        response=client.post('/reset-password/'+token,data={'password':'Changed@2027','confirm_password':'Changed@2027'})
        self.assertEqual(response.location,'/login')
        with app.app_context(): self.assertIsNone(User.query.filter_by(email=self.email).one().reset_token)
        self.assertEqual(client.get('/reset-password/'+token).location,'/forgot-password')
        self.assertEqual(client.post('/login',data={'login_id':self.email,'password':'Changed@2027'}).location,'/shop/utech-official')

    def test_csrf_guard(self):
        app.config['WTF_CSRF_ENABLED']=True
        try:
            client=app.test_client()
            self.assertEqual(client.post('/login',data={'login_id':'utech','password':TEST_SELLER_PASSWORD}).status_code,400)
            response=client.get('/login?next=/seller')
            token=re.search(r'name="csrf_token" value="([^"]+)"',response.data.decode()).group(1)
            self.assertEqual(client.post('/login?next=/seller',data={'login_id':'utech','password':TEST_SELLER_PASSWORD,'csrf_token':token}).location,'/seller')
        finally: app.config['WTF_CSRF_ENABLED']=False

    def test_bulk_products_are_scoped_and_visible_to_buyers(self):
        first,_,_=self.listing()
        second,_,_=self.listing()
        response=self.seller.post('/seller/products/bulk',data={'product_ids':[first,second],'status':'archived'})
        self.assertEqual(response.status_code,302)
        for pid in [first,second]:
            self.assertEqual(self.buyer.get('/product/'+str(pid)).status_code,404)
        with app.app_context():
            foreign=Product.query.filter(Product.shop_id!=self.shop_id).first().id
        self.assertEqual(self.seller.post('/seller/products/bulk',data={'product_ids':[first,foreign],'status':'active'}).status_code,403)
        with app.app_context(): self.assertEqual(db.session.get(Product,first).status,'archived')
        self.seller.post('/seller/products/bulk',data={'product_ids':[first,second],'status':'active'})
        for pid in [first,second]:
            self.assertEqual(self.buyer.get('/product/'+str(pid)).status_code,200)
        self.seller.post('/seller/products/bulk',data={'product_ids':[first],'status':'invalid'})
        with app.app_context(): self.assertEqual(db.session.get(Product,first).status,'active')

    def test_bulk_orders_roll_back_mixed_states(self):
        pid,vid,_=self.listing()
        self.add(pid,vid);first=self.checkout()
        self.add(pid,vid);second=self.checkout()
        self.seller.post('/seller/orders/'+str(second),data={'status':'paid'})
        self.seller.post('/seller/orders/bulk',data={'order_ids':[second,first],'status':'shipped'})
        with app.app_context():
            self.assertEqual(db.session.get(Order,first).status,'pending')
            self.assertEqual(db.session.get(Order,second).status,'paid')
        self.seller.post('/seller/orders/bulk',data={'order_ids':[first],'status':'paid'})
        self.seller.post('/seller/orders/bulk',data={'order_ids':[first,second],'status':'shipped'})
        with app.app_context():
            self.assertEqual(db.session.get(Order,first).status,'shipped')
            self.assertEqual(db.session.get(Order,second).status,'shipped')

    def test_new_filters_and_vietnam_date_boundary(self):
        pid,vid,sku=self.listing()
        self.add(pid,vid);oid=self.checkout()
        with app.app_context():
            order=db.session.get(Order,oid)
            # 18:30 UTC on October 1 is 01:30 on October 2 in Vietnam.
            order.created_at=datetime(2026,10,1,18,30)
            db.session.commit()
        visible=self.seller.get('/seller/orders?q='+str(oid)+'&date_from=2026-10-02&date_to=2026-10-02').data.decode()
        hidden=self.seller.get('/seller/orders?q='+str(oid)+'&date_from=2026-10-01&date_to=2026-10-01').data.decode()
        self.assertIn('Mã đơn #'+str(oid),visible)
        self.assertNotIn('Mã đơn #'+str(oid),hidden)
        invalid=self.seller.get('/seller/orders?date_from=invalid').data.decode()
        self.assertIn('Khoảng ngày không hợp lệ',invalid)
        self.assertIn(sku,self.seller.get('/seller/products?q='+sku+'&category='+str(self.category_id)+'&sort=stock').data.decode())
        reviews=self.seller.get('/seller/reviews?rating=3&unanswered=1').data.decode()
        ratings=re.findall(r'data-rating="(\d)"',reviews)
        self.assertTrue(ratings)
        self.assertEqual(set(ratings),{'3'})

    def test_charts_exclude_cancelled_future_and_other_shop_orders(self):
        from seller import chart_data
        with app.app_context():
            shop=Shop(name='Stats test',slug='stats-'+uuid.uuid4().hex[:10])
            db.session.add(shop);db.session.flush()
            now=datetime.utcnow()
            for status,amount,created in [('pending',120000,now-timedelta(minutes=1)),('delivered',80000,now-timedelta(minutes=2)),('cancelled',999999,now),('returned',999999,now),('pending',999999,now+timedelta(days=1))]:
                db.session.add(Order(user_id=self.buyer_id,shop_id=shop.id,total_amount=amount,status=status,created_at=created))
            db.session.commit()
            for days in (1,7,30):
                result=chart_data(shop.id,days)
                # At the very start of a VN day, minute-old orders belong to yesterday.
                expected=[o for o in Order.query.filter_by(shop_id=shop.id).all() if o.status not in ('cancelled','returned') and o.created_at<=now and (o.created_at+timedelta(hours=7)).date()>=(now+timedelta(hours=7)).date()-timedelta(days=days-1)]
                self.assertEqual(result['total'],sum(o.total_amount for o in expected))
                self.assertEqual(result['orders'],len(expected))
                self.assertEqual(sum(result['values']),result['total'])
                self.assertEqual(len(result['samples']),24 if days==1 else days)


if __name__=='__main__':
    try: unittest.main(verbosity=2)
    finally: TEMP.cleanup()
