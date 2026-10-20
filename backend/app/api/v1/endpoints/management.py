from typing import Literal

from fastapi import APIRouter, Depends, Query, HTTPException

from app.api.v1.endpoints.seller_tools import get_shop, shop_error
from app.integrations import management
from app.integrations.ute_mall import ShopDatabaseError, UTEMallRepository
from app.integrations.ute_mall import ShopItemNotFoundError
from app.integrations.order_management import order_detail, update_order, OrderConflictError
from app.schemas.order_management import OrderUpdate

router = APIRouter(prefix="/management", tags=["mobile management"])


@router.get("/dashboard")
def dashboard(days: int = Query(7), shop: UTEMallRepository = Depends(get_shop)):
    if days not in (1, 7, 30):
        raise HTTPException(422, detail="Chọn khoảng 1, 7 hoặc 30 ngày.")
    try:
        return {"data": management.dashboard(shop, days)}
    except ShopDatabaseError as error:
        raise shop_error(error) from error


@router.get("/products")
def products(q: str = Query("", max_length=200), low: bool = False,
             limit: int = Query(20, ge=1, le=50), offset: int = Query(0, ge=0),
             shop: UTEMallRepository = Depends(get_shop)):
    try:
        return {"data": management.products(shop, q.strip(), limit, offset, low)}
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
