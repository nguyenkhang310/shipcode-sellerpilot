"""AI and LLM Guardrails for Gemini & local models.
Implements Cloudflare security-audit-skill AI-AND-LLM.md specifications:
- Prompt injection & jailbreak detection
- PII / sensitive data redaction prior to outbound API calls
- Tool-calling Human-in-the-loop authorization gates
"""
import re
from typing import Any

# Signatures for prompt injection & instruction overrides
INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior)\s+(instructions|directives|prompts)", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?(previous|prior)\s+(instructions|system\s+prompt)", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(an?\s+)?(unrestricted|jailbroken|dan|root|admin)", re.IGNORECASE),
    re.compile(r"(reveal|print|leak|output|dump)\s+(your\s+)?(system\s+prompt|secret|api[_\s]?key)", re.IGNORECASE),
    re.compile(r"bỏ\s+qua\s+(toàn\s+bộ\s+)?(chỉ\s+dẫn|hướng\s+dẫn|quy\s+tắc)\s+(trước|hệ\s+thống)", re.IGNORECASE),
    re.compile(r"in\s+(ra\s+)?(toàn\s+bộ\s+)?(system\s+prompt|mật\s+khẩu|api\s+key|token)", re.IGNORECASE),
]

# Sensitive PII patterns
EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
VN_PHONE_PATTERN = re.compile(r"(?:\+84|0)[35789]\d{8}\b")
BEARER_TOKEN_PATTERN = re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/]+=*", re.IGNORECASE)
API_KEY_PATTERN = re.compile(r"(?:api[_-]?key|secret|password)[\"'\s:=]+([A-Za-z0-9_\-]{16,})", re.IGNORECASE)

# Dangerous mutating tools requiring explicit human confirmation
CRITICAL_TOOLS = {
    "update_price",
    "apply_price_change",
    "delete_product",
    "publish_draft",
    "modify_stock",
    "cancel_order",
}

def detect_prompt_injection(prompt: str) -> bool:
    """Returns True if the input contains prompt injection or jailbreak indicators."""
    if not prompt or not isinstance(prompt, str):
        return False
    for pattern in INJECTION_PATTERNS:
        if pattern.search(prompt):
            return True
    return False

def sanitize_ai_prompt(prompt: str) -> str:
    """Neutralizes detected prompt injection by escaping / flagging, or raises/strips."""
    if detect_prompt_injection(prompt):
        return "[CANH_BAO_BAO_MAT: Phát hiện chuỗi lệnh cố gắng ghi đè hướng dẫn hệ thống. Nội dung đã bị vô hiệu hóa an toàn.]"
    return prompt

def redact_sensitive_pii(text: str) -> str:
    """Masks email addresses, Vietnamese phone numbers, and bearer tokens before sending context to AI."""
    if not text or not isinstance(text, str):
        return text
    scrubbed = EMAIL_PATTERN.sub("[REDACTED_EMAIL]", text)
    scrubbed = VN_PHONE_PATTERN.sub("[REDACTED_PHONE]", scrubbed)
    scrubbed = BEARER_TOKEN_PATTERN.sub("Bearer [REDACTED_TOKEN]", scrubbed)
    return scrubbed

def validate_tool_execution(tool_name: str, arguments: dict[str, Any], confirmed_by_user: bool = False) -> tuple[bool, str]:
    """Enforces human-in-the-loop confirmation for any destructive or financial tool call."""
    if tool_name in CRITICAL_TOOLS and not confirmed_by_user:
        return False, f"Thao tác nhạy cảm '{tool_name}' bắt buộc phải có sự xác nhận rõ ràng của chủ shop trước khi thực thi."
    return True, "Thao tác hợp lệ."
