from fastapi import APIRouter

from app.api.v1.endpoints.health import router as health_router
from app.api.v1.endpoints.chat import router as chat_router
from app.api.v1.endpoints.seller_tools import router as seller_tools_router
from app.api.v1.endpoints.management import router as management_router
from app.api.v1.endpoints.product_drafts import router as product_drafts_router

router = APIRouter(prefix="/api/v1")
router.include_router(health_router)
router.include_router(chat_router)
router.include_router(seller_tools_router)
router.include_router(management_router)
router.include_router(product_drafts_router)
