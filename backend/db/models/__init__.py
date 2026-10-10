"""Model registry.

Importing this module registers every table on ``Base.metadata``, which is what
Alembic autogenerate and ``Base.metadata.create_all`` rely on. Keep it in sync
whenever a new model module is added.
"""

from backend.db.base import Base
from backend.db.models.ai import AIMessage, AIConversation, AuditLog
from backend.db.models.documents import Document, DocumentCategory
from backend.db.models.financial import (
    FinancialBankAttachment,
    FinancialItemDefinition,
    FinancialPeriod,
    FinancialReviewAction,
    FinancialSummaryItem,
    FinancialSummaryVersion,
)
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
from backend.db.models.integrations import WebhookDelivery, WebhookEndpoint
from backend.db.models.notifications import Notification
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
from backend.db.models.website import (
    WebsiteLead,
    WebsiteLeadAttachment,
    WebsiteOpportunity,
)
from backend.db.models.website_cms import (
    WebsiteCompany,
    WebsiteContentRevision,
    WebsiteContentSection,
    WebsiteMedia,
    WebsiteMenu,
    WebsitePage,
    WebsiteSeoMeta,
    WebsiteService,
    WebsiteSettings,
    WebsiteSlide,
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
    # Execution 02: subsidiary financial summary workflow
    "FinancialPeriod",
    "FinancialSummaryVersion",
    "FinancialItemDefinition",
    "FinancialSummaryItem",
    "FinancialBankAttachment",
    "FinancialReviewAction",
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
    # Phase 6: notification centre
    "Notification",
    # Phase 9: external integrations
    "WebhookEndpoint",
    "WebhookDelivery",
    # Phase 10: public website leads and opportunities
    "WebsiteLead",
    "WebsiteLeadAttachment",
    "WebsiteOpportunity",
    # Phase 11: website CMS
    "WebsiteSettings",
    "WebsiteSlide",
    "WebsiteMedia",
    "WebsitePage",
    "WebsiteContentSection",
    "WebsiteMenu",
    "WebsiteCompany",
    "WebsiteService",
    "WebsiteSeoMeta",
    "WebsiteContentRevision",
]
