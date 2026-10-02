"""Model registry.

Importing this module registers every table on ``Base.metadata``, which is what
Alembic autogenerate and ``Base.metadata.create_all`` rely on. Keep it in sync
whenever a new model module is added.
"""

from backend.db.base import Base
from backend.db.models.ai import AIMessage, AIConversation, AuditLog
from backend.db.models.identity import (
    Company,
    Permission,
    Role,
    RolePermission,
    User,
    UserCompanyAccess,
)
from backend.db.models.report import (
    MonthlyReport,
    MonthlyReportAttachment,
    MonthlyReportFinancialReview,
)
from backend.db.models.support import (
    SupportRequest,
    SupportRequestAttachment,
    SupportRequestComment,
)

__all__ = [
    "Base",
    "Role",
    "Permission",
    "RolePermission",
    "User",
    "Company",
    "UserCompanyAccess",
    "MonthlyReport",
    "MonthlyReportFinancialReview",
    "MonthlyReportAttachment",
    "SupportRequest",
    "SupportRequestComment",
    "SupportRequestAttachment",
    "AIConversation",
    "AIMessage",
    "AuditLog",
]
