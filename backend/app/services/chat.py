import json
import re
from uuid import uuid4
from datetime import date, datetime
from time import perf_counter
from typing import Any

from sqlalchemy.orm import Session

from app.ai.contracts import AIProvider, AIProviderError, ParsedCommand
from app.ai.fallback import (
    extract_day,
    extract_price,
    extract_sku,
    extract_threshold,
    normalize_text,
    parse_fallback,
)
from app.integrations.ute_mall import ShopItemNotFoundError, UTEMallRepository
from app.integrations import management
from app.services.conversations import recent_runs, resolve_message, history_messages
from app.models.agent_run import AgentRun
from app.services.advisor import (enrich_advice, forget_memory, is_forget_request,
                                  read_memory, pricing_reply, shop_context)
from app.services.seller_tools import (
    PriceUnchangedError,
    create_price_proposal,
    proposal_to_dict,
)


async def handle_chat(
    session: Session,
    shop: UTEMallRepository,
    ai_provider: AIProvider,
    *,
    message: str,
    conversation_id: str | None = None,
) -> dict[str, Any]:
    started_at = perf_counter()
    today = datetime.now(shop.timezone).date()
    mode = "ai"
    provider_name = getattr(ai_provider, "provider", "ollama")
    natural_responses = bool(getattr(ai_provider, "natural_responses", False))
    model_name: str | None = None
    fallback_reason: str | None = None
    runs = recent_runs(session, shop, conversation_id, limit=24)
    reset_at = read_memory(session, shop, 'system').get('reset_at')
    if reset_at:
        runs = [run for run in runs if run.created_at >= datetime.fromisoformat(reset_at)]
    last_reset = next((i for i in range(len(runs) - 1, -1, -1)
                       if runs[i].tool_name == 'forget_assistant_memory'), None)
    if last_reset is not None:
        runs = runs[last_reset + 1:]
    conversation_id = str(conversation_id or uuid4())
    resolved = resolve_message(message, runs)
    history = history_messages(runs)
    simple = simple_reply(message, runs)
    classifier_input = resolved
    if history:
        classifier_input = ("Lịch sử tham khảo:\n" + "\n".join(row["role"] + ": " + row["content"][:240] for row in history[-4:])
                            + "\n\nTIN NHẮN HIỆN TẠI:\n" + resolved)

    direct = parse_fallback(resolved, today=today)
    forgetting = is_forget_request(message)
    skip_classifier = callable(getattr(ai_provider, "respond", None)) and (
        direct.intent == "sales_advice"
        or natural_responses and direct.intent in (
            "shop_summary", "inventory_query", "product_search"
        )
        or natural_responses and direct.intent == "unknown"
    )
    if skip_classifier:
        # Strong local matches need one grounded generation, not a second model
        # round-trip merely to rediscover their intent.
        command = direct
        model_name = getattr(ai_provider, "model", None)
    else:
        try:
            classification = await ai_provider.classify(classifier_input, today=today)
            command = enrich_ai_command(
                classification.command, message=resolved, today=today,
                prefer_model_intent=bool(getattr(ai_provider, "prefer_model_intent", False)),
            )
            provider_name = classification.provider
            model_name = classification.model
        except AIProviderError as error:
            command = direct
            mode = "fallback"
            provider_name = "deterministic_parser"
            fallback_reason = error.reason

    if simple:
        command = ParsedCommand(intent="unknown")
    result = execute_command(session, shop, command)
    preferences = read_memory(session, shop, 'shop')
    if preferences:
        result['facts']['seller_preferences'] = preferences
    if forgetting:
        forget_memory(session, shop)
        command = ParsedCommand(intent='unknown')
        result = response('Mình đã xóa bộ nhớ cá nhân hóa và các chi phí đã ghi nhớ của shop. Lịch sử chat vẫn còn; từ giờ mình sẽ hỏi lại thông tin cần thiết.',
                          'forget_assistant_memory', {}, {'seller_preferences': {}})
    elif callable(getattr(ai_provider, 'respond', None)) and command.intent in ('sales_advice', 'unknown') and not simple and not is_casual_message(message):
        if command.intent == 'unknown':
            result['facts'].pop('supported_intents', None)
            result['facts'].update(shop_context(shop))
        advisor = await enrich_advice(session, shop, ai_provider, message=message,
            resolved=resolved, conversation_id=conversation_id, runs=runs, history=history)
        result['facts'].update({key: value for key, value in advisor.items() if value is not None})
        if advisor['pricing_analysis']:
            command = ParsedCommand(intent='sales_advice')
            result.update(answer=pricing_reply(advisor['pricing_analysis']), tool='calculate_pricing',
                          tool_arguments=advisor['pricing_analysis']['inputs'])
    # Price proposals and confirmations retain the backend's exact wording.
    # OpenCode may phrase read-only tool results naturally using their actual facts.
    can_generate = command.intent in ("sales_advice", "unknown") or (
        natural_responses and command.intent != "change_price"
    )
    confirmation_reply = bool(simple and runs and any(
        word in normalize_text(message) for word in ("xác nhận", "đồng ý", "confirm")
    ))
    if can_generate and not forgetting:
        if simple and (not natural_responses or confirmation_reply or mode != "ai"):
            result["answer"] = simple
        elif hasattr(ai_provider, "respond") and mode == "ai":
            try:
                generated = await ai_provider.respond(message, history=history, facts=result["facts"])
                # A language-only response cannot claim a write. Only the proposal
                # confirmation endpoint can update shop data.
                if re.search(r"\bđã\s+(?:cập nhật|đổi giá|thay đổi giá|đăng bán|đăng sản phẩm|gửi tin|xác nhận đơn|hủy đơn)", generated, re.IGNORECASE):
                    raise AIProviderError("invalid_response")
                if re.search(r"không cần (?:xử lý|xác nhận|gửi).{0,20}lại|lớn nhất trong tasks", generated, re.IGNORECASE):
                    raise AIProviderError("invalid_response")
                generated = re.sub(r"\s*\((?:pending_orders|packing_orders|shipping_orders)\)", "", generated)
                generated = re.sub(r"\bstock\s*[=:]?\s*(\d+)", r"còn \1", generated, flags=re.IGNORECASE)
                result["answer"] = generated
            except AIProviderError as error:
                mode, provider_name, fallback_reason = "fallback", "deterministic_parser", error.reason
    if mode == "fallback" and natural_responses and command.intent == "unknown" and not simple and not forgetting:
        result["answer"] = (
            "Mình chưa kết nối được Muse Spark lúc này. Bạn có thể thử lại sau; "
            "các câu hỏi trực tiếp về doanh số, SKU và tồn kho vẫn đọc được dữ liệu shop."
        )
    if forgetting:
        mode, provider_name, model_name, fallback_reason = 'ai', 'deterministic_parser', None, None
    result["suggestions"] = suggestions_for(command, result)
    elapsed_ms = max(0, int(round((perf_counter() - started_at) * 1_000)))

    run = AgentRun(
        conversation_id=conversation_id,
        shop_slug=shop.seller_shop_slug or "local",
        proposal_id=result["proposal"]["id"] if result["proposal"] else None,
        product_draft_id=None,
        message=message,
        answer=result["answer"],
        intent=command.intent,
        mode=mode,
        status="completed" if mode == "ai" else "fallback",
        provider=provider_name,
        model=model_name,
        fallback_reason=fallback_reason,
        tool_name=result["tool"],
        tool_arguments_json=json.dumps(result.pop("tool_arguments"), ensure_ascii=False),
        facts_json=json.dumps(result["facts"], ensure_ascii=False, default=str),
        elapsed_ms=elapsed_ms,
    )
    session.add(run)
    session.commit()
    session.refresh(run)

    return {
        "run_id": run.id,
        "conversation_id": conversation_id,
        "intent": command.intent,
        "mode": mode,
        "provider": provider_name,
        "model": model_name,
        "fallback_reason": fallback_reason,
        "integration_mode": "local_store",
        **result,
        "product_draft": None,
    }


def enrich_ai_command(
    command: ParsedCommand,
    *,
    message: str,
    today: date,
    prefer_model_intent: bool = False,
) -> ParsedCommand:
    """Verify exact identifiers and amounts from the original seller message."""

    fallback = parse_fallback(message, today=today)
    if fallback.intent != "unknown" and (not prefer_model_intent or fallback.intent == "change_price"):
        # Exact business instructions outrank a mistaken classifier prediction.
        command = fallback
    data = command.model_dump()
    normalized_message = normalize_text(message)
    exact_sku = extract_sku(normalized_message)

    # Never let model transcription change an explicit SKU or monetary value.
    # An invented model SKU must never choose a product for an action.
    data["sku"] = exact_sku
    if command.intent == "change_price":
        exact_price = extract_price(normalized_message, sku=exact_sku or data["sku"])
        data["new_price_vnd"] = exact_price

    if fallback.intent == command.intent:
        if fallback.inventory_scope is not None:
            data["inventory_scope"] = fallback.inventory_scope

    if command.intent == "shop_summary":
        data["day"] = extract_day(normalized_message, today=today)
        data["days"] = fallback.days or command.days
    if fallback.intent == "product_search":
        data["query"] = fallback.query
    if command.intent == "inventory_query" and data["inventory_scope"] == "low_stock":
        data["low_stock_threshold"] = extract_threshold(normalized_message)

    return ParsedCommand.model_validate(data)


def execute_command(
    session: Session,
    shop: UTEMallRepository,
    command: ParsedCommand,
) -> dict[str, Any]:
    if command.intent == "shop_summary":
        if command.days and command.days > 1:
            stats = management.dashboard(shop, command.days)
            facts = {key: stats[key] for key in ("days", "from_date", "to_date", "order_value_vnd", "order_count", "average_order_vnd", "delivered_value_vnd", "change_percent")}
            answer = (f"Trong **{command.days} ngày qua**, shop có **{stats['order_count']} đơn** hợp lệ.\n\n"
                      f"• Giá trị đơn hàng: **{format_vnd(stats['order_value_vnd'])}**\n"
                      f"• Giá trị trung bình: **{format_vnd(stats['average_order_vnd'])}/đơn**\n"
                      f"• Giá trị đơn đã giao: **{format_vnd(stats['delivered_value_vnd'])}**\n\n"
                      "Giá trị đơn hàng chưa phải toàn bộ tiền đã thu; không bao gồm đơn hủy hoặc hoàn.")
            return response(answer, "get_shop_summary", {"days": command.days}, facts)
        summary_day = command.day or datetime.now(shop.timezone).date()
        summary = shop.summary(summary_day, as_of=datetime.now(shop.timezone) if command.days == 1 else None)
        facts = {
            "date": summary["date"],
            "timezone": summary["timezone"],
            "order_count": summary["order_count"],
            "order_value_vnd": summary["revenue_vnd"],
            "pending_count": summary["pending_count"],
            "cancelled_count": summary["cancelled_count"],
            "status_counts": summary["status_counts"],
        }
        answer = (f"Ngày **{format_day(summary['date'])}**, shop có **{summary['order_count']} đơn** hợp lệ.\n\n"
                  f"• Giá trị đơn hàng: **{format_vnd(summary['revenue_vnd'])}**\n"
                  f"• Chờ xử lý: **{summary['pending_count']} đơn**\n"
                  f"• Đã hủy: **{summary['cancelled_count']} đơn**\n\n"
                  "Đây là giá trị đơn, chưa phải toàn bộ tiền đã thu.")
        return response(answer, "get_shop_summary", {"date": summary["date"]}, facts)

    if command.intent == "inventory_query" and command.inventory_scope == "low_stock":
        threshold = (
            command.low_stock_threshold
            if command.low_stock_threshold is not None
            else 5
        )
        items = shop.low_stock(threshold, 50)
        compact_items = [{
            "sku": item["sku"],
            "product_name": item["product_name"],
            "variant_title": item["variant_title"],
            "stock": item["stock"],
            "price_vnd": item["price_vnd"],
        } for item in items]
        if compact_items:
            preview = "\n".join(f"• **{item['product_name']}** — còn **{item['stock']}**\n  SKU: {item['sku']}" for item in compact_items[:5])
            suffix = "" if len(compact_items) <= 5 else f"\n\nCòn {len(compact_items) - 5} SKU khác trong danh sách."
            qualifier = "Ít nhất " if len(items) == 50 else ""
            answer = f"{qualifier}**{len(compact_items)} SKU** có tồn kho không quá {threshold}:\n\n{preview}{suffix}\n\nBạn muốn kiểm tra kỹ sản phẩm nào?"
        else:
            answer = f"Không có SKU nào tồn kho không quá {threshold}."
        facts = {
            "threshold": threshold,
            "count": len(compact_items),
            "items": compact_items,
        }
        return response(
            answer,
            "get_low_stock",
            {"threshold": threshold, "limit": 50},
            facts,
        )

    if command.intent == "inventory_query" and command.inventory_scope == "overview":
        facts = shop.inventory_overview(low_stock_threshold=5)
        answer = (
            "Tồn kho hiện tại của shop:\n\n"
            f"• **{facts['active_product_count']} sản phẩm** đang bán\n"
            f"• **{facts['sku_count']} SKU** với **{format_number(facts['unit_count'])} sản phẩm** trong kho\n"
            f"• **{facts['low_stock_count']} SKU** sắp hết (còn 1–5)\n"
            f"• **{facts['out_of_stock_count']} SKU** đã hết hàng\n"
            f"• Giá trị hàng theo giá bán hiện tại: **{format_vnd(facts['retail_value_vnd'])}**\n\n"
            "Bạn muốn xem danh sách sắp hết hay kiểm tra một SKU cụ thể?"
        )
        return response(answer, "get_inventory_overview", {}, facts)

    if command.intent == "inventory_query":
        if not command.sku:
            return response(
                "Bạn muốn kiểm tra sản phẩm nào? Gửi mình mã SKU, hoặc tên để mình tìm trong shop.",
                None,
                {},
                {"missing_fields": ["sku"]},
            )
        try:
            item = shop.get_item_by_sku(command.sku)
        except ShopItemNotFoundError:
            return response(
                f"Mình chưa tìm thấy mã **{command.sku}** trong shop đang kết nối. Bạn kiểm tra lại mã hoặc cho mình tên sản phẩm nhé.",
                "get_inventory",
                {"sku": command.sku},
                {"sku": command.sku, "found": False},
            )
        variant = f" ({item['variant_title']})" if item["variant_title"] else ""
        active_text = "đang bán" if item["is_active"] else "đang ngừng bán"
        answer = (f"**{item['product_name']}**{variant}\n\n"
                  f"• Tồn kho: **{item['stock']} sản phẩm**\n"
                  f"• Giá bán: **{format_vnd(item['price_vnd'])}**\n"
                  f"• Trạng thái: {active_text}\n\nSKU: {item['sku']}"
                  + ("\n\nMẫu này sắp hết hàng. Bạn nên cân nhắc bổ sung trước khi chạy ưu đãi." if item["stock"]<=5 else ""))
        return response(answer, "get_inventory", {"sku": item["sku"]}, item)

    if command.intent == "change_price":
        missing_fields = []
        if not command.sku:
            missing_fields.append("sku")
        if command.new_price_vnd is None:
            missing_fields.append("new_price_vnd")
        if missing_fields:
            return response(
                ("Bạn muốn đặt giá mới bao nhiêu cho mã " + command.sku + "?" if command.sku else
                 "Bạn muốn đổi giá sản phẩm nào? Gửi mình SKU để chọn đúng hàng."),
                None,
                {},
                {"missing_fields": missing_fields, "sku": command.sku},
            )
        if command.new_price_vnd <= 0 or command.new_price_vnd > 1_000_000_000:
            return response(
                "Giá mới phải lớn hơn 0 và không vượt quá 1.000.000.000đ.",
                None,
                {},
                {"sku": command.sku, "new_price_vnd": command.new_price_vnd, "valid": False},
            )
        try:
            proposal = create_price_proposal(
                session,
                shop,
                sku=command.sku,
                new_price_vnd=command.new_price_vnd,
            )
        except ShopItemNotFoundError:
            return response(
                f"Không tìm thấy SKU {command.sku}; mình chưa tạo đề xuất nào.",
                "get_inventory",
                {"sku": command.sku},
                {"sku": command.sku, "found": False},
            )
        except PriceUnchangedError:
            return response(
                f"SKU {command.sku} đã có giá {format_vnd(command.new_price_vnd)}, nên không cần cập nhật.",
                "get_inventory",
                {"sku": command.sku},
                {"sku": command.sku, "current_price_vnd": command.new_price_vnd, "unchanged": True},
            )
        proposal_data = proposal_to_dict(proposal)
        facts = {
            "sku": proposal.sku,
            "product_name": proposal.product_name,
            "current_price_vnd": proposal.old_price_vnd,
            "new_price_vnd": proposal.new_price_vnd,
        }
        answer = (
            f"Mình tìm thấy SKU {proposal.sku} — {proposal.product_name}. "
            f"Mức giá bạn đề xuất là **{format_vnd(proposal.new_price_vnd)}**, "
            f"hiện tại **{format_vnd(proposal.old_price_vnd)}**. "
            "Mình chưa thay đổi giá. Bạn kiểm tra và xác nhận ở thẻ bên dưới nhé."
        )
        return response(
            answer,
            "create_price_proposal",
            {"sku": proposal.sku, "new_price_vnd": proposal.new_price_vnd},
            facts,
            proposal_data,
        )

    if command.intent == "product_search":
        query = (command.query or "").strip()
        if not query:
            return response("Bạn đang tìm sản phẩm nào? Cho mình tên hoặc loại hàng nhé.", None, {}, {"missing_fields": ["query"]})
        found = management.products(shop, query, limit=8)
        lines = "\n\n".join(f"**{i+1}. {p['name']}**\n{format_vnd(round(p['price_vnd']))} · Kho {p['stock']}\nSKU: {p['sku']}" for i,p in enumerate(found["items"]))
        answer = (f"Mình tìm thấy **{found['total']} sản phẩm** khớp “{query}” trong shop.\n\n{lines}\n\nBạn muốn kiểm tra hoặc điều chỉnh sản phẩm nào?" if found["items"] else
                  f"Chưa có sản phẩm khớp “{query}” trong shop. Bạn thử tên ngắn hơn hoặc mã SKU nhé.")
        return response(answer, "search_products", {"query": query, "limit": 8}, found)

    if command.intent == "sales_advice":
        facts = shop_context(shop, command.days or 7)
        facts.update(period_days=facts['period']['days'],
                     order_value_vnd=facts['period']['order_value_vnd'],
                     order_count=facts['period']['order_count'])
        if command.sku:
            try: facts["selected_product"] = shop.get_item_by_sku(command.sku)
            except ShopItemNotFoundError: facts["selected_product"] = {"sku": command.sku, "found": False}
        answer = (f"Từ dữ liệu hiện tại, mình đề xuất ưu tiên:\n\n"
                  f"• **Xử lý đơn:** có {facts['tasks']['pending_orders']} đơn chờ xác nhận.\n"
                  f"• **Kiểm tra tồn kho:** {facts['tasks']['low_stock_products']} sản phẩm còn không quá 5.\n"
                  f"• **Chăm sóc khách hàng:** {facts['tasks']['unanswered_reviews']} đánh giá chưa phản hồi.\n\n"
                  "Bạn muốn mình đi sâu vào phần nào?")
        return response(answer, "get_shop_insights", {"days": 7}, facts)

    return response(
        "Mình chưa hiểu rõ việc bạn muốn làm. Bạn muốn xem tình hình bán hàng, tìm sản phẩm, "
        "kiểm tra kho hay chuẩn bị nội dung bán hàng? Nói tự nhiên như bạn đang nhờ một cộng sự nhé.",
        None,
        {},
        {"supported_intents": ["shop_summary", "inventory_query", "change_price", "product_search", "sales_advice"]},
    )


def simple_reply(message, runs):
    text = normalize_text(message).strip("!.? ")
    if text in {"chào", "chào bạn", "xin chào", "hello", "hi", "alo"}:
        return "Chào bạn, mình là SellerPilot của ShipCode. Mình ở đây để cùng bạn quản lý shop — từ xem tình hình bán hàng đến kiểm tra sản phẩm và chuẩn bị thay đổi giá. Hôm nay bạn muốn bắt đầu từ đâu?"
    if text in {"cảm ơn", "cảm ơn bạn", "thanks", "ok", "oke", "được rồi"}:
        return "Rất sẵn lòng. Khi cần xem số liệu hoặc xử lý việc tiếp theo cho shop, cứ nhắn mình nhé."
    if runs and any(run.proposal_id for run in runs[-3:]) and re.search(r'^(?:(?:mình|tôi)\s+)?(?:xác nhận|đồng ý|confirm)\b', text):
        return "Để tránh thay đổi nhầm, bạn hãy bấm **Xác nhận đổi giá** trên đúng thẻ đề xuất. Tin nhắn này chưa thay đổi dữ liệu."
    return None


def is_casual_message(message):
    """Recognize obvious conversation without treating day words as shop reports."""
    text = normalize_text(message)
    return any(phrase in text for phrase in (
        "nói chuyện", "noi chuyen", "tâm sự", "tam su", "hơi mệt", "hoi met",
        "mệt quá", "met qua", "buồn quá", "buon qua", "chán quá", "chan qua",
        "bạn khỏe không", "ban khoe khong", "bạn là ai", "ban la ai",
    ))


def suggestions_for(command, result):
    pricing = result['facts'].get('pricing_analysis')
    if pricing:
        if pricing['status'] == 'missing_cost':
            return ['Mình cần cung cấp những chi phí nào để tính giá?', 'Biên lợi nhuận khác lời trên giá vốn thế nào?']
        return ['Nếu giảm giá 10% thì lời còn bao nhiêu?', 'Gợi ý cách tăng lợi nhuận mà không tăng giá']
    if command.intent == 'sales_advice':
        return ['Lập kế hoạch hành động 7 ngày cho shop', 'Đề xuất nào phù hợp với ngân sách nhỏ?', 'Giải thích rõ hơn phần quan trọng nhất']
    sku = result["facts"].get("sku")
    if command.intent == "inventory_query" and sku and result["facts"].get("found") is not False:
        return [f"Viết mô tả bán hàng cho SKU {sku}", "Shop có sản phẩm nào sắp hết?"]
    if command.intent == "product_search" and result["facts"].get("items"):
        return [f"SKU {result['facts']['items'][0]['sku']} còn bao nhiêu?", "Hôm nay shop bán hàng thế nào?"]
    if command.intent == "change_price":
        return ["Kiểm tra lại giá và tồn kho mã này", "Tình hình shop hôm nay"]
    return ["Shop có sản phẩm nào sắp hết?", "Tư vấn việc cần ưu tiên hôm nay", "Tìm bàn phím"]


def response(
    answer: str,
    tool: str | None,
    tool_arguments: dict[str, Any],
    facts: dict[str, Any],
    proposal: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "answer": answer,
        "tool": tool,
        "tool_arguments": tool_arguments,
        "facts": facts,
        "proposal": proposal,
    }


def format_vnd(value: int) -> str:
    return format_number(value) + "đ"


def format_number(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def format_day(iso_day: str) -> str:
    return datetime.strptime(iso_day, "%Y-%m-%d").strftime("%d/%m/%Y")
