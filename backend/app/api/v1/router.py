from fastapi import APIRouter, Depends
from app.services.auth import require_seller
from app.api.v1.endpoints.auth import router as auth_router

from app.api.v1.endpoints.health import router as health_router
from app.api.v1.endpoints.chat import router as chat_router
from app.api.v1.endpoints.seller_tools import router as seller_tools_router
from app.api.v1.endpoints.management import router as management_router
from app.api.v1.endpoints.product_drafts import router as product_drafts_router
from app.api.v1.endpoints.product_edits import router as product_edits_router
from app.api.v1.endpoints.browser_connector import router as browser_connector_router

router = APIRouter(prefix="/api/v1")
router.include_router(health_router)
router.include_router(auth_router)
for secured in (chat_router, seller_tools_router, management_router, product_drafts_router, product_edits_router):
    router.include_router(secured, dependencies=[Depends(require_seller)])
router.include_router(browser_connector_router)
