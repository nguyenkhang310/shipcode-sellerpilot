"""Evaluate the live Ollama classifier without executing seller tools."""

import asyncio
import json
from datetime import date
from pathlib import Path

import httpx

from app.ai.client import OllamaClient
from app.ai.contracts import AIProviderError
from app.core.config import Settings
from app.services.chat import enrich_ai_command

EVALUATION_DAY = date(2026, 10, 15)
CASES_PATH = (
    Path(__file__).resolve().parents[3]
    / "sample_data"
    / "quick_demo"
    / "evaluation_cases.json"
)


async def evaluate() -> int:
    settings = Settings()
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    failures = 0

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

        for case in cases:
            try:
                classified = await provider.classify(case["message"], today=EVALUATION_DAY)
                command = enrich_ai_command(
                    classified.command,
                    message=case["message"],
                    today=EVALUATION_DAY,
                )
                actual = command.model_dump(mode="json")
                mismatches = {
                    field: {"expected": expected, "actual": actual.get(field)}
                    for field, expected in case["expected"].items()
                    if actual.get(field) != expected
                }
            except AIProviderError as error:
                mismatches = {"provider": {"expected": "valid", "actual": error.reason}}

            passed = not mismatches
            failures += int(not passed)
            print(f"{'PASS' if passed else 'FAIL'} {case['id']}")
            if mismatches:
                print(json.dumps(mismatches, ensure_ascii=False, indent=2))

    print(f"\n{len(cases) - failures}/{len(cases)} cases passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(evaluate()))
