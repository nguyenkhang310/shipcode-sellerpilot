"""Route a seller message to advice or its active product draft."""
import re
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.ai.fallback import parse_fallback
from app.integrations.ute_mall import ShopDatabaseError, UTEMallRepository
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.advisor import is_forget_request
from app.services.chat import handle_chat
from app.services.conversations import recent_runs
from app.services.product_drafts import (
    ProductDraftConflictError, _wants_ai_description,
    advance_product_draft, get_active_draft,
)


async def dispatch_chat(payload: ChatRequest, session: Session, shop: UTEMallRepository, provider, settings) -> ChatResponse:
    try:
        conversation_id = str(payload.conversation_id) if payload.conversation_id else None
        active_draft = get_active_draft(session, shop, conversation_id)
        direct = parse_fallback(payload.message, today=datetime.now(shop.timezone).date())
        asking_shop = direct.intent in {'shop_summary', 'inventory_query', 'product_search'} or (
            direct.intent == 'change_price' and direct.sku is not None) or (
            direct.intent == 'sales_advice' and not _wants_ai_description(payload.message))
        editing_draft = bool(re.search(r'(?:^|[,;\n])\s*(?:tên(?:\s+sản phẩm)?|giá(?:\s+bán)?|tồn(?:\s+kho)?|số\s+lượng|ngành(?:\s+hàng)?|mô\s+tả)\s*[:=]', payload.message, re.I))
        if active_draft is not None and not editing_draft and not _wants_ai_description(payload.message):
            last = recent_runs(session, shop, conversation_id, limit=1)
            if last and last[-1].tool_name == 'calculate_pricing' and direct.intent == 'unknown':
                # A bare "100k" after an advisor asks for cost is a cost answer,
                # not the draft's selling price. Labelled draft edits still resume it.
                asking_shop = True
        asking_shop = asking_shop and not editing_draft
        if active_draft is not None and not asking_shop and not is_forget_request(payload.message):
            return ChatResponse(data=await advance_product_draft(
                session, shop, provider, active_draft,
                message=payload.message,
                upload_dir=settings.shop_product_upload_dir,
            ))
        return ChatResponse(data=await handle_chat(
            session,
            shop,
            provider,
            message=payload.message,
            conversation_id=conversation_id,
        ))
    except ShopDatabaseError as error:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "shop_database_unavailable",
                "message": "Không đọc được database UTE MALL",
            },
        ) from error
    except ProductDraftConflictError as error:
        raise HTTPException(
            status_code=409,
            detail={"code": "product_draft_conflict", "message": str(error)},
        ) from error
