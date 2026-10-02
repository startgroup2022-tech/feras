"""Enumerations shared by models, schemas, RBAC and services.

Values are stored as short lowercase strings so that the schema stays readable
and migrations are trivial to review.
"""

from __future__ import annotations

import enum


class RoleCode(str, enum.Enum):
    """The six V1 roles."""

    HOLDING_OWNER = "holding_owner"
    COMPANY_MANAGER = "company_manager"
    ACCOUNTANT = "accountant"
    BUSINESS_DEVELOPMENT = "business_development"
    MARKETING = "marketing"
    DESIGNER = "designer"


class ReportStatus(str, enum.Enum):
    """Monthly report lifecycle. Deliberately short -- no complex workflow."""

    DRAFT = "draft"
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    REVIEWED = "reviewed"


class FinancialReviewStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    FLAGGED = "flagged"


class SupportCategory(str, enum.Enum):
    ACCOUNTING = "accounting"
    BUSINESS_DEVELOPMENT = "business_development"
    MARKETING = "marketing"
    DESIGN = "design"
    GENERAL = "general"


class SupportStatus(str, enum.Enum):
    NEW = "new"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CLOSED = "closed"


class AIScope(str, enum.Enum):
    """Two AI contexts: Holding-level and per-company."""

    HOLDING = "holding"
    COMPANY = "company"


class AIMessageRole(str, enum.Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class CompanyStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class CompanyHealth(str, enum.Enum):
    """Executive health indicator shown on the dashboard overview."""

    STRONG = "strong"
    STABLE = "stable"
    WATCH = "watch"
    ATTENTION = "attention"
