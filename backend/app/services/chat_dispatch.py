"""Route a seller message to advice or its active product draft."""
import re
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.ai.fallback import parse_fallback
from app.ai.money import money_mentions
from app.ai.money import plain
from app.ai.quantities import quantity_value
from app.ai.small_talk import social_reply
from app.integrations.ute_mall import ShopDatabaseError, UTEMallRepository
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.advisor import is_forget_request
from app.services.business_advisor import planning_request
from app.services.chat import handle_chat, is_casual_message
from app.services.order_assistant import is_order_question
from app.services.conversations import recent_runs, history_messages
from app.services.product_edit_chat import is_product_edit_request, pending_edit, handle_product_edit
from app.ai.fallback import extract_sku
from app.services.product_drafts import (
    ProductDraftConflictError, _wants_ai_description,
    advance_product_draft, get_active_draft,
    create_text_product_draft,
)


def listing_request(message):
    text = plain(message).lower()
    if planning_request(message) or re.search(r'\b(?:neu|gia su|co nen|huong dan|cach dang)\b', text):
        return False
    if re.search(r'\b(?:khong|dung|chua)(?:\s+(?:can|muon))?\s+(?:dang|tao|them|dua)\b', text):
        return False
    return bool(re.search(r'\b(?:dang(?: ban)?|tao|them|dua)\s+(?:(?:mot|1)\s+)?(?:san pham|mat hang|mon hang)\b', text)
                or re.search(r'\b(?:dang|dua)\b.{0,80}\blen (?:san|shop|gian hang)\b', text)
                or re.match(r'^(?:(?:ban|hay|giup|minh|toi|em|muon)\s+){0,4}dang\s+(?!bai|video|tin|story|reel|ky)\S', text))


async def dispatch_chat(payload: ChatRequest, session: Session, shop: UTEMallRepository, provider, settings) -> ChatResponse:
    try:
        conversation_id = str(payload.conversation_id) if payload.conversation_id else None
        active_draft = get_active_draft(session, shop, conversation_id)
        previous=recent_runs(session,shop,conversation_id,limit=24)
        # Social acknowledgements are not names, captions or edit targets.
        # Keep work in progress intact so the next factual reply can resume it.
        casual = is_casual_message(payload.message) and not re.search(
            r'(?:^|[\n;,])\s*(?:tên|tiêu đề|mô tả|caption|nội dung)\s*[:=]', payload.message, re.I)
        if social_reply(payload.message) or casual and not listing_request(payload.message) and not _wants_ai_description(payload.message):
            return ChatResponse(data=await handle_chat(session, shop, provider,
                message=payload.message, conversation_id=conversation_id))
        # A current order read must not be mistaken for a draft title or a
        # product-edit clarification merely because its sentence is short.
        if is_order_question(payload.message, previous):
            return ChatResponse(data=await handle_chat(session, shop, provider,
                message=payload.message, conversation_id=conversation_id))
        if active_draft is None and listing_request(payload.message):
            active_draft = create_text_product_draft(session, shop, conversation_id)
            return ChatResponse(data=await advance_product_draft(session, shop, provider, active_draft,
                message=payload.message, upload_dir=settings.shop_product_upload_dir))
        continue_edit=bool(pending_edit(previous) and not planning_request(payload.message)
            and (extract_sku(payload.message.lower()) or re.match(r'\s*(?:tieu de|ten san pham|mo ta|gia|ton|so luong)\s*[:=]',plain(payload.message))
                 or parse_fallback(payload.message,today=datetime.now(shop.timezone).date()).intent=='unknown'))
        if (is_product_edit_request(payload.message) or continue_edit) and (
                active_draft is None or extract_sku(payload.message.lower()) or 'đã đăng' in payload.message.lower()):
            return ChatResponse(data=await handle_product_edit(session,shop,provider,message=payload.message,
                conversation_id=conversation_id))
        direct = parse_fallback(payload.message, today=datetime.now(shop.timezone).date())
        asking_shop = direct.intent in {'shop_summary', 'inventory_query', 'product_search'} or (
            direct.intent == 'change_price' and direct.sku is not None) or (
            direct.intent == 'sales_advice' and not _wants_ai_description(payload.message))
        editing_draft = bool(re.search(r'(?:^|[,;\n])\s*(?:tên(?:\s+sản phẩm)?|giá(?:\s+bán)?|tồn(?:\s+kho)?|số\s+lượng|ngành(?:\s+hàng)?|mô\s+tả)\s*[:=]', payload.message, re.I))
        labeled_edit = editing_draft
        # Inventory keywords occur in listings too ("kho còn 20 cái"). Do not
        # divert the seller's listing paragraph into a shop inventory query.
        listing_turn = bool(re.search(r'\bđăng\b|\b(?:tạo|thêm)\s+(?:sản phẩm|mặt hàng)|\b(?:tiêu đề|nội dung|caption)\s*[:=]', payload.message, re.I))
        commercial_detail = any(item.explicit for item in money_mentions(payload.message)) or bool(re.search(r'\b(?:giá|tồn kho|kho còn|còn lại)\s*[:=]?\s*\d', payload.message, re.I))
        question = bool(re.search(r'\?|bao nhiêu|thế nào|nên bán|nên để|tư vấn|kiểm tra|xem\s+(?:kho|tồn|doanh)', payload.message, re.I))
        editing_draft = editing_draft or listing_turn or (commercial_detail and not question and not (direct.intent == 'change_price' and direct.sku))
        if active_draft is not None and not labeled_edit and not listing_turn and not _wants_ai_description(payload.message):
            last = recent_runs(session, shop, conversation_id, limit=1)
            explicit_selling_price = bool(re.search(r'giá\s+bán|chốt\s+giá|đặt\s+giá', payload.message, re.I))
            if last and last[-1].tool_name == 'calculate_pricing' and direct.intent == 'unknown' and not explicit_selling_price:
                # A bare "100k" after an advisor asks for cost is a cost answer,
                # not the draft's selling price. Labelled draft edits still resume it.
                asking_shop = True
                editing_draft = False
        quantity_reply = active_draft is not None and quantity_value(payload.message) is not None
        asking_shop = asking_shop and not editing_draft and not quantity_reply
        if active_draft is not None and not labeled_edit:
            # A video caption or a plan to post content is advice, not a change
            # to the active product's listing caption/price/title.
            history = history_messages(recent_runs(session, shop, conversation_id, limit=4))
            if planning_request(payload.message, history):
                asking_shop = True
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
                "message": "Không đọc được database Shopee",
            },
        ) from error
    except ProductDraftConflictError as error:
        raise HTTPException(
            status_code=409,
            detail={"code": "product_draft_conflict", "message": str(error)},
        ) from error
