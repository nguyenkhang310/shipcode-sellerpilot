import base64
import json
import logging
import os
import re
import secrets
import unicodedata
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session
from pydantic import ValidationError

from app.ai.contracts import AIProviderError
from app.ai.listing_text import _is_generic_product_command, _wants_ai_description
from app.ai.quantities import quantity_value, EMPTY_STOCK_PHRASES
from app.ai.listing_evidence import commercial_context as _commercial_context
from app.ai.listing_contracts import ListingCopy, listing_validation_context, contextual_product_reference
from app.ai.fallback import extract_price, normalize_text
from app.ai.money import money_hints, money_mentions, single_money, affirmed_quote
from app.integrations.ute_mall import (
    ProductPublishConflictError,
    UTEMallRepository,
)
from app.models.agent_run import AgentRun
from app.models.product_draft import ProductDraft
from app.services.conversation_state import ensure_conversation_open

MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_PRODUCT_IMAGES = 6
ACTIVE_STATUSES = ("collecting", "ready")
LISTING_PROMPT = (Path(__file__).resolve().parents[1] / 'ai' / 'prompts' / 'listing.md').read_text(encoding='utf-8')
logger = logging.getLogger(__name__)


class ProductDraftError(ValueError):
    pass


class ProductDraftNotFoundError(LookupError):
    pass


class ProductDraftConflictError(RuntimeError):
    pass


def image_kind(content: bytes) -> tuple[str, str]:
    if content.startswith(b"\xff\xd8\xff"):
        return ".jpg", "image/jpeg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png", "image/png"
    if content.startswith(b"RIFF") and len(content) >= 12 and content[8:12] == b"WEBP":
        return ".webp", "image/webp"
    raise ProductDraftError("Ảnh phải là file JPG, PNG hoặc WEBP hợp lệ.")


def store_image(content: bytes, upload_dir: Path) -> tuple[str, str, str]:
    if not content:
        raise ProductDraftError("Ảnh đang trống. Hãy chọn lại ảnh sản phẩm.")
    if len(content) > MAX_IMAGE_BYTES:
        raise ProductDraftError("Ảnh tối đa 8 MB.")
    extension, mime = image_kind(content)
    upload_dir.mkdir(parents=True, exist_ok=True)
    filename = uuid4().hex + extension
    temporary = upload_dir / (filename + ".tmp")
    target = upload_dir / filename
    try:
        with temporary.open("xb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return filename, f"/static/uploads/sellerpilot/{filename}", mime


def missing_fields(draft: ProductDraft) -> list[str]:
    fields = [field for field in ("name", "price_vnd", "stock", "category_id", "description")
            if not str(getattr(draft, field) or '').strip()
            and not (field == 'stock' and draft.stock == 0)]
    return fields + ([] if draft_stored_images(draft) else ['image'])


def draft_stored_images(draft: ProductDraft) -> list[dict]:
    images = [{
        "filename": draft.image_filename,
        "url": draft.image_url,
        "mime": draft.image_mime,
        "bytes": draft.image_bytes,
    }] if draft.image_filename and draft.image_url else []
    if draft.extra_images_json:
        try:
            extras = json.loads(draft.extra_images_json)
            if isinstance(extras, list):
                images.extend(item for item in extras if isinstance(item, dict))
        except (TypeError, ValueError):
            pass
    return images[:MAX_PRODUCT_IMAGES]


def delete_draft_images(draft: ProductDraft, upload_dir: Path) -> None:
    for image in draft_stored_images(draft):
        filename = Path(str(image.get("filename") or "")).name
        if filename:
            (upload_dir / filename).unlink(missing_ok=True)


def draft_to_dict(draft: ProductDraft) -> dict:
    stored_images = draft_stored_images(draft)
    return {
        "id": draft.id,
        "status": draft.status,
        "preview_url": f"/product-drafts/{draft.id}/image" if stored_images else '',
        "preview_urls": [
            f"/product-drafts/{draft.id}/image" if index == 0
            else f"/product-drafts/{draft.id}/images/{index}"
            for index in range(len(stored_images))
        ],
        "image_count": len(stored_images),
        "name": draft.name,
        "description": draft.description,
        "category_id": draft.category_id,
        "category_name": draft.category_name,
        "price_vnd": draft.price_vnd,
        "stock": draft.stock,
        "sku": draft.sku,
        "missing_fields": missing_fields(draft),
        "published_product_id": draft.published_product_id,
        "created_at": draft.created_at,
        "decided_at": draft.decided_at,
    }


def get_active_draft(session: Session, shop: UTEMallRepository, conversation_id: str | None):
    if not conversation_id:
        return None
    return session.scalar(select(ProductDraft).where(
        ProductDraft.conversation_id == conversation_id,
        ProductDraft.shop_slug == (shop.seller_shop_slug or "local"),
        ProductDraft.status.in_(ACTIVE_STATUSES),
    ).order_by(ProductDraft.id.desc()).limit(1))


def create_product_draft(
    session: Session,
    shop: UTEMallRepository,
    *,
    content: bytes,
    upload_dir: Path,
    conversation_id: str | None,
) -> dict:
    return create_product_draft_images(
        session, shop, contents=[content], upload_dir=upload_dir,
        conversation_id=conversation_id,
    )


def create_text_product_draft(session, shop, conversation_id=None):
    conversation_id = conversation_id or str(uuid4())
    ensure_conversation_open(session, shop.seller_shop_slug or 'local', conversation_id)
    draft = ProductDraft(conversation_id=conversation_id, shop_slug=shop.seller_shop_slug or 'local',
                         status='collecting', image_filename='', image_url='', image_mime='', image_bytes=0)
    session.add(draft)
    session.flush()
    return draft


def create_product_draft_images(
    session: Session,
    shop: UTEMallRepository,
    *,
    contents: list[bytes],
    upload_dir: Path,
    conversation_id: str | None,
) -> dict:
    if not 1 <= len(contents) <= MAX_PRODUCT_IMAGES:
        raise ProductDraftError(f"Mỗi sản phẩm cần từ 1 đến {MAX_PRODUCT_IMAGES} ảnh.")
    conversation_id = conversation_id or str(uuid4())
    ensure_conversation_open(session, shop.seller_shop_slug or 'local', conversation_id)
    existing = get_active_draft(session, shop, conversation_id)
    if existing and draft_stored_images(existing):
        raise ProductDraftConflictError("Hãy hoàn tất hoặc hủy sản phẩm đang soạn trước khi thêm ảnh mới.")
    stored: list[tuple[str, str, str, int]] = []
    try:
        for content in contents:
            filename, image_url, mime = store_image(content, upload_dir)
            stored.append((filename, image_url, mime, len(content)))
        primary = stored[0]
        extras = [
            {"filename": filename, "url": url, "mime": mime, "bytes": size}
            for filename, url, mime, size in stored[1:]
        ]
        draft = existing or ProductDraft(
            conversation_id=conversation_id,
            shop_slug=shop.seller_shop_slug or "local",
            status="collecting",
            image_filename=primary[0],
            image_url=primary[1],
            image_mime=primary[2],
            image_bytes=primary[3],
            extra_images_json=json.dumps(extras, ensure_ascii=False) if extras else None,
        )
        if existing:
            draft.image_filename, draft.image_url, draft.image_mime, draft.image_bytes = primary
            draft.extra_images_json = json.dumps(extras, ensure_ascii=False) if extras else None
        session.add(draft)
        session.flush()
        answer = (
            f"Đã nhận **{len(stored)} ảnh**. Mình sẽ dùng ảnh cùng yêu cầu của bạn để soạn sản phẩm."
            if len(stored) > 1 else "Đã nhận ảnh. Mình sẽ dùng ảnh cùng yêu cầu của bạn để soạn sản phẩm."
        )
        run = _record_run(
            session, draft,
            message=f"Đã thêm {len(stored)} ảnh sản phẩm",
            answer=answer,
            tool="create_product_draft", facts={
                "draft_id": draft.id, "image_count": len(stored),
                "missing_fields": missing_fields(draft),
            },
        )
        session.commit()
        session.refresh(draft)
        session.refresh(run)
    except Exception:
        session.rollback()
        for filename, _url, _mime, _size in stored:
            (upload_dir / filename).unlink(missing_ok=True)
        raise
    return _chat_data(run, draft, answer, "create_product_draft")


async def advance_product_draft(
    session: Session,
    shop: UTEMallRepository,
    ai_provider,
    draft: ProductDraft,
    *,
    message: str,
    upload_dir: Path,
) -> dict:
    text = normalize_text(message).strip(".! ")
    previous = session.scalar(select(AgentRun).where(AgentRun.product_draft_id == draft.id)
                              .order_by(AgentRun.id.desc()).limit(1))
    pending_fields = json.loads(previous.facts_json).get('pending_fields', []) if previous else []
    used_model = False
    fallback_reason = None
    fallback_stage = None
    categories = shop.product_categories()
    repaired = _repair_command_content(draft)
    was_ready = draft.status == 'ready'
    original = (draft.name, draft.description, draft.price_vnd, draft.stock, draft.category_id)
    wants_copy = _wants_ai_description(message)
    if wants_copy:
        draft.copy_instructions = message[:2000]

    if text in {"hủy", "huy", "hủy đăng", "huy dang", "bỏ bản nháp", "bo ban nhap", "để sau", "de sau"}:
        pending_fields = []
        draft.status = "cancelled"
        draft.decided_at = draft.updated_at = datetime.utcnow()
        delete_draft_images(draft, upload_dir)
        answer = "Đã hủy bản nháp và xóa ảnh chưa đăng."
    elif draft.status == "ready" and not wants_copy and _is_publish_command(message):
        published = publish_product_draft(session, shop, draft.id)
        answer = (
            f"Đã đăng **{published.name}** lên gian hàng UTech Official. "
            f"SKU **{published.sku}** đã đồng bộ với mục Sản phẩm và tồn kho."
        )
        return _save_draft_turn(
            session, published, message, answer, used_model, fallback_reason,
            tool="publish_product", ai_provider=ai_provider,
        )
    else:
        changed = _apply_explicit_details(draft, message, categories)
        pending_fields = [field for field in pending_fields if field not in changed]
        fields = missing_fields(draft)
        field = pending_fields[0] if pending_fields else fields[0] if fields else None
        validation_error = None
        clarification = None
        copy = None
        simple_name = field == "name" and _simple_name_reply(message)
        mentions = money_mentions(text)
        simple_name = simple_name and not mentions
        money_only = len(mentions) == 1 and mentions[0].start == 0 and mentions[0].end == len(text)
        if (field == 'name' and money_only and mentions[0].explicit
                and mentions[0].value is not None and 1_000 <= mentions[0].value <= 1_000_000_000):
            draft.price_vnd = mentions[0].value
            changed.add('price_vnd')
        bare = (field == "stock" and quantity_value(text) is not None) or money_only or bool(re.fullmatch(r"[\d.,]+\s*(?:đ|₫|vnd|k|nghìn|ngàn|triệu|tr|sản phẩm|cái|chiếc)?", text))
        if field == 'price_vnd' and draft.price_vnd is not None and text in {'giữ giá cũ', 'giu gia cu', 'không đổi giá', 'khong doi gia'}:
            pending_fields = [item for item in pending_fields if item != 'price_vnd']
            changed.add('price_vnd')
        if simple_name and not changed:
            draft.name = _candidate_product_name(message)
            changed.add("name")
        elif bare and not changed and field == "price_vnd":
            value = extract_price(text, sku=None)
            if value is not None and 1_000 <= value <= 1_000_000_000:
                draft.price_vnd = value
                changed.add('price_vnd')
            else:
                validation_error = "Bạn nhập giá bán từ 1.000đ đến 1.000.000.000đ nhé."
        elif bare and not changed and field == "stock":
            value = _extract_stock(text)
            if value is not None and 0 <= value <= 1_000_000:
                draft.stock = value
                changed.add('stock')
            else:
                validation_error = "Bạn nhập số lượng tồn kho từ 0 đến 1.000.000 nhé."
        elif field == "category_id" and not changed and not wants_copy:
            category = _match_category(message, categories)
            if category:
                draft.category_id, draft.category_name = category["id"], category["name"]
                changed.add("category_id")

        if draft.category_id is None and draft.name:
            inferred = _match_category(draft.name, categories)
            if inferred:
                draft.category_id, draft.category_name = inferred["id"], inferred["name"]

        # Understand the images when the item is unknown, and compose copy
        # automatically once the seller has supplied the commercial facts.
        core_complete = all(getattr(draft, key) is not None for key in ("name", "price_vnd", "stock"))
        # A natural message can contain every field in any order. Interpret the
        # whole turn before deciding which question to ask, including ready edits.
        semantic_turn = not bare and (bool(missing_fields(draft)) or not changed)
        needs_model = wants_copy or simple_name or semantic_turn or repaired or (core_complete and not draft.description)
        if needs_model:
            try:
                copy = await _compose_product_copy(session, ai_provider, draft, categories, upload_dir, message)
                used_model = True
                changed.update(_apply_model_details(draft, copy, message, categories, rewrite=wants_copy or simple_name or contextual_product_reference(message)))
                clarification = copy.clarification
                validation_error = None
            except AIProviderError as error:
                fallback_reason = error.reason
                fallback_stage = error.stage or 'listing_validation'
                logger.warning('Listing used grounded fallback: draft_id=%s reason=%s stage=%s', draft.id, fallback_reason, fallback_stage)
                # Keep supplied facts and ask only for what remains. Never pass
                # a paragraph/instruction off as a product title when AI is offline.
                if error.reason == 'free_tier_restricted':
                    clarification = (
                        'OpenCode đang chặn model miễn phí trên đường gọi của SellerPilot. '
                        'Mình chưa đọc được ảnh hoặc viết lại nội dung ở lượt này. '
                        'Ảnh và thông tin bản nháp vẫn được giữ; chưa có sản phẩm nào được đăng. '
                        'Bạn có thể gửi tên và mô tả sẵn có để tiếp tục.'
                    )
                elif was_ready:
                    clarification = 'Mình chưa xử lý được yêu cầu sửa lúc này. Thông tin bản nháp vẫn được giữ; bạn thử lại giúp mình nhé.'
                elif error.reason == 'invalid_response':
                    clarification = ('AI đã phản hồi nhưng nội dung bản nháp chưa hợp lệ nên mình chưa áp dụng. '
                                     'Ảnh và thông tin bạn gửi vẫn được giữ. Bạn nhắn **soạn lại bản nháp** để mình thử lại nhé.')
                elif draft.name and not draft.description:
                    clarification = (
                        "Mình chưa gọi được AI để soạn nội dung lúc này. Bản nháp và ảnh vẫn được giữ. "
                        "Bạn gửi mô tả sẵn có, hoặc nhắn **viết lại nội dung** để thử lại."
                    )
                elif not draft.name:
                    clarification = (
                        "Mình chưa đọc được ảnh bằng AI. Bạn đang bán sản phẩm gì? "
                        "Cho mình tên hoặc vài đặc điểm để mình viết tiêu đề và mô tả."
                    )

        pending_fields = [field for field in pending_fields if field not in changed]
        issue = next((item for item in mentions if item.explicit and item.value is None
            and (money_only and field != 'stock' or re.search(
                r'(?:giá(?:\s+bán)?|gia(?:\s+ban)?|bán|ban|để|de|chốt|chot)\s*(?:là|la|[:=])?\s*$',
                text[max(0, item.start - 25):item.start]))), None)
        if issue:
            # Do not keep a guessed endpoint of a range, even as draft data.
            draft.price_vnd = original[2]
            if 'price_vnd' not in pending_fields:
                pending_fields.append('price_vnd')
            validation_error = f'“{issue.text}” chưa rõ số tiền. Bạn chốt **giá bán bao nhiêu đồng** cho sản phẩm này?'
        remaining = list(dict.fromkeys(pending_fields + missing_fields(draft)))
        if pending_fields:
            draft.status = 'collecting'
            answer = validation_error or _missing_question(remaining, categories, draft=draft)
        elif clarification:
            draft.status = "collecting"
            answer = clarification
        elif not remaining:
            if not draft.sku:
                draft.sku = f"SP-{draft.id:06d}-{secrets.token_hex(2).upper()}"
            draft.status = "ready"
            updated = original != (draft.name, draft.description, draft.price_vnd, draft.stock, draft.category_id)
            prefix = ('Mình đã cập nhật bản nháp.' if updated else 'Bản nháp hiện tại đã đủ thông tin.') if was_ready else 'Mình đã chuẩn bị xong bản nháp.'
            answer = _ready_answer(draft, prefix=prefix)
        else:
            draft.status = "collecting"
            answer = validation_error or _safe_followup(copy, remaining) or _missing_question(remaining, categories, draft=draft)
            if used_model and draft.name and draft.description and not validation_error:
                answer = f"Mình đã soạn tiêu đề và mô tả cho **{draft.name}**.\n\n" + answer
        if repaired:
            answer = "Tên cũ đang là câu lệnh nên mình đã bỏ khỏi bản nháp. " + answer
        draft.updated_at = datetime.utcnow()

    return _save_draft_turn(session, draft, message, answer, used_model, fallback_reason,
                            ai_provider=ai_provider, pending_fields=pending_fields, fallback_stage=fallback_stage)


def publish_product_draft(session: Session, shop: UTEMallRepository, draft_id: int) -> ProductDraft:
    draft = _owned_draft(session, shop, draft_id)
    if draft.status == "published":
        return draft
    if _repair_command_content(draft):
        session.commit()
        raise ProductDraftConflictError("Tên sản phẩm cũ đang là câu lệnh. Mở chat để mình soạn lại trước khi đăng.")
    if draft.status != "ready" or missing_fields(draft):
        raise ProductDraftConflictError("Bản nháp chưa đủ thông tin để đăng.")
    try:
        product_id = shop.publish_product(
            draft_id=draft.id, name=draft.name or "", description=draft.description or "",
            category_id=draft.category_id or 0, price_vnd=draft.price_vnd or 0,
            stock=draft.stock or 0, sku=draft.sku or "",
            image_urls=[item["url"] for item in draft_stored_images(draft)],
        )
    except ProductPublishConflictError as error:
        draft.status = "conflict"
        draft.decided_at = draft.updated_at = datetime.utcnow()
        session.commit()
        raise ProductDraftConflictError(str(error)) from error
    draft.status = "published"
    draft.published_product_id = product_id
    draft.decided_at = draft.updated_at = datetime.utcnow()
    session.commit()
    session.refresh(draft)
    return draft


def cancel_product_draft(
    session: Session, shop: UTEMallRepository, draft_id: int, upload_dir: Path
) -> ProductDraft:
    draft = _owned_draft(session, shop, draft_id)
    if draft.status == "cancelled":
        return draft
    if draft.status == "published":
        raise ProductDraftConflictError("Sản phẩm đã đăng nên không thể hủy bản nháp.")
    draft.status = "cancelled"
    draft.decided_at = draft.updated_at = datetime.utcnow()
    delete_draft_images(draft, upload_dir)
    session.commit()
    session.refresh(draft)
    return draft


def get_product_draft(session: Session, shop: UTEMallRepository, draft_id: int) -> ProductDraft:
    return _owned_draft(session, shop, draft_id)


def _owned_draft(session, shop, draft_id):
    draft = session.get(ProductDraft, draft_id)
    if not draft or draft.shop_slug != (shop.seller_shop_slug or "local"):
        raise ProductDraftNotFoundError(draft_id)
    ensure_conversation_open(session, draft.shop_slug, draft.conversation_id)
    return draft


def _save_draft_turn(session, draft, message, answer, used_model, fallback_reason, tool=None, ai_provider=None, pending_fields=None, fallback_stage=None):
    tool = tool or ("prepare_product_publish" if draft.status == "ready" else "update_product_draft")
    run = _record_run(
        session, draft, message=message, answer=answer, tool=tool,
        facts={"draft_id": draft.id, "image_count": len(draft_stored_images(draft)),
               "missing_fields": missing_fields(draft), 'pending_fields': pending_fields or [],
               **({'ai_failure': {'reason': fallback_reason, 'stage': fallback_stage}} if fallback_reason else {})},
        provider=getattr(ai_provider, 'response_provider', getattr(ai_provider, "provider", "unknown")) if used_model else "deterministic_parser",
        model=getattr(ai_provider, 'response_model', getattr(ai_provider, "model", None)) if used_model else None,
        fallback_reason=fallback_reason,
    )
    session.commit()
    session.refresh(draft)
    session.refresh(run)
    return _chat_data(run, draft, answer, tool)


def _repair_command_content(draft: ProductDraft) -> bool:
    if draft.status == 'published':
        return False
    if draft.name and (_is_generic_product_command(draft.name) or _wants_ai_description(draft.name) or contextual_product_reference(draft.name)):
        draft.name = draft.description = None
        draft.category_id = draft.category_name = None
        draft.status = 'collecting'
        return True
    if draft.description and (_is_generic_product_command(draft.description) or _wants_ai_description(draft.description)):
        draft.description = None
        draft.status = 'collecting'
        return True
    return False


async def _compose_product_copy(session, ai_provider, draft, categories, upload_dir, message) -> ListingCopy:
    runs = list(reversed(session.scalars(select(AgentRun).where(
        AgentRun.product_draft_id == draft.id,
    ).order_by(AgentRun.id.desc()).limit(6)).all()))
    history = []
    for run in runs:
        history.extend([{'role': 'user', 'content': run.message[:4000]},
                        {'role': 'assistant', 'content': run.answer[:600]}])
    history.append({'role': 'user', 'content': message[:4000]})
    facts = {
        'name': draft.name, 'description': draft.description,
        'category_id': draft.category_id, 'category': draft.category_name,
        'price_vnd': draft.price_vnd, 'stock': draft.stock,
        'copy_instructions': draft.copy_instructions,
        'allowed_categories': categories,
        'current_message': message,
        'last_question': runs[-1].answer if runs else None,
        'image_count': len(draft_stored_images(draft)),
        'money_interpretations': money_hints(message),
        'missing_fields': list(dict.fromkeys((json.loads(runs[-1].facts_json).get('pending_fields', []) if runs else []) + missing_fields(draft))),
        'response_schema': ListingCopy.model_json_schema(),
    }
    if hasattr(ai_provider, 'compose_listing'):
        images = []
        # Include the gallery on the first interpretation, even if the seller
        # supplied a name. Later price/stock corrections can reuse confirmed facts.
        if (not draft.name or contextual_product_reference(message)
                or not any(run.provider in {'opencode', 'ollama', 'antigravity', 'gemini', 'groq'} and run.model
                           and json.loads(run.facts_json).get('image_count', 0) > 0 for run in runs)):
            for item in draft_stored_images(draft):
                path = upload_dir / Path(item['filename']).name
                if path.is_file():
                    encoded = base64.b64encode(path.read_bytes()).decode('ascii')
                    images.append({'type': 'file', 'mime': item['mime'],
                                   'url': f"data:{item['mime']};base64,{encoded}"})
        raw = await ai_provider.compose_listing(facts=facts, history=history, images=images)
    else:
        # Text-only providers receive no invented image observations.
        raw = await ai_provider.respond(LISTING_PROMPT + '\nẢnh không được đính kèm.',
                                        history=history, facts=facts)
    try:
        raw = re.sub(r'^```(?:json)?\s*|\s*```$', '', raw.strip(), flags=re.I)
        result = ListingCopy.model_validate_json(raw, context=listing_validation_context(facts, history))
    except (ValidationError, ValueError, TypeError, AttributeError) as error:
        raise AIProviderError('invalid_response', stage='listing_validation') from error
    return result


def _evidence_in_message(evidence: str | None, message: str) -> bool:
    return bool(evidence and normalize_text(evidence) in normalize_text(message))



def _apply_model_details(draft, copy: ListingCopy, message: str, categories, *, rewrite: bool):
    """Model interprets language; backend verifies seller-supplied commercial values."""
    applied = set()
    if copy.price_vnd is not None and _evidence_in_message(copy.price_evidence, message):
        mentions = money_mentions(copy.price_evidence)
        amount = single_money(copy.price_evidence)
        if (amount is not None and 1_000 <= amount <= 1_000_000_000
                and (amount == copy.price_vnd or len(mentions) == 1 and mentions[0].colloquial)
                and _commercial_context(copy.price_evidence, message)):
            draft.price_vnd = amount
            applied.add('price_vnd')
    if copy.stock is not None and _evidence_in_message(copy.stock_evidence, message):
        if quantity_value(copy.stock_evidence) == copy.stock and _commercial_context(copy.stock_evidence, message, stock=True):
            draft.stock = copy.stock
            applied.add('stock')
    if not copy.clarification:
        if copy.name and (draft.name is None or rewrite or _evidence_in_message(copy.name_evidence, message)):
            draft.name = copy.name.strip()
            applied.add('name')
        if copy.description and (draft.description is None or rewrite or _evidence_in_message(copy.description_evidence, message)):
            # Preserve the seller's supplied prose verbatim; generated copy is
            # used only when no source description was supplied or rewriting was requested.
            draft.description = copy.description_evidence.strip() if _evidence_in_message(copy.description_evidence, message) else copy.description.strip()
            applied.add('description')
        if copy.category_id is not None and (draft.category_id is None or _evidence_in_message(copy.name_evidence, message)
                                              or 'name' in applied and contextual_product_reference(message)):
            category = next(item for item in categories if item['id'] == copy.category_id)
            draft.category_id, draft.category_name = category['id'], category['name']
            applied.add('category_id')
    return applied


def _record_run(session, draft, *, message, answer, tool, facts, provider="deterministic_parser", model=None, fallback_reason=None):
    run = AgentRun(
        conversation_id=draft.conversation_id, shop_slug=draft.shop_slug,
        product_draft_id=draft.id, proposal_id=None, message=message, answer=answer,
        intent="create_product", mode="fallback" if fallback_reason else "ai", status="completed", provider=provider,
        model=model, fallback_reason=fallback_reason, tool_name=tool,
        tool_arguments_json=json.dumps({"draft_id": draft.id}),
        facts_json=json.dumps(facts, ensure_ascii=False), elapsed_ms=0,
    )
    session.add(run)
    session.flush()
    return run


def _chat_data(run, draft, answer, tool):
    draft_data = draft_to_dict(draft)
    pending = json.loads(run.facts_json).get('pending_fields', [])
    if draft.status == 'collecting':
        draft_data['missing_fields'] = list(dict.fromkeys(pending + draft_data['missing_fields']))
    return {
        "run_id": run.id, "conversation_id": draft.conversation_id,
        "answer": answer, "intent": "create_product", "mode": run.mode,
        "provider": run.provider, "model": run.model,
        "fallback_reason": run.fallback_reason, "tool": tool,
        "facts": json.loads(run.facts_json), "proposal": None,
        "product_draft": draft_data, "suggestions": [],
        "integration_mode": "local_store",
    }


def _extract_stock(text):
    return quantity_value(text)


def _stock_number(value: str) -> int | None:
    if re.fullmatch(r'\d+|\d{1,3}(?:[.,]\d{3})+', value):
        return int(value.replace('.', '').replace(',', ''))
    return None


def _plain(value):
    value = unicodedata.normalize("NFKD", normalize_text(value).replace("đ", "d"))
    return " ".join("".join(char for char in value if not unicodedata.combining(char)).split())


FIELD_LABELS = (
    r"tên(?:\s+sản phẩm)?|ten(?:\s+san pham)?|tiêu\s+đề|tieu\s+de|"
    r"giá(?:\s+bán)?|gia(?:\s+ban)?|"
    r"tồn(?:\s+kho)?|ton(?:\s+kho)?|số\s+lượng|so\s+luong|"
    r"ngành(?:\s+hàng)?|nganh(?:\s+hang)?|danh\s+mục|danh\s+muc|"
    r"mô\s+tả|mo\s+ta|nội\s+dung|noi\s+dung|caption"
)


def _extract_labeled_value(message: str, labels: str) -> str | None:
    match = re.search(
        rf"(?:^|[,;\n])\s*(?:{labels})\s*(?:là\s+|la\s+|[:=\-]\s*)(.+)",
        message.strip(), flags=re.I | re.S,
    )
    if not match:
        return None
    value = re.split(rf"[,;\n]\s*(?=(?:{FIELD_LABELS})\s*(?:là\s|la\s|[:=\-]))", match.group(1), maxsplit=1, flags=re.I)[0]
    return value.strip(" \t\r\n\"'") or None




def _is_publish_command(message: str) -> bool:
    text = _plain(message).strip(" .!?")
    return bool(re.fullmatch(
        r"(?:(?:xac nhan|dong y)\s+)?dang(?:\s+san pham)?(?:\s+nay)?"
        r"(?:\s+len(?:\s+(?:san|shop))?)?(?:\s+(?:giup minh|di|nhe))?",
        text,
    ))




def _command_product_name(message: str) -> str | None:
    match = re.match(
        r"^\s*(?:(?:hãy|vui lòng|làm ơn)\s+)?(?:đăng|tạo|thêm|đưa)\s+"
        r"(?:sản phẩm|mặt hàng)\s+(.+)$",
        message.strip(), flags=re.I,
    )
    if not match:
        return None
    value = re.split(rf"[,;\n]\s*(?=(?:{FIELD_LABELS})\b)", match.group(1), maxsplit=1, flags=re.I)[0]
    value = re.sub(r"\s+(?:lên|vào)\s+(?:sàn|shop)\s*$", "", value, flags=re.I)
    value = re.sub(r"\s+(?:giúp mình|cho mình|đi|nhé)\s*$", "", value, flags=re.I)
    if _plain(value).startswith(("nay", "moi", "tu anh", "trong anh")):
        return None
    return value.strip(" \t\r\n.,;:\"'") or None


def _candidate_product_name(message: str) -> str | None:
    if _is_generic_product_command(message) or _wants_ai_description(message) or contextual_product_reference(message):
        return None
    value = _extract_labeled_value(message, r"tên(?:\s+sản phẩm)?|ten(?:\s+san pham)?")
    value = value or _command_product_name(message)
    if value is None:
        if re.search(rf"\b(?:{FIELD_LABELS})\b", message, flags=re.I):
            value = re.split(rf"[,;\n]?\s*(?=(?:{FIELD_LABELS})\b)", message, maxsplit=1, flags=re.I)[0]
        else:
            value = message
    value = value.strip(" \t\r\n.,;:\"'")
    if not value or _is_publish_command(value) or _is_generic_product_command(value):
        return None
    return value


def _simple_name_reply(message: str) -> bool:
    """A short product label is safe locally; conversational paragraphs need the model."""
    text = _plain(message)
    return bool(5 <= len(message.strip()) <= 100 and '\n' not in message
                and text not in {'dong y', 'duoc roi', 'cam on', 'rat tot', 'oke nhe', 'ok roi'}
                and len(text.split()) <= 12
                and not re.search(r'\b(?:minh|toi|giup|dang|gia|kho|con|doi|sua|cho|hay|nhe|mo ta|noi dung|tieu de)\b', text)
                and not re.search(r'\d\s*(?:k|tr|trieu|nghin|ngan|đ|₫)\b', text)
                and _candidate_product_name(message))


def _description_value(message: str) -> str | None:
    if _wants_ai_description(message) or _is_publish_command(message) or _is_generic_product_command(message):
        return None
    value = _extract_labeled_value(message, r"mô\s+tả|mo\s+ta") or message.strip()
    return value.strip(" \t\r\n") or None


def _extract_labeled_stock(message: str) -> int | None:
    match = re.search(
        r"\b(?:tồn(?:\s+kho)?|ton(?:\s+kho)?|số\s+lượng|so\s+luong|sl)\s*"
        r"(?:là\s+|la\s+|[:=\-]\s*)?([0-9][0-9.,]*)\b",
        message, flags=re.I,
    )
    if not match:
        match = re.search(
            r'\b(?:còn|con)(?:\s+(?:lại|lai|khoảng|khoang|tầm|tam))?\s+'
            r'([0-9][0-9.,]*)\s*(?:cái|cai|chiếc|chiec|sản phẩm|san pham|sp|trái|trai|quả|qua)\b',
            message, re.I,
        )
    return _stock_number(match.group(1).rstrip('.,')) if match else None


def _extract_labeled_price(message: str) -> int | None:
    values = []
    for match in re.finditer(r'\b(?:giá(?:\s+bán)?|gia(?:\s+ban)?|bán|ban|để|de|chốt|chot)\s*(?:là\s+|la\s+|[:=]\s*)?', message, re.I):
        tail = message[match.end():].lstrip()
        mentions = money_mentions(tail)
        if mentions and mentions[0].start == 0 and affirmed_quote(mentions[0].text, message):
            values.append(mentions[0].value)
    if not values:
        # Natural Vietnamese often inserts the product reference between the
        # label and amount: "giá của nó là 15k/trái". Use the same guarded
        # commercial-context check as model evidence so costs/fees are not
        # mistaken for the selling price.
        reference = (r'(?:nó|no|mình|minh|em|món\s+này|mon\s+nay|cái\s+này|cai\s+nay|'
                     r'sản\s+phẩm\s+này|san\s+pham\s+nay|'
                     r'(?:mỗi|moi|từng|tung)\s+(?:trái|trai|quả|qua|cái|cai|chiếc|chiec))')
        for match in re.finditer(r'\b(?:giá(?:\s+bán)?|gia(?:\s+ban)?)\s+'
                                 r'(?:(?:của|cua)\s+)?' + reference +
                                 r'\s*(?:là\s+|la\s+|[:=]\s*)?', message, re.I):
            tail = message[match.end():].lstrip()
            mentions = money_mentions(tail)
            if (mentions and mentions[0].start == 0 and mentions[0].value is not None
                    and _commercial_context(mentions[0].text, message)):
                values.append(mentions[0].value)
    # Multiple competing selling prices require clarification, not a last-value win.
    return values[0] if values and all(value == values[0] for value in values) else None


def _apply_explicit_details(draft, message: str, categories: list[dict]) -> set[str]:
    """Apply clearly labelled facts, including corrections to an existing draft."""
    changed: set[str] = set()
    if _plain(message).strip(' .!?') in EMPTY_STOCK_PHRASES:
        draft.stock = 0
        changed.add('stock')
    name = _extract_labeled_value(message, r"tên(?:\s+sản phẩm)?|ten(?:\s+san pham)?|tiêu\s+đề|tieu\s+de")
    if not name:
        candidate = _command_product_name(message)
        name = candidate if candidate and _simple_name_reply(candidate) else None
    if name and _candidate_product_name(name) is not None and 5 <= len(name) <= 200:
        draft.name = name
        changed.add("name")
    if re.search(r"\b(?:giá|gia|bán|ban|để|de|chốt|chot)\b", message, flags=re.I):
        price = _extract_labeled_price(message)
        if price is not None and 1_000 <= price <= 1_000_000_000:
            draft.price_vnd = price
            changed.add("price_vnd")
    stock = _extract_labeled_stock(message)
    if stock is not None and 0 <= stock <= 1_000_000:
        draft.stock = stock
        changed.add("stock")
    category_text = _extract_labeled_value(message, r"ngành(?:\s+hàng)?|nganh(?:\s+hang)?|danh\s+mục|danh\s+muc")
    category = _match_category(category_text or (draft.name if draft.category_id is None else '') or '', categories)
    if category:
        draft.category_id, draft.category_name = category["id"], category["name"]
        changed.add("category_id")
    description = _extract_labeled_value(message, r"mô\s+tả|mo\s+ta|nội\s+dung|noi\s+dung|caption")
    if description and not _wants_ai_description(description) and len(description) >= 10:
        draft.description = _clean_supplied_description(description)[:10_000]
        changed.add("description")
    return changed


def _clean_supplied_description(description: str) -> str:
    lines = description.strip().splitlines()
    while lines:
        last = _plain(lines[-1]).strip(' .!?')
        if not (_is_publish_command(lines[-1]) or _is_generic_product_command(lines[-1])
                or re.fullmatch(r'(?:dang|dua)\s+(?:giup|cho)\s+(?:minh|toi|em)(?:\s+(?:nhe|nha|di))*', last)):
            break
        lines.pop()
    return '\n'.join(lines).strip()


def _match_category(message, categories):
    text = _plain(message)
    for category in categories:
        name = _plain(category["name"])
        if text == name or name in text:
            return category
    aliases = {
        "Thời Trang Nữ": ("ao nu", "quan nu", "dam nu", "vay nu", "do nu", "ao thun nu", "noi y", "bra"),
        "Thời Trang Nam": ("ao nam", "quan nam", "do nam", "ao thun nam", "so mi nam", "polo nam"),
        "Điện Thoại & Phụ Kiện": ("dien thoai", "smartphone", "op lung", "sac dien thoai", "phu kien dien thoai"),
        "Máy Tính & Laptop": ("may tinh", "laptop", "ban phim", "chuot", "man hinh", "o cung", "ssd", "usb", "webcam"),
        "Giày Dép": ("giay", "dep", "sandal", "sneaker"),
        "Túi Ví & Phụ Kiện": ("tui xach", "vi da", "balo", "that lung", "kinh mat"),
        "Nhà Cửa & Đời Sống": ("nha cua", "noi that", "gia dung", "phong ngu", "nha bep"),
        "Sắc Đẹp": ("my pham", "sac dep", "son moi", "kem duong", "trang diem", "nuoc hoa"),
        "Sức Khỏe": ("suc khoe", "thuc pham chuc nang", "y te", "khau trang"),
        "Bách Hóa Online": ("bach hoa", "thuc pham", "do uong", "banh keo", "ot", "rau", "cu qua", "nong san", "gia vi"),
        "Thể Thao & Du Lịch": ("the thao", "du lich", "gym", "camping", "bong da"),
        "Mẹ & Bé": ("me va be", "me be", "tre em", "em be", "bim", "sua bot"),
        "Chăm Sóc Thú Cưng": ("thu cung", "cho meo", "thuc an cho", "thuc an meo", "do cho cho", "do cho meo", "pet"),
        "Ô Tô & Xe Máy": ("o to", "xe may", "phu tung", "mu bao hiem"),
        "Nhà Sách & Văn Phòng": ("sach", "van phong pham", "but bi", "vo hoc sinh", "giay in"),
        "Đồ Chơi": ("do choi", "lego", "mo hinh", "gau bong"),
    }
    by_name = {_plain(item["name"]): item for item in categories}
    matches = []
    for category_name, phrases in aliases.items():
        if any(re.search(rf"\b{re.escape(phrase)}\b", text) for phrase in phrases):
            category = by_name.get(_plain(category_name))
            if category and category not in matches:
                matches.append(category)
    if len(matches) == 1:
        return matches[0]
    return None


def _category_question(categories):
    names = [item["name"] for item in categories]
    midpoint = (len(names) + 1) // 2
    first = " · ".join(f"**{name}**" for name in names[:midpoint])
    second = " · ".join(f"**{name}**" for name in names[midpoint:])
    return f"Shopee có {len(names)} ngành hàng. Bạn chọn một nhóm:\n\n{first}\n\n{second}"


def _question_for(field: str, categories: list[dict]) -> str:
    return {
        "name": "Bạn muốn bán mặt hàng nào? Mình có thể soạn tiêu đề và mô tả từ ảnh hoặc vài đặc điểm của món hàng.",
        "price_vnd": "Giá bán của sản phẩm là bao nhiêu? Ví dụ: **249.000đ**.",
        "stock": "Số lượng tồn kho ban đầu là bao nhiêu?",
        "category_id": _category_question(categories),
        "description": "Bạn gửi mô tả sản phẩm, hoặc nhắn **AI tự viết** để mình soạn từ thông tin đã có.",
        "image": "Bạn thêm ít nhất một ảnh sản phẩm bằng nút **+**, rồi bấm gửi để mình hoàn thiện bản nháp nhé.",
    }[field]


def _safe_followup(copy, fields):
    if not copy or not copy.next_question or not copy.next_question_fields:
        return None
    requested = set(copy.next_question_fields)
    if not requested <= set(fields):
        return None
    for field, pattern in {'price_vnd': r'giá|bao nhiêu tiền', 'stock': r'tồn|số lượng|mấy (?:cái|chiếc)',
                           'description': r'mô tả|caption', 'category_id': r'ngành|danh mục'}.items():
        if field not in fields and re.search(pattern, copy.next_question, re.I):
            return None
    # Do not turn an untrusted generated number into a suggested commercial value.
    if any(item.explicit for item in money_mentions(copy.next_question)):
        return None
    return copy.next_question.strip()


def _missing_question(fields: list[str], categories, *, draft=None) -> str:
    name = f' **{draft.name}**' if draft and draft.name else ' sản phẩm này'
    if fields == ['price_vnd', 'stock']:
        return f'Bạn muốn bán{name} giá bao nhiêu, và kho còn bao nhiêu cái?'
    if fields[0] == 'price_vnd':
        return f'Bạn chốt **giá bán** cho{name} là bao nhiêu?'
    if fields[0] == 'stock':
        return f'Bạn còn bao nhiêu cái{name} trong **tồn kho** để mình đăng bán?'
    return _question_for(fields[0], categories)


def _ready_answer(draft, prefix="Mình đã chuẩn bị xong bản nháp."):
    return (
        f"{prefix}\n\n"
        f"• **{draft.name}**\n"
        f"• Giá: **{draft.price_vnd:,}đ**\n"
        f"• Tồn kho: **{draft.stock}**\n"
        f"• Ngành hàng: **{draft.category_name}**\n\n"
        "Bạn kiểm tra thẻ bên dưới rồi bấm **Đăng sản phẩm**. Chưa có gì được đăng ở bước này."
    ).replace(f"{draft.price_vnd:,}", f"{draft.price_vnd:,}".replace(",", "."))
