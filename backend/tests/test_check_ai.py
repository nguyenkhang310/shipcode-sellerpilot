from contextlib import asynccontextmanager

import asyncio

from app.ai.contracts import AIProviderError
from app.core.config import Settings
from app.scripts import check_ai


def test_missing_gemini_key_returns_actionable_failure(monkeypatch, capsys):
    settings = Settings(ai_provider='gemini', gemini_api_key='',
                        gemini_api_key_2='', gemini_api_key_3='')
    monkeypatch.setattr(check_ai, 'Settings', lambda: settings)
    assert asyncio.run(check_ai.main()) == 1
    assert 'Chưa có GEMINI_API_KEY' in capsys.readouterr().out


def test_gemini_provider_failure_is_reported_without_traceback(monkeypatch, capsys):
    settings = Settings(ai_provider='gemini', gemini_api_key='synthetic-secret')
    monkeypatch.setattr(check_ai, 'Settings', lambda: settings)

    @asynccontextmanager
    async def rejected_provider(_settings):
        raise AIProviderError('provider_rate_limited', stage='model_gateway')
        yield  # pragma: no cover

    monkeypatch.setattr(check_ai, 'create_provider', rejected_provider)
    assert asyncio.run(check_ai.main()) == 1
    output = capsys.readouterr().out
    assert 'provider_rate_limited' in output
    assert 'synthetic-secret' not in output
