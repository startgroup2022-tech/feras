"""Model registry.

Importing this module registers every table on ``Base.metadata``, which is what
Alembic autogenerate and ``Base.metadata.create_all`` rely on. Keep it in sync
whenever a new model module is added.
"""

from backend.db.base import Base
from backend.db.models.ai import AIMessage, AIConversation, AuditLog
from backend.db.models.documents import Document, DocumentCategory
from backend.db.models.forms import (
    DynamicForm,
    FormCompany,
    FormField,
    FormRequirement,
    FormVersion,
)
from backend.db.models.group import Department, Holding, Ownership
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
from backend.db.models.submissions import FormSubmission, SubmissionRequirement
from backend.db.models.support import (
    SupportRequest,
    SupportRequestAttachment,
    SupportRequestComment,
)
from backend.db.models.workflows import (
    ApprovalEvent,
    ApprovalTask,
    WorkflowDefinition,
    WorkflowInstance,
    WorkflowStep,
    WorkflowVersion,
)

__all__ = [
    "Base",
    "Role",
    "Permission",
    "RolePermission",
    "User",
    "Company",
    "UserCompanyAccess",
    "Holding",
    "Ownership",
    "Department",
    "MonthlyReport",
    "MonthlyReportFinancialReview",
    "MonthlyReportAttachment",
    "SupportRequest",
    "SupportRequestComment",
    "SupportRequestAttachment",
    "AIConversation",
    "AIMessage",
    "AuditLog",
    # Phase 3: dynamic operations platform
    "DynamicForm",
    "FormVersion",
    "FormCompany",
    "FormField",
    "FormRequirement",
    "WorkflowDefinition",
    "WorkflowVersion",
    "WorkflowStep",
    "WorkflowInstance",
    "ApprovalTask",
    "ApprovalEvent",
    "FormSubmission",
    "SubmissionRequirement",
    "Document",
    "DocumentCategory",
]
