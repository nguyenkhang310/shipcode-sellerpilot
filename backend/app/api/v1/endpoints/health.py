from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.integrations.ute_mall import ShopDatabaseError
from app.schemas.health import HealthData, HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, responses={503: {"model": HealthResponse}})
async def health(request: Request, response: Response, session: Session = Depends(get_session)) -> HealthResponse:
    database = "ok"
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        database = "unavailable"
        response.status_code = 503
    shop_database = "ok"
    try:
        request.app.state.shop_repository.ping()
    except ShopDatabaseError:
        shop_database = "unavailable"
        response.status_code = 503
    provider = await request.app.state.ai_provider.check_health()
    settings = request.app.state.settings
    ready = (
        database == "ok" and shop_database == "ok"
        and provider.availability == "available" and provider.model_available
    )
    return HealthResponse(data=HealthData(
        status="ok" if ready else "degraded",
        database=database,
        shop_database=shop_database,
        provider=settings.ai_provider,
        ai_availability=provider.availability,
        # Legacy field; it must not label OpenCode as an Ollama connection.
        ollama=provider.availability if settings.ai_provider == "ollama" else "unavailable",
        model=(settings.gemini_model if settings.ai_provider == 'gemini' else
               settings.antigravity_model if settings.ai_provider == "antigravity" else
               settings.opencode_model if settings.ai_provider == "opencode" else settings.ollama_model),
        model_available=provider.model_available,
        demo_mode=settings.demo_mode,
        integration_mode="local_store" if shop_database == "ok" else "not_connected",
    ))
