"""Version 1 API router aggregation."""

from fastapi import APIRouter

from backend.api.v1 import (
    admin,
    ai,
    analytics,
    auth,
    dashboard,
    documents,
    forms,
    integrations,
    notifications,
    reports,
    submissions,
    support,
    users,
    workflows,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(admin.router)
api_router.include_router(users.router)
api_router.include_router(reports.router)
api_router.include_router(support.router)
api_router.include_router(dashboard.router)
api_router.include_router(ai.router)
# Phase 3: dynamic operations platform
api_router.include_router(forms.router)
api_router.include_router(workflows.router)
api_router.include_router(submissions.router)
api_router.include_router(submissions.approvals_router)
api_router.include_router(documents.router)
# Phase 6: notification centre
api_router.include_router(notifications.router)
# Phase 7-8: analytics and executive intelligence
api_router.include_router(analytics.router)
# Phase 9: external integrations
api_router.include_router(integrations.router)

__all__ = ["api_router"]
