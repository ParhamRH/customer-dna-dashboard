from fastapi import APIRouter

from app.api.v1 import (
    assets,
    auth,
    brands,
    collections,
    context,
    exports,
    integrations,
    jobs,
    knowledge,
    organizations,
    platform_admin,
    projects,
    review,
    search,
    visual_identity,
    workspace,
)

router = APIRouter()
for module in (auth, organizations, platform_admin, workspace, brands, assets, collections, jobs, search, review,
               knowledge, visual_identity, projects, context, exports, integrations):
    router.include_router(module.router)
router.include_router(assets.files_router)
