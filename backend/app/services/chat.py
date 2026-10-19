import json
import logging
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
    reporting_days,
)
from app.ai.money import money_mentions, plain
from app.ai.catalog_query import catalog_lookup
from app.ai.text import assistant_text
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
from app.services.seller_voice import read_reply
from app.services.business_advisor import (attach_business_brief, planning_fallback,
                                          business_reply_issue, business_correction)

logger = logging.getLogger(__name__)


def reply_issue(answer: str, facts: dict | None = None, *, seller_context: str = '') -> str | None:
    if re.search(r'đạt giới hạn số bước|hết bước xử lý|maximum steps reached', answer, re.I):
        return 'internal_agent_message'
    for match in re.finditer(r"\bđã\s+(?:cập nhật|đổi giá|thay đổi giá|đăng bán|đăng sản phẩm|đăng video|lên lịch|chạy quảng cáo|gửi tin|xác nhận đơn|hủy đơn)", answer, re.IGNORECASE):
        prefix = answer[:match.start()].rstrip()
        # "Nếu bạn đã đăng sản phẩm..." is a condition, not an executed write.
        if not re.search(r'\b(?:nếu|khi|sau khi)(?:\s+(?:bạn|mình|shop|chủ shop))?\s*$', prefix, re.IGNORECASE):
            return 'unexecuted_write_claim'
    if re.search(r"không cần (?:xử lý|xác nhận|gửi).{0,20}lại|lớn nhất trong tasks", answer, re.IGNORECASE):
        return 'unsupported_fulfillment_claim'
    if facts and not facts.get('shop', {}).get('created_at') and not re.search(
            r'mới\s+(?:mở|thành lập|hoạt động)|shop\s+mới', seller_context, re.I):
        for match in re.finditer(r'(?:shop|gian hàng)\s+(?:của bạn\s+)?mới\s+(?:mở|thành lập|hoạt động|nên)', answer, re.I):
            if not re.search(r'(?:nếu|khi|giả sử)(?:\s+đây là)?\s*$', answer[:match.start()], re.I):
                return 'unsupported_shop_age'
    pricing = facts.get('pricing_analysis') if facts else None
    if pricing:
        # Keep stated profit tied to Decimal calculations while allowing the
        # model to explain fee deductions and discuss hypothetical sale prices.
        allowed_profit = {item['profit_per_unit_vnd'] for key in ('at_selling_price', 'after_discount', 'target_price')
                          if (item := pricing.get(key)) and 'profit_per_unit_vnd' in item}
        text = normalize_text(answer.replace('*', '').replace('`', ''))
        for mention in money_mentions(text):
            prefix = text[max(0, mention.start - 70):mention.start]
            states_profit = re.search(r'(?:tiền lời|lợi nhuận|lời|lãi)(?:\s+(?:gộp|ròng|ước tính|còn|khoảng|là|mỗi máy|mỗi sản phẩm|mỗi đơn|mỗi cái))*[\s:≈~=>-]*$', prefix)
            if mention.explicit and states_profit and mention.value not in allowed_profit:
                return 'unsupported_pricing_amount'
    return None


def fallback_explanation(reason: str | None) -> str:
    messages = {
        'invalid_response': 'Câu trả lời của AI chưa vượt qua kiểm tra nên mình chưa hiển thị. Bạn thử lại nhé; số liệu shop vẫn đọc được bình thường.',
        'provider_timeout': 'AI phản hồi quá lâu ở lượt này. Bạn thử lại nhé; các câu hỏi trực tiếp về doanh số và tồn kho vẫn đọc được dữ liệu shop.',
        'provider_rejected': 'Dịch vụ AI đang từ chối yêu cầu hoặc giới hạn lượt gọi. Bạn thử lại sau một chút nhé; dữ liệu shop vẫn truy cập được.',
        'free_model_unavailable': 'Model GLM miễn phí hiện chưa sẵn sàng trên OpenCode. Mình vẫn có thể đọc doanh số, SKU và tồn kho của shop.',
        'free_tier_restricted': 'OpenCode đang chặn model miễn phí trên đường gọi của SellerPilot và yêu cầu dùng trong OpenCode. Mình chưa có câu trả lời AI ở lượt này; doanh số và tồn kho của shop vẫn xem được.',
        'provider_rate_limited': 'AI đang đạt giới hạn lượt gọi. Bạn thử lại sau nhé; mình vẫn có thể đọc doanh số, SKU và tồn kho của shop.',
        'model_unavailable': 'Model AI hiện chưa sẵn sàng. Mình vẫn có thể đọc doanh số, SKU và tồn kho của shop.',
        'tool_not_allowed': 'Phản hồi AI có thao tác chưa được phép nên mình đã dừng lượt này. Chưa có thay đổi nào được thực hiện. Bạn thử diễn đạt lại yêu cầu nhé.',
    }
    return messages.get(reason, 'Mình chưa kết nối được dịch vụ AI lúc này. Bạn thử lại sau nhé; các câu hỏi trực tiếp về doanh số, SKU và tồn kho vẫn đọc được dữ liệu shop.')


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
    prepared_answer = None
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
    # A complete shop-wide read must not inherit a SKU merely because its
    # wording contains "giá trị" after a previous product discussion.
    current_command = parse_fallback(message, today=today)
    if is_exact_fact_question(message, current_command):
        resolved = message
    history = history_messages(runs)
    simple = simple_reply(message, runs)
    classifier_input = resolved
    if history:
        classifier_input = ("Lịch sử tham khảo:\n" + "\n".join(row["role"] + ": " + row["content"][:240] for row in history[-4:])
                            + "\n\nTIN NHẮN HIỆN TẠI:\n" + resolved)

    direct = parse_fallback(resolved, today=today)
    forgetting = is_forget_request(message)
    catalog_read = direct.intent == 'product_search' and catalog_lookup(message) is not None
    skip_classifier = catalog_read or callable(getattr(ai_provider, "respond", None)) and (
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
    direct_reply = catalog_read or bool(getattr(ai_provider, 'prefer_direct_facts', False)) and (
        bool(simple) or is_exact_fact_question(message, command)
    )
    if command.intent in ('sales_advice', 'unknown') and not command.days:
        days = reporting_days(message)
        if not days:
            for prior in reversed(runs):
                previous_facts = json.loads(prior.facts_json)
                days = previous_facts.get('period', {}).get('days') or previous_facts.get('days')
                if isinstance(days, int) and 1 <= days <= 30:
                    break
                days = None
        if days:
            command = command.model_copy(update={'days': days})
    result = execute_command(session, shop, command)
    preferences = read_memory(session, shop, 'shop')
    if preferences:
        result['facts']['seller_preferences'] = preferences
    if getattr(ai_provider, 'prefer_direct_facts', False):
        rendered = read_reply(result, today=today, preferences=preferences)
        if rendered is not None:
            result['answer'] = rendered
    if forgetting:
        forget_memory(session, shop)
        command = ParsedCommand(intent='unknown')
        result = response('Mình đã xóa bộ nhớ cá nhân hóa và các chi phí đã ghi nhớ của shop. Lịch sử chat vẫn còn; từ giờ mình sẽ hỏi lại thông tin cần thiết.',
                          'forget_assistant_memory', {}, {'seller_preferences': {}})
    elif callable(getattr(ai_provider, 'respond', None)) and command.intent in ('sales_advice', 'unknown') and not simple and not is_casual_message(message):
        if command.intent == 'unknown':
            result['facts'].pop('supported_intents', None)
            result['facts'].update(shop_context(shop, command.days or 7))
        connection_question = len(message) < 140 and re.search(r'kết nối|ket noi|offline|mất mạng|mat mang', message, re.I)
        if not connection_question:
            attach_business_brief(shop, result['facts'], message=message, history=history,
                                  preferences=preferences)
            advisor = await enrich_advice(session, shop, ai_provider, message=message,
                resolved=resolved, conversation_id=conversation_id, runs=runs, history=history,
                facts=result['facts'])
            prepared_answer = advisor.pop('_prepared_answer', None)
            result['facts'].update({key: value for key, value in advisor.items() if value is not None})
            prior_focus = result['facts'].get('business_advisory', {}).get('focus_product')
            brief = attach_business_brief(shop, result['facts'], message=message, history=history,
                                          preferences=advisor['seller_preferences'])
            if brief:
                if prior_focus != brief.get('focus_product'):
                    prepared_answer = None
                result['answer'] = planning_fallback(result['facts'])
                if command.intent == 'unknown':
                    command = command.model_copy(update={'intent': 'sales_advice'})
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
        if direct_reply:
            if simple:
                result['answer'] = simple
            mode, provider_name, model_name, fallback_reason = 'ai', 'deterministic_parser', None, None
        elif simple and (not natural_responses or confirmation_reply or mode != "ai"):
            result["answer"] = simple
        elif hasattr(ai_provider, "respond") and mode == "ai":
            try:
                response_facts = result['facts']
                for attempt in range(2):
                    generated = (prepared_answer if attempt == 0 and prepared_answer is not None else
                                 await ai_provider.respond(message, history=history, facts=response_facts))
                    generated = assistant_text(generated)
                    seller_context = '\n'.join([row['content'] for row in history if row['role'] == 'user'] + [message])
                    issue = reply_issue(generated, result['facts'], seller_context=seller_context)
                    issue = issue or business_reply_issue(generated, result['facts'], message=message,
                                                          seller_context=seller_context)
                    if not issue:
                        break
                    logger.warning('AI reply needs correction: reason=%s attempt=%s', issue, attempt + 1)
                    if attempt:
                        raise AIProviderError('invalid_response', stage=issue)
                    response_facts = {**result['facts'], 'reply_correction': {
                        'reason': issue,
                        'requirements': 'Viết lại dựa trên đúng số liệu. Chỉ đề xuất, không nói đã thực hiện thay đổi. Không suy đoán shop mới mở từ số đơn bằng 0. Mọi số tiền tính lời/giảm giá phải lấy đúng từ pricing_analysis. Đơn đang giao không phải đơn cần gửi lại. ' + business_correction(issue),
                    }}
                generated = re.sub(r"\s*\((?:pending_orders|packing_orders|shipping_orders)\)", "", generated)
                generated = re.sub(r"\bstock\s*[=:]?\s*(\d+)", r"còn \1", generated, flags=re.IGNORECASE)
                result["answer"] = generated
                provider_name = getattr(ai_provider, 'response_provider', provider_name)
                model_name = getattr(ai_provider, 'response_model', model_name)
            except AIProviderError as error:
                logger.warning('Chat used grounded fallback: reason=%s stage=%s', error.reason, error.stage or 'unknown')
                mode, provider_name, fallback_reason = "fallback", "deterministic_parser", error.reason
    if mode == "fallback" and natural_responses and command.intent == "unknown" and not simple and not forgetting:
        result["answer"] = fallback_explanation(fallback_reason)
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
        data['min_price_vnd'] = fallback.min_price_vnd
        data['max_price_vnd'] = fallback.max_price_vnd
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
        filters = {'min_price_vnd': command.min_price_vnd, 'max_price_vnd': command.max_price_vnd}
        found = management.products(shop, query, limit=8, **filters)
        found.update(query=query, **filters)
        lines = "\n\n".join(f"**{i+1}. {p['name']}**\n{format_vnd(round(p['price_vnd']))} · Kho {p['stock']}\nSKU: {p['sku']}" for i,p in enumerate(found["items"]))
        answer = (f"Mình tìm thấy **{found['total']} sản phẩm** khớp “{query}” trong shop.\n\n{lines}\n\nBạn muốn kiểm tra hoặc điều chỉnh sản phẩm nào?" if found["items"] else
                  f"Chưa có sản phẩm khớp “{query}” trong shop. Bạn thử tên ngắn hơn hoặc mã SKU nhé.")
        return response(answer, "search_products", {"query": query, "limit": 8, **filters}, found)

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
        return response(answer, "get_shop_insights", {"days": command.days or 7}, facts)

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
        return "Chào bạn, mình là SellerPilot của ShipCode. Hôm nay bạn muốn mình giúp gì cho shop?"
    if text in {"cảm ơn", "cảm ơn bạn", "thanks", "ok", "oke", "được rồi"}:
        return "Rất sẵn lòng. Khi cần xem số liệu hoặc xử lý việc tiếp theo cho shop, cứ nhắn mình nhé."
    if runs and any(run.proposal_id for run in runs[-3:]) and re.search(r'^(?:(?:mình|tôi)\s+)?(?:xác nhận|đồng ý|confirm)\b', text):
        return "Để tránh thay đổi nhầm, bạn hãy bấm **Xác nhận đổi giá** trên đúng thẻ đề xuất. Tin nhắn này chưa thay đổi dữ liệu."
    return None


def is_exact_fact_question(message, command):
    """Only complete, unambiguous read requests may bypass model wording.

    Extra analysis, instructions and follow-up text fail the full match and
    continue through the natural assistant. This never handles write actions.
    """
    text = plain(normalize_text(message)).strip(' ?!.')
    if command.intent == 'inventory_query':
        patterns = [
            r'(?:xem |kiem tra )?(?:ton kho|hang ton kho)(?: cua shop| shop)?',
            r'(?:shop (?:minh |toi )?co )?(?:nhung |cac )?san pham nao sap het(?: hang)?',
        ]
        if command.sku:
            patterns.append(r'(?:sku )?[a-z0-9._-]+ con bao nhieu(?: hang| san pham| chiec| cai)?')
    elif command.intent == 'shop_summary':
        # Parse complete read clauses, including the app's own starter prompt.
        # At most one distinct reporting period is allowed. Requests to explain,
        # compare, calculate hypothetical revenue or change data fail fullmatch.
        periods = re.findall(r'\b(?:hom nay|hom qua|(?:7|30) ngay(?: qua| gan day)?|tuan (?:nay|qua)|thang (?:nay|qua))\b', text)
        if len(set(periods)) > 1:
            return False
        body = re.sub(r'\b(?:hom nay|hom qua|(?:7|30) ngay(?: qua| gan day)?|tuan (?:nay|qua)|thang (?:nay|qua))\b', ' ', text)
        body = ' '.join(body.replace(',', ' ').split())
        subject = r'(?:shop(?: cua (?:toi|minh)| (?:toi|minh))? )?'
        count = r'(?:(?:co|ban duoc|nhan duoc) )?bao nhieu don(?: hang)?'
        value = r'(?:tong )?(?:doanh thu|doanh so|gia tri don(?: hang)?)(?: cua shop)?(?: (?:la |duoc )?bao nhieu)?'
        clause = rf'(?:{count}|{value})'
        if re.fullmatch(rf'{subject}{clause}(?: va {clause})?', body):
            return True
        patterns = [
            r'(?:doanh thu|doanh so|gia tri don)(?: cua shop)? (?:hom nay|hom qua|7 ngay qua|30 ngay qua)(?: (?:la |duoc )?bao nhieu)?',
            r'(?:hom nay|hom qua) (?:shop (?:toi |minh )?)?(?:co |ban duoc )?bao nhieu don(?: hang)?',
        ]
    elif command.intent == 'product_search':
        if catalog_lookup(message):
            return True
        # Short catalog lookups, including the home-screen quick action. A
        # second request or instruction continues through model interpretation.
        if re.search(r'\b(?:va|roi|nen|khong|ko|viet|phan tich|tu van|goi y|mo ta|giai thich|gia su|neu|bang)\b', text):
            return False
        return bool(command.query and len(command.query.split()) <= 5
                    and re.fullmatch(r'tim(?: kiem)?(?: san pham)? [a-z0-9][a-z0-9 ._-]{0,79}', text))
    else:
        return False
    return any(re.fullmatch(pattern, text) for pattern in patterns)


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
        brief = result['facts'].get('business_advisory')
        if brief:
            focus = brief.get('focus_product')
            sku = focus.get('sku') if focus else None
            return ([f"Viết kịch bản TikTok chi tiết cho SKU {sku}" if sku else "Chọn sản phẩm nào để quay video trước?",
                     "Cụ thể hơn", "Lập kế hoạch 7 ngày với một người thực hiện"]
                    if brief['mode'] != 'video_script' else
                    ["Viết thêm 2 câu mở đầu khác để thử", "Hướng dẫn đo hiệu quả từng video", "Lập kế hoạch nội dung 7 ngày"])
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
