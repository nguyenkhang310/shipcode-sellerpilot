import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import sessionmaker

from app.ai.factory import create_provider
from app.api.v1.router import router
from app.core.config import Settings
from app.core.logging import configure_logging
from app.db.session import build_engine
from app.integrations.ute_mall import UTEMallRepository
from app.services.chat_requests import ChatRequestManager

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        configure_logging()
        engine = build_engine(settings.database_url)
        app.state.session_factory = sessionmaker(bind=engine, expire_on_commit=False)
        app.state.shop_repository = UTEMallRepository(
            settings.shop_database_path,
            settings.shop_timezone,
            settings.seller_shop_slug,
        )
        try:
            async with create_provider(settings) as provider:
                app.state.ai_provider = provider
                manager = ChatRequestManager(app.state.session_factory, lambda: app.state.ai_provider, settings)
                app.state.chat_requests = manager
                manager.recover()
                try:
                    yield
                finally:
                    await manager.close()
        finally:
            engine.dispose()

    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type"],
    )
    app.include_router(router)
    # Mobile clients already reach the API on port 8000. Serve the shop's
    # public catalogue media through the same origin so product thumbnails do
    # not depend on the UTE MALL web server also being reachable on port 5011.
    app.mount(
        "/store-static",
        StaticFiles(directory=settings.shop_static_dir, check_dir=False),
        name="store-static",
    )

    @app.exception_handler(Exception)
    async def unexpected_error(_request: Request, error: Exception) -> JSONResponse:
        logger.error("Unhandled API exception: %s", type(error).__name__)
        return JSONResponse(status_code=500, content={
            "detail": "Internal server error", "code": "internal_error",
        })

    return app


app = create_app()
