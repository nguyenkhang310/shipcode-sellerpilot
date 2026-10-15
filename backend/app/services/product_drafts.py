import base64
import json
import os
import re
import secrets
import unicodedata
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.ai.contracts import AIProviderError
from app.ai.fallback import extract_price, normalize_text
from app.integrations.ute_mall import (
    ProductPublishConflictError,
    UTEMallRepository,
)
from app.models.agent_run import AgentRun
from app.models.product_draft import ProductDraft

MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_PRODUCT_IMAGES = 6
ACTIVE_STATUSES = ("collecting", "ready")
AI_DESCRIPTION_PHRASES = {
    "ai viết", "ai viet", "viết giúp", "viet giup", "tự viết", "tu viet",
    "sellerpilot viết", "sellerpilot viet",
}
LISTING_PROMPT = (Path(__file__).resolve().parents[1] / 'ai' / 'prompts' / 'listing.md').read_text(encoding='utf-8')


class ListingCopy(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=10_000)
    category_id: int | None = None
    clarification: str | None = Field(default=None, max_length=600)


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
    return [field for field in ("name", "price_vnd", "stock", "category_id", "description")
            if not str(getattr(draft, field) or '').strip()
            and not (field == 'stock' and draft.stock == 0)]


def draft_stored_images(draft: ProductDraft) -> list[dict]:
    images = [{
        "filename": draft.image_filename,
        "url": draft.image_url,
        "mime": draft.image_mime,
        "bytes": draft.image_bytes,
    }]
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
        "preview_url": f"/product-drafts/{draft.id}/image",
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
    existing = get_active_draft(session, shop, conversation_id)
    if existing:
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
        draft = ProductDraft(
            conversation_id=conversation_id,
            shop_slug=shop.seller_shop_slug or "local",
            status="collecting",
            image_filename=primary[0],
            image_url=primary[1],
            image_mime=primary[2],
            image_bytes=primary[3],
            extra_images_json=json.dumps(extras, ensure_ascii=False) if extras else None,
        )
        session.add(draft)
        session.flush()
        answer = (
            f"Mình đã nhận **{len(stored)} ảnh**. **Sản phẩm này tên gì?**"
            if len(stored) > 1 else "Mình đã nhận ảnh. **Sản phẩm này tên gì?**"
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
    used_model = False
    fallback_reason = None
    categories = shop.product_categories()
    repaired = _repair_command_content(draft)
    wants_copy = _wants_ai_description(message)
    if wants_copy:
        draft.copy_instructions = message[:2000]

    if text in {"hủy", "huy", "hủy đăng", "huy dang", "bỏ bản nháp", "bo ban nhap", "để sau", "de sau"}:
        draft.status = "cancelled"
        draft.decided_at = draft.updated_at = datetime.utcnow()
        delete_draft_images(draft, upload_dir)
        answer = "Đã hủy bản nháp và xóa ảnh chưa đăng."
    elif draft.status == "ready" and not wants_copy:
        if _is_publish_command(message):
            published = publish_product_draft(session, shop, draft.id)
            answer = (
                f"Đã đăng **{published.name}** lên gian hàng UTech Official. "
                f"SKU **{published.sku}** đã đồng bộ với mục Sản phẩm và tồn kho."
            )
            return _save_draft_turn(
                session, published, message, answer, used_model, fallback_reason,
                tool="publish_product", ai_provider=ai_provider,
            )
        changed = _edit_ready_draft(draft, message, shop)
        answer = _ready_answer(draft, prefix="Mình đã cập nhật bản nháp.") if changed else (
            "Bạn muốn sửa tên, mô tả hay giá? Mình có thể viết lại nội dung cho sản phẩm này."
        )
    else:
        changed = _apply_explicit_details(draft, message, categories)
        fields = missing_fields(draft)
        field = fields[0] if fields else None
        validation_error = None
        clarification = None

        if field == "name" and "name" not in changed:
            value = _candidate_product_name(message)
            if value and 5 <= len(value) <= 200:
                draft.name = value
                changed.add("name")
            elif not wants_copy and not _is_generic_product_command(message):
                validation_error = "Bạn cho mình tên hoặc loại sản phẩm đang bán nhé."
        elif field == "price_vnd" and not changed and not wants_copy:
            value = extract_price(text, sku=None)
            if value is None or not 1_000 <= value <= 1_000_000_000:
                validation_error = "Bạn nhập giá bán từ 1.000đ đến 1.000.000.000đ nhé. Ví dụ: **249.000đ**."
            else:
                draft.price_vnd = value
        elif field == "stock" and not changed and not wants_copy:
            value = _extract_stock(text)
            if value is None or not 0 <= value <= 1_000_000:
                validation_error = "Bạn nhập số lượng tồn kho từ 0 đến 1.000.000 nhé."
            else:
                draft.stock = value
        elif field == "category_id" and not changed and not wants_copy:
            category = _match_category(message, categories)
            if category:
                draft.category_id, draft.category_name = category["id"], category["name"]
            else:
                validation_error = "Mình chưa xác định chắc ngành hàng. " + _category_question(categories)
        elif field == "description" and not changed and not wants_copy:
            value = _description_value(message)
            if value and len(value) >= 10:
                draft.description = value[:10_000]

        if draft.category_id is None and draft.name:
            inferred = _match_category(draft.name, categories)
            if inferred:
                draft.category_id, draft.category_name = inferred["id"], inferred["name"]

        # Understand the images when the item is unknown, and compose copy
        # automatically once the seller has supplied the commercial facts.
        identify_from_images = draft.name is None and (
            wants_copy or _is_generic_product_command(message) or repaired
        )
        core_complete = all(getattr(draft, key) is not None for key in ("name", "price_vnd", "stock"))
        if wants_copy or identify_from_images or (core_complete and not draft.description):
            try:
                copy = await _compose_product_copy(session, ai_provider, draft, categories, upload_dir, message)
                used_model = True
                clarification = copy.clarification
                if not clarification:
                    if copy.name:
                        draft.name = copy.name.strip()
                    if copy.description:
                        draft.description = copy.description.strip()
                    if draft.category_id is None and copy.category_id is not None:
                        category = next(item for item in categories if item["id"] == copy.category_id)
                        draft.category_id, draft.category_name = category["id"], category["name"]
                    validation_error = None
            except AIProviderError as error:
                fallback_reason = error.reason
                clarification = (
                    "Mình chưa gọi được AI để soạn nội dung lúc này. Bản nháp và ảnh vẫn được giữ. "
                    "Bạn nhắn **viết lại nội dung** để thử lại."
                    if draft.name else
                    "Mình chưa đọc được ảnh bằng AI. Bạn đang bán sản phẩm gì? "
                    "Cho mình tên hoặc vài đặc điểm để mình viết tiêu đề và mô tả."
                )

        remaining = missing_fields(draft)
        if clarification:
            draft.status = "collecting"
            answer = clarification
        elif not remaining:
            if not draft.sku:
                draft.sku = f"SP-{draft.id:06d}-{secrets.token_hex(2).upper()}"
            draft.status = "ready"
            answer = _ready_answer(draft)
        else:
            draft.status = "collecting"
            answer = validation_error or _question_for(remaining[0], categories)
            if used_model and draft.name and draft.description and not validation_error:
                answer = f"Mình đã soạn tiêu đề và mô tả cho **{draft.name}**.\n\n" + answer
        if repaired:
            answer = "Tên cũ đang là câu lệnh nên mình đã bỏ khỏi bản nháp. " + answer
        draft.updated_at = datetime.utcnow()

    return _save_draft_turn(session, draft, message, answer, used_model, fallback_reason,
                            ai_provider=ai_provider)


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
    return draft


def _save_draft_turn(session, draft, message, answer, used_model, fallback_reason, tool=None, ai_provider=None):
    tool = tool or ("prepare_product_publish" if draft.status == "ready" else "update_product_draft")
    run = _record_run(
        session, draft, message=message, answer=answer, tool=tool,
        facts={"draft_id": draft.id, "missing_fields": missing_fields(draft)},
        provider=getattr(ai_provider, "provider", "unknown") if used_model else "deterministic_parser",
        model=getattr(ai_provider, "model", None) if used_model else None,
        fallback_reason=fallback_reason,
    )
    session.commit()
    session.refresh(draft)
    session.refresh(run)
    return _chat_data(run, draft, answer, tool)


def _repair_command_content(draft: ProductDraft) -> bool:
    if draft.status == 'published':
        return False
    if draft.name and (_is_generic_product_command(draft.name) or _wants_ai_description(draft.name)):
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
        history.extend([{'role': 'user', 'content': run.message[:1000]},
                        {'role': 'assistant', 'content': run.answer[:600]}])
    history.append({'role': 'user', 'content': message[:2000]})
    facts = {
        'name': draft.name, 'description': draft.description,
        'category_id': draft.category_id, 'category': draft.category_name,
        'price_vnd': draft.price_vnd, 'stock': draft.stock,
        'copy_instructions': draft.copy_instructions,
        'allowed_categories': categories,
    }
    if hasattr(ai_provider, 'compose_listing'):
        images = []
        # A known product can be rewritten from its confirmed facts. Re-send
        # images only while identifying it, avoiding repeated vision requests.
        if not draft.name:
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
        result = ListingCopy.model_validate_json(raw)
    except (ValidationError, ValueError, TypeError, AttributeError) as error:
        raise AIProviderError('invalid_response') from error
    if result.clarification:
        return result
    if result.category_id is not None and result.category_id not in {item['id'] for item in categories}:
        raise AIProviderError('invalid_response')
    if (not result.name or len(result.name.strip()) < 5
            or _is_generic_product_command(result.name) or _wants_ai_description(result.name)
            or not result.description or len(result.description.strip()) < 10
            or _is_generic_product_command(result.description) or _wants_ai_description(result.description)):
        raise AIProviderError('invalid_response')
    return result


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
    return {
        "run_id": run.id, "conversation_id": draft.conversation_id,
        "answer": answer, "intent": "create_product", "mode": run.mode,
        "provider": run.provider, "model": run.model,
        "fallback_reason": run.fallback_reason, "tool": tool,
        "facts": json.loads(run.facts_json), "proposal": None,
        "product_draft": draft_to_dict(draft), "suggestions": [],
        "integration_mode": "local_store",
    }


def _extract_stock(text):
    match = re.search(r"(?<![\d.,])([0-9]{1,7})(?:\s*(?:sản phẩm|san pham|cái|cai|chiếc|chiec))?\b", text)
    return int(match.group(1)) if match else None


def _plain(value):
    value = unicodedata.normalize("NFKD", normalize_text(value).replace("đ", "d"))
    return " ".join("".join(char for char in value if not unicodedata.combining(char)).split())


FIELD_LABELS = (
    r"tên(?:\s+sản phẩm)?|ten(?:\s+san pham)?|"
    r"giá(?:\s+bán)?|gia(?:\s+ban)?|"
    r"tồn(?:\s+kho)?|ton(?:\s+kho)?|số\s+lượng|so\s+luong|"
    r"ngành(?:\s+hàng)?|nganh(?:\s+hang)?|danh\s+mục|danh\s+muc|"
    r"mô\s+tả|mo\s+ta"
)


def _extract_labeled_value(message: str, labels: str) -> str | None:
    match = re.search(
        rf"(?:^|[,;\n])\s*(?:{labels})\s*(?:là\s+|la\s+|[:=\-]\s*)(.+)",
        message.strip(), flags=re.I,
    )
    if not match:
        return None
    value = re.split(rf"[,;\n]\s*(?=(?:{FIELD_LABELS})\b)", match.group(1), maxsplit=1, flags=re.I)[0]
    return value.strip(" \t\r\n.,;:\"'") or None


def _is_generic_product_command(message: str) -> bool:
    text = _plain(message).strip(" .!?")
    if re.search(r'\b(?:dang|dua|tao|them)\b', text) and re.search(
        r'\b(?:san pham nay|mat hang nay|anh nay|cai nay|len san|len shop)\b', text
    ):
        return True
    if re.match(r"^(?:(?:hay|vui long|lam on|ban)\s+)?(?:dang|tao|them|dua)\s+"
                r"(?:san pham|mat hang)\s+(?:nay|do|nay len|tu anh|trong anh)\b", text):
        return True
    return bool(re.fullmatch(
        r"(?:(?:hay|vui long|lam on)\s+)?(?:dang|tao|them|dua)\s+"
        r"(?:san pham|mat hang)(?:\s+(?:nay|moi|tu anh|trong anh))?"
        r"(?:\s+(?:len(?:\s+(?:san|shop))?|vao(?:\s+(?:san|shop))?|"
        r"giup(?:\s+(?:minh|toi|em))?|cho\s+(?:minh|toi|em)|duoc|khong|di|nhe|nha))*",
        text,
    ))


def _is_publish_command(message: str) -> bool:
    text = _plain(message).strip(" .!?")
    return bool(re.fullmatch(
        r"(?:(?:xac nhan|dong y)\s+)?dang(?:\s+san pham)?(?:\s+nay)?"
        r"(?:\s+len(?:\s+(?:san|shop))?)?(?:\s+(?:giup minh|di|nhe))?",
        text,
    ))


def _wants_ai_description(message: str) -> bool:
    text = _plain(message).strip(" .!?")
    return bool(
        text in {_plain(item) for item in AI_DESCRIPTION_PHRASES}
        or re.search(r"\b(?:ai|sellerpilot)\b.{0,25}\b(?:viet|soan|tao)\b", text)
        or re.search(r"\b(?:viet|soan|tao)\b.{0,25}\b(?:mo ta|bang ai)\b", text)
        or re.search(r"\b(?:viet|soan|tao|toi uu|sua)\b.{0,40}\b(?:caption|tieu de|noi dung)\b", text)
        or re.search(r"\btu\s+(?:viet|soan)\b", text)
        or re.search(r"\b(?:caption|tieu de|noi dung)\b.{0,35}\b(?:viet|soan|sua|hay hon)\b", text)
    )


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
    if _is_generic_product_command(message) or _wants_ai_description(message):
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


def _description_value(message: str) -> str | None:
    if _wants_ai_description(message) or _is_publish_command(message) or _is_generic_product_command(message):
        return None
    value = _extract_labeled_value(message, r"mô\s+tả|mo\s+ta") or message.strip()
    return value.strip(" \t\r\n") or None


def _extract_labeled_stock(message: str) -> int | None:
    match = re.search(
        r"\b(?:tồn(?:\s+kho)?|ton(?:\s+kho)?|số\s+lượng|so\s+luong|sl)\s*"
        r"(?:là\s+|la\s+|[:=\-]\s*)?([0-9]{1,7})\b",
        message, flags=re.I,
    )
    return int(match.group(1)) if match else None


def _extract_labeled_price(message: str) -> int | None:
    value = _extract_labeled_value(message, r"giá(?:\s+bán)?|gia(?:\s+ban)?")
    if not value:
        return None
    return extract_price(normalize_text(value), sku=None)


def _apply_explicit_details(draft, message: str, categories: list[dict]) -> set[str]:
    """Apply only clearly labelled facts; never turn an instruction into catalog copy."""
    changed: set[str] = set()
    if draft.name is None:
        name = _extract_labeled_value(message, r"tên(?:\s+sản phẩm)?|ten(?:\s+san pham)?")
        name = name or _command_product_name(message)
        if name and _candidate_product_name(name) is not None and 5 <= len(name) <= 200:
            draft.name = name
            changed.add("name")
    if draft.price_vnd is None and re.search(r"\b(?:giá|gia)(?:\s+bán|\s+ban)?\b", message, flags=re.I):
        price = _extract_labeled_price(message)
        if price is not None and 1_000 <= price <= 1_000_000_000:
            draft.price_vnd = price
            changed.add("price_vnd")
    if draft.stock is None:
        stock = _extract_labeled_stock(message)
        if stock is not None and 0 <= stock <= 1_000_000:
            draft.stock = stock
            changed.add("stock")
    if draft.category_id is None:
        category_text = _extract_labeled_value(message, r"ngành(?:\s+hàng)?|nganh(?:\s+hang)?|danh\s+mục|danh\s+muc")
        category = _match_category(category_text or draft.name or '', categories)
        if category:
            draft.category_id, draft.category_name = category["id"], category["name"]
            changed.add("category_id")
    if draft.description is None:
        description = _extract_labeled_value(message, r"mô\s+tả|mo\s+ta")
        if description and not _wants_ai_description(description) and len(description) >= 10:
            draft.description = description[:10_000]
            changed.add("description")
    return changed


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
        "Bách Hóa Online": ("bach hoa", "thuc pham", "do uong", "banh keo"),
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
    return f"UTE MALL có {len(names)} ngành hàng. Bạn chọn một nhóm:\n\n{first}\n\n{second}"


def _question_for(field: str, categories: list[dict]) -> str:
    return {
        "name": "Ảnh đã nằm trong bản nháp và **chưa được đăng**. Tên sản phẩm hiển thị với người mua là gì?",
        "price_vnd": "Giá bán của sản phẩm là bao nhiêu? Ví dụ: **249.000đ**.",
        "stock": "Số lượng tồn kho ban đầu là bao nhiêu?",
        "category_id": _category_question(categories),
        "description": "Bạn gửi mô tả sản phẩm, hoặc nhắn **AI tự viết** để mình soạn từ thông tin đã có.",
    }[field]


def _edit_ready_draft(draft, message, shop):
    text = normalize_text(message)
    name = _extract_labeled_value(message, r"tên(?:\s+sản phẩm)?|ten(?:\s+san pham)?")
    if name and 5 <= len(name) <= 200:
        draft.name = name
        draft.updated_at = datetime.utcnow()
        return True
    description = _extract_labeled_value(message, r"mô\s+tả|mo\s+ta")
    if description and len(description) >= 10 and not _wants_ai_description(description):
        draft.description = description[:10_000]
        draft.updated_at = datetime.utcnow()
        return True
    if any(word in text for word in ("giá", "gia")):
        value = extract_price(text, sku=None)
        if value is not None and 1_000 <= value <= 1_000_000_000:
            draft.price_vnd = value
            draft.updated_at = datetime.utcnow()
            return True
    if any(word in text for word in ("tồn", "ton", "số lượng", "so luong")):
        value = _extract_stock(text)
        if value is not None and 0 <= value <= 1_000_000:
            draft.stock = value
            draft.updated_at = datetime.utcnow()
            return True
    category = _match_category(message, shop.product_categories())
    if category:
        draft.category_id, draft.category_name = category["id"], category["name"]
        draft.updated_at = datetime.utcnow()
        return True
    return False


def _ready_answer(draft, prefix="Mình đã chuẩn bị xong bản nháp."):
    return (
        f"{prefix}\n\n"
        f"• **{draft.name}**\n"
        f"• Giá: **{draft.price_vnd:,}đ**\n"
        f"• Tồn kho: **{draft.stock}**\n"
        f"• Ngành hàng: **{draft.category_name}**\n\n"
        "Bạn kiểm tra thẻ bên dưới rồi bấm **Đăng sản phẩm**. Chưa có gì được đăng ở bước này."
    ).replace(f"{draft.price_vnd:,}", f"{draft.price_vnd:,}".replace(",", "."))
