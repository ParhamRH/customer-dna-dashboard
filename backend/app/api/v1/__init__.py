from fastapi import APIRouter

from app.api.v1 import (
    assets,
    auth,
    brands,
    collections,
    context,
    jobs,
    knowledge,
    organizations,
    projects,
    review,
    search,
    visual_identity,
    workspace,
)

router = APIRouter()
for module in (auth, organizations, workspace, brands, assets, collections, jobs, search, review, knowledge,
               visual_identity, projects, context):
    router.include_router(module.router)
router.include_router(assets.files_router)
