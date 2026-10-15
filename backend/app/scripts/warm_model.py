"""Load the configured Ollama model before a live demo starts."""

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from app.ai.client import OllamaClient
from app.ai.contracts import AIProviderError
from app.core.config import Settings


async def warm_model() -> int:
    settings = Settings()
    if settings.ai_provider == "opencode":
        print("API sẽ khởi động OpenCode với Muse Spark Free; không cần nạp Qwen.", flush=True)
        return 0
    print(
        f"Đang nạp nóng {settings.ollama_model}; lần đầu từ HDD có thể mất gần 2 phút...",
        flush=True,
    )
    async with httpx.AsyncClient(
        base_url=settings.ollama_host,
        timeout=settings.ollama_generation_timeout_seconds,
        trust_env=False,
    ) as http:
        provider = OllamaClient(
            http,
            settings.ollama_model,
            health_timeout_seconds=settings.ollama_health_timeout_seconds,
            generation_timeout_seconds=settings.ollama_generation_timeout_seconds,
            context_length=settings.ollama_context_length,
            max_output_tokens=settings.ollama_max_output_tokens,
            keep_alive=settings.ollama_keep_alive,
        )
        today = datetime.now(ZoneInfo(settings.shop_timezone)).date()
        try:
            await provider.classify("Tình hình shop hôm nay", today=today)
        except AIProviderError as error:
            print(f"Không thể nạp model ({error.reason}); API sẽ dùng fallback.", flush=True)
            return 1

    print(f"Model {settings.ollama_model} đã sẵn sàng.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(warm_model()))
