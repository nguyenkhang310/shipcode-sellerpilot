from typing import Literal
from datetime import date as CalendarDate, datetime

from fastapi import APIRouter, Depends, Query, HTTPException

from app.api.v1.endpoints.seller_tools import get_shop, shop_error
from app.integrations import management
from app.integrations.ute_mall import ShopDatabaseError, UTEMallRepository
from app.integrations.ute_mall import ShopItemNotFoundError
from app.integrations.order_management import order_detail, update_order, OrderConflictError
from app.schemas.order_management import OrderUpdate
from app.integrations.product_management import product_detail, update_product, ProductConflictError
from app.schemas.product_management import ProductUpdate

router = APIRouter(prefix="/management", tags=["mobile management"])


@router.get("/dashboard")
def dashboard(days: int | None = Query(None), date: CalendarDate | None = Query(None), shop: UTEMallRepository = Depends(get_shop)):
    if date and (date.year < 1970 or date > datetime.now(shop.timezone).date() or days not in (None, 1)):
        raise HTTPException(422, detail="Chọn một ngày từ năm 1970 đến hôm nay; ngày cụ thể chỉ dùng kỳ 1 ngày.")
    days = days if days is not None else 1 if date else 7
    if days not in (1, 7, 30):
        raise HTTPException(422, detail="Chọn khoảng 1, 7 hoặc 30 ngày.")
    try:
        return {"data": management.dashboard(shop, days, date)}
    except ShopDatabaseError as error:
        raise shop_error(error) from error


@router.get("/products")
def products(q: str = Query("", max_length=200), low: bool = False,
             limit: int = Query(20, ge=1, le=50), offset: int = Query(0, ge=0),
             sort: Literal['newest', 'bestselling'] = 'bestselling',
             shop: UTEMallRepository = Depends(get_shop)):
    try:
        return {"data": management.products(shop, q.strip(), limit, offset, low, sort=sort)}
    except ShopDatabaseError as error:
        raise shop_error(error) from error


@router.get("/orders")
def orders(status: Literal["all", "pending", "paid", "shipped", "delivered", "cancelled", "returned"] = "all",
           q: str = Query("", max_length=200), limit: int = Query(20, ge=1, le=50),
           offset: int = Query(0, ge=0), shop: UTEMallRepository = Depends(get_shop)):
    try:
        return {"data": management.orders(shop, status, q.strip(), limit, offset)}
    except ShopDatabaseError as error:
        raise shop_error(error) from error


@router.get('/products/{product_id}')
def get_product(product_id: int, shop: UTEMallRepository = Depends(get_shop)):
    try:
        return {'data': product_detail(shop, product_id)}
    except ShopItemNotFoundError as error:
        raise HTTPException(404, detail='Không tìm thấy sản phẩm trong shop đang liên kết.') from error
    except ShopDatabaseError as error:
        raise shop_error(error) from error


@router.patch('/products/{product_id}')
def patch_product(product_id: int, payload: ProductUpdate, shop: UTEMallRepository = Depends(get_shop)):
    try:
        return {'data': update_product(shop, product_id, payload)}
    except ShopItemNotFoundError as error:
        raise HTTPException(404, detail='Không tìm thấy sản phẩm trong shop đang liên kết.') from error
    except ProductConflictError as error:
        raise HTTPException(409, detail=str(error)) from error
    except ShopDatabaseError as error:
        raise shop_error(error) from error


@router.get('/orders/{order_id}')
def get_order(order_id: int, shop: UTEMallRepository = Depends(get_shop)):
    try:
        return {'data': order_detail(shop, order_id)}
    except ShopItemNotFoundError as error:
        raise HTTPException(404, detail='Không tìm thấy đơn hàng trong shop đang liên kết.') from error
    except ShopDatabaseError as error:
        raise shop_error(error) from error


@router.patch('/orders/{order_id}')
def patch_order(order_id: int, payload: OrderUpdate, shop: UTEMallRepository = Depends(get_shop)):
    try:
        return {'data': update_order(shop, order_id, payload)}
    except ShopItemNotFoundError as error:
        raise HTTPException(404, detail='Không tìm thấy đơn hàng trong shop đang liên kết.') from error
    except OrderConflictError as error:
        raise HTTPException(409, detail=str(error)) from error
    except ShopDatabaseError as error:
        raise shop_error(error) from error
