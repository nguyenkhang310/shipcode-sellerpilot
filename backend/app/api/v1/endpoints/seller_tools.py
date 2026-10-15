from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.integrations.ute_mall import (
    ShopDatabaseError,
    ShopItemNotFoundError,
    UTEMallRepository,
)
from app.schemas.seller_tools import (
    InventoryResponse,
    LowStockResponse,
    PriceChangeRequest,
    ProposalResponse,
    ShopSummaryResponse,
)
from app.services.seller_tools import (
    PriceUnchangedError,
    ProposalConflictError,
    ProposalNotFoundError,
    confirm_price_proposal,
    create_price_proposal,
    proposal_to_dict,
    reject_price_proposal,
)

router = APIRouter(tags=["seller tools"])


def get_shop(request: Request) -> UTEMallRepository:
    return request.app.state.shop_repository


def shop_error(error: Exception) -> HTTPException:
    if isinstance(error, ShopItemNotFoundError):
        return HTTPException(status_code=404, detail={"code": "sku_not_found", "message": "Không tìm thấy SKU"})
    return HTTPException(status_code=503, detail={"code": "shop_database_unavailable", "message": "Không đọc được database UTE MALL"})


@router.get("/shop/summary", response_model=ShopSummaryResponse)
def get_shop_summary(
    shop: UTEMallRepository = Depends(get_shop),
    day: date | None = Query(default=None, alias="date"),
) -> ShopSummaryResponse:
    local_day = day or datetime.now(shop.timezone).date()
    try:
        return ShopSummaryResponse(data=shop.summary(local_day))
    except ShopDatabaseError as error:
        raise shop_error(error) from error


@router.get("/inventory/low-stock", response_model=LowStockResponse)
def get_low_stock(
    threshold: int = Query(default=5, ge=0, le=10_000),
    limit: int = Query(default=50, ge=1, le=200),
    shop: UTEMallRepository = Depends(get_shop),
) -> LowStockResponse:
    try:
        items = shop.low_stock(threshold, limit)
        return LowStockResponse(data={"threshold": threshold, "count": len(items), "items": items})
    except ShopDatabaseError as error:
        raise shop_error(error) from error


@router.get("/inventory/{sku}", response_model=InventoryResponse)
def get_inventory(sku: str, shop: UTEMallRepository = Depends(get_shop)) -> InventoryResponse:
    try:
        return InventoryResponse(data=shop.get_item_by_sku(sku))
    except (ShopItemNotFoundError, ShopDatabaseError) as error:
        raise shop_error(error) from error


@router.post("/proposals/price-change", response_model=ProposalResponse, status_code=201)
def propose_price_change(
    payload: PriceChangeRequest,
    session: Session = Depends(get_session),
    shop: UTEMallRepository = Depends(get_shop),
) -> ProposalResponse:
    try:
        proposal = create_price_proposal(
            session, shop, sku=payload.sku, new_price_vnd=payload.new_price_vnd
        )
        return ProposalResponse(data=proposal_to_dict(proposal))
    except (ShopItemNotFoundError, ShopDatabaseError) as error:
        raise shop_error(error) from error
    except PriceUnchangedError as error:
        raise HTTPException(
            status_code=409,
            detail={"code": "price_unchanged", "message": "Giá mới trùng với giá hiện tại"},
        ) from error


@router.post("/proposals/{proposal_id}/confirm", response_model=ProposalResponse)
def confirm_proposal(
    proposal_id: int,
    session: Session = Depends(get_session),
    shop: UTEMallRepository = Depends(get_shop),
) -> ProposalResponse:
    try:
        proposal, idempotent = confirm_price_proposal(session, shop, proposal_id)
        return ProposalResponse(data=proposal_to_dict(proposal, idempotent=idempotent))
    except ProposalNotFoundError as error:
        raise HTTPException(status_code=404, detail={"code": "proposal_not_found"}) from error
    except ProposalConflictError as error:
        raise HTTPException(status_code=409, detail={"code": "proposal_conflict", "message": str(error)}) from error
    except (ShopItemNotFoundError, ShopDatabaseError) as error:
        raise shop_error(error) from error


@router.post("/proposals/{proposal_id}/reject", response_model=ProposalResponse)
def reject_proposal(
    proposal_id: int,
    session: Session = Depends(get_session),
) -> ProposalResponse:
    try:
        proposal, idempotent = reject_price_proposal(session, proposal_id)
        return ProposalResponse(data=proposal_to_dict(proposal, idempotent=idempotent))
    except ProposalNotFoundError as error:
        raise HTTPException(status_code=404, detail={"code": "proposal_not_found"}) from error
    except ProposalConflictError as error:
        raise HTTPException(status_code=409, detail={"code": "proposal_conflict", "message": str(error)}) from error
