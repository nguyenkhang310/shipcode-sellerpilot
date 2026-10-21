"""Shared marketplace rules: tenant ownership, counters and order lifecycle."""
from datetime import datetime
import json
import re
from pathlib import Path
from uuid import uuid4
from sqlalchemy import func, update, text
from extensions import db
from models import Order, OrderItem, Product, Review, Shop, ProductVariant, ReturnRequest

STATUS_LABELS = {'pending':'Chờ xác nhận','paid':'Chờ lấy hàng','shipped':'Đang giao','delivered':'Đã giao','cancelled':'Đã hủy','returned':'Đã hoàn hàng'}
TRANSITIONS = {'pending': {'paid','cancelled'}, 'paid': {'shipped','cancelled'}, 'shipped': {'delivered'}, 'delivered': set(), 'cancelled': set(), 'returned': set()}
SHIPPING_CARRIERS = json.loads((Path(__file__).resolve().parents[1] / 'backend/app/integrations/shipping_carriers.json').read_text(encoding='utf-8'))


def order_tracking(order):
    """Seller and buyer pages read the app's same committed journal/waybill."""
    slug = order.seller_shop.slug if order.seller_shop else 'local'
    params = {'slug': slug, 'id': order.id}
    tables = set(db.session.execute(text("SELECT name FROM sqlite_master WHERE type='table'")).scalars())
    events, shipping = [], None
    if 'sellerpilot_order_event' in tables:
        for row in db.session.execute(text('SELECT * FROM sellerpilot_order_event WHERE shop_slug=:slug AND order_id=:id ORDER BY id DESC'), params).mappings():
            initial = row['operation_id'].startswith('initial:')
            status = row['from_status'] != row['to_status']
            fields = json.loads(row['changed_fields'])
            title = (STATUS_LABELS.get(row['to_status'], row['to_status']) + ' · ghi nhận ban đầu' if initial else
                     STATUS_LABELS.get(row['to_status'], row['to_status']) if status else
                     'Cập nhật vận đơn' if set(fields) & {'shipping_carrier', 'tracking_number'} else
                     'Cập nhật ghi chú' if fields == ['note'] else 'Cập nhật thông tin nhận hàng')
            events.append({'title': title, 'created_at': row['created_at'], 'status': row['to_status'] if initial or status else None,
                           'detail': 'Thời điểm ghi nhận trạng thái ban đầu của đơn.' if initial else ''})
    if 'sellerpilot_order_shipping' in tables:
        shipping = db.session.execute(text('SELECT carrier,tracking_number FROM sellerpilot_order_shipping WHERE shop_slug=:slug AND order_id=:id'), params).mappings().first()
    last = next((event['status'] for event in events if event['status']), 'pending')
    if last != order.status:
        events.insert(0, {'title': STATUS_LABELS.get(order.status, order.status), 'created_at': None,
                         'detail': 'Trạng thái hiện tại. Chưa có thời điểm cập nhật.'})
    events.append({'title': 'Đơn được tạo', 'created_at': order.created_at, 'detail': ''})
    return {'events': events, 'shipping': shipping, 'carriers': SHIPPING_CARRIERS}


def update_order_waybill(order, carrier, number, expected_carrier, expected_number):
    """Compare original waybill and phase in the same SQLite write transaction."""
    carrier, number = carrier.strip(), number.strip()
    if len(carrier) > 80 or any(ord(char) < 32 for char in carrier):
        raise ValueError('Tên đơn vị vận chuyển không hợp lệ.')
    if bool(carrier) != bool(number) or number and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/-]{2,79}', number):
        raise ValueError('Nhập đơn vị vận chuyển và mã vận đơn hợp lệ (3–80 ký tự).')
    # Acquire the write lock before reading the previous waybill. A no-op
    # guarded UPDATE checks phase but does not append a status event.
    claimed = db.session.execute(update(Order).where(Order.id == order.id, Order.status.in_(['pending', 'paid'])).values(status=Order.status))
    if claimed.rowcount != 1:
        raise ValueError('Chỉ sửa vận đơn trước khi bàn giao. Tải lại chi tiết đơn để tiếp tục.')
    slug = order.seller_shop.slug if order.seller_shop else 'local'
    params = {'slug': slug, 'id': order.id}
    previous = db.session.execute(text('SELECT carrier,tracking_number FROM sellerpilot_order_shipping WHERE shop_slug=:slug AND order_id=:id'), params).mappings().first()
    current = (previous['carrier'], previous['tracking_number']) if previous else ('', '')
    if current != (expected_carrier, expected_number):
        raise ValueError('Vận đơn vừa được cập nhật ở phiên khác. Tải lại trang trước khi lưu.')
    if current == (carrier, number): return False
    params.update(carrier=carrier, number=number, now=datetime.utcnow().isoformat(), operation=str(uuid4()))
    db.session.execute(text('''INSERT INTO sellerpilot_order_shipping VALUES(:slug,:id,:carrier,:number,:now)
        ON CONFLICT(shop_slug,order_id) DO UPDATE SET carrier=excluded.carrier,tracking_number=excluded.tracking_number,updated_at=excluded.updated_at'''), params)
    db.session.execute(text('''INSERT INTO sellerpilot_order_event(operation_id,shop_slug,order_id,from_status,to_status,changed_fields,created_at)
        SELECT :operation,:slug,:id,status,status,'["shipping_carrier","tracking_number"]',:now FROM "order" WHERE id=:id'''), params)
    return True


def refresh_product(product):
    """Public numbers use persisted reviews and fulfilled order quantities."""
    count, average = db.session.query(func.count(Review.id), func.avg(Review.rating)).filter(Review.product_id == product.id).one()
    product.rating_count, product.rating = count, round(float(average or 0), 1)
    fulfilled=int(db.session.query(func.coalesce(func.sum(OrderItem.quantity), 0)).join(Order).filter(OrderItem.product_id == product.id, Order.status == 'delivered').scalar())
    baseline=0 if product.seller_shop and product.seller_shop.is_sellerpilot else int(product.historical_sold_count or 0)
    product.sold_count=baseline+fulfilled


def refresh_shop(shop_id):
    shop = db.session.get(Shop, shop_id)
    average = db.session.query(func.avg(Review.rating)).join(Product).filter(Product.shop_id == shop_id).scalar()
    if shop: shop.rating = round(float(average or 0), 1)


def change_order_status(order, new_status):
    if new_status == order.status: return False
    if new_status not in TRANSITIONS.get(order.status, set()):
        raise ValueError('Không thể chuyển trạng thái đơn từ %s sang %s.' % (STATUS_LABELS.get(order.status,order.status), STATUS_LABELS.get(new_status,new_status)))
    claimed=db.session.execute(update(Order).where(Order.id==order.id,Order.status==order.status).values(status=new_status))
    if claimed.rowcount!=1:
        raise ValueError('Trạng thái đơn vừa thay đổi. Hãy tải lại trang trước khi xử lý.')
    if new_status == 'cancelled':
        for item in order.items:
            if item.product: db.session.execute(update(Product).where(Product.id==item.product_id).values(stock=Product.stock+item.quantity))
            if item.variant: db.session.execute(update(ProductVariant).where(ProductVariant.id==item.variant_id).values(stock=ProductVariant.stock+item.quantity))
        order.payment_status = 'cancelled'
    if new_status == 'delivered': order.payment_status = 'paid'
    order.status = new_status
    db.session.flush()
    for item in order.items:
        if item.product: refresh_product(item.product)
    return True


def approve_return(ticket):
    if ticket.status != 'pending': raise ValueError('Yêu cầu này đã được xử lý.')
    if ticket.order.status != 'delivered': raise ValueError('Chỉ hoàn hàng cho đơn đã giao.')
    claimed=db.session.execute(update(ReturnRequest).where(ReturnRequest.id==ticket.id,ReturnRequest.status=='pending').values(status='approved'))
    if claimed.rowcount!=1: raise ValueError('Yêu cầu hoàn hàng đã được xử lý.')
    claimed_order=db.session.execute(update(Order).where(Order.id==ticket.order_id,Order.status=='delivered').values(status='returned'))
    if claimed_order.rowcount!=1: raise ValueError('Trạng thái đơn vừa thay đổi. Vui lòng tải lại.')
    for item in ticket.order.items:
        if item.product: db.session.execute(update(Product).where(Product.id==item.product_id).values(stock=Product.stock+item.quantity))
        if item.variant: db.session.execute(update(ProductVariant).where(ProductVariant.id==item.variant_id).values(stock=ProductVariant.stock+item.quantity))
    ticket.order.payment_status = 'refunded'
    db.session.flush()
    for item in ticket.order.items:
        if item.product: refresh_product(item.product)
