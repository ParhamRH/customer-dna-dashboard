from fastapi import APIRouter

from app.api.v1 import auth, brands, organizations, workspace

router = APIRouter()
router.include_router(auth.router)
router.include_router(organizations.router)
router.include_router(workspace.router)
router.include_router(brands.router)
