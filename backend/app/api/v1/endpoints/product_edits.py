from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.v1.endpoints.seller_tools import get_shop, shop_error
from app.db.session import get_session
from app.integrations.ute_mall import UTEMallRepository, ShopDatabaseError, ShopItemNotFoundError
from app.schemas.product_edits import ProductEditRequest, ProductEditResponse
from app.services.product_edits import create_product_edit, decide_product_edit, edit_to_dict
from app.services.seller_tools import ProposalConflictError, ProposalNotFoundError

router=APIRouter(prefix='/product-edits',tags=['product edits'])


@router.post('',response_model=ProductEditResponse,status_code=201)
def propose_edit(payload:ProductEditRequest,session:Session=Depends(get_session),shop:UTEMallRepository=Depends(get_shop)):
    try:
        return ProductEditResponse(data=edit_to_dict(create_product_edit(session,shop,sku=payload.sku,changes=payload.changes)))
    except ProposalConflictError as error:
        raise HTTPException(409,detail={'code':'product_edit_conflict','message':str(error)}) from error
    except (ShopDatabaseError,ShopItemNotFoundError) as error:
        raise shop_error(error) from error


def decide(proposal_id,approve,session,shop):
    try:
        proposal,repeated=decide_product_edit(session,shop,proposal_id,approve=approve)
        return ProductEditResponse(data=edit_to_dict(proposal,idempotent=repeated))
    except ProposalNotFoundError as error:
        raise HTTPException(404,detail={'code':'product_edit_not_found'}) from error
    except ProposalConflictError as error:
        raise HTTPException(409,detail={'code':'product_edit_conflict','message':str(error)}) from error
    except (ShopDatabaseError,ShopItemNotFoundError) as error:
        raise shop_error(error) from error


@router.post('/{proposal_id}/confirm',response_model=ProductEditResponse)
def confirm(proposal_id:int,session:Session=Depends(get_session),shop:UTEMallRepository=Depends(get_shop)):
    return decide(proposal_id,True,session,shop)


@router.post('/{proposal_id}/reject',response_model=ProductEditResponse)
def reject(proposal_id:int,session:Session=Depends(get_session),shop:UTEMallRepository=Depends(get_shop)):
    return decide(proposal_id,False,session,shop)
