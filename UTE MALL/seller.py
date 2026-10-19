"""Shopee seller centre and connected buyer workflows."""
from datetime import datetime, timedelta
from functools import wraps
import csv
import io
import math
import re
import uuid
from pathlib import Path

from flask import Blueprint, abort, current_app, flash, g, make_response, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, or_, update, delete
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from werkzeug.utils import secure_filename

from extensions import db
from models import (Shop, ShopMember, ShopFollow, Product, ProductVariant, Category,
                    Order, OrderItem, Coupon, Review, Conversation, Message,
                    ReturnRequest, SellerActivity)
from commerce import STATUS_LABELS, change_order_status, approve_return

bp = Blueprint('seller', __name__)
NAV = [
    ('TỔNG QUAN', [('dashboard','space_dashboard','Trang chủ')]),
    ('QUẢN LÝ ĐƠN HÀNG', [('orders','receipt_long','Tất cả đơn hàng'),('shipping','local_shipping','Quản lý vận chuyển'),('returns','assignment_return','Trả hàng / Hoàn tiền')]),
    ('QUẢN LÝ SẢN PHẨM', [('products','inventory_2','Tất cả sản phẩm'),('product_new','add_box','Thêm sản phẩm'),('inventory','warehouse','Quản lý tồn kho')]),
    ('KÊNH MARKETING', [('marketing','campaign','Mã giảm giá của Shop')]),
    ('TÀI CHÍNH & DỮ LIỆU', [('finance','account_balance_wallet','Doanh thu'),('analytics','monitoring','Phân tích bán hàng')]),
    ('QUẢN LÝ SHOP', [('reviews','star','Đánh giá Shop'),('inbox','chat','Tin nhắn'),('settings','storefront','Hồ sơ & Thiết lập Shop'),('activity','history','Nhật ký hoạt động')]),
]


def member_shop():
    if not current_user.is_authenticated: return None
    member=ShopMember.query.filter_by(user_id=current_user.id).first()
    return member.shop if member and member.shop.status=='active' else None


def seller_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        g.seller_shop=member_shop()
        if not g.seller_shop:
            flash('Tài khoản này chưa có quyền quản lý UTech Official. Hãy đăng nhập tài khoản chủ shop.', 'info')
            return redirect(url_for('seller.access'))
        return view(*args, **kwargs)
    return wrapped


@bp.app_context_processor
def context():
    def page_url(n):
        args=request.args.to_dict()
        args.update(request.view_args or {})
        args['page']=n
        return url_for(request.endpoint,**args)
    shop=getattr(g,'seller_shop',None)
    alerts={}
    if shop:
        alerts={
            'orders':Order.query.filter_by(shop_id=shop.id,status='pending').count(),
            'returns':ReturnRequest.query.join(Order).filter(Order.shop_id==shop.id,ReturnRequest.status=='pending').count(),
            'stock':Product.query.filter_by(shop_id=shop.id,status='active').filter(Product.stock<=5).count(),
            'reviews':Review.query.join(Product).filter(Product.shop_id==shop.id,Review.seller_reply.is_(None)).count(),
        }
    return {'seller_shop':shop,'seller_nav':NAV,'seller_alerts':alerts,'status_labels':STATUS_LABELS,'page_url':page_url}


@bp.app_template_filter('vnd')
def vnd(value): return '{:,.0f}₫'.format(float(value or 0)).replace(',','.')


@bp.app_template_filter('vn_time')
def vn_time(value): return (value+timedelta(hours=7)).strftime('%d/%m/%Y %H:%M') if value else '—'


def log(action):
    db.session.add(SellerActivity(shop_id=g.seller_shop.id,user_id=current_user.id,action=action[:500]))


def page(query, per_page=15):
    return query.paginate(page=max(1,request.args.get('page',1,type=int)),per_page=per_page,error_out=False)


def owned_product(product_id):
    return Product.query.filter_by(id=product_id,shop_id=g.seller_shop.id).first_or_404()


def owned_order(order_id):
    return Order.query.filter_by(id=order_id,shop_id=g.seller_shop.id).first_or_404()


def number(raw, name, minimum=0, maximum=1000000000):
    try: value=float(raw)
    except (ValueError,TypeError): raise ValueError(name+' không hợp lệ.')
    if not math.isfinite(value) or value != int(value) or value<minimum or value>maximum:
        raise ValueError(name+' nằm ngoài phạm vi cho phép.')
    return int(value)


def upload_image(field, existing=None):
    file=request.files.get(field)
    if not file or not file.filename: return existing
    ext=Path(secure_filename(file.filename)).suffix.lower()
    if ext not in {'.jpg','.jpeg','.png','.webp'}: raise ValueError('Ảnh phải có định dạng JPG, PNG hoặc WEBP.')
    content=file.read(8*1024*1024+1)
    if len(content)>8*1024*1024: raise ValueError('Ảnh tối đa 8 MB.')
    valid=(content.startswith(b'\xff\xd8\xff') or content.startswith(b'\x89PNG\r\n\x1a\n') or (content.startswith(b'RIFF') and content[8:12]==b'WEBP'))
    if not valid: raise ValueError('Nội dung file không phải ảnh hợp lệ.')
    filename=uuid.uuid4().hex+ext
    Path(current_app.config['UPLOAD_FOLDER'],filename).write_bytes(content)
    return url_for('static',filename='uploads/'+filename)


def safe_image_url(value):
    value=(value or '').strip()
    if not value: return None
    if any(char in value for char in ['\"', "'", '<', '>', '\\', '\n', '\r']):
        raise ValueError('Đường dẫn ảnh chứa ký tự không hợp lệ.')
    if value.startswith(('https://','http://','/static/')): return value[:500]
    raise ValueError('Đường dẫn ảnh phải là HTTPS/HTTP hoặc ảnh đã tải lên.')


@bp.route('/seller/access')
@login_required
def access(): return render_template('seller/access.html')


@bp.route('/seller')
@bp.route('/seller/')
@seller_required
def dashboard():
    shop=g.seller_shop
    start=datetime.utcnow().replace(hour=17,minute=0,second=0,microsecond=0)
    if datetime.utcnow().hour<17: start-=timedelta(days=1)
    orders=Order.query.filter_by(shop_id=shop.id)
    today=orders.filter(Order.created_at>=start,Order.created_at<=datetime.utcnow()).all()
    valid=[o for o in today if o.status not in {'cancelled','returned'}]
    counts=dict(db.session.query(Order.status,func.count(Order.id)).filter(Order.shop_id==shop.id).group_by(Order.status).all())
    low=Product.query.filter(Product.shop_id==shop.id,Product.status=='active',Product.stock<=5).count()
    total_products=Product.query.filter_by(shop_id=shop.id,status='active').count()
    days=request.args.get('days',7,type=int)
    if days not in (1,7,30): days=7
    data=chart_data(shop.id,days)
    drafts=Product.query.filter_by(shop_id=shop.id,status='draft').count()
    return render_template('seller/dashboard.html',title='Tổng quan',today_orders=len(valid),today_revenue=sum(o.total_amount for o in valid),counts=counts,low_stock=low,total_products=total_products,draft_products=drafts,recent_orders=orders.order_by(Order.created_at.desc()).limit(6).all(),chart=data,activity=SellerActivity.query.filter_by(shop_id=shop.id).order_by(SellerActivity.id.desc()).limit(5).all())


@bp.route('/seller/products')
@seller_required
def products():
    query=Product.query.filter_by(shop_id=g.seller_shop.id)
    counts=dict(db.session.query(Product.status,func.count(Product.id)).filter(Product.shop_id==g.seller_shop.id).group_by(Product.status).all())
    counts['all']=sum(counts.values())
    counts['low']=query.filter(Product.stock<=5,Product.status=='active').count()
    q=(request.args.get('q') or '').strip()
    status=request.args.get('status','all')
    if q: query=query.filter(or_(Product.name.ilike('%'+q+'%'),Product.sku.ilike('%'+q+'%')))
    if status=='low': query=query.filter(Product.stock<=5,Product.status=='active')
    elif status in {'active','draft','archived'}: query=query.filter_by(status=status)
    if status not in {'all','low','active','draft','archived'}: status='all'
    category=request.args.get('category',type=int)
    if category: query=query.filter_by(category_id=category)
    sort=request.args.get('sort','newest')
    sort_column={'newest':Product.id.desc(),'stock':Product.stock.asc(),'sold':Product.sold_count.desc(),'price':Product.price.asc()}.get(sort,Product.id.desc())
    categories=Category.query.join(Product).filter(Product.shop_id==g.seller_shop.id).distinct().order_by(Category.display_order).all()
    return render_template('seller/products.html',title='Tất cả sản phẩm',pagination=page(query.order_by(sort_column,Product.id.desc())),q=q,selected=status,counts=counts,categories=categories,selected_category=category,sort=sort)


@bp.route('/seller/products/bulk',methods=['POST'])
@seller_required
def product_bulk():
    ids=set(request.form.getlist('product_ids',type=int))
    status=request.form.get('status')
    if not ids or len(ids)>100 or status not in {'active','archived'}:
        flash('Chọn từ 1 đến 100 sản phẩm và thao tác hợp lệ.','error')
        return redirect(url_for('seller.products'))
    products=Product.query.filter(Product.shop_id==g.seller_shop.id,Product.id.in_(ids)).all()
    if len(products)!=len(ids): abort(403)
    for product in products: product.status=status
    log(('Hiển thị' if status=='active' else 'Ẩn')+' hàng loạt '+str(len(products))+' sản phẩm')
    db.session.commit()
    flash('Đã cập nhật '+str(len(products))+' sản phẩm trên gian hàng.','success')
    return redirect(url_for('seller.products',status=status))


def product_form(product=None):
    categories=Category.query.order_by(Category.display_order).all()
    if request.method=='POST':
        try:
            name=(request.form.get('name') or '').strip()
            if len(name)<5 or len(name)>200: raise ValueError('Tên sản phẩm cần từ 5 đến 200 ký tự.')
            sku=(request.form.get('sku') or '').strip().upper()
            if not re.fullmatch(r'[A-Z0-9_-]{3,100}',sku): raise ValueError('SKU cần 3–100 ký tự gồm chữ, số, dấu gạch ngang hoặc gạch dưới.')
            duplicate=Product.query.filter(Product.sku==sku)
            if product: duplicate=duplicate.filter(Product.id!=product.id)
            if duplicate.first(): raise ValueError('SKU đã được sử dụng.')
            if not product and ProductVariant.query.filter_by(sku=sku).first(): raise ValueError('SKU đã tồn tại trong biến thể.')
            category=db.session.get(Category,request.form.get('category_id',type=int))
            if not category: raise ValueError('Hãy chọn ngành hàng hợp lệ.')
            price=number(request.form.get('price'),'Giá bán',1000)
            stock=number(request.form.get('stock'),'Tồn kho',0,1000000)
            old_price=number(request.form.get('old_price') or 0,'Giá niêm yết')
            if old_price and old_price<=price: raise ValueError('Giá niêm yết phải lớn hơn giá bán.')
            status=request.form.get('status','active')
            if status not in {'active','draft','archived'}: raise ValueError('Trạng thái không hợp lệ.')
            image=upload_image('image_file',safe_image_url(request.form.get('image_url')))
            if not image: raise ValueError('Hãy tải ảnh hoặc nhập URL ảnh sản phẩm.')
            is_new=product is None
            if is_new:
                product=Product(shop_id=g.seller_shop.id,name=name,sku=sku,price=price,stock=stock,category_id=category.id,source='seller_upload',currency='VND',slug='utech-'+uuid.uuid4().hex[:16],rating=0,rating_count=0,sold_count=0)
                db.session.add(product); db.session.flush()
            product.name=name; product.sku=sku; product.price=price; product.stock=stock
            product.category_id=category.id; product.old_price=old_price or None
            product.is_on_sale=bool(old_price); product.status=status; product.image_url=image
            product.description=(request.form.get('description') or '').strip()[:10000]
            product.vendor=(request.form.get('vendor') or '').strip()[:150]
            product.subcategory=(request.form.get('subcategory') or '').strip()[:100]
            product.location=g.seller_shop.location
            if not product.variants:
                product.variants.append(ProductVariant(sku=sku,title=(request.form.get('standard_variant_title') or 'Phiên bản tiêu chuẩn').strip()[:200],price=price,old_price=old_price or None,stock=stock,is_active=True))
            elif len(product.variants)==1:
                variant=product.variants[0]
                other=ProductVariant.query.filter(ProductVariant.sku==sku,ProductVariant.id!=variant.id).first()
                if other: raise ValueError('SKU đã tồn tại trong biến thể.')
                variant.sku=sku; variant.price=price; variant.old_price=old_price or None; variant.stock=stock; variant.is_active=True
                variant.title=(request.form.get('standard_variant_title') or variant.title).strip()[:200]
            else:
                for variant in product.variants:
                    variant.price=number(request.form.get('variant_price_'+str(variant.id),variant.price),'Giá biến thể',1000)
                    variant.stock=number(request.form.get('variant_stock_'+str(variant.id),variant.stock),'Kho biến thể',0,1000000)
                    variant.title=(request.form.get('variant_title_'+str(variant.id)) or variant.title).strip()[:200]
            new_title=(request.form.get('new_variant_title') or '').strip()
            new_sku=(request.form.get('new_variant_sku') or '').strip().upper()
            if new_title or new_sku or request.form.get('new_variant_price') or request.form.get('new_variant_stock'):
                if not 2<=len(new_title)<=200: raise ValueError('Tên phân loại mới cần từ 2 đến 200 ký tự.')
                if not re.fullmatch(r'[A-Z0-9_-]{3,100}',new_sku): raise ValueError('SKU phân loại mới không hợp lệ.')
                if new_sku==sku or ProductVariant.query.filter_by(sku=new_sku).first() or Product.query.filter_by(sku=new_sku).first():
                    raise ValueError('SKU phân loại mới đã được sử dụng.')
                variant_price=number(request.form.get('new_variant_price'),'Giá phân loại mới',1000)
                variant_stock=number(request.form.get('new_variant_stock'),'Kho phân loại mới',0,1000000)
                product.variants.append(ProductVariant(sku=new_sku,title=new_title,price=variant_price,stock=variant_stock,is_active=True))
            active_variants=[v for v in product.variants if v.is_active]
            product.stock=sum(v.stock for v in active_variants)
            product.price=min(v.price for v in active_variants)
            log(('Đăng sản phẩm: ' if is_new else 'Cập nhật sản phẩm: ')+name)
            db.session.commit(); flash('Đã lưu sản phẩm. Thông tin được cập nhật trên gian hàng.','success')
            return redirect(url_for('seller.products'))
        except ValueError as e:
            db.session.rollback(); flash(str(e),'error')
    return render_template('seller/product_form.html',title='Chỉnh sửa sản phẩm' if product else 'Thêm sản phẩm',product=product,categories=categories)


@bp.route('/seller/products/new',methods=['GET','POST'])
@seller_required
def product_new(): return product_form()


@bp.route('/seller/products/<int:product_id>/edit',methods=['GET','POST'])
@seller_required
def product_edit(product_id): return product_form(owned_product(product_id))


@bp.route('/seller/products/<int:product_id>/visibility',methods=['POST'])
@seller_required
def product_visibility(product_id):
    product=owned_product(product_id)
    product.status='archived' if product.status=='active' else 'active'
    log(('Ẩn' if product.status=='archived' else 'Hiển thị')+' sản phẩm: '+product.name)
    db.session.commit(); flash('Đã cập nhật trạng thái sản phẩm.','success')
    return redirect(url_for('seller.products'))


@bp.route('/seller/inventory',methods=['GET','POST'])
@seller_required
def inventory():
    if request.method=='POST':
        product=owned_product(request.form.get('product_id',type=int) or 0)
        try:
            variants=[v for v in product.variants if v.is_active]
            if variants:
                for v in variants: v.stock=number(request.form.get('stock_'+str(v.id)),'Tồn kho',0,1000000)
                product.stock=sum(v.stock for v in variants)
            else: product.stock=number(request.form.get('stock'),'Tồn kho',0,1000000)
            log('Điều chỉnh tồn kho '+(product.sku or str(product.id))+' → '+str(product.stock))
            db.session.commit(); flash('Đã cập nhật tồn kho.','success')
        except ValueError as e: db.session.rollback(); flash(str(e),'error')
        return redirect(url_for('seller.inventory',q=request.args.get('q','')))
    query=Product.query.filter(Product.shop_id==g.seller_shop.id,Product.status!='archived')
    q=(request.args.get('q') or '').strip()
    if q: query=query.filter(or_(Product.name.ilike('%'+q+'%'),Product.sku.ilike('%'+q+'%')))
    if request.args.get('low')=='1': query=query.filter(Product.stock<=5)
    return render_template('seller/inventory.html',title='Quản lý tồn kho',pagination=page(query.order_by(Product.stock,Product.id)),q=q)


@bp.route('/seller/orders')
@seller_required
def orders():
    query=Order.query.filter_by(shop_id=g.seller_shop.id)
    counts=dict(db.session.query(Order.status,func.count(Order.id)).filter(Order.shop_id==g.seller_shop.id).group_by(Order.status).all())
    counts['all']=sum(counts.values())
    selected=request.args.get('status','all')
    if selected in STATUS_LABELS: query=query.filter_by(status=selected)
    else: selected='all'
    q=(request.args.get('q') or '').strip()
    if q:
        query=query.filter(or_(Order.id==int(q) if q.isdigit() else False,Order.shipping_name.ilike('%'+q+'%'),Order.shipping_phone.ilike('%'+q+'%')))
    date_from=request.args.get('date_from','')
    date_to=request.args.get('date_to','')
    try:
        start=datetime.strptime(date_from,'%Y-%m-%d')-timedelta(hours=7) if date_from else None
        end=datetime.strptime(date_to,'%Y-%m-%d')+timedelta(days=1)-timedelta(hours=7) if date_to else None
        if start and end and start>=end: raise ValueError()
        if start: query=query.filter(Order.created_at>=start)
        if end: query=query.filter(Order.created_at<end)
    except ValueError:
        flash('Khoảng ngày không hợp lệ. Hãy chọn ngày bắt đầu trước ngày kết thúc.','error')
        date_from=date_to=''
    return render_template('seller/orders.html',title='Tất cả đơn hàng',pagination=page(query.order_by(Order.created_at.desc())),selected=selected,q=q,counts=counts,date_from=date_from,date_to=date_to)


@bp.route('/seller/orders/<int:order_id>',methods=['GET','POST'])
@seller_required
def order_detail(order_id):
    order=owned_order(order_id)
    if request.method=='POST':
        try:
            change_order_status(order,request.form.get('status'))
            log('Cập nhật đơn #'+str(order.id)+' → '+STATUS_LABELS.get(order.status,order.status))
            db.session.commit(); flash('Đã cập nhật trạng thái đơn hàng.','success')
        except ValueError as e: db.session.rollback(); flash(str(e),'error')
        return redirect(url_for('seller.order_detail',order_id=order.id))
    return render_template('seller/order.html',title='Chi tiết đơn #'+str(order.id),order=order)


@bp.route('/seller/orders/bulk',methods=['POST'])
@seller_required
def order_bulk():
    ids=request.form.getlist('order_ids',type=int)
    status=request.form.get('status')
    if not ids or len(ids)>100: flash('Chọn từ 1 đến 100 đơn hàng.','error'); return redirect(url_for('seller.orders'))
    orders=Order.query.filter(Order.id.in_(ids),Order.shop_id==g.seller_shop.id).all()
    if len(orders)!=len(set(ids)): abort(403)
    try:
        for order in orders: change_order_status(order,status)
        log('Xử lý hàng loạt '+str(len(orders))+' đơn → '+STATUS_LABELS.get(status,str(status)))
        db.session.commit(); flash('Đã cập nhật '+str(len(orders))+' đơn hàng.','success')
    except ValueError as e: db.session.rollback(); flash(str(e),'error')
    return redirect(url_for('seller.orders'))


@bp.route('/seller/orders/<int:order_id>/label')
@seller_required
def order_label(order_id): return render_template('seller/label.html',order=owned_order(order_id),shop=g.seller_shop)


@bp.route('/seller/shipping')
@seller_required
def shipping():
    query=Order.query.filter(Order.shop_id==g.seller_shop.id,Order.status.in_(['paid','shipped']))
    return render_template('seller/shipping.html',title='Quản lý vận chuyển',pagination=page(query.order_by(Order.created_at.desc())))


@bp.route('/seller/returns',methods=['GET','POST'])
@seller_required
def returns():
    if request.method=='POST':
        ticket=ReturnRequest.query.join(Order).filter(ReturnRequest.id==request.form.get('ticket_id',type=int),Order.shop_id==g.seller_shop.id).first_or_404()
        try:
            if ticket.status!='pending': raise ValueError('Yêu cầu đã được xử lý.')
            decision=request.form.get('decision')
            if decision=='approved': approve_return(ticket)
            elif decision=='rejected': ticket.status='rejected'
            else: raise ValueError('Thao tác không hợp lệ.')
            ticket.seller_note=(request.form.get('seller_note') or '').strip()[:1000]
            log('Xử lý hoàn hàng đơn #'+str(ticket.order_id)+' → '+ticket.status)
            db.session.commit(); flash('Đã xử lý yêu cầu hoàn hàng.','success')
        except ValueError as e: db.session.rollback(); flash(str(e),'error')
        return redirect(url_for('seller.returns'))
    query=ReturnRequest.query.join(Order).filter(Order.shop_id==g.seller_shop.id)
    return render_template('seller/returns.html',title='Trả hàng / Hoàn tiền',pagination=page(query.order_by(ReturnRequest.id.desc())))


@bp.route('/seller/marketing',methods=['GET','POST'])
@seller_required
def marketing():
    if request.method=='POST':
        try:
            code=(request.form.get('code') or '').upper().strip()
            if not re.fullmatch(r'[A-Z0-9_-]{3,30}',code): raise ValueError('Mã cần 3–30 ký tự chữ, số hoặc gạch ngang.')
            if Coupon.query.filter_by(code=code).first(): raise ValueError('Mã giảm giá đã tồn tại.')
            kind=request.form.get('coupon_type')
            if kind not in {'percent','fixed','shipping'}: raise ValueError('Loại ưu đãi không hợp lệ.')
            value=number(request.form.get('value'),'Giá trị',1,100 if kind=='percent' else 10000000)
            minimum=number(request.form.get('min_subtotal') or 0,'Đơn tối thiểu')
            uses=number(request.form.get('max_uses') or 100,'Lượt dùng',1,1000000)
            expiry=datetime.strptime(request.form.get('expires_at') or '', '%Y-%m-%d')+timedelta(days=1)-timedelta(hours=7)
            if expiry<=datetime.utcnow(): raise ValueError('Ngày hết hạn phải từ hôm nay trở đi.')
            db.session.add(Coupon(shop_id=g.seller_shop.id,code=code,coupon_type=kind,value=value,min_subtotal=minimum,max_uses=uses,expires_at=expiry,is_active=True))
            log('Tạo mã giảm giá '+code); db.session.commit(); flash('Đã tạo voucher. Người mua có thể dùng trong giỏ hàng của shop.','success')
        except ValueError as e: db.session.rollback(); flash(str(e),'error')
        return redirect(url_for('seller.marketing'))
    coupons=Coupon.query.filter_by(shop_id=g.seller_shop.id).order_by(Coupon.id.desc()).all()
    now=datetime.utcnow()
    def coupon_state(c):
        if c.expires_at and c.expires_at<=now: return 'expired'
        if c.max_uses is not None and c.used_count>=c.max_uses: return 'used'
        return 'active' if c.is_active else 'paused'
    states={c.id:coupon_state(c) for c in coupons}
    counts={state:sum(1 for value in states.values() if value==state) for state in ('active','paused','expired','used')}
    counts['all']=len(coupons)
    selected=request.args.get('status','all')
    if selected not in counts: selected='all'
    visible=[c for c in coupons if selected=='all' or states[c.id]==selected]
    return render_template('seller/marketing.html',title='Mã giảm giá của Shop',coupons=visible,coupon_states=states,counts=counts,selected=selected,used_total=sum(c.used_count for c in coupons),today=(now+timedelta(hours=7)).strftime('%Y-%m-%d'))


@bp.route('/seller/marketing/<int:coupon_id>/toggle',methods=['POST'])
@seller_required
def coupon_toggle(coupon_id):
    coupon=Coupon.query.filter_by(id=coupon_id,shop_id=g.seller_shop.id).first_or_404()
    coupon.is_active=not coupon.is_active; log(('Bật' if coupon.is_active else 'Tắt')+' voucher '+coupon.code)
    db.session.commit(); flash('Đã cập nhật voucher.','success'); return redirect(url_for('seller.marketing'))


def chart_data(shop_id,days):
    now=datetime.utcnow()
    end=now+timedelta(hours=7)
    first=end.date()-timedelta(days=days-1)
    orders=Order.query.filter(Order.shop_id==shop_id,Order.created_at>=datetime.combine(first,datetime.min.time())-timedelta(hours=7),Order.created_at<=now,Order.status.notin_(['cancelled','returned'])).all()
    values={i:0 for i in range(24)} if days==1 else {first+timedelta(days=i):0 for i in range(days)}
    for order in orders:
        local=order.created_at+timedelta(hours=7)
        key=local.hour if days==1 else local.date()
        if key in values: values[key]+=order.total_amount
    maximum=max(values.values()) or 1
    labels=['%02d:00'%h for h in values] if days==1 else [d.strftime('%d/%m') for d in values]
    samples=[{'x':round(90+i*810/max(1,len(values)-1),1),'y':round(210-v/maximum*170,1),'value':v,'label':labels[i]} for i,v in enumerate(values.values())]
    points=' '.join('%s,%s'%(s['x'],s['y']) for s in samples)
    ticks=[{'y':210-i*42.5,'value':maximum*i/4} for i in range(5)]
    return {'days':days,'points':points,'samples':samples,'ticks':ticks,'values':list(values.values()),'labels':labels,'total':sum(values.values()),'orders':len(orders),'average':sum(values.values())/len(orders) if orders else 0}


@bp.route('/seller/analytics')
@seller_required
def analytics():
    days=request.args.get('days',30,type=int)
    if days not in (7,30,90): days=30
    top=db.session.query(Product,func.sum(OrderItem.quantity).label('units'),func.sum(OrderItem.price*OrderItem.quantity).label('revenue')).join(OrderItem).join(Order,Order.id==OrderItem.order_id).filter(Product.shop_id==g.seller_shop.id,Order.status=='delivered',Order.created_at>=datetime.utcnow()-timedelta(days=days)).group_by(Product.id).order_by(func.sum(OrderItem.quantity).desc()).limit(8).all()
    return render_template('seller/analytics.html',title='Phân tích bán hàng',chart=chart_data(g.seller_shop.id,days),top=top)


@bp.route('/seller/finance')
@seller_required
def finance():
    query=Order.query.filter_by(shop_id=g.seller_shop.id)
    delivered=query.filter_by(status='delivered')
    received=db.session.query(func.coalesce(func.sum(Order.total_amount),0)).filter(Order.shop_id==g.seller_shop.id,Order.status=='delivered').scalar()
    pending=db.session.query(func.coalesce(func.sum(Order.total_amount),0)).filter(Order.shop_id==g.seller_shop.id,Order.status.in_(['paid','shipped'])).scalar()
    return render_template('seller/finance.html',title='Doanh thu',received=received,pending=pending,pagination=page(delivered.order_by(Order.created_at.desc())))


@bp.route('/seller/export/<kind>')
@seller_required
def export(kind):
    stream=io.StringIO(); writer=csv.writer(stream)
    def safe(value):
        value=str(value or '')
        return "'"+value if value.startswith(('=','+','-','@')) else value
    if kind=='products':
        writer.writerow(['SKU','Tên sản phẩm','Giá VND','Tồn kho','Trạng thái'])
        for p in Product.query.filter_by(shop_id=g.seller_shop.id).order_by(Product.id): writer.writerow([safe(p.sku),safe(p.name),int(p.price),p.stock,p.status])
    elif kind=='orders':
        writer.writerow(['Mã đơn','Ngày tạo UTC','Trạng thái','Tổng tiền VND','Thanh toán'])
        for order in Order.query.filter_by(shop_id=g.seller_shop.id).order_by(Order.id): writer.writerow([order.id,order.created_at.isoformat(),order.status,int(order.total_amount),order.payment_method])
    else: abort(404)
    response=make_response('\ufeff'+stream.getvalue()); response.headers['Content-Type']='text/csv; charset=utf-8'; response.headers['Content-Disposition']='attachment; filename="utech-'+kind+'.csv"'
    return response


@bp.route('/seller/reviews',methods=['GET','POST'])
@seller_required
def reviews():
    if request.method=='POST':
        review=Review.query.join(Product).filter(Review.id==request.form.get('review_id',type=int),Product.shop_id==g.seller_shop.id).first_or_404()
        reply=(request.form.get('reply') or '').strip()
        if not reply or len(reply)>2000: flash('Phản hồi cần từ 1 đến 2.000 ký tự.','error')
        else:
            review.seller_reply=reply; review.replied_at=datetime.utcnow(); log('Phản hồi đánh giá #'+str(review.id)); db.session.commit(); flash('Đã gửi phản hồi, hiển thị trên trang sản phẩm.','success')
        return redirect(url_for('seller.reviews'))
    query=Review.query.join(Product).filter(Product.shop_id==g.seller_shop.id)
    counts=dict(db.session.query(Review.rating,func.count(Review.id)).join(Product).filter(Product.shop_id==g.seller_shop.id).group_by(Review.rating).all())
    total=sum(counts.values())
    unanswered=query.filter(Review.seller_reply.is_(None)).count()
    if request.args.get('unanswered')=='1': query=query.filter(Review.seller_reply.is_(None))
    rating=request.args.get('rating',0,type=int)
    if rating in range(1,6): query=query.filter(Review.rating==rating)
    else: rating=0
    return render_template('seller/reviews.html',title='Đánh giá Shop',pagination=page(query.order_by(Review.created_at.desc())),rating=rating,rating_counts=counts,review_total=total,unanswered=unanswered)


@bp.route('/seller/inbox',methods=['GET','POST'])
@seller_required
def inbox():
    query=Conversation.query.filter_by(shop_id=g.seller_shop.id)
    conversation_id=request.args.get('conversation',type=int) or request.form.get('conversation_id',type=int)
    conversation=query.filter_by(id=conversation_id).first_or_404() if conversation_id else query.order_by(Conversation.updated_at.desc()).first()
    if request.method=='POST':
        body=(request.form.get('body') or '').strip()
        if conversation and 0<len(body)<=4000:
            db.session.add(Message(conversation_id=conversation.id,sender_id=current_user.id,from_seller=True,body=body)); conversation.updated_at=datetime.utcnow(); db.session.commit(); flash('Đã gửi tin nhắn.','success')
        else: flash('Tin nhắn cần từ 1 đến 4.000 ký tự.','error')
        return redirect(url_for('seller.inbox',conversation=conversation.id if conversation else None))
    return render_template('seller/inbox.html',title='Tin nhắn',conversations=query.order_by(Conversation.updated_at.desc()).limit(100).all(),conversation=conversation)


@bp.route('/seller/settings',methods=['GET','POST'])
@seller_required
def settings():
    shop=g.seller_shop
    if request.method=='POST':
        try:
            name=(request.form.get('name') or '').strip()
            if not 3<=len(name)<=150: raise ValueError('Tên shop cần từ 3 đến 150 ký tự.')
            shop.name=name; shop.description=(request.form.get('description') or '').strip()[:2000]
            shop.location=(request.form.get('location') or '').strip()[:120]
            shop.shipping_address=(request.form.get('shipping_address') or '').strip()[:500]
            shop.phone=(request.form.get('phone') or '').strip()[:30]
            shop.contact_email=(request.form.get('contact_email') or '').strip()[:180]
            if shop.contact_email and not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+',shop.contact_email): raise ValueError('Email shop không hợp lệ.')
            shop.logo_url=upload_image('logo_file',safe_image_url(request.form.get('logo_url')))
            shop.cover_url=upload_image('cover_file',safe_image_url(request.form.get('cover_url')))
            shop.vacation_mode=bool(request.form.get('vacation_mode'))
            log('Cập nhật hồ sơ và thiết lập shop'); db.session.commit(); flash('Đã lưu hồ sơ shop.','success')
        except ValueError as e: db.session.rollback(); flash(str(e),'error')
        return redirect(url_for('seller.settings'))
    return render_template('seller/settings.html',title='Hồ sơ & Thiết lập Shop')


@bp.route('/seller/activity')
@seller_required
def activity(): return render_template('seller/activity.html',title='Nhật ký hoạt động',pagination=page(SellerActivity.query.filter_by(shop_id=g.seller_shop.id).order_by(SellerActivity.id.desc()),25))


@bp.route('/vouchers')
def vouchers():
    coupons=Coupon.query.filter(Coupon.is_active==True,or_(Coupon.expires_at.is_(None),Coupon.expires_at>datetime.utcnow())).order_by(Coupon.id.desc()).all()
    return render_template('vouchers.html',coupons=coupons)


@bp.route('/shop/<slug>/follow',methods=['POST'])
@login_required
def follow(slug):
    shop=Shop.query.filter_by(slug=slug,status='active').first_or_404()
    row=ShopFollow.query.filter_by(shop_id=shop.id,user_id=current_user.id).first()
    action=request.form.get('action') or ('unfollow' if row else 'follow')
    if action=='follow':
        result=db.session.execute(sqlite_insert(ShopFollow).values(shop_id=shop.id,user_id=current_user.id).on_conflict_do_nothing(index_elements=['shop_id','user_id']))
        if result.rowcount: db.session.execute(update(Shop).where(Shop.id==shop.id).values(follower_count=Shop.follower_count+1))
        flash('Đã theo dõi shop.','success')
    elif action=='unfollow':
        result=db.session.execute(delete(ShopFollow).where(ShopFollow.shop_id==shop.id,ShopFollow.user_id==current_user.id))
        if result.rowcount: db.session.execute(update(Shop).where(Shop.id==shop.id).values(follower_count=func.max(0,Shop.follower_count-1)))
        flash('Đã bỏ theo dõi shop.','info')
    else: abort(400)
    db.session.commit(); return redirect(url_for('shop_page',slug=slug))



@bp.route('/messages',methods=['GET','POST'])
@login_required
def messages():
    shop_slug=request.args.get('shop','utech-official')
    shop=Shop.query.filter_by(slug=shop_slug,status='active').first_or_404()
    conversation=Conversation.query.filter_by(shop_id=shop.id,buyer_id=current_user.id).first()
    if request.method=='POST':
        body=(request.form.get('body') or '').strip()
        if 0<len(body)<=4000:
            if not conversation:
                conversation=Conversation(shop_id=shop.id,buyer_id=current_user.id); db.session.add(conversation); db.session.flush()
            db.session.add(Message(conversation_id=conversation.id,sender_id=current_user.id,from_seller=False,body=body)); conversation.updated_at=datetime.utcnow(); db.session.commit(); flash('Đã gửi tin nhắn tới shop.','success')
        else: flash('Tin nhắn cần từ 1 đến 4.000 ký tự.','error')
        return redirect(url_for('seller.messages',shop=shop.slug))
    return render_template('messages.html',chat_shop=shop,conversation=conversation)


@bp.route('/order/<int:order_id>/cancel',methods=['POST'])
@login_required
def buyer_cancel(order_id):
    order=Order.query.filter_by(id=order_id,user_id=current_user.id).first_or_404()
    try:
        if order.status not in {'pending','paid'}: raise ValueError('Đơn đã bàn giao vận chuyển nên không thể hủy.')
        change_order_status(order,'cancelled'); db.session.commit(); flash('Đã hủy đơn và hoàn lại tồn kho.','success')
    except ValueError as e: db.session.rollback(); flash(str(e),'error')
    return redirect(url_for('order_detail',order_id=order.id))


@bp.route('/order/<int:order_id>/received',methods=['POST'])
@login_required
def received(order_id):
    order=Order.query.filter_by(id=order_id,user_id=current_user.id).first_or_404()
    try:
        change_order_status(order,'delivered'); db.session.commit(); flash('Đã xác nhận nhận hàng. Bạn có thể đánh giá sản phẩm.','success')
    except ValueError as e: db.session.rollback(); flash(str(e),'error')
    return redirect(url_for('order_detail',order_id=order.id))


@bp.route('/order/<int:order_id>/return',methods=['POST'])
@login_required
def buyer_return(order_id):
    order=Order.query.filter_by(id=order_id,user_id=current_user.id).first_or_404()
    reason=(request.form.get('reason') or '').strip()
    if order.status!='delivered': flash('Chỉ yêu cầu hoàn hàng sau khi đã nhận hàng.','error')
    elif order.return_request: flash('Đơn hàng đã có yêu cầu hoàn hàng.','info')
    elif not 10<=len(reason)<=2000: flash('Lý do cần từ 10 đến 2.000 ký tự.','error')
    else:
        db.session.add(ReturnRequest(order_id=order.id,reason=reason)); db.session.commit(); flash('Đã gửi yêu cầu hoàn hàng tới shop.','success')
    return redirect(url_for('order_detail',order_id=order.id))


@bp.route('/following')
@login_required
def following():
    shops=Shop.query.join(ShopFollow,ShopFollow.shop_id==Shop.id).filter(ShopFollow.user_id==current_user.id,Shop.status=='active').order_by(Shop.name).all()
    return render_template('following.html',shops=shops)


@bp.after_request
def protect_seller_responses(response):
    if request.path.startswith('/seller'):
        response.headers['Cache-Control']='no-store'
    return response
