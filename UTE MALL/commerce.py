"""Shared marketplace rules: tenant ownership, counters and order lifecycle."""
from datetime import datetime
from sqlalchemy import func, update
from extensions import db
from models import Order, OrderItem, Product, Review, Shop, ProductVariant, ReturnRequest

STATUS_LABELS = {'pending':'Chờ xác nhận','paid':'Chờ lấy hàng','shipped':'Đang giao','delivered':'Đã giao','cancelled':'Đã hủy','returned':'Đã hoàn hàng'}
TRANSITIONS = {'pending': {'paid','cancelled'}, 'paid': {'shipped','cancelled'}, 'shipped': {'delivered'}, 'delivered': set(), 'cancelled': set(), 'returned': set()}


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
