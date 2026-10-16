import base64
import binascii
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.v1.endpoints.seller_tools import get_shop, shop_error
from app.db.session import get_session
from app.integrations.ute_mall import ShopDatabaseError, UTEMallRepository
from app.schemas.chat import ChatResponse
from app.schemas.product_drafts import (
    ProductDraftResponse,
    ProductImageDataRequest,
    ProductImagesDataRequest,
)
from app.services.product_drafts import (
    MAX_IMAGE_BYTES,
    ProductDraftConflictError,
    ProductDraftError,
    ProductDraftNotFoundError,
    cancel_product_draft,
    create_product_draft,
    create_product_draft_images,
    draft_to_dict,
    draft_stored_images,
    get_product_draft,
    publish_product_draft,
)

router = APIRouter(prefix="/product-drafts", tags=["product publishing"])


def _not_found(error):
    return HTTPException(404, detail={"code": "product_draft_not_found", "message": "Không tìm thấy bản nháp sản phẩm."})


@router.post("", response_model=ChatResponse, status_code=201)
async def upload_product_image(
    request: Request,
    image: UploadFile = File(...),
    conversation_id: UUID | None = Form(default=None),
    session: Session = Depends(get_session),
    shop: UTEMallRepository = Depends(get_shop),
) -> ChatResponse:
    content = await image.read(MAX_IMAGE_BYTES + 1)
    request.app.state.chat_requests.ensure_conversation_available(shop.seller_shop_slug or 'local', conversation_id)
    try:
        data = create_product_draft(
            session, shop, content=content,
            upload_dir=request.app.state.settings.shop_product_upload_dir,
            conversation_id=str(conversation_id) if conversation_id else None,
        )
        return ChatResponse(data=data)
    except ProductDraftError as error:
        raise HTTPException(422, detail={"code": "invalid_product_image", "message": str(error)}) from error
    except ProductDraftConflictError as error:
        raise HTTPException(409, detail={"code": "active_product_draft", "message": str(error)}) from error
    except ShopDatabaseError as error:
        raise shop_error(error) from error


@router.post("/image-data", response_model=ChatResponse, status_code=201)
async def upload_product_image_data(
    payload: ProductImageDataRequest,
    request: Request,
    session: Session = Depends(get_session),
    shop: UTEMallRepository = Depends(get_shop),
) -> ChatResponse:
    """Receive a compressed image without relying on native multipart file URIs."""
    request.app.state.chat_requests.ensure_conversation_available(shop.seller_shop_slug or 'local', payload.conversation_id)
    encoded = payload.image_base64
    if encoded.startswith("data:"):
        encoded = encoded.partition(",")[2]
    try:
        content = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as error:
        raise HTTPException(
            422,
            detail={"code": "invalid_product_image", "message": "Dữ liệu ảnh không hợp lệ."},
        ) from error
    try:
        data = create_product_draft(
            session, shop, content=content,
            upload_dir=request.app.state.settings.shop_product_upload_dir,
            conversation_id=str(payload.conversation_id) if payload.conversation_id else None,
        )
        return ChatResponse(data=data)
    except ProductDraftError as error:
        raise HTTPException(422, detail={"code": "invalid_product_image", "message": str(error)}) from error
    except ProductDraftConflictError as error:
        raise HTTPException(409, detail={"code": "active_product_draft", "message": str(error)}) from error
    except ShopDatabaseError as error:
        raise shop_error(error) from error


def _decode_image_data(encoded: str) -> bytes:
    if encoded.startswith("data:"):
        encoded = encoded.partition(",")[2]
    try:
        return base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as error:
        raise HTTPException(
            422,
            detail={"code": "invalid_product_image", "message": "Dữ liệu ảnh không hợp lệ."},
        ) from error


@router.post("/images-data", response_model=ChatResponse, status_code=201)
async def upload_product_images_data(
    payload: ProductImagesDataRequest,
    request: Request,
    session: Session = Depends(get_session),
    shop: UTEMallRepository = Depends(get_shop),
) -> ChatResponse:
    """Create one product draft with an ordered gallery of up to six images."""
    request.app.state.chat_requests.ensure_conversation_available(shop.seller_shop_slug or 'local', payload.conversation_id)
    contents = [_decode_image_data(encoded) for encoded in payload.images_base64]
    try:
        if payload.request_id:
            from app.services.image_requests import upload_once
            return upload_once(request.app.state.chat_requests, shop, payload, contents,
                               request.app.state.settings.shop_product_upload_dir)
        data = create_product_draft_images(
            session, shop, contents=contents,
            upload_dir=request.app.state.settings.shop_product_upload_dir,
            conversation_id=str(payload.conversation_id) if payload.conversation_id else None,
        )
        return ChatResponse(data=data)
    except ProductDraftError as error:
        raise HTTPException(422, detail={"code": "invalid_product_image", "message": str(error)}) from error
    except ProductDraftConflictError as error:
        raise HTTPException(409, detail={"code": "active_product_draft", "message": str(error)}) from error
    except ShopDatabaseError as error:
        raise shop_error(error) from error


@router.get("/{draft_id}/image")
def product_draft_image(
    draft_id: int,
    request: Request,
    session: Session = Depends(get_session),
    shop: UTEMallRepository = Depends(get_shop),
):
    try:
        draft = get_product_draft(session, shop, draft_id)
    except ProductDraftNotFoundError as error:
        raise _not_found(error) from error
    path = Path(request.app.state.settings.shop_product_upload_dir) / draft.image_filename
    if not path.is_file():
        raise HTTPException(404, detail="Ảnh bản nháp không còn tồn tại.")
    return FileResponse(path, media_type=draft.image_mime, filename=draft.image_filename)


@router.get("/{draft_id}/images/{image_index}")
def product_draft_gallery_image(
    draft_id: int,
    image_index: int,
    request: Request,
    session: Session = Depends(get_session),
    shop: UTEMallRepository = Depends(get_shop),
):
    try:
        draft = get_product_draft(session, shop, draft_id)
    except ProductDraftNotFoundError as error:
        raise _not_found(error) from error
    images = draft_stored_images(draft)
    if image_index < 0 or image_index >= len(images):
        raise HTTPException(404, detail="Ảnh bản nháp không tồn tại.")
    image = images[image_index]
    filename = Path(str(image.get("filename") or "")).name
    path = Path(request.app.state.settings.shop_product_upload_dir) / filename
    if not filename or not path.is_file():
        raise HTTPException(404, detail="Ảnh bản nháp không còn tồn tại.")
    return FileResponse(path, media_type=str(image.get("mime") or "image/jpeg"), filename=filename)


@router.post("/{draft_id}/publish", response_model=ProductDraftResponse)
async def publish(
    draft_id: int,
    request: Request,
    session: Session = Depends(get_session),
    shop: UTEMallRepository = Depends(get_shop),
) -> ProductDraftResponse:
    try:
        manager = request.app.state.chat_requests
        # Publishing and deleting history must agree about which images are
        # public. Serialize them so deletion cannot remove a published gallery.
        async with manager.execution:
            draft = get_product_draft(session, shop, draft_id)
            manager.ensure_conversation_available(shop.seller_shop_slug or 'local', draft.conversation_id)
            return ProductDraftResponse(data=draft_to_dict(publish_product_draft(session, shop, draft_id)))
    except ProductDraftNotFoundError as error:
        raise _not_found(error) from error
    except ProductDraftConflictError as error:
        raise HTTPException(409, detail={"code": "product_draft_conflict", "message": str(error)}) from error
    except ShopDatabaseError as error:
        raise shop_error(error) from error


@router.post("/{draft_id}/cancel", response_model=ProductDraftResponse)
async def cancel(
    draft_id: int,
    request: Request,
    session: Session = Depends(get_session),
    shop: UTEMallRepository = Depends(get_shop),
) -> ProductDraftResponse:
    try:
        manager = request.app.state.chat_requests
        async with manager.execution:
            draft = get_product_draft(session, shop, draft_id)
            manager.ensure_conversation_available(shop.seller_shop_slug or 'local', draft.conversation_id)
            draft = cancel_product_draft(
                session, shop, draft_id, request.app.state.settings.shop_product_upload_dir
            )
            return ProductDraftResponse(data=draft_to_dict(draft))
    except ProductDraftNotFoundError as error:
        raise _not_found(error) from error
    except ProductDraftConflictError as error:
        raise HTTPException(409, detail={"code": "product_draft_conflict", "message": str(error)}) from error
