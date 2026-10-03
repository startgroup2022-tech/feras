"""Enumerations shared by models, schemas, RBAC and services.

Values are stored as short lowercase strings so that the schema stays readable
and migrations are trivial to review.
"""

from __future__ import annotations

import enum


class RoleCode(str, enum.Enum):
    """Platform roles.

    The original six V1 roles are extended in Phase 2 with group
    administration and company-governance roles. Roles only ever *group
    permissions*: no endpoint branches on a role name.
    """

    # V1 roles
    HOLDING_OWNER = "holding_owner"
    COMPANY_MANAGER = "company_manager"
    ACCOUNTANT = "accountant"
    BUSINESS_DEVELOPMENT = "business_development"
    MARKETING = "marketing"
    DESIGNER = "designer"

    # Phase 2 group-administration and governance roles
    SUPER_ADMIN = "super_admin"
    HOLDING_FINANCE = "holding_finance"
    COMPANY_OWNER = "company_owner"
    CEO = "ceo"
    FINANCE_MANAGER = "finance_manager"
    HR_MANAGER = "hr_manager"
    DEPARTMENT_MANAGER = "department_manager"
    EMPLOYEE = "employee"


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
    ARCHIVED = "archived"


class CompanyType(str, enum.Enum):
    """Coarse classification of a subsidiary entity."""

    HOLDING = "holding"
    SUBSIDIARY = "subsidiary"
    JOINT_VENTURE = "joint_venture"
    AFFILIATE = "affiliate"


class OwnershipStatus(str, enum.Enum):
    """Lifecycle of an ownership stake.

    Rows are never deleted: a change closes the previous row (``ended``) and a
    new row is opened, so the ownership history is preserved and auditable.
    """

    ACTIVE = "active"
    ENDED = "ended"


class DepartmentStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class HoldingStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class CompanyHealth(str, enum.Enum):
    """Executive health indicator shown on the dashboard overview."""

    STRONG = "strong"
    STABLE = "stable"
    WATCH = "watch"
    ATTENTION = "attention"
