"""Version 1 API router aggregation."""

from fastapi import APIRouter

from backend.api.v1 import admin, ai, auth, dashboard, reports, support, users

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(admin.router)
api_router.include_router(users.router)
api_router.include_router(reports.router)
api_router.include_router(support.router)
api_router.include_router(dashboard.router)
api_router.include_router(ai.router)

__all__ = ["api_router"]
