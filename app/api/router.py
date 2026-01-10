from fastapi import APIRouter

from app.api.routers.jobs import router as jobs_router
from app.api.routers.meta import router as meta_router
from app.api.routers.summaries import router as summaries_router

router = APIRouter()

router.include_router(meta_router)
router.include_router(jobs_router)
router.include_router(summaries_router)
